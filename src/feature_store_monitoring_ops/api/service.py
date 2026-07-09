"""Serving utilities for the local FastAPI prediction API."""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    TARGET_COLUMN,
    get_model_input_columns,
)
from feature_store_monitoring_ops.features.online import validate_online_feature_rows
from feature_store_monitoring_ops.paths import (
    DEFAULT_MODEL_MANIFEST_PATH,
    DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_SELECTED_MODEL_PATH,
)
from feature_store_monitoring_ops.storage.config import StorageConfig, build_online_feature_store
from feature_store_monitoring_ops.storage.online import JsonBackedOnlineFeatureStore, OnlineFeatureStore


@dataclass
class ApiMetrics:
    """In-memory metrics for the local API process."""

    request_count: int = 0
    prediction_count: int = 0
    error_count: int = 0
    total_prediction_latency_ms: float = 0.0

    def record_request(self) -> None:
        self.request_count += 1

    def record_error(self) -> None:
        self.error_count += 1

    def record_prediction(self, latency_ms: float) -> None:
        self.prediction_count += 1
        self.total_prediction_latency_ms += latency_ms

    def snapshot(self) -> dict[str, float | int]:
        average_latency = 0.0
        if self.prediction_count:
            average_latency = self.total_prediction_latency_ms / self.prediction_count
        return {
            "request_count": self.request_count,
            "prediction_count": self.prediction_count,
            "error_count": self.error_count,
            "average_prediction_latency_ms": round(average_latency, 6),
        }


@dataclass(frozen=True)
class ServingArtifacts:
    """Artifact paths required by the local prediction API."""

    model_path: Path = DEFAULT_SELECTED_MODEL_PATH
    model_manifest_path: Path = DEFAULT_MODEL_MANIFEST_PATH
    feature_snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH
    feature_manifest_path: Path = DEFAULT_ONLINE_FEATURE_MANIFEST_PATH


@dataclass
class ServingContext:
    """Loaded model, feature store, manifests, and load-time errors."""

    artifacts: ServingArtifacts
    model: Any | None = None
    model_manifest: dict[str, Any] = field(default_factory=dict)
    feature_manifest: dict[str, Any] = field(default_factory=dict)
    feature_store: OnlineFeatureStore | None = None
    load_errors: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return (
            self.model is not None
            and self.feature_store is not None
            and not self.load_errors
            and bool(self.feature_store.all_rows())
        )

    @property
    def selected_model(self) -> str | None:
        selected = self.model_manifest.get("selected_model")
        if selected is None:
            return None
        return str(selected)

    @property
    def model_version(self) -> str:
        return str(self.model_manifest.get("model_version", __version__))


def load_serving_context(
    artifacts: ServingArtifacts | None = None,
    *,
    feature_store: OnlineFeatureStore | None = None,
    storage_config: StorageConfig | None = None,
) -> ServingContext:
    """Load model and online feature artifacts without crashing on missing files."""

    active_artifacts = artifacts or ServingArtifacts()
    context = ServingContext(artifacts=active_artifacts)
    _load_model(context)
    _load_model_manifest(context)
    _load_feature_manifest(context)
    _load_feature_store(context, feature_store=feature_store, storage_config=storage_config)
    _validate_manifest_contract(context)
    return context


def get_feature_row(context: ServingContext, zone_id: str) -> dict[str, object]:
    """Return the latest feature row for a zone from the loaded online snapshot."""

    _require_feature_store(context)
    assert context.feature_store is not None
    row = context.feature_store.get({"zone_id": zone_id})
    if row is None:
        raise KeyError(f"unknown zone_id: {zone_id}")
    _validate_required_input_columns(row)
    return row


def predict_for_zone(context: ServingContext, zone_id: str) -> tuple[float, dict[str, object], float]:
    """Run the selected model for a zone and return prediction plus feature row and latency."""

    _require_model(context)
    row = get_feature_row(context, zone_id)
    prediction, latency_ms = predict_from_feature_row(context, row)
    return prediction, row, latency_ms


def predict_from_feature_row(context: ServingContext, row: dict[str, object]) -> tuple[float, float]:
    """Run the selected model for an already validated feature row."""

    _require_model(context)
    _validate_required_input_columns(row)
    input_columns = get_model_input_columns()
    features = pd.DataFrame([{column: row[column] for column in input_columns}])
    start = time.perf_counter()
    prediction_values = context.model.predict(features)
    latency_ms = (time.perf_counter() - start) * 1000
    prediction = _first_prediction_value(prediction_values)
    return prediction, latency_ms


def extract_model_features(row: dict[str, object]) -> dict[str, object]:
    """Extract exactly the model input feature columns from a feature row."""

    _validate_required_input_columns(row)
    return {column: row[column] for column in get_model_input_columns()}


def build_feature_freshness(
    context: ServingContext,
    row: dict[str, object],
    *,
    feature_freshness_seconds: float | None = None,
) -> dict[str, object]:
    """Build deterministic feature freshness metadata for prediction responses."""

    return {
        "as_of_timestamp": row[AS_OF_TIMESTAMP_COLUMN],
        "feature_freshness_seconds": feature_freshness_seconds,
        "online_snapshot_row_count": context.feature_manifest.get("row_count"),
        "source_artifact_path": context.feature_manifest.get("source_artifact_path"),
    }


def build_api_serving_summary(
    *,
    artifacts: ServingArtifacts,
    smoke_test_passed: bool | None,
    selected_model: str | None,
    metrics: dict[str, float | int],
) -> str:
    """Build a tracked Markdown report for the local API serving layer."""

    smoke_status = "not run"
    if smoke_test_passed is True:
        smoke_status = "passed"
    elif smoke_test_passed is False:
        smoke_status = "failed"
    endpoint_lines = "\n".join(
        [
            "- `GET /health`",
            "- `GET /model`",
            "- `GET /features/{zone_id}`",
            "- `POST /predict`",
            "- `GET /metrics`",
        ],
    )
    feature_lines = "\n".join(f"- `{column}`" for column in get_model_input_columns())
    return "\n".join(
        [
            "# API Serving Summary",
            "",
            "Added a local FastAPI prediction service for Milestone 5.",
            "",
            "## Artifacts",
            "",
            f"- Model: `{artifacts.model_path}`",
            f"- Model manifest: `{artifacts.model_manifest_path}`",
            f"- Online features: `{artifacts.feature_snapshot_path}`",
            f"- Online feature manifest: `{artifacts.feature_manifest_path}`",
            "",
            "## Endpoints",
            "",
            endpoint_lines,
            "",
            "## Model",
            "",
            f"- Selected model: `{selected_model}`",
            "",
            "## Model Input Features",
            "",
            feature_lines,
            "",
            "## Smoke Test",
            "",
            f"- Status: {smoke_status}",
            "",
            "## Local Metrics",
            "",
            f"- Request count: {metrics['request_count']}",
            f"- Prediction count: {metrics['prediction_count']}",
            f"- Error count: {metrics['error_count']}",
            f"- Average prediction latency ms: {metrics['average_prediction_latency_ms']}",
            "",
            "## Notes",
            "",
            "- Serving is local and uses JSON-backed online features.",
            "- Predictions use exactly the shared model input feature columns.",
            "- Metrics are in-memory only for this milestone.",
            "- Redis, Postgres, Docker, and external serving infrastructure are not required yet.",
            "",
        ],
    )


def _load_model(context: ServingContext) -> None:
    if not context.artifacts.model_path.exists():
        context.load_errors.append(f"missing model artifact: {context.artifacts.model_path}")
        return
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Setting the shape on a NumPy array has been deprecated in NumPy 2\.5\.",
                category=DeprecationWarning,
                module=r"joblib\.numpy_pickle",
            )
            context.model = joblib.load(context.artifacts.model_path)
    except Exception as exc:  # pragma: no cover - defensive artifact error path
        context.load_errors.append(f"failed to load model artifact: {exc}")


def _load_model_manifest(context: ServingContext) -> None:
    context.model_manifest = _read_json_artifact(
        path=context.artifacts.model_manifest_path,
        label="model manifest",
        errors=context.load_errors,
    )


def _load_feature_manifest(context: ServingContext) -> None:
    context.feature_manifest = _read_json_artifact(
        path=context.artifacts.feature_manifest_path,
        label="online feature manifest",
        errors=context.load_errors,
    )


def _load_feature_store(
    context: ServingContext,
    *,
    feature_store: OnlineFeatureStore | None = None,
    storage_config: StorageConfig | None = None,
) -> None:
    if feature_store is not None:
        try:
            rows = feature_store.all_rows()
            validate_online_feature_rows(rows)
        except ValueError as exc:
            context.load_errors.append(f"invalid online feature store: {exc}")
            return
        context.feature_store = feature_store
        return

    active_config = storage_config or StorageConfig.from_env()
    if active_config.online_backend == "json" and not context.artifacts.feature_snapshot_path.exists():
        context.load_errors.append(
            f"missing online feature snapshot: {context.artifacts.feature_snapshot_path}",
        )
        return
    store = _build_serving_feature_store(
        config=active_config,
        snapshot_path=context.artifacts.feature_snapshot_path,
    )
    try:
        rows = store.all_rows()
        validate_online_feature_rows(rows)
    except ValueError as exc:
        context.load_errors.append(f"invalid online feature snapshot: {exc}")
        return
    except Exception as exc:  # pragma: no cover - defensive adapter/runtime error path
        context.load_errors.append(f"failed to load online feature store: {exc}")
        return
    context.feature_store = store


def _validate_manifest_contract(context: ServingContext) -> None:
    input_features = context.model_manifest.get("input_features")
    if input_features is not None and list(get_model_input_columns()) != list(input_features):
        context.load_errors.append("model manifest input features do not match shared contract")

    feature_columns = context.feature_manifest.get("feature_columns")
    if feature_columns is not None and list(get_model_input_columns()) != list(feature_columns):
        context.load_errors.append("online feature manifest columns do not match shared contract")


def _read_json_artifact(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        errors.append(f"missing {label}: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"invalid {label}: expected object")
        return {}
    return payload


def _require_model(context: ServingContext) -> None:
    if context.model is None:
        raise RuntimeError("model artifact is not loaded")


def _require_feature_store(context: ServingContext) -> None:
    if context.feature_store is None:
        raise RuntimeError("online feature snapshot is not loaded")


def _validate_required_input_columns(row: dict[str, object]) -> None:
    missing = sorted(set(get_model_input_columns()).difference(row))
    if missing:
        raise ValueError(f"feature row missing required columns: {', '.join(missing)}")
    if TARGET_COLUMN in row:
        raise ValueError("feature row unexpectedly contains target column")


def _first_prediction_value(predictions: object) -> float:
    if hasattr(predictions, "iloc"):
        return round(float(predictions.iloc[0]), 6)
    if hasattr(predictions, "__getitem__"):
        return round(float(predictions[0]), 6)  # type: ignore[index]
    return round(float(predictions), 6)


def _build_serving_feature_store(
    *,
    config: StorageConfig,
    snapshot_path: Path,
) -> OnlineFeatureStore:
    if config.online_backend == "json":
        return JsonBackedOnlineFeatureStore(snapshot_path=snapshot_path)
    return build_online_feature_store(config, snapshot_path=snapshot_path)


__all__ = [
    "ApiMetrics",
    "ServingArtifacts",
    "ServingContext",
    "build_api_serving_summary",
    "build_feature_freshness",
    "extract_model_features",
    "get_feature_row",
    "load_serving_context",
    "predict_from_feature_row",
    "predict_for_zone",
]

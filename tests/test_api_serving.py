from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx
import joblib
import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.api.app import create_app
from feature_store_monitoring_ops.api.service import ServingArtifacts
from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.features.contract import (
    TARGET_COLUMN,
    get_model_input_columns,
    get_online_feature_columns,
)
from feature_store_monitoring_ops.features.online import build_online_feature_manifest
from feature_store_monitoring_ops.models.training import ColumnBaselineRegressor


def test_health_endpoint(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["status"] == "ok"


def test_model_endpoint(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.get("/model")

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_model"] == "naive_lag_1"
    assert payload["input_features"] == list(get_model_input_columns())
    assert payload["target_column"] == TARGET_COLUMN


def test_feature_lookup_endpoint(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.get("/features/zone_01")

    assert response.status_code == 200
    payload = response.json()
    assert payload["zone_id"] == "zone_01"
    assert payload["as_of_timestamp"] == "2026-01-30T12:00:00+00:00"
    assert TARGET_COLUMN not in payload["features"]
    assert payload["feature_columns"] == list(get_model_input_columns())


def test_successful_prediction(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.post("/predict", json={"zone_id": "zone_01"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["zone_id"] == "zone_01"
    assert payload["prediction"] == 17.5
    assert payload["model_name"] == "naive_lag_1"
    assert payload["as_of_timestamp"] == "2026-01-30T12:00:00+00:00"
    assert payload["feature_columns"] == list(get_model_input_columns())


def test_unknown_zone_id_returns_clean_error(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.post("/predict", json={"zone_id": "missing_zone"})

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown zone_id: missing_zone"


def test_metrics_update_after_prediction(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)
    before = client.get("/metrics").json()

    prediction_response = client.post("/predict", json={"zone_id": "zone_02"})
    after = client.get("/metrics").json()

    assert prediction_response.status_code == 200
    assert after["prediction_count"] == before["prediction_count"] + 1
    assert after["request_count"] > before["request_count"]
    assert after["average_prediction_latency_ms"] >= 0


def test_serve_api_cli_smoke_behavior(tmp_path) -> None:
    artifacts = _write_serving_artifacts(tmp_path)
    report_path = tmp_path / "api_serving_summary.md"
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "serve-api",
            "--smoke-test",
            "--model-path",
            str(artifacts.model_path),
            "--model-manifest-path",
            str(artifacts.model_manifest_path),
            "--feature-snapshot-path",
            str(artifacts.feature_snapshot_path),
            "--feature-manifest-path",
            str(artifacts.feature_manifest_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "api smoke test passed" in result.output
    assert report_path.exists()
    assert "Status: passed" in report_path.read_text(encoding="utf-8")


class InProcessTestClient:
    def __init__(self, app) -> None:
        self.app = app

    def get(self, path: str) -> httpx.Response:
        return asyncio.run(self._request("GET", path))

    def post(self, path: str, *, json: dict[str, object]) -> httpx.Response:
        return asyncio.run(self._request("POST", path, json=json))

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


def _client_with_artifacts(tmp_path: Path) -> InProcessTestClient:
    artifacts = _write_serving_artifacts(tmp_path)
    return InProcessTestClient(create_app(artifacts=artifacts))


def _write_serving_artifacts(tmp_path: Path) -> ServingArtifacts:
    model_path = tmp_path / "selected_model.joblib"
    model_manifest_path = tmp_path / "model_manifest.json"
    feature_snapshot_path = tmp_path / "latest_features.json"
    feature_manifest_path = tmp_path / "manifest.json"
    rows = _online_feature_rows()

    model = ColumnBaselineRegressor("lag_1_observed_demand").fit(pd.DataFrame(rows))
    joblib.dump(model, model_path)
    model_manifest_path.write_text(
        json.dumps(
            {
                "selected_model": "naive_lag_1",
                "model_version": "test",
                "input_features": list(get_model_input_columns()),
                "target_column": TARGET_COLUMN,
                "row_counts": {"train": 2, "validation": 1, "test": 1},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    feature_snapshot_path.write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    feature_manifest_path.write_text(
        json.dumps(
            build_online_feature_manifest(
                row_count=len(rows),
                source_path=tmp_path / "offline_features.parquet",
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ServingArtifacts(
        model_path=model_path,
        model_manifest_path=model_manifest_path,
        feature_snapshot_path=feature_snapshot_path,
        feature_manifest_path=feature_manifest_path,
    )


def _online_feature_rows() -> list[dict[str, object]]:
    base_rows = [
        ("zone_01", "2026-01-30T12:00:00+00:00", 12, 17.5),
        ("zone_02", "2026-01-30T13:00:00+00:00", 13, 23.25),
    ]
    rows: list[dict[str, object]] = []
    for zone_id, timestamp, hour, lag_1 in base_rows:
        row = {
            "zone_id": zone_id,
            "timestamp": timestamp,
            "hour": hour,
            "day_of_week": 4,
            "is_weekend": False,
            "lag_1_observed_demand": lag_1,
            "lag_3_observed_demand": lag_1 - 2.0,
            "rolling_mean_3": lag_1 - 1.0,
            "rolling_mean_6": lag_1 - 1.5,
            "rolling_std_6": 1.25,
            "zone_hour_mean_demand": lag_1 + 0.5,
        }
        assert set(row) == set(get_online_feature_columns())
        rows.append(row)
    return rows

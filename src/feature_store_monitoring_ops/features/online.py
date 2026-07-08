"""Online feature materialization and offline/online parity checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    ENTITY_KEY_COLUMNS,
    ONLINE_FEATURE_COLUMNS,
    TARGET_COLUMN,
    get_model_input_columns,
    get_online_feature_columns,
)
from feature_store_monitoring_ops.paths import (
    DEFAULT_OFFLINE_FEATURES_PATH,
    DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    DEFAULT_ONLINE_FEATURE_REPORT_PATH,
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
)
from feature_store_monitoring_ops.storage.online import JsonBackedOnlineFeatureStore, OnlineFeatureStore


@dataclass(frozen=True)
class OnlineFeatureMaterializationResult:
    """Paths and row count from online feature materialization."""

    snapshot_path: Path
    manifest_path: Path
    report_path: Path
    row_count: int


def read_offline_features(path: Path = DEFAULT_OFFLINE_FEATURES_PATH) -> pd.DataFrame:
    """Read offline features from parquet."""

    if not path.exists():
        raise FileNotFoundError(f"offline features file not found: {path}")
    return pd.read_parquet(path)


def select_latest_online_features(offline_features: pd.DataFrame) -> pd.DataFrame:
    """Select the latest valid online feature row per entity from offline features."""

    missing = sorted(set(ONLINE_FEATURE_COLUMNS).difference(offline_features.columns))
    if missing:
        raise ValueError(f"offline features missing online columns: {', '.join(missing)}")
    if TARGET_COLUMN not in offline_features.columns:
        raise ValueError(f"offline features missing target column: {TARGET_COLUMN}")

    frame = offline_features.copy()
    frame[AS_OF_TIMESTAMP_COLUMN] = pd.to_datetime(
        frame[AS_OF_TIMESTAMP_COLUMN],
        utc=True,
        errors="raise",
    )
    sort_columns = [*ENTITY_KEY_COLUMNS, AS_OF_TIMESTAMP_COLUMN]
    if "event_id" in frame.columns:
        sort_columns.append("event_id")

    latest = (
        frame.dropna(subset=list(ONLINE_FEATURE_COLUMNS))
        .sort_values(sort_columns, kind="mergesort")
        .groupby(list(ENTITY_KEY_COLUMNS), sort=False)
        .tail(1)
        .sort_values(list(ENTITY_KEY_COLUMNS), kind="mergesort")
        .reset_index(drop=True)
    )
    online_features = latest.loc[:, get_online_feature_columns()]
    if TARGET_COLUMN in online_features.columns:
        raise ValueError("target column leaked into online feature snapshot")
    if online_features.empty:
        raise ValueError("online feature materialization produced no rows")
    return online_features


def online_features_to_records(online_features: pd.DataFrame) -> list[dict[str, object]]:
    """Convert online feature rows to deterministic JSON-safe records."""

    columns = get_online_feature_columns()
    missing = sorted(set(columns).difference(online_features.columns))
    if missing:
        raise ValueError(f"online features missing required columns: {', '.join(missing)}")

    records: list[dict[str, object]] = []
    for row in online_features.loc[:, columns].to_dict(orient="records"):
        record = {column: _to_jsonable(row[column]) for column in columns}
        records.append(record)
    return records


def validate_online_feature_rows(rows: list[dict[str, object]]) -> None:
    """Validate online snapshot row shape against the shared feature contract."""

    expected_columns = set(get_online_feature_columns())
    for index, row in enumerate(rows, start=1):
        actual_columns = set(row)
        if actual_columns != expected_columns:
            missing = sorted(expected_columns.difference(actual_columns))
            unexpected = sorted(actual_columns.difference(expected_columns))
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ValueError(f"online row {index} does not match feature contract ({'; '.join(details)})")
        if TARGET_COLUMN in row:
            raise ValueError(f"online row {index} contains target column")


def validate_online_offline_parity(
    online_rows: list[dict[str, object]],
    offline_features: pd.DataFrame,
) -> None:
    """Validate online rows match latest corresponding offline feature rows."""

    validate_online_feature_rows(online_rows)
    expected_rows = online_features_to_records(select_latest_online_features(offline_features))
    if _sort_records(online_rows) != _sort_records(expected_rows):
        raise ValueError("online feature snapshot does not match latest offline feature rows")


def materialize_online_features(
    *,
    source_path: Path = DEFAULT_OFFLINE_FEATURES_PATH,
    snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    manifest_path: Path = DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    report_path: Path = DEFAULT_ONLINE_FEATURE_REPORT_PATH,
    store: OnlineFeatureStore | None = None,
) -> OnlineFeatureMaterializationResult:
    """Materialize latest offline feature rows into a local online feature snapshot."""

    offline_features = read_offline_features(source_path)
    latest_features = select_latest_online_features(offline_features)
    rows = online_features_to_records(latest_features)
    active_store = store or JsonBackedOnlineFeatureStore(snapshot_path=snapshot_path)
    active_store.put_many(rows)
    stored_rows = active_store.all_rows()
    validate_online_offline_parity(stored_rows, offline_features)

    manifest = build_online_feature_manifest(
        row_count=len(stored_rows),
        source_path=source_path,
    )
    _write_json(manifest, manifest_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_online_feature_summary(
            row_count=len(stored_rows),
            source_path=source_path,
            snapshot_path=snapshot_path,
            manifest_path=manifest_path,
        ),
        encoding="utf-8",
    )
    return OnlineFeatureMaterializationResult(
        snapshot_path=snapshot_path,
        manifest_path=manifest_path,
        report_path=report_path,
        row_count=len(stored_rows),
    )


def build_online_feature_manifest(*, row_count: int, source_path: Path) -> dict[str, Any]:
    """Build manifest metadata for the online feature snapshot."""

    return {
        "row_count": row_count,
        "feature_columns": list(get_model_input_columns()),
        "online_columns": list(get_online_feature_columns()),
        "entity_keys": list(ENTITY_KEY_COLUMNS),
        "as_of_column": AS_OF_TIMESTAMP_COLUMN,
        "target_column": TARGET_COLUMN,
        "target_excluded": True,
        "source_artifact_path": str(source_path),
    }


def build_online_feature_summary(
    *,
    row_count: int,
    source_path: Path,
    snapshot_path: Path,
    manifest_path: Path,
) -> str:
    """Build a tracked Markdown summary for online feature materialization."""

    feature_lines = "\n".join(f"- `{column}`" for column in get_model_input_columns())
    entity_lines = "\n".join(f"- `{column}`" for column in ENTITY_KEY_COLUMNS)
    return "\n".join(
        [
            "# Online Feature Materialization Summary",
            "",
            "Materialized the latest offline feature row per entity for Milestone 4.",
            "",
            "## Artifacts",
            "",
            f"- Source offline features: `{source_path}`",
            f"- Online snapshot: `{snapshot_path}`",
            f"- Manifest: `{manifest_path}`",
            "",
            "## Snapshot",
            "",
            f"- Row count: {row_count}",
            f"- As-of column: `{AS_OF_TIMESTAMP_COLUMN}`",
            "",
            "## Entity Keys",
            "",
            entity_lines,
            "",
            "## Model Input Feature Columns",
            "",
            feature_lines,
            "",
            "## Parity Notes",
            "",
            "- Snapshot rows contain model input features plus entity/as-of metadata only.",
            "- The latest valid offline feature row is selected per `zone_id`.",
            "- Online values are validated against the corresponding latest offline rows.",
            f"- `{TARGET_COLUMN}` is excluded from online features.",
            "",
        ],
    )


def _sort_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: tuple(row[column] for column in ENTITY_KEY_COLUMNS))


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _to_jsonable(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


__all__ = [
    "OnlineFeatureMaterializationResult",
    "build_online_feature_manifest",
    "build_online_feature_summary",
    "materialize_online_features",
    "online_features_to_records",
    "read_offline_features",
    "select_latest_online_features",
    "validate_online_feature_rows",
    "validate_online_offline_parity",
]

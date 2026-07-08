from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app
from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    ENTITY_KEY_COLUMNS,
    MODEL_INPUT_FEATURE_COLUMNS,
    ONLINE_FEATURE_COLUMNS,
    TARGET_COLUMN,
    get_model_input_columns,
    get_online_feature_columns,
)
from feature_store_monitoring_ops.features.online import (
    materialize_online_features,
    online_features_to_records,
    select_latest_online_features,
    validate_online_offline_parity,
)
from feature_store_monitoring_ops.storage.online import InMemoryOnlineFeatureStore


def test_shared_feature_contract_excludes_target_from_inputs() -> None:
    assert TARGET_COLUMN not in get_model_input_columns()
    assert TARGET_COLUMN not in get_online_feature_columns()
    assert ENTITY_KEY_COLUMNS == ("zone_id",)
    assert AS_OF_TIMESTAMP_COLUMN == "timestamp"


def test_latest_row_per_zone_is_selected_correctly() -> None:
    latest = select_latest_online_features(_offline_features_frame())

    assert list(latest["zone_id"]) == ["zone_01", "zone_02"]
    assert list(latest["hour"]) == [2, 4]
    assert list(latest["lag_1_observed_demand"]) == [12.0, 22.0]


def test_online_snapshot_excludes_target() -> None:
    latest = select_latest_online_features(_offline_features_frame())
    rows = online_features_to_records(latest)

    assert rows
    assert TARGET_COLUMN not in rows[0]
    assert set(rows[0]) == set(ONLINE_FEATURE_COLUMNS)


def test_online_offline_parity_for_deterministic_dataframe() -> None:
    offline_features = _offline_features_frame()
    latest = select_latest_online_features(offline_features)
    rows = online_features_to_records(latest)
    store = InMemoryOnlineFeatureStore()

    store.put_many(rows)

    validate_online_offline_parity(store.all_rows(), offline_features)
    assert store.get({"zone_id": "zone_01"}) == rows[0]


def test_materialize_online_features_cli_smoke(tmp_path) -> None:
    runner = CliRunner()
    source_path = tmp_path / "offline_features.parquet"
    snapshot_path = tmp_path / "latest_features.json"
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "online_feature_materialization_summary.md"
    _offline_features_frame().to_parquet(source_path, index=False)

    result = runner.invoke(
        app,
        [
            "materialize-online-features",
            "--source-path",
            str(source_path),
            "--snapshot-path",
            str(snapshot_path),
            "--manifest-path",
            str(manifest_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert snapshot_path.exists()
    assert manifest_path.exists()
    assert report_path.exists()

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(snapshot) == 2
    assert TARGET_COLUMN not in snapshot[0]
    assert manifest["row_count"] == 2
    assert manifest["feature_columns"] == list(MODEL_INPUT_FEATURE_COLUMNS)
    assert manifest["entity_keys"] == list(ENTITY_KEY_COLUMNS)
    assert manifest["source_artifact_path"] == str(source_path)
    assert "Row count: 2" in report_path.read_text(encoding="utf-8")


def test_materialize_online_features_with_in_memory_store(tmp_path) -> None:
    source_path = tmp_path / "offline_features.parquet"
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "online_feature_materialization_summary.md"
    store = InMemoryOnlineFeatureStore()
    _offline_features_frame().to_parquet(source_path, index=False)

    result = materialize_online_features(
        source_path=source_path,
        snapshot_path=tmp_path / "unused_latest_features.json",
        manifest_path=manifest_path,
        report_path=report_path,
        store=store,
    )

    assert result.row_count == 2
    assert len(store.all_rows()) == 2
    assert not (tmp_path / "unused_latest_features.json").exists()


def _offline_features_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    values = [
        ("evt_000001", "2026-01-01T00:00:00+00:00", "zone_01", 0, 0, False, 10.0, 8.0),
        ("evt_000002", "2026-01-01T02:00:00+00:00", "zone_01", 2, 0, False, 12.0, 14.0),
        ("evt_000003", "2026-01-01T01:00:00+00:00", "zone_02", 1, 0, False, 20.0, 18.0),
        ("evt_000004", "2026-01-01T04:00:00+00:00", "zone_02", 4, 0, False, 22.0, 24.0),
    ]
    for event_id, timestamp, zone_id, hour, day_of_week, is_weekend, lag_1, target in values:
        rows.append(
            {
                "event_id": event_id,
                "timestamp": timestamp,
                "zone_id": zone_id,
                "hour": hour,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "lag_1_observed_demand": lag_1,
                "lag_3_observed_demand": lag_1 - 2.0,
                "rolling_mean_3": lag_1 - 1.0,
                "rolling_mean_6": lag_1 - 1.5,
                "rolling_std_6": 1.25,
                "zone_hour_mean_demand": lag_1 + 0.5,
                "target_next_observed_demand": target,
            },
        )
    return pd.DataFrame(rows)

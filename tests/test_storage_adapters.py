from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.features.contract import get_online_feature_columns
from feature_store_monitoring_ops.storage.config import StorageConfig
from feature_store_monitoring_ops.storage.online import (
    InMemoryOnlineFeatureStore,
    JsonBackedOnlineFeatureStore,
    RedisOnlineFeatureStore,
)
from feature_store_monitoring_ops.storage.sync import inspect_storage, sync_storage
from feature_store_monitoring_ops.storage.telemetry import (
    JsonlPredictionTelemetryStore,
    SQLitePredictionTelemetryStore,
)


def test_sqlite_telemetry_insert_read_count(tmp_path) -> None:
    store = SQLitePredictionTelemetryStore(db_path=tmp_path / "telemetry.db")

    store.append(_telemetry_row(request_id="req_000001", zone_id="zone_01", prediction=12.0))
    store.append(_telemetry_row(request_id="req_000002", zone_id="zone_02", prediction=None, status="error"))

    rows = store.all_rows()
    assert store.count() == 2
    assert rows[0]["request_id"] == "req_000001"
    assert rows[1]["status"] == "error"
    assert store.timestamp_bounds() == (
        "2026-02-01T00:00:00+00:00",
        "2026-02-01T00:00:00+00:00",
    )


def test_jsonl_to_sqlite_sync(tmp_path) -> None:
    snapshot_path = tmp_path / "latest_features.json"
    telemetry_log_path = tmp_path / "predictions.jsonl"
    sqlite_path = tmp_path / "telemetry.db"
    _write_online_snapshot(snapshot_path)
    jsonl_store = JsonlPredictionTelemetryStore(log_path=telemetry_log_path)
    jsonl_store.append(_telemetry_row(request_id="req_000001", zone_id="zone_01", prediction=12.0))
    jsonl_store.append(_telemetry_row(request_id="req_000002", zone_id="zone_02", prediction=14.0))

    result = sync_storage(
        config=StorageConfig(sqlite_path=sqlite_path),
        feature_snapshot_path=snapshot_path,
        telemetry_log_path=telemetry_log_path,
        report_path=tmp_path / "storage_sync_summary.md",
    )

    sqlite_store = SQLitePredictionTelemetryStore(db_path=sqlite_path)
    assert result.telemetry_source_row_count == 2
    assert result.telemetry_store_row_count == 2
    assert sqlite_store.count() == 2


def test_redis_adapter_behavior_with_fake_client() -> None:
    fake_client = FakeRedis()
    store = RedisOnlineFeatureStore(redis_url="redis://fake", client=fake_client)
    rows = _online_rows()

    store.put_many(rows)

    assert store.zone_ids() == ["zone_01", "zone_02"]
    assert store.get({"zone_id": "zone_01"}) == rows[0]
    assert store.all_rows() == rows


def test_online_feature_store_interface_consistency(tmp_path) -> None:
    rows = _online_rows()
    stores = [
        InMemoryOnlineFeatureStore(),
        JsonBackedOnlineFeatureStore(snapshot_path=tmp_path / "latest_features.json"),
        RedisOnlineFeatureStore(redis_url="redis://fake", client=FakeRedis()),
    ]

    for store in stores:
        store.put_many(rows)
        assert store.zone_ids() == ["zone_01", "zone_02"]
        assert store.get({"zone_id": "zone_02"}) == rows[1]
        assert store.all_rows() == rows


def test_sync_storage_cli_smoke_behavior(tmp_path) -> None:
    snapshot_path = tmp_path / "latest_features.json"
    telemetry_log_path = tmp_path / "predictions.jsonl"
    report_path = tmp_path / "storage_sync_summary.md"
    sqlite_path = tmp_path / "telemetry.db"
    _write_online_snapshot(snapshot_path)
    JsonlPredictionTelemetryStore(log_path=telemetry_log_path).append_many(
        [
            _telemetry_row(request_id="req_000001", zone_id="zone_01", prediction=12.0),
            _telemetry_row(request_id="req_000002", zone_id="zone_02", prediction=14.0),
        ],
    )
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "sync-storage",
            "--feature-snapshot-path",
            str(snapshot_path),
            "--telemetry-log-path",
            str(telemetry_log_path),
            "--report-path",
            str(report_path),
            "--sqlite-path",
            str(sqlite_path),
        ],
    )

    assert result.exit_code == 0
    assert "synced online feature rows: 2" in result.output
    assert "synced telemetry rows: 2" in result.output
    assert report_path.exists()
    assert SQLitePredictionTelemetryStore(db_path=sqlite_path).count() == 2


def test_inspect_storage_cli_smoke_behavior(tmp_path) -> None:
    snapshot_path = tmp_path / "latest_features.json"
    telemetry_log_path = tmp_path / "predictions.jsonl"
    sqlite_path = tmp_path / "telemetry.db"
    report_path = tmp_path / "storage_inspection_summary.md"
    _write_online_snapshot(snapshot_path)
    sync_storage(
        config=StorageConfig(sqlite_path=sqlite_path),
        feature_snapshot_path=snapshot_path,
        telemetry_log_path=telemetry_log_path,
        report_path=tmp_path / "storage_sync_summary.md",
    )
    SQLitePredictionTelemetryStore(db_path=sqlite_path).append_many(
        [
            _telemetry_row(request_id="req_000001", zone_id="zone_01", prediction=12.0),
            _telemetry_row(request_id="req_000002", zone_id="zone_02", prediction=14.0),
        ],
    )
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "inspect-storage",
            "--feature-snapshot-path",
            str(snapshot_path),
            "--telemetry-log-path",
            str(telemetry_log_path),
            "--report-path",
            str(report_path),
            "--sqlite-path",
            str(sqlite_path),
        ],
    )

    assert result.exit_code == 0
    assert "online feature row count: 2" in result.output
    assert "telemetry row count: 2" in result.output
    assert "zone_01, zone_02" in result.output
    assert report_path.exists()


def test_inspect_storage_function_payload(tmp_path) -> None:
    snapshot_path = tmp_path / "latest_features.json"
    sqlite_path = tmp_path / "telemetry.db"
    _write_online_snapshot(snapshot_path)
    SQLitePredictionTelemetryStore(db_path=sqlite_path).append(
        _telemetry_row(request_id="req_000001", zone_id="zone_01", prediction=12.0),
    )

    result = inspect_storage(
        config=StorageConfig(sqlite_path=sqlite_path),
        feature_snapshot_path=snapshot_path,
        telemetry_log_path=tmp_path / "predictions.jsonl",
        report_path=tmp_path / "storage_inspection_summary.md",
    )

    assert result.online_feature_row_count == 2
    assert result.telemetry_row_count == 1
    assert result.min_telemetry_timestamp == "2026-02-01T00:00:00+00:00"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value)

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.sets.pop(key, None)


def _write_online_snapshot(path) -> None:
    path.write_text(json.dumps(_online_rows(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _online_rows() -> list[dict[str, object]]:
    rows = [
        {
            "zone_id": "zone_01",
            "timestamp": "2026-01-30T12:00:00+00:00",
            "hour": 12,
            "day_of_week": 4,
            "is_weekend": False,
            "lag_1_observed_demand": 12.0,
            "lag_3_observed_demand": 10.0,
            "rolling_mean_3": 11.0,
            "rolling_mean_6": 10.5,
            "rolling_std_6": 1.25,
            "zone_hour_mean_demand": 12.5,
        },
        {
            "zone_id": "zone_02",
            "timestamp": "2026-01-30T13:00:00+00:00",
            "hour": 13,
            "day_of_week": 4,
            "is_weekend": False,
            "lag_1_observed_demand": 14.0,
            "lag_3_observed_demand": 12.0,
            "rolling_mean_3": 13.0,
            "rolling_mean_6": 12.5,
            "rolling_std_6": 1.5,
            "zone_hour_mean_demand": 14.5,
        },
    ]
    for row in rows:
        assert set(row) == set(get_online_feature_columns())
    return rows


def _telemetry_row(
    *,
    request_id: str,
    zone_id: str,
    prediction: float | None,
    status: str = "success",
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "timestamp": "2026-02-01T00:00:00+00:00",
        "zone_id": zone_id,
        "as_of_timestamp": "2026-01-30T00:00:00+00:00" if status == "success" else None,
        "prediction": prediction,
        "model_name": "test_model",
        "model_version": "test",
        "feature_freshness_seconds": 172800.0 if status == "success" else None,
        "latency_ms": 5.0,
        "status": status,
        "error_type": None if status == "success" else "unknown_zone",
    }

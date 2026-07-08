from __future__ import annotations

from datetime import UTC, datetime

from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.monitoring.serving import (
    REQUIRED_SERVING_MONITORING_METRIC_KEYS,
    ServingMonitoringThresholds,
    build_serving_monitoring_warnings,
    compute_serving_monitoring_metrics,
    monitor_prediction_logs,
)
from feature_store_monitoring_ops.monitoring.telemetry import (
    IncrementingClock,
    PredictionTelemetryLogger,
    read_prediction_logs,
)
from tests.test_api_serving import _client_with_artifacts, _write_serving_artifacts


def test_telemetry_log_writing(tmp_path) -> None:
    log_path = tmp_path / "predictions.jsonl"
    logger = PredictionTelemetryLogger(
        log_path=log_path,
        now_fn=IncrementingClock(datetime(2026, 2, 1, tzinfo=UTC)),
    )
    request_id = logger.next_request_id()

    logger.log_success(
        request_id=request_id,
        zone_id="zone_01",
        as_of_timestamp="2026-01-30T12:00:00+00:00",
        prediction=12.5,
        model_name="naive_lag_1",
        model_version="test",
        latency_ms=3.25,
    )

    rows = read_prediction_logs(log_path)
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req_000001"
    assert rows[0]["status"] == "success"
    assert rows[0]["feature_freshness_seconds"] > 0


def test_failed_prediction_logging(tmp_path) -> None:
    client = _client_with_artifacts(tmp_path)

    response = client.post("/predict", json={"zone_id": "unknown_zone"})

    rows = read_prediction_logs(tmp_path / "predictions.jsonl")
    assert response.status_code == 404
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["error_type"] == "unknown_zone"
    assert rows[0]["zone_id"] == "unknown_zone"


def test_simulate_traffic_cli_smoke_behavior(tmp_path) -> None:
    artifacts = _write_serving_artifacts(tmp_path)
    telemetry_log_path = tmp_path / "predictions.jsonl"
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "simulate-traffic",
            "--model-path",
            str(artifacts.model_path),
            "--model-manifest-path",
            str(artifacts.model_manifest_path),
            "--feature-snapshot-path",
            str(artifacts.feature_snapshot_path),
            "--feature-manifest-path",
            str(artifacts.feature_manifest_path),
            "--telemetry-log-path",
            str(telemetry_log_path),
        ],
    )

    rows = read_prediction_logs(telemetry_log_path)
    assert result.exit_code == 0
    assert "simulated 3 prediction requests" in result.output
    assert len(rows) == 3
    assert sum(row["status"] == "success" for row in rows) == 2
    assert sum(row["status"] == "error" for row in rows) == 1


def test_monitoring_metrics_contain_required_keys() -> None:
    metrics = compute_serving_monitoring_metrics(
        _sample_telemetry_rows(),
        freshness_threshold_seconds=60.0,
    )

    assert set(REQUIRED_SERVING_MONITORING_METRIC_KEYS).issubset(metrics)


def test_stale_feature_warning_behavior() -> None:
    metrics = compute_serving_monitoring_metrics(
        _sample_telemetry_rows(),
        freshness_threshold_seconds=60.0,
    )
    warnings = build_serving_monitoring_warnings(
        metrics,
        ServingMonitoringThresholds(
            error_rate=0.50,
            p95_latency_ms=1000.0,
            freshness_seconds=60.0,
            min_prediction_count=1,
        ),
    )

    assert any("stale feature" in warning.lower() for warning in warnings)


def test_monitoring_report_is_written(tmp_path) -> None:
    log_path = tmp_path / "predictions.jsonl"
    report_path = tmp_path / "serving_monitoring_summary.md"
    metrics_path = tmp_path / "serving_monitoring_metrics.json"
    logger = PredictionTelemetryLogger(
        log_path=log_path,
        now_fn=IncrementingClock(datetime(2026, 2, 1, tzinfo=UTC)),
    )
    logger.write_row(_sample_telemetry_rows()[0])
    logger.write_row(_sample_telemetry_rows()[1])

    result = monitor_prediction_logs(
        log_path=log_path,
        report_path=report_path,
        metrics_path=metrics_path,
        thresholds=ServingMonitoringThresholds(freshness_seconds=60.0, min_prediction_count=5),
    )

    assert report_path.exists()
    assert metrics_path.exists()
    assert result.metrics["total_requests"] == 2
    assert "WARNING:" in report_path.read_text(encoding="utf-8")


def _sample_telemetry_rows() -> list[dict[str, object]]:
    return [
        {
            "request_id": "req_000001",
            "timestamp": "2026-02-01T00:00:00+00:00",
            "zone_id": "zone_01",
            "as_of_timestamp": "2026-01-30T00:00:00+00:00",
            "prediction": 12.0,
            "model_name": "naive_lag_1",
            "model_version": "test",
            "feature_freshness_seconds": 172800.0,
            "latency_ms": 10.0,
            "status": "success",
            "error_type": None,
        },
        {
            "request_id": "req_000002",
            "timestamp": "2026-02-01T00:00:01+00:00",
            "zone_id": "missing_zone",
            "as_of_timestamp": None,
            "prediction": None,
            "model_name": "naive_lag_1",
            "model_version": "test",
            "feature_freshness_seconds": None,
            "latency_ms": 2.0,
            "status": "error",
            "error_type": "unknown_zone",
        },
    ]

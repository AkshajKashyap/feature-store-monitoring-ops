from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.monitoring.drift import (
    DriftMonitoringThresholds,
    build_drift_monitoring_warnings,
    compute_categorical_coverage_drift,
    compute_numeric_feature_drift,
    compute_prediction_drift,
    monitor_drift,
    run_data_quality_checks,
)


def test_numeric_drift_metric_calculation() -> None:
    reference = _feature_frame(value_offset=0.0)
    current = _feature_frame(value_offset=10.0)

    metrics = compute_numeric_feature_drift(reference, current)
    lag_metrics = metrics["lag_1_observed_demand"]

    assert lag_metrics["current_mean"] > lag_metrics["reference_mean"]
    assert lag_metrics["mean_shift"] > 0
    assert lag_metrics["psi"] is not None


def test_missing_rate_detection() -> None:
    reference = _feature_frame(value_offset=0.0)
    current = _feature_frame(value_offset=0.0)
    current.loc[0, "lag_1_observed_demand"] = None

    metrics = compute_numeric_feature_drift(reference, current)
    quality = run_data_quality_checks(current)

    assert metrics["lag_1_observed_demand"]["current_missing_rate"] > 0
    assert not quality["passed"]
    assert any("missing values" in failure for failure in quality["failures"])


def test_zone_coverage_warning() -> None:
    reference = _feature_frame(zones=("zone_01", "zone_02", "zone_03"))
    current = _feature_frame(zones=("zone_01", "zone_02"))
    metrics = _drift_metrics(reference, current)

    warnings = build_drift_monitoring_warnings(
        metrics,
        DriftMonitoringThresholds(psi=100.0, prediction_mean_shift=100.0, min_prediction_count=1),
    )

    assert metrics["categorical_coverage_drift"]["zone_id"]["lost_values"] == ["zone_03"]
    assert any("Lost zone coverage" in warning for warning in warnings)


def test_prediction_drift_warning_with_small_logs() -> None:
    reference = _feature_frame()
    current = _feature_frame()
    prediction_drift = compute_prediction_drift(
        [_telemetry_row(prediction=15.0)],
        {
            "available": True,
            "source": "model_metrics.json",
            "selected_model": "test_model",
            "mean_prediction": 15.0,
        },
    )
    metrics = _drift_metrics(reference, current, prediction_drift=prediction_drift)

    warnings = build_drift_monitoring_warnings(
        metrics,
        DriftMonitoringThresholds(psi=100.0, prediction_mean_shift=100.0, min_prediction_count=10),
    )

    assert any("too small" in warning for warning in warnings)


def test_data_quality_check_failure_on_missing_column() -> None:
    frame = _feature_frame().drop(columns=["lag_1_observed_demand"])

    quality = run_data_quality_checks(frame)

    assert not quality["passed"]
    assert any("missing columns: lag_1_observed_demand" in failure for failure in quality["failures"])


def test_monitor_drift_cli_smoke_behavior(tmp_path) -> None:
    reference_path = tmp_path / "reference_features.parquet"
    current_path = tmp_path / "current_features.parquet"
    telemetry_log_path = tmp_path / "predictions.jsonl"
    model_metrics_path = tmp_path / "model_metrics.json"
    report_path = tmp_path / "drift_monitoring_summary.md"
    metrics_path = tmp_path / "drift_monitoring_metrics.json"
    _feature_frame(value_offset=0.0).to_parquet(reference_path, index=False)
    _feature_frame(value_offset=2.0).to_parquet(current_path, index=False)
    telemetry_log_path.write_text(json.dumps(_telemetry_row(prediction=20.0)) + "\n", encoding="utf-8")
    model_metrics_path.write_text(
        json.dumps(
            {
                "selected_model": "test_model",
                "test_metrics": {"mean_prediction": 19.0},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "monitor-drift",
            "--reference-path",
            str(reference_path),
            "--current-path",
            str(current_path),
            "--telemetry-log-path",
            str(telemetry_log_path),
            "--model-metrics-path",
            str(model_metrics_path),
            "--report-path",
            str(report_path),
            "--metrics-path",
            str(metrics_path),
            "--min-prediction-count",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "monitored feature drift rows" in result.output
    assert report_path.exists()
    assert metrics_path.exists()
    assert "Drift Monitoring Summary" in report_path.read_text(encoding="utf-8")


def test_monitoring_report_is_written(tmp_path) -> None:
    reference_path = tmp_path / "reference_features.parquet"
    current_path = tmp_path / "current_features.parquet"
    telemetry_log_path = tmp_path / "predictions.jsonl"
    model_metrics_path = tmp_path / "model_metrics.json"
    report_path = tmp_path / "drift_monitoring_summary.md"
    metrics_path = tmp_path / "drift_monitoring_metrics.json"
    _feature_frame(value_offset=0.0).to_parquet(reference_path, index=False)
    _feature_frame(value_offset=4.0).to_parquet(current_path, index=False)
    telemetry_log_path.write_text(json.dumps(_telemetry_row(prediction=18.0)) + "\n", encoding="utf-8")
    model_metrics_path.write_text(
        json.dumps({"selected_model": "test_model", "test_metrics": {"mean_prediction": 17.0}})
        + "\n",
        encoding="utf-8",
    )

    result = monitor_drift(
        reference_path=reference_path,
        current_path=current_path,
        telemetry_log_path=telemetry_log_path,
        model_metrics_path=model_metrics_path,
        report_path=report_path,
        metrics_path=metrics_path,
        thresholds=DriftMonitoringThresholds(min_prediction_count=1),
    )

    assert report_path.exists()
    assert metrics_path.exists()
    assert result.metrics["row_counts"]["reference"] == 4


def _drift_metrics(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    prediction_drift: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "row_counts": {"reference": len(reference), "current": len(current), "prediction_logs": 20},
        "numeric_feature_drift": compute_numeric_feature_drift(reference, current),
        "categorical_coverage_drift": compute_categorical_coverage_drift(reference, current),
        "prediction_drift": prediction_drift
        or {
            "reference_mean_prediction": 20.0,
            "current_mean_prediction": 20.0,
            "mean_prediction_shift": 0.0,
            "count": 20,
            "min_prediction": 18.0,
            "max_prediction": 22.0,
        },
        "data_quality": {
            "reference": run_data_quality_checks(reference),
            "current": run_data_quality_checks(current),
        },
    }


def _feature_frame(
    *,
    zones: tuple[str, ...] = ("zone_01", "zone_02", "zone_03", "zone_04"),
    value_offset: float = 0.0,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, zone_id in enumerate(zones):
        value = 10.0 + index + value_offset
        day_of_week = index % 7
        rows.append(
            {
                "zone_id": zone_id,
                "timestamp": f"2026-01-01T{index:02d}:00:00+00:00",
                "hour": index,
                "day_of_week": day_of_week,
                "is_weekend": day_of_week >= 5,
                "lag_1_observed_demand": value,
                "lag_3_observed_demand": value - 1.0,
                "rolling_mean_3": value - 0.5,
                "rolling_mean_6": value - 0.25,
                "rolling_std_6": 1.0 + index,
                "zone_hour_mean_demand": value + 0.5,
            },
        )
    return pd.DataFrame(rows)


def _telemetry_row(*, prediction: float) -> dict[str, object]:
    return {
        "request_id": "req_000001",
        "timestamp": "2026-02-01T00:00:00+00:00",
        "zone_id": "zone_01",
        "as_of_timestamp": "2026-01-30T00:00:00+00:00",
        "prediction": prediction,
        "model_name": "test_model",
        "model_version": "test",
        "feature_freshness_seconds": 172800.0,
        "latency_ms": 5.0,
        "status": "success",
        "error_type": None,
    }

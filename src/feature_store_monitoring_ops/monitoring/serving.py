"""Offline monitoring over persisted local serving telemetry."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from feature_store_monitoring_ops.monitoring.telemetry import read_prediction_logs
from feature_store_monitoring_ops.paths import (
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_SERVING_MONITORING_METRICS_PATH,
    DEFAULT_SERVING_MONITORING_REPORT_PATH,
)

REQUIRED_SERVING_MONITORING_METRIC_KEYS: tuple[str, ...] = (
    "total_requests",
    "successful_predictions",
    "failed_predictions",
    "error_rate",
    "average_latency_ms",
    "p95_latency_ms",
    "mean_prediction",
    "min_prediction",
    "max_prediction",
    "request_count_by_zone",
    "stale_feature_count",
)


@dataclass(frozen=True)
class ServingMonitoringThresholds:
    """Thresholds used to produce serving monitoring warnings."""

    error_rate: float = 0.10
    p95_latency_ms: float = 250.0
    freshness_seconds: float = 172800.0
    min_prediction_count: int = 10


@dataclass(frozen=True)
class ServingMonitoringResult:
    """Paths, metrics, and warnings from offline serving monitoring."""

    report_path: Path
    metrics_path: Path
    metrics: dict[str, Any]
    warnings: list[str]


def compute_serving_monitoring_metrics(
    rows: list[dict[str, Any]],
    *,
    freshness_threshold_seconds: float,
) -> dict[str, Any]:
    """Compute offline serving metrics from prediction telemetry rows."""

    total_requests = len(rows)
    successful_rows = [row for row in rows if row.get("status") == "success"]
    failed_predictions = total_requests - len(successful_rows)
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if row.get("latency_ms") is not None
    ]
    predictions = [
        float(row["prediction"])
        for row in successful_rows
        if row.get("prediction") is not None
    ]
    request_count_by_zone: dict[str, int] = {}
    for row in rows:
        zone_id = str(row.get("zone_id"))
        request_count_by_zone[zone_id] = request_count_by_zone.get(zone_id, 0) + 1

    stale_feature_count = sum(
        1
        for row in successful_rows
        if row.get("feature_freshness_seconds") is not None
        and float(row["feature_freshness_seconds"]) > freshness_threshold_seconds
    )

    return {
        "total_requests": total_requests,
        "successful_predictions": len(successful_rows),
        "failed_predictions": failed_predictions,
        "error_rate": _round_or_zero(failed_predictions / total_requests if total_requests else 0.0),
        "average_latency_ms": _round_or_none(_mean(latencies)),
        "p95_latency_ms": _round_or_none(_percentile(latencies, percentile=0.95)),
        "mean_prediction": _round_or_none(_mean(predictions)),
        "min_prediction": _round_or_none(min(predictions) if predictions else None),
        "max_prediction": _round_or_none(max(predictions) if predictions else None),
        "request_count_by_zone": dict(sorted(request_count_by_zone.items())),
        "stale_feature_count": stale_feature_count,
    }


def build_serving_monitoring_warnings(
    metrics: dict[str, Any],
    thresholds: ServingMonitoringThresholds,
) -> list[str]:
    """Build warning messages for serving monitoring thresholds."""

    warnings: list[str] = []
    if float(metrics["error_rate"]) > thresholds.error_rate:
        warnings.append(
            f"Error rate {metrics['error_rate']:.3f} exceeds threshold {thresholds.error_rate:.3f}.",
        )
    p95_latency = metrics["p95_latency_ms"]
    if p95_latency is not None and float(p95_latency) > thresholds.p95_latency_ms:
        warnings.append(
            f"P95 latency {p95_latency:.3f} ms exceeds threshold {thresholds.p95_latency_ms:.3f} ms.",
        )
    if int(metrics["stale_feature_count"]) > 0:
        warnings.append(f"Detected {metrics['stale_feature_count']} stale feature rows.")
    if int(metrics["successful_predictions"]) < thresholds.min_prediction_count:
        warnings.append(
            "Prediction count is too small to trust "
            f"({metrics['successful_predictions']} < {thresholds.min_prediction_count}).",
        )
    return warnings


def monitor_prediction_logs(
    *,
    log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Path = DEFAULT_SERVING_MONITORING_REPORT_PATH,
    metrics_path: Path = DEFAULT_SERVING_MONITORING_METRICS_PATH,
    thresholds: ServingMonitoringThresholds = ServingMonitoringThresholds(),
) -> ServingMonitoringResult:
    """Read prediction telemetry, write serving monitoring report and metrics JSON."""

    rows = read_prediction_logs(log_path)
    metrics = compute_serving_monitoring_metrics(
        rows,
        freshness_threshold_seconds=thresholds.freshness_seconds,
    )
    warnings = build_serving_monitoring_warnings(metrics, thresholds)
    metrics_payload = {
        **metrics,
        "thresholds": {
            "error_rate": thresholds.error_rate,
            "p95_latency_ms": thresholds.p95_latency_ms,
            "freshness_seconds": thresholds.freshness_seconds,
            "min_prediction_count": thresholds.min_prediction_count,
        },
        "warnings": warnings,
    }

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_serving_monitoring_report(
            log_path=log_path,
            metrics=metrics,
            warnings=warnings,
            thresholds=thresholds,
        ),
        encoding="utf-8",
    )
    return ServingMonitoringResult(
        report_path=report_path,
        metrics_path=metrics_path,
        metrics=metrics,
        warnings=warnings,
    )


def build_serving_monitoring_report(
    *,
    log_path: Path,
    metrics: dict[str, Any],
    warnings: list[str],
    thresholds: ServingMonitoringThresholds,
) -> str:
    """Build a tracked Markdown serving monitoring report."""

    warning_lines = "\n".join(f"- WARNING: {warning}" for warning in warnings)
    if not warning_lines:
        warning_lines = "- No warnings."
    zone_lines = "\n".join(
        f"- `{zone_id}`: {count}"
        for zone_id, count in metrics["request_count_by_zone"].items()
    )
    if not zone_lines:
        zone_lines = "- No requests."

    return "\n".join(
        [
            "# Serving Monitoring Summary",
            "",
            "Offline monitoring over persisted local prediction telemetry for Milestone 6.",
            "",
            "## Source",
            "",
            f"- Prediction log: `{log_path}`",
            "",
            "## Metrics",
            "",
            f"- Total requests: {metrics['total_requests']}",
            f"- Successful predictions: {metrics['successful_predictions']}",
            f"- Failed predictions: {metrics['failed_predictions']}",
            f"- Error rate: {metrics['error_rate']:.3f}",
            f"- Average latency ms: {_format_optional_float(metrics['average_latency_ms'])}",
            f"- P95 latency ms: {_format_optional_float(metrics['p95_latency_ms'])}",
            f"- Mean prediction: {_format_optional_float(metrics['mean_prediction'])}",
            f"- Min prediction: {_format_optional_float(metrics['min_prediction'])}",
            f"- Max prediction: {_format_optional_float(metrics['max_prediction'])}",
            f"- Stale feature count: {metrics['stale_feature_count']}",
            "",
            "## Request Count By Zone",
            "",
            zone_lines,
            "",
            "## Thresholds",
            "",
            f"- Error rate: {thresholds.error_rate:.3f}",
            f"- P95 latency ms: {thresholds.p95_latency_ms:.3f}",
            f"- Feature freshness seconds: {thresholds.freshness_seconds:.3f}",
            f"- Minimum prediction count: {thresholds.min_prediction_count}",
            "",
            "## Warnings",
            "",
            warning_lines,
            "",
        ],
    )


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _percentile(values: list[float], *, percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _round_or_zero(value: float) -> float:
    return round(float(value), 6)


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


__all__ = [
    "REQUIRED_SERVING_MONITORING_METRIC_KEYS",
    "ServingMonitoringResult",
    "ServingMonitoringThresholds",
    "build_serving_monitoring_report",
    "build_serving_monitoring_warnings",
    "compute_serving_monitoring_metrics",
    "monitor_prediction_logs",
]

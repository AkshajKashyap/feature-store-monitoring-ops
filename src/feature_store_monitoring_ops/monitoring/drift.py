"""Feature, prediction, and data quality drift monitoring."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    ENTITY_KEY_COLUMNS,
    get_model_input_columns,
    get_online_feature_columns,
)
from feature_store_monitoring_ops.monitoring.telemetry import read_prediction_logs
from feature_store_monitoring_ops.paths import (
    DEFAULT_DRIFT_MONITORING_METRICS_PATH,
    DEFAULT_DRIFT_MONITORING_REPORT_PATH,
    DEFAULT_MODEL_METRICS_PATH,
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_TEST_FEATURES_PATH,
    DEFAULT_TRAIN_FEATURES_PATH,
)

NUMERIC_DRIFT_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    column for column in get_model_input_columns() if column not in ENTITY_KEY_COLUMNS
)
COVERAGE_DRIFT_COLUMNS: tuple[str, ...] = ("zone_id", "hour", "day_of_week")
NONNEGATIVE_DEMAND_FEATURE_COLUMNS: tuple[str, ...] = (
    "lag_1_observed_demand",
    "lag_3_observed_demand",
    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_std_6",
    "zone_hour_mean_demand",
)
REQUIRED_DRIFT_MONITORING_METRIC_KEYS: tuple[str, ...] = (
    "row_counts",
    "numeric_feature_drift",
    "categorical_coverage_drift",
    "prediction_drift",
    "data_quality",
)


@dataclass(frozen=True)
class DriftMonitoringThresholds:
    """Thresholds used to produce drift monitoring warnings."""

    psi: float = 0.20
    prediction_mean_shift: float = 5.0
    min_prediction_count: int = 10


@dataclass(frozen=True)
class DriftMonitoringResult:
    """Paths, metrics, and warnings from drift monitoring."""

    report_path: Path
    metrics_path: Path
    metrics: dict[str, Any]
    warnings: list[str]


def read_feature_window(path: Path) -> pd.DataFrame:
    """Read a feature monitoring window from parquet or JSON records."""

    if not path.exists():
        raise FileNotFoundError(f"feature window not found: {path}")
    if path.suffix.lower() == ".json":
        return _read_json_feature_window(path)
    return pd.read_parquet(path)


def compute_numeric_feature_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...] = NUMERIC_DRIFT_FEATURE_COLUMNS,
    bins: int = 10,
) -> dict[str, dict[str, float | None]]:
    """Compute mean, standard deviation, missing-rate, and PSI drift per numeric feature."""

    metrics: dict[str, dict[str, float | None]] = {}
    for column in feature_columns:
        reference_values = _numeric_series(reference, column)
        current_values = _numeric_series(current, column)
        reference_mean = _round_or_none(_mean(reference_values))
        current_mean = _round_or_none(_mean(current_values))
        reference_std = _round_or_none(_std(reference_values))
        current_std = _round_or_none(_std(current_values))
        reference_missing_rate = _round_or_none(_missing_rate(reference_values))
        current_missing_rate = _round_or_none(_missing_rate(current_values))
        metrics[column] = {
            "reference_mean": reference_mean,
            "current_mean": current_mean,
            "mean_shift": _difference(current_mean, reference_mean),
            "reference_std": reference_std,
            "current_std": current_std,
            "std_shift": _difference(current_std, reference_std),
            "reference_missing_rate": reference_missing_rate,
            "current_missing_rate": current_missing_rate,
            "missing_rate_difference": _difference(current_missing_rate, reference_missing_rate),
            "psi": _compute_psi(reference_values, current_values, bins=bins),
        }
    return metrics


def compute_categorical_coverage_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    columns: tuple[str, ...] = COVERAGE_DRIFT_COLUMNS,
) -> dict[str, dict[str, Any]]:
    """Compute value coverage changes for entity and categorical feature columns."""

    metrics: dict[str, dict[str, Any]] = {}
    for column in columns:
        reference_values = _unique_jsonable_values(reference, column)
        current_values = _unique_jsonable_values(current, column)
        reference_set = set(reference_values)
        current_set = set(current_values)
        metrics[column] = {
            "reference_count": len(reference_values),
            "current_count": len(current_values),
            "reference_values": reference_values,
            "current_values": current_values,
            "lost_values": sorted(reference_set.difference(current_set), key=str),
            "new_values": sorted(current_set.difference(reference_set), key=str),
        }
    return metrics


def run_data_quality_checks(
    frame: pd.DataFrame,
    *,
    required_columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run deterministic data quality checks for offline or online feature rows."""

    expected_columns = required_columns or get_online_feature_columns()
    failures: list[str] = []
    checks: dict[str, dict[str, object]] = {}

    missing_columns = sorted(set(expected_columns).difference(frame.columns))
    _record_check(
        checks,
        failures,
        "required_columns_present",
        not missing_columns,
        "all required columns present"
        if not missing_columns
        else f"missing columns: {', '.join(missing_columns)}",
    )

    present_input_columns = [column for column in get_model_input_columns() if column in frame.columns]
    missing_value_counts = {
        column: int(frame[column].isna().sum())
        for column in present_input_columns
        if int(frame[column].isna().sum()) > 0
    }
    _record_check(
        checks,
        failures,
        "no_missing_model_input_features",
        not missing_value_counts,
        "no missing model input feature values"
        if not missing_value_counts
        else "missing values: "
        + ", ".join(f"{column}={count}" for column, count in missing_value_counts.items()),
    )

    duplicate_subset = [*ENTITY_KEY_COLUMNS, AS_OF_TIMESTAMP_COLUMN]
    if all(column in frame.columns for column in duplicate_subset):
        duplicate_count = int(frame.duplicated(subset=duplicate_subset).sum())
        duplicate_details = (
            "no duplicate entity/as-of rows"
            if duplicate_count == 0
            else f"duplicate entity/as-of rows: {duplicate_count}"
        )
        duplicate_check_passed = duplicate_count == 0
    else:
        duplicate_check_passed = False
        duplicate_details = "cannot check duplicates because entity/as-of columns are missing"
    _record_check(
        checks,
        failures,
        "no_duplicate_entity_as_of_rows",
        duplicate_check_passed,
        duplicate_details,
    )

    nonnumeric_columns: dict[str, int] = {}
    negative_counts: dict[str, int] = {}
    for column in NONNEGATIVE_DEMAND_FEATURE_COLUMNS:
        if column not in frame.columns:
            continue
        numeric_values = pd.to_numeric(frame[column], errors="coerce")
        nonmissing_original = frame[column].notna()
        invalid_count = int(numeric_values[nonmissing_original].isna().sum())
        negative_count = int((numeric_values.dropna() < 0).sum())
        if invalid_count:
            nonnumeric_columns[column] = invalid_count
        if negative_count:
            negative_counts[column] = negative_count
    nonnegative_passed = not nonnumeric_columns and not negative_counts
    nonnegative_details = "nonnegative lag and rolling demand features"
    if nonnumeric_columns or negative_counts:
        details = []
        if nonnumeric_columns:
            details.append(
                "nonnumeric values: "
                + ", ".join(f"{column}={count}" for column, count in nonnumeric_columns.items()),
            )
        if negative_counts:
            details.append(
                "negative values: "
                + ", ".join(f"{column}={count}" for column, count in negative_counts.items()),
            )
        nonnegative_details = "; ".join(details)
    _record_check(
        checks,
        failures,
        "nonnegative_demand_features",
        nonnegative_passed,
        nonnegative_details,
    )

    if AS_OF_TIMESTAMP_COLUMN in frame.columns:
        parsed_timestamps = pd.to_datetime(frame[AS_OF_TIMESTAMP_COLUMN], utc=True, errors="coerce")
        invalid_timestamp_count = int(parsed_timestamps.isna().sum())
        timestamp_passed = invalid_timestamp_count == 0
        timestamp_details = (
            "timestamps parse correctly"
            if timestamp_passed
            else f"unparseable timestamps: {invalid_timestamp_count}"
        )
    else:
        timestamp_passed = False
        timestamp_details = f"missing timestamp column: {AS_OF_TIMESTAMP_COLUMN}"
    _record_check(
        checks,
        failures,
        "timestamps_parse",
        timestamp_passed,
        timestamp_details,
    )

    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
    }


def load_reference_prediction_summary(path: Path = DEFAULT_MODEL_METRICS_PATH) -> dict[str, Any]:
    """Load the selected model test prediction summary used as a prediction reference."""

    if not path.exists():
        return {
            "available": False,
            "source": str(path),
            "selected_model": None,
            "mean_prediction": None,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    test_metrics = payload.get("test_metrics", {})
    return {
        "available": True,
        "source": str(path),
        "selected_model": payload.get("selected_model"),
        "mean_prediction": test_metrics.get("mean_prediction"),
    }


def compute_prediction_drift(
    telemetry_rows: list[dict[str, Any]],
    reference_summary: dict[str, Any],
) -> dict[str, Any]:
    """Compare recent telemetry predictions with a reference prediction summary."""

    predictions = [
        float(row["prediction"])
        for row in telemetry_rows
        if row.get("status") == "success" and row.get("prediction") is not None
    ]
    current_mean = _round_or_none(sum(predictions) / len(predictions) if predictions else None)
    reference_mean = _round_or_none(_coerce_optional_float(reference_summary.get("mean_prediction")))
    return {
        "reference_source": reference_summary.get("source"),
        "reference_available": bool(reference_summary.get("available")),
        "reference_selected_model": reference_summary.get("selected_model"),
        "reference_mean_prediction": reference_mean,
        "current_mean_prediction": current_mean,
        "mean_prediction_shift": _difference(current_mean, reference_mean),
        "count": len(predictions),
        "min_prediction": _round_or_none(min(predictions) if predictions else None),
        "max_prediction": _round_or_none(max(predictions) if predictions else None),
    }


def build_drift_monitoring_warnings(
    metrics: dict[str, Any],
    thresholds: DriftMonitoringThresholds,
) -> list[str]:
    """Build warning messages for drift and data quality thresholds."""

    warnings: list[str] = []
    for feature, feature_metrics in metrics["numeric_feature_drift"].items():
        psi = feature_metrics["psi"]
        if psi is not None and float(psi) > thresholds.psi:
            warnings.append(
                f"Feature `{feature}` PSI {float(psi):.3f} exceeds threshold "
                f"{thresholds.psi:.3f}.",
            )
        current_missing_rate = feature_metrics["current_missing_rate"]
        if current_missing_rate is not None and float(current_missing_rate) > 0:
            warnings.append(
                f"Feature `{feature}` has current missing rate {float(current_missing_rate):.3f}.",
            )

    lost_zones = metrics["categorical_coverage_drift"].get("zone_id", {}).get("lost_values", [])
    if lost_zones:
        warnings.append(f"Lost zone coverage: {', '.join(str(zone) for zone in lost_zones)}.")

    prediction_drift = metrics["prediction_drift"]
    prediction_count = int(prediction_drift["count"])
    if prediction_count < thresholds.min_prediction_count:
        warnings.append(
            "Prediction drift sample is too small to trust "
            f"({prediction_count} < {thresholds.min_prediction_count}).",
        )
    prediction_shift = prediction_drift["mean_prediction_shift"]
    if prediction_shift is not None and abs(float(prediction_shift)) > thresholds.prediction_mean_shift:
        warnings.append(
            f"Prediction mean shift {float(prediction_shift):.3f} exceeds threshold "
            f"{thresholds.prediction_mean_shift:.3f}.",
        )

    for label, quality in metrics["data_quality"].items():
        if not quality["passed"]:
            warnings.append(
                f"{label.title()} data quality failed with {len(quality['failures'])} issue(s).",
            )
    return warnings


def monitor_drift(
    *,
    reference_path: Path = DEFAULT_TRAIN_FEATURES_PATH,
    current_path: Path = DEFAULT_TEST_FEATURES_PATH,
    telemetry_log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
    model_metrics_path: Path = DEFAULT_MODEL_METRICS_PATH,
    report_path: Path = DEFAULT_DRIFT_MONITORING_REPORT_PATH,
    metrics_path: Path = DEFAULT_DRIFT_MONITORING_METRICS_PATH,
    thresholds: DriftMonitoringThresholds = DriftMonitoringThresholds(),
) -> DriftMonitoringResult:
    """Build feature drift, prediction drift, and data quality monitoring outputs."""

    reference = read_feature_window(reference_path)
    current = read_feature_window(current_path)
    telemetry_rows = read_prediction_logs(telemetry_log_path)
    reference_prediction_summary = load_reference_prediction_summary(model_metrics_path)

    metrics: dict[str, Any] = {
        "row_counts": {
            "reference": len(reference),
            "current": len(current),
            "prediction_logs": len(telemetry_rows),
        },
        "numeric_feature_drift": compute_numeric_feature_drift(reference, current),
        "categorical_coverage_drift": compute_categorical_coverage_drift(reference, current),
        "prediction_drift": compute_prediction_drift(
            telemetry_rows,
            reference_prediction_summary,
        ),
        "data_quality": {
            "reference": run_data_quality_checks(reference),
            "current": run_data_quality_checks(current),
        },
    }
    warnings = build_drift_monitoring_warnings(metrics, thresholds)
    payload = {
        **metrics,
        "sources": {
            "reference_features": str(reference_path),
            "current_features": str(current_path),
            "prediction_logs": str(telemetry_log_path),
            "model_metrics": str(model_metrics_path),
        },
        "thresholds": {
            "psi": thresholds.psi,
            "prediction_mean_shift": thresholds.prediction_mean_shift,
            "min_prediction_count": thresholds.min_prediction_count,
        },
        "warnings": warnings,
    }

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_drift_monitoring_report(
            reference_path=reference_path,
            current_path=current_path,
            telemetry_log_path=telemetry_log_path,
            model_metrics_path=model_metrics_path,
            metrics=metrics,
            warnings=warnings,
            thresholds=thresholds,
        ),
        encoding="utf-8",
    )

    return DriftMonitoringResult(
        report_path=report_path,
        metrics_path=metrics_path,
        metrics=metrics,
        warnings=warnings,
    )


def build_drift_monitoring_report(
    *,
    reference_path: Path,
    current_path: Path,
    telemetry_log_path: Path,
    model_metrics_path: Path,
    metrics: dict[str, Any],
    warnings: list[str],
    thresholds: DriftMonitoringThresholds,
) -> str:
    """Build a tracked Markdown drift monitoring report."""

    numeric_rows = "\n".join(
        (
            f"| `{feature}` | {_format_optional_float(values['mean_shift'])} | "
            f"{_format_optional_float(values['std_shift'])} | "
            f"{_format_optional_float(values['missing_rate_difference'])} | "
            f"{_format_optional_float(values['psi'])} |"
        )
        for feature, values in metrics["numeric_feature_drift"].items()
    )
    coverage_lines = "\n".join(
        (
            f"- `{column}`: reference={values['reference_count']}, "
            f"current={values['current_count']}, lost={values['lost_values']}, "
            f"new={values['new_values']}"
        )
        for column, values in metrics["categorical_coverage_drift"].items()
    )
    quality_lines = "\n".join(
        f"- {label.title()}: {'passed' if quality['passed'] else 'failed'}"
        for label, quality in metrics["data_quality"].items()
    )
    warning_lines = "\n".join(f"- WARNING: {warning}" for warning in warnings)
    if not warning_lines:
        warning_lines = "- No warnings."

    prediction_drift = metrics["prediction_drift"]
    return "\n".join(
        [
            "# Drift Monitoring Summary",
            "",
            "Feature drift, prediction drift, and data quality checks for Milestone 7.",
            "",
            "## Sources",
            "",
            f"- Reference features: `{reference_path}`",
            f"- Current features: `{current_path}`",
            f"- Prediction logs: `{telemetry_log_path}`",
            f"- Model metrics reference: `{model_metrics_path}`",
            "",
            "## Row Counts",
            "",
            f"- Reference feature rows: {metrics['row_counts']['reference']}",
            f"- Current feature rows: {metrics['row_counts']['current']}",
            f"- Prediction log rows: {metrics['row_counts']['prediction_logs']}",
            "",
            "## Numeric Feature Drift",
            "",
            "| Feature | Mean Shift | Std Shift | Missing Rate Difference | PSI |",
            "| --- | ---: | ---: | ---: | ---: |",
            numeric_rows,
            "",
            "## Coverage Drift",
            "",
            coverage_lines,
            "",
            "## Prediction Drift",
            "",
            f"- Reference selected model: `{prediction_drift['reference_selected_model']}`",
            f"- Reference mean prediction: "
            f"{_format_optional_float(prediction_drift['reference_mean_prediction'])}",
            f"- Current mean prediction: "
            f"{_format_optional_float(prediction_drift['current_mean_prediction'])}",
            f"- Mean prediction shift: "
            f"{_format_optional_float(prediction_drift['mean_prediction_shift'])}",
            f"- Prediction count: {prediction_drift['count']}",
            f"- Min prediction: {_format_optional_float(prediction_drift['min_prediction'])}",
            f"- Max prediction: {_format_optional_float(prediction_drift['max_prediction'])}",
            "",
            "## Data Quality",
            "",
            quality_lines,
            "",
            "## Thresholds",
            "",
            f"- PSI: {thresholds.psi:.3f}",
            f"- Prediction mean shift: {thresholds.prediction_mean_shift:.3f}",
            f"- Minimum prediction count: {thresholds.min_prediction_count}",
            "",
            "## Warnings",
            "",
            warning_lines,
            "",
        ],
    )


def _read_json_feature_window(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return pd.DataFrame(payload["rows"])
    raise ValueError(f"JSON feature window must contain records: {path}")


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([pd.NA] * len(frame), dtype="Float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _mean(values: pd.Series) -> float | None:
    valid = values.dropna()
    if valid.empty:
        return None
    return float(valid.mean())


def _std(values: pd.Series) -> float | None:
    valid = values.dropna()
    if valid.empty:
        return None
    return float(valid.std(ddof=0))


def _missing_rate(values: pd.Series) -> float:
    if len(values) == 0:
        return 0.0
    return float(values.isna().mean())


def _compute_psi(reference: pd.Series, current: pd.Series, *, bins: int) -> float | None:
    reference_values = reference.dropna().astype(float)
    current_values = current.dropna().astype(float)
    if reference_values.empty or current_values.empty:
        return None

    lower = float(min(reference_values.min(), current_values.min()))
    upper = float(max(reference_values.max(), current_values.max()))
    if math.isclose(lower, upper):
        return 0.0

    width = (upper - lower) / bins
    edges = [lower + (width * index) for index in range(bins + 1)]
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    reference_counts = pd.cut(reference_values, bins=edges, include_lowest=True).value_counts(
        sort=False,
    )
    current_counts = pd.cut(current_values, bins=edges, include_lowest=True).value_counts(
        sort=False,
    )
    reference_total = float(reference_counts.sum())
    current_total = float(current_counts.sum())
    epsilon = 1e-6
    psi = 0.0
    for reference_count, current_count in zip(reference_counts, current_counts, strict=True):
        reference_pct = max(float(reference_count) / reference_total, epsilon)
        current_pct = max(float(current_count) / current_total, epsilon)
        psi += (current_pct - reference_pct) * math.log(current_pct / reference_pct)
    return round(max(float(psi), 0.0), 6)


def _unique_jsonable_values(frame: pd.DataFrame, column: str) -> list[object]:
    if column not in frame.columns:
        return []
    values = {_jsonable_scalar(value) for value in frame[column].dropna().unique()}
    return sorted(values, key=str)


def _record_check(
    checks: dict[str, dict[str, object]],
    failures: list[str],
    name: str,
    passed: bool,
    details: str,
) -> None:
    checks[name] = {"passed": passed, "details": details}
    if not passed:
        failures.append(f"{name}: {details}")


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), 6)


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 6)


def _format_optional_float(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


def _jsonable_scalar(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


__all__ = [
    "COVERAGE_DRIFT_COLUMNS",
    "DriftMonitoringResult",
    "DriftMonitoringThresholds",
    "NONNEGATIVE_DEMAND_FEATURE_COLUMNS",
    "NUMERIC_DRIFT_FEATURE_COLUMNS",
    "REQUIRED_DRIFT_MONITORING_METRIC_KEYS",
    "build_drift_monitoring_report",
    "build_drift_monitoring_warnings",
    "compute_categorical_coverage_drift",
    "compute_numeric_feature_drift",
    "compute_prediction_drift",
    "load_reference_prediction_summary",
    "monitor_drift",
    "read_feature_window",
    "run_data_quality_checks",
]

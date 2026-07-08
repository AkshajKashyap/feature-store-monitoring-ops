"""Offline temporal feature engineering for synthetic demand events."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    MODEL_INPUT_FEATURE_COLUMNS,
    REQUIRED_OFFLINE_FEATURE_COLUMNS,
    TARGET_COLUMN,
)
from feature_store_monitoring_ops.paths import (
    DEFAULT_OFFLINE_FEATURE_REPORT_PATH,
    DEFAULT_OFFLINE_FEATURES_PATH,
    DEFAULT_SYNTHETIC_EVENTS_PATH,
    DEFAULT_TEST_FEATURES_PATH,
    DEFAULT_TRAIN_FEATURES_PATH,
    DEFAULT_VALIDATION_FEATURES_PATH,
)
from feature_store_monitoring_ops.schema import REQUIRED_SYNTHETIC_EVENT_COLUMNS

OFFLINE_FEATURE_COLUMNS = MODEL_INPUT_FEATURE_COLUMNS


@dataclass(frozen=True)
class OfflineFeatureBuildResult:
    """Output paths and split row counts from building offline features."""

    offline_features_path: Path
    train_features_path: Path
    validation_features_path: Path
    test_features_path: Path
    report_path: Path
    row_counts: dict[str, int]


def read_synthetic_events(path: Path = DEFAULT_SYNTHETIC_EVENTS_PATH) -> pd.DataFrame:
    """Read synthetic events from CSV and normalize dtypes for feature engineering."""

    if not path.exists():
        raise FileNotFoundError(f"synthetic events file not found: {path}")
    events = pd.read_csv(path)
    return normalize_synthetic_events(events)


def normalize_synthetic_events(events: pd.DataFrame) -> pd.DataFrame:
    """Normalize event dataframe columns and sort by event time."""

    missing = set(REQUIRED_SYNTHETIC_EVENT_COLUMNS).difference(events.columns)
    if missing:
        raise ValueError(f"synthetic events missing required columns: {', '.join(sorted(missing))}")

    normalized = events.copy()
    normalized[AS_OF_TIMESTAMP_COLUMN] = pd.to_datetime(
        normalized[AS_OF_TIMESTAMP_COLUMN],
        utc=True,
        errors="raise",
    )
    normalized["event_id"] = normalized["event_id"].astype(str)
    normalized["zone_id"] = normalized["zone_id"].astype(str)
    normalized["user_id"] = normalized["user_id"].astype(str)
    normalized["demand_count"] = pd.to_numeric(normalized["demand_count"], errors="raise")
    normalized["base_demand"] = pd.to_numeric(normalized["base_demand"], errors="raise")
    normalized["observed_demand"] = pd.to_numeric(normalized["observed_demand"], errors="raise")
    normalized["hour"] = normalized[AS_OF_TIMESTAMP_COLUMN].dt.hour.astype("int64")
    normalized["day_of_week"] = normalized[AS_OF_TIMESTAMP_COLUMN].dt.dayofweek.astype("int64")
    normalized["is_weekend"] = normalized[AS_OF_TIMESTAMP_COLUMN].dt.dayofweek.ge(5)

    return normalized.sort_values(
        [AS_OF_TIMESTAMP_COLUMN, "zone_id", "event_id"],
        kind="mergesort",
        ignore_index=True,
    )


def build_offline_features(events: pd.DataFrame) -> pd.DataFrame:
    """Build model-ready temporal features without using future observations."""

    frame = normalize_synthetic_events(events)
    frame["lag_1_observed_demand"] = frame.groupby("zone_id", sort=False)[
        "observed_demand"
    ].shift(1)
    frame["lag_3_observed_demand"] = frame.groupby("zone_id", sort=False)[
        "observed_demand"
    ].shift(3)

    prior_zone_observed = frame.groupby("zone_id", sort=False)["observed_demand"].shift(1)
    frame["rolling_mean_3"] = _rolling_by_zone(
        values=prior_zone_observed,
        zones=frame["zone_id"],
        window=3,
        min_periods=1,
        aggregation="mean",
    )
    frame["rolling_mean_6"] = _rolling_by_zone(
        values=prior_zone_observed,
        zones=frame["zone_id"],
        window=6,
        min_periods=1,
        aggregation="mean",
    )
    frame["rolling_std_6"] = _rolling_by_zone(
        values=prior_zone_observed,
        zones=frame["zone_id"],
        window=6,
        min_periods=2,
        aggregation="std",
    )

    frame["_prior_zone_hour_observed"] = frame.groupby(["zone_id", "hour"], sort=False)[
        "observed_demand"
    ].shift(1)
    frame["zone_hour_mean_demand"] = (
        frame.groupby(["zone_id", "hour"], sort=False)["_prior_zone_hour_observed"]
        .expanding()
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )
    frame[TARGET_COLUMN] = frame.groupby("zone_id", sort=False)["observed_demand"].shift(-1)

    features = frame.loc[:, REQUIRED_OFFLINE_FEATURE_COLUMNS].dropna(
        subset=REQUIRED_OFFLINE_FEATURE_COLUMNS,
    )
    features = features.sort_values(
        [AS_OF_TIMESTAMP_COLUMN, "zone_id", "event_id"],
        kind="mergesort",
        ignore_index=True,
    )
    if features.empty:
        raise ValueError("offline feature construction produced no rows")
    return features


def split_chronologically(
    features: pd.DataFrame,
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> dict[str, pd.DataFrame]:
    """Split feature rows into deterministic chronological train/validation/test sets."""

    _validate_split_fractions(
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
    )
    ordered = features.sort_values(
        [AS_OF_TIMESTAMP_COLUMN, "zone_id", "event_id"],
        kind="mergesort",
        ignore_index=True,
    )
    if len(ordered) < 3:
        raise ValueError("at least three feature rows are required for train/validation/test splits")

    train_count = max(1, int(len(ordered) * train_fraction))
    validation_count = max(1, int(len(ordered) * validation_fraction))
    if train_count + validation_count >= len(ordered):
        train_count = max(1, len(ordered) - 2)
        validation_count = 1

    train_end = train_count
    validation_end = train_end + validation_count
    return {
        "train": ordered.iloc[:train_end].reset_index(drop=True),
        "validation": ordered.iloc[train_end:validation_end].reset_index(drop=True),
        "test": ordered.iloc[validation_end:].reset_index(drop=True),
    }


def build_and_save_offline_features(
    *,
    input_path: Path = DEFAULT_SYNTHETIC_EVENTS_PATH,
    offline_features_path: Path = DEFAULT_OFFLINE_FEATURES_PATH,
    train_features_path: Path = DEFAULT_TRAIN_FEATURES_PATH,
    validation_features_path: Path = DEFAULT_VALIDATION_FEATURES_PATH,
    test_features_path: Path = DEFAULT_TEST_FEATURES_PATH,
    report_path: Path = DEFAULT_OFFLINE_FEATURE_REPORT_PATH,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> OfflineFeatureBuildResult:
    """Read synthetic events, build features, write parquet splits and a summary report."""

    events = read_synthetic_events(input_path)
    features = build_offline_features(events)
    splits = split_chronologically(
        features,
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
    )

    _write_parquet(features, offline_features_path)
    _write_parquet(splits["train"], train_features_path)
    _write_parquet(splits["validation"], validation_features_path)
    _write_parquet(splits["test"], test_features_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_offline_feature_summary(features, splits), encoding="utf-8")

    return OfflineFeatureBuildResult(
        offline_features_path=offline_features_path,
        train_features_path=train_features_path,
        validation_features_path=validation_features_path,
        test_features_path=test_features_path,
        report_path=report_path,
        row_counts={
            "offline": len(features),
            "train": len(splits["train"]),
            "validation": len(splits["validation"]),
            "test": len(splits["test"]),
        },
    )


def build_offline_feature_summary(
    features: pd.DataFrame,
    splits: dict[str, pd.DataFrame],
) -> str:
    """Build a Markdown summary for offline feature artifacts."""

    target = features[TARGET_COLUMN]
    feature_lines = "\n".join(f"- `{column}`" for column in OFFLINE_FEATURE_COLUMNS)
    row_count_lines = "\n".join(f"- {name}: {len(split)} rows" for name, split in splits.items())
    split_range_lines = "\n".join(
        f"- {name}: {len(split)} rows, {_format_time_range(split)}"
        for name, split in splits.items()
    )

    return "\n".join(
        [
            "# Offline Feature Summary",
            "",
            "Built deterministic offline temporal features for Milestone 2.",
            "",
            "## Row Counts",
            "",
            f"- Offline features: {len(features)}",
            row_count_lines,
            "",
            "## Split Time Ranges",
            "",
            split_range_lines,
            "",
            "## Feature Columns",
            "",
            feature_lines,
            "",
            "## Target Summary",
            "",
            f"- Target column: `{TARGET_COLUMN}`",
            f"- Non-null targets: {int(target.notna().sum())}",
            f"- Mean: {target.mean():.3f}",
            f"- Minimum: {target.min():.3f}",
            f"- Maximum: {target.max():.3f}",
            "",
            "## Leakage Notes",
            "",
            "- Rows are sorted chronologically before feature construction and splitting.",
            "- Lag and rolling features are grouped by `zone_id` and shifted by one row first.",
            "- `zone_hour_mean_demand` uses an expanding mean of prior matching zone-hour rows.",
            "- `target_next_observed_demand` is the next future observed demand for the same zone.",
            "- Chronological train/validation/test splits are created after target rows are filtered.",
            "",
        ],
    )


def _rolling_by_zone(
    *,
    values: pd.Series,
    zones: pd.Series,
    window: int,
    min_periods: int,
    aggregation: str,
) -> pd.Series:
    rolling = values.groupby(zones, sort=False).rolling(window=window, min_periods=min_periods)
    if aggregation == "mean":
        result = rolling.mean()
    elif aggregation == "std":
        result = rolling.std()
    else:
        raise ValueError(f"unsupported rolling aggregation: {aggregation}")
    return result.reset_index(level=0, drop=True)


def _validate_split_fractions(*, train_fraction: float, validation_fraction: float) -> None:
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("train_fraction and validation_fraction must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must be less than 1")


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _format_time_range(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "empty"
    return (
        f"{frame[AS_OF_TIMESTAMP_COLUMN].min().isoformat()} to "
        f"{frame[AS_OF_TIMESTAMP_COLUMN].max().isoformat()}"
    )


__all__ = [
    "OFFLINE_FEATURE_COLUMNS",
    "REQUIRED_OFFLINE_FEATURE_COLUMNS",
    "TARGET_COLUMN",
    "OfflineFeatureBuildResult",
    "build_and_save_offline_features",
    "build_offline_feature_summary",
    "build_offline_features",
    "normalize_synthetic_events",
    "read_synthetic_events",
    "split_chronologically",
]

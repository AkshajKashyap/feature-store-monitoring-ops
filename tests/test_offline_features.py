from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app
from feature_store_monitoring_ops.features.offline import (
    OFFLINE_FEATURE_COLUMNS,
    REQUIRED_OFFLINE_FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_offline_features,
    split_chronologically,
)
from feature_store_monitoring_ops.synthetic_events import (
    SyntheticEventConfig,
    generate_synthetic_events,
    write_synthetic_events_csv,
)


def test_offline_features_include_required_columns() -> None:
    features = build_offline_features(_sequential_events(row_count=72))

    assert set(REQUIRED_OFFLINE_FEATURE_COLUMNS).issubset(features.columns)
    assert set(OFFLINE_FEATURE_COLUMNS).issubset(features.columns)


def test_chronological_split_ordering() -> None:
    features = build_offline_features(_sequential_events(row_count=96))
    splits = split_chronologically(features, train_fraction=0.60, validation_fraction=0.20)

    assert len(splits["train"]) + len(splits["validation"]) + len(splits["test"]) == len(features)
    assert splits["train"]["timestamp"].max() <= splits["validation"]["timestamp"].min()
    assert splits["validation"]["timestamp"].max() <= splits["test"]["timestamp"].min()


def test_offline_features_have_no_missing_target_values() -> None:
    features = build_offline_features(_sequential_events(row_count=72))

    assert features[TARGET_COLUMN].notna().all()


def test_lag_features_are_shifted_from_past_zone_observations() -> None:
    features = build_offline_features(_sequential_events(row_count=32))
    first_feature_row = features.iloc[0]

    assert first_feature_row["event_id"] == "evt_000025"
    assert first_feature_row["lag_1_observed_demand"] == 23.0
    assert first_feature_row["lag_3_observed_demand"] == 21.0
    assert first_feature_row["rolling_mean_3"] == 22.0
    assert first_feature_row["rolling_mean_6"] == 20.5
    assert first_feature_row["zone_hour_mean_demand"] == 0.0
    assert first_feature_row[TARGET_COLUMN] == 25.0


def test_build_offline_features_cli_smoke(tmp_path) -> None:
    runner = CliRunner()
    input_path = tmp_path / "synthetic_events.csv"
    offline_path = tmp_path / "offline_features.parquet"
    train_path = tmp_path / "train_features.parquet"
    validation_path = tmp_path / "validation_features.parquet"
    test_path = tmp_path / "test_features.parquet"
    report_path = tmp_path / "offline_feature_summary.md"
    rows = generate_synthetic_events(
        SyntheticEventConfig(num_events=96, seed=123, zone_count=1, user_count=5),
    )
    write_synthetic_events_csv(rows, input_path)

    result = runner.invoke(
        app,
        [
            "build-offline-features",
            "--input-path",
            str(input_path),
            "--output-path",
            str(offline_path),
            "--train-path",
            str(train_path),
            "--validation-path",
            str(validation_path),
            "--test-path",
            str(test_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert offline_path.exists()
    assert train_path.exists()
    assert validation_path.exists()
    assert test_path.exists()
    assert report_path.exists()

    offline_features = pd.read_parquet(offline_path)
    train_features = pd.read_parquet(train_path)
    validation_features = pd.read_parquet(validation_path)
    test_features = pd.read_parquet(test_path)

    split_row_count = len(train_features) + len(validation_features) + len(test_features)
    assert split_row_count == len(offline_features)
    assert set(REQUIRED_OFFLINE_FEATURE_COLUMNS).issubset(offline_features.columns)
    assert "Leakage Notes" in report_path.read_text(encoding="utf-8")


def _sequential_events(row_count: int) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        timestamp = start + timedelta(hours=index)
        observed_demand = float(index)
        rows.append(
            {
                "event_id": f"evt_{index + 1:06d}",
                "timestamp": timestamp.isoformat(),
                "zone_id": "zone_01",
                "user_id": "user_0001",
                "demand_count": int(observed_demand),
                "hour": timestamp.hour,
                "day_of_week": timestamp.weekday(),
                "is_weekend": timestamp.weekday() >= 5,
                "base_demand": observed_demand,
                "observed_demand": observed_demand,
            },
        )
    return pd.DataFrame(rows)

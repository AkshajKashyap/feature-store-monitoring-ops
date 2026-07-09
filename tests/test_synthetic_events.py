from __future__ import annotations

import csv
from datetime import UTC, datetime

from typer.testing import CliRunner

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.cli import app
from feature_store_monitoring_ops.schema import (
    REQUIRED_SYNTHETIC_EVENT_COLUMNS,
    ensure_valid_synthetic_event_rows,
    parse_event_timestamp,
)
from feature_store_monitoring_ops.synthetic_events import (
    PORTFOLIO_SYNTHETIC_PRESET,
    SyntheticEventConfig,
    build_synthetic_event_config,
    generate_synthetic_events,
)


def test_synthetic_events_are_deterministic_with_fixed_seed() -> None:
    config = SyntheticEventConfig(
        num_events=24,
        seed=123,
        start_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert generate_synthetic_events(config) == generate_synthetic_events(config)


def test_synthetic_events_include_required_columns() -> None:
    rows = generate_synthetic_events(SyntheticEventConfig(num_events=5, seed=7))

    assert set(REQUIRED_SYNTHETIC_EVENT_COLUMNS).issubset(rows[0].keys())
    ensure_valid_synthetic_event_rows(rows)


def test_synthetic_event_timestamps_are_valid_and_temporal_columns_match() -> None:
    rows = generate_synthetic_events(SyntheticEventConfig(num_events=12, seed=11))

    for row in rows:
        timestamp = parse_event_timestamp(row["timestamp"])
        assert int(row["hour"]) == timestamp.hour
        assert int(row["day_of_week"]) == timestamp.weekday()
        assert bool(row["is_weekend"]) is (timestamp.weekday() >= 5)


def test_synthetic_event_demand_values_are_nonnegative() -> None:
    rows = generate_synthetic_events(SyntheticEventConfig(num_events=36, seed=13))

    for row in rows:
        assert int(row["demand_count"]) >= 0
        assert float(row["base_demand"]) >= 0
        assert float(row["observed_demand"]) >= 0


def test_generator_accepts_custom_scale_params() -> None:
    config = SyntheticEventConfig(
        seed=21,
        zone_count=4,
        user_count=25,
        num_days=3,
        events_per_zone_per_day=2,
    )

    rows = generate_synthetic_events(config)

    assert len(rows) == 24
    assert len({row["zone_id"] for row in rows}) == 4
    assert rows[0]["zone_id"] == "zone_01"
    assert rows[3]["zone_id"] == "zone_04"


def test_portfolio_preset_produces_more_zones_than_default() -> None:
    default_rows = generate_synthetic_events(build_synthetic_event_config())
    portfolio_rows = generate_synthetic_events(
        build_synthetic_event_config(preset=PORTFOLIO_SYNTHETIC_PRESET),
    )

    assert len({row["zone_id"] for row in default_rows}) == 5
    assert len({row["zone_id"] for row in portfolio_rows}) >= 50
    assert len(portfolio_rows) > len(default_rows)


def test_cli_smoke_generates_events_and_report(tmp_path) -> None:
    runner = CliRunner()
    csv_path = tmp_path / "synthetic_events.csv"
    report_path = tmp_path / "synthetic_events_summary.md"

    version_result = runner.invoke(app, ["--version"])
    assert version_result.exit_code == 0
    assert __version__ in version_result.output

    info_result = runner.invoke(app, ["project-info"])
    assert info_result.exit_code == 0
    assert "feature-store-monitoring-ops" in info_result.output

    generate_result = runner.invoke(
        app,
        [
            "generate-synthetic-events",
            "--events",
            "8",
            "--seed",
            "99",
            "--output-path",
            str(csv_path),
            "--report-path",
            str(report_path),
        ],
    )
    assert generate_result.exit_code == 0
    assert csv_path.exists()
    assert report_path.exists()

    with csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 8
    ensure_valid_synthetic_event_rows(rows)
    assert "Rows: 8" in report_path.read_text(encoding="utf-8")


def test_cli_generates_portfolio_preset(tmp_path) -> None:
    runner = CliRunner()
    csv_path = tmp_path / "synthetic_events.csv"
    report_path = tmp_path / "synthetic_events_summary.md"

    result = runner.invoke(
        app,
        [
            "generate-synthetic-events",
            "--preset",
            "portfolio",
            "--output-path",
            str(csv_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    with csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 3000
    assert len({row["zone_id"] for row in rows}) == 50

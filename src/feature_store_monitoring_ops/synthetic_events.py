"""Deterministic synthetic temporal demand event generation."""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from feature_store_monitoring_ops.paths import (
    DEFAULT_SYNTHETIC_EVENTS_PATH,
    DEFAULT_SYNTHETIC_REPORT_PATH,
)
from feature_store_monitoring_ops.schema import (
    REQUIRED_SYNTHETIC_EVENT_COLUMNS,
    ensure_valid_synthetic_event_rows,
    parse_event_timestamp,
)

DEFAULT_START_TIMESTAMP = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
DEFAULT_SYNTHETIC_PRESET = "default"
PORTFOLIO_SYNTHETIC_PRESET = "portfolio"
SYNTHETIC_PRESETS: tuple[str, ...] = (DEFAULT_SYNTHETIC_PRESET, PORTFOLIO_SYNTHETIC_PRESET)


@dataclass(frozen=True)
class SyntheticEventConfig:
    """Configuration for deterministic synthetic temporal demand events."""

    num_events: int = 720
    seed: int = 42
    start_timestamp: datetime = field(default_factory=lambda: DEFAULT_START_TIMESTAMP)
    interval_minutes: int = 60
    zone_count: int = 5
    user_count: int = 200
    num_days: int | None = None
    events_per_zone_per_day: int | None = None

    def validate(self) -> None:
        """Validate config values before event generation."""

        if self.num_events <= 0:
            raise ValueError("num_events must be greater than zero")
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be greater than zero")
        if self.zone_count <= 0:
            raise ValueError("zone_count must be greater than zero")
        if self.user_count <= 0:
            raise ValueError("user_count must be greater than zero")
        if (self.num_days is None) != (self.events_per_zone_per_day is None):
            raise ValueError("num_days and events_per_zone_per_day must be provided together")
        if self.num_days is not None and self.num_days <= 0:
            raise ValueError("num_days must be greater than zero")
        if self.events_per_zone_per_day is not None and self.events_per_zone_per_day <= 0:
            raise ValueError("events_per_zone_per_day must be greater than zero")
        if self.events_per_zone_per_day is not None and self.events_per_zone_per_day > 1440:
            raise ValueError("events_per_zone_per_day must be less than or equal to 1440")

    @property
    def uses_zone_day_grid(self) -> bool:
        """Return whether generation should cover every zone for every configured day."""

        return self.num_days is not None and self.events_per_zone_per_day is not None

    @property
    def expected_rows(self) -> int:
        """Return the deterministic row count implied by this config."""

        if self.uses_zone_day_grid:
            assert self.num_days is not None
            assert self.events_per_zone_per_day is not None
            return self.zone_count * self.num_days * self.events_per_zone_per_day
        return self.num_events


@dataclass(frozen=True)
class SyntheticGenerationResult:
    """Output paths and row count from generating synthetic events."""

    csv_path: Path
    report_path: Path
    rows_written: int


def generate_synthetic_events(
    config: SyntheticEventConfig | None = None,
) -> list[dict[str, object]]:
    """Generate deterministic temporal demand events for local development."""

    active_config = config or SyntheticEventConfig()
    active_config.validate()
    rng = random.Random(active_config.seed)

    rows: list[dict[str, object]] = []
    for event_index, timestamp, zone_number in _event_schedule(active_config):
        rows.append(
            _build_event_row(
                config=active_config,
                rng=rng,
                event_index=event_index,
                timestamp=timestamp,
                zone_number=zone_number,
            ),
        )

    ensure_valid_synthetic_event_rows(rows)
    return rows


def build_synthetic_event_config(
    *,
    preset: str = DEFAULT_SYNTHETIC_PRESET,
    num_events: int | None = None,
    seed: int | None = None,
    start_timestamp: datetime | None = None,
    interval_minutes: int | None = None,
    zone_count: int | None = None,
    user_count: int | None = None,
    num_days: int | None = None,
    events_per_zone_per_day: int | None = None,
) -> SyntheticEventConfig:
    """Build a synthetic event config from a named preset and optional overrides."""

    preset_config = _synthetic_config_for_preset(preset)
    config = SyntheticEventConfig(
        num_events=num_events if num_events is not None else preset_config.num_events,
        seed=seed if seed is not None else preset_config.seed,
        start_timestamp=start_timestamp or preset_config.start_timestamp,
        interval_minutes=(
            interval_minutes if interval_minutes is not None else preset_config.interval_minutes
        ),
        zone_count=zone_count if zone_count is not None else preset_config.zone_count,
        user_count=user_count if user_count is not None else preset_config.user_count,
        num_days=num_days if num_days is not None else preset_config.num_days,
        events_per_zone_per_day=(
            events_per_zone_per_day
            if events_per_zone_per_day is not None
            else preset_config.events_per_zone_per_day
        ),
    )
    config.validate()
    return config


def generate_and_save_synthetic_events(
    config: SyntheticEventConfig | None = None,
    *,
    output_path: Path = DEFAULT_SYNTHETIC_EVENTS_PATH,
    report_path: Path = DEFAULT_SYNTHETIC_REPORT_PATH,
) -> SyntheticGenerationResult:
    """Generate synthetic events and write the CSV plus Markdown summary."""

    rows = generate_synthetic_events(config=config)
    write_synthetic_events_csv(rows=rows, output_path=output_path)
    write_synthetic_events_summary(rows=rows, report_path=report_path)
    return SyntheticGenerationResult(
        csv_path=output_path,
        report_path=report_path,
        rows_written=len(rows),
    )


def write_synthetic_events_csv(
    rows: Sequence[Mapping[str, object]],
    output_path: Path,
) -> None:
    """Write validated synthetic event rows to CSV."""

    ensure_valid_synthetic_event_rows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REQUIRED_SYNTHETIC_EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_synthetic_events_summary(
    rows: Sequence[Mapping[str, object]],
    report_path: Path,
) -> None:
    """Write a small Markdown summary for generated synthetic events."""

    ensure_valid_synthetic_event_rows(rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_synthetic_events_summary(rows), encoding="utf-8")


def build_synthetic_events_summary(rows: Sequence[Mapping[str, object]]) -> str:
    """Build a compact Markdown report for generated synthetic events."""

    ensure_valid_synthetic_event_rows(rows)
    timestamps = [parse_event_timestamp(row["timestamp"]) for row in rows]
    zones = sorted({str(row["zone_id"]) for row in rows})
    users = sorted({str(row["user_id"]) for row in rows})
    total_demand = sum(int(row["demand_count"]) for row in rows)
    average_demand = total_demand / len(rows)
    average_observed_demand = sum(float(row["observed_demand"]) for row in rows) / len(rows)

    return "\n".join(
        [
            "# Synthetic Events Summary",
            "",
            "Generated deterministic temporal demand events for Milestone 1.",
            "",
            f"- Rows: {len(rows)}",
            f"- Timestamp range: {min(timestamps).isoformat()} to {max(timestamps).isoformat()}",
            f"- Zones: {len(zones)} ({', '.join(zones)})",
            f"- Unique users sampled: {len(users)}",
            f"- Total demand_count: {total_demand}",
            f"- Average demand_count: {average_demand:.2f}",
            f"- Average observed_demand: {average_observed_demand:.2f}",
            "",
        ],
    )


def parse_start_timestamp(value: str) -> datetime:
    """Parse a CLI timestamp and attach UTC when no timezone is supplied."""

    timestamp = parse_event_timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def _synthetic_config_for_preset(preset: str) -> SyntheticEventConfig:
    if preset == DEFAULT_SYNTHETIC_PRESET:
        return SyntheticEventConfig()
    if preset == PORTFOLIO_SYNTHETIC_PRESET:
        return SyntheticEventConfig(
            seed=42,
            zone_count=50,
            user_count=5000,
            num_days=30,
            events_per_zone_per_day=2,
        )
    raise ValueError(f"unknown synthetic event preset: {preset}")


def _event_schedule(
    config: SyntheticEventConfig,
) -> list[tuple[int, datetime, int]]:
    if not config.uses_zone_day_grid:
        return [
            (
                event_index,
                config.start_timestamp + timedelta(minutes=config.interval_minutes * event_index),
                0,
            )
            for event_index in range(config.num_events)
        ]

    assert config.num_days is not None
    assert config.events_per_zone_per_day is not None
    slot_minutes = max(1, (24 * 60) // config.events_per_zone_per_day)
    schedule: list[tuple[int, datetime, int]] = []
    event_index = 0
    for day_index in range(config.num_days):
        for slot_index in range(config.events_per_zone_per_day):
            timestamp = config.start_timestamp + timedelta(
                days=day_index,
                minutes=slot_minutes * slot_index,
            )
            for zone_number in range(1, config.zone_count + 1):
                schedule.append((event_index, timestamp, zone_number))
                event_index += 1
    return schedule


def _build_event_row(
    *,
    config: SyntheticEventConfig,
    rng: random.Random,
    event_index: int,
    timestamp: datetime,
    zone_number: int,
) -> dict[str, object]:
    hour = timestamp.hour
    day_of_week = timestamp.weekday()
    is_weekend = day_of_week >= 5
    if zone_number <= 0:
        zone_number = rng.randint(1, config.zone_count)
    user_number = rng.randint(1, config.user_count)

    base_demand = _base_temporal_demand(
        event_index=event_index,
        total_events=config.expected_rows,
        hour=hour,
        day_of_week=day_of_week,
        zone_number=zone_number,
    )
    observed_demand = max(0.0, base_demand + rng.gauss(0.0, max(1.0, base_demand * 0.08)))
    demand_count = max(0, int(round(observed_demand)))

    return {
        "event_id": f"evt_{event_index + 1:06d}",
        "timestamp": timestamp.isoformat(),
        "zone_id": f"zone_{zone_number:02d}",
        "user_id": f"user_{user_number:04d}",
        "demand_count": demand_count,
        "hour": hour,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "base_demand": round(base_demand, 3),
        "observed_demand": round(observed_demand, 3),
    }


def _base_temporal_demand(
    *,
    event_index: int,
    total_events: int,
    hour: int,
    day_of_week: int,
    zone_number: int,
) -> float:
    morning_peak = math.exp(-((hour - 8) ** 2) / 18)
    evening_peak = math.exp(-((hour - 17) ** 2) / 14)
    daily_wave = 0.8 * math.sin((2 * math.pi * hour) / 24)
    weekend_multiplier = 0.78 if day_of_week >= 5 else 1.0
    weekday_multiplier = 1.1 if day_of_week in {1, 2, 3} else 1.0
    zone_multiplier = 0.85 + (zone_number * 0.08)
    trend_multiplier = 1.0 + (event_index / max(total_events - 1, 1)) * 0.1

    demand = (
        10.0
        + (18.0 * morning_peak)
        + (24.0 * evening_peak)
        + daily_wave
        + (day_of_week * 0.7)
    )
    return max(0.0, demand * weekend_multiplier * weekday_multiplier * zone_multiplier * trend_multiplier)


__all__ = [
    "DEFAULT_START_TIMESTAMP",
    "DEFAULT_SYNTHETIC_PRESET",
    "PORTFOLIO_SYNTHETIC_PRESET",
    "SYNTHETIC_PRESETS",
    "SyntheticEventConfig",
    "SyntheticGenerationResult",
    "build_synthetic_event_config",
    "build_synthetic_events_summary",
    "generate_and_save_synthetic_events",
    "generate_synthetic_events",
    "parse_start_timestamp",
    "write_synthetic_events_csv",
    "write_synthetic_events_summary",
]

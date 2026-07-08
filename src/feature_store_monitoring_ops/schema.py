"""Schema checks for synthetic temporal demand events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

REQUIRED_SYNTHETIC_EVENT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "timestamp",
    "zone_id",
    "user_id",
    "demand_count",
    "hour",
    "day_of_week",
    "is_weekend",
    "base_demand",
    "observed_demand",
)


class SchemaValidationError(ValueError):
    """Raised when generated synthetic events do not match the expected schema."""


@dataclass(frozen=True)
class SchemaValidationResult:
    """Result from validating a batch of synthetic event rows."""

    row_count: int
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return True when validation found no schema errors."""

        return not self.errors


def parse_event_timestamp(value: object) -> datetime:
    """Parse an event timestamp from a datetime or ISO-8601 string."""

    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    msg = f"expected ISO-8601 timestamp, got {type(value).__name__}"
    raise ValueError(msg)


def validate_synthetic_event_rows(
    rows: Sequence[Mapping[str, object]],
) -> SchemaValidationResult:
    """Validate required columns and basic value constraints for synthetic events."""

    errors: list[str] = []
    if not rows:
        errors.append("at least one synthetic event row is required")
        return SchemaValidationResult(row_count=0, errors=tuple(errors))

    required = set(REQUIRED_SYNTHETIC_EVENT_COLUMNS)
    for index, row in enumerate(rows, start=1):
        missing = sorted(required.difference(row.keys()))
        if missing:
            errors.append(f"row {index}: missing required columns: {', '.join(missing)}")
            continue

        _validate_row_values(row=row, row_number=index, errors=errors)

    return SchemaValidationResult(row_count=len(rows), errors=tuple(errors))


def ensure_valid_synthetic_event_rows(rows: Sequence[Mapping[str, object]]) -> None:
    """Raise SchemaValidationError when synthetic event rows fail validation."""

    result = validate_synthetic_event_rows(rows)
    if not result.is_valid:
        raise SchemaValidationError("; ".join(result.errors))


def _validate_row_values(
    row: Mapping[str, object],
    row_number: int,
    errors: list[str],
) -> None:
    try:
        timestamp = parse_event_timestamp(row["timestamp"])
    except ValueError as exc:
        errors.append(f"row {row_number}: invalid timestamp: {exc}")
        return

    event_id = str(row["event_id"]).strip()
    zone_id = str(row["zone_id"]).strip()
    user_id = str(row["user_id"]).strip()
    if not event_id:
        errors.append(f"row {row_number}: event_id must be non-empty")
    if not zone_id:
        errors.append(f"row {row_number}: zone_id must be non-empty")
    if not user_id:
        errors.append(f"row {row_number}: user_id must be non-empty")

    hour = _parse_int(row["hour"], column="hour", row_number=row_number, errors=errors)
    day_of_week = _parse_int(
        row["day_of_week"],
        column="day_of_week",
        row_number=row_number,
        errors=errors,
    )
    is_weekend = _parse_bool(
        row["is_weekend"],
        column="is_weekend",
        row_number=row_number,
        errors=errors,
    )

    if hour is not None and hour != timestamp.hour:
        errors.append(f"row {row_number}: hour does not match timestamp")
    if day_of_week is not None and day_of_week != timestamp.weekday():
        errors.append(f"row {row_number}: day_of_week does not match timestamp")
    if is_weekend is not None and is_weekend != (timestamp.weekday() >= 5):
        errors.append(f"row {row_number}: is_weekend does not match timestamp")

    demand_count = _parse_int(
        row["demand_count"],
        column="demand_count",
        row_number=row_number,
        errors=errors,
    )
    if demand_count is not None and demand_count < 0:
        errors.append(f"row {row_number}: demand_count must be nonnegative")

    for column in ("base_demand", "observed_demand"):
        value = _parse_float(row[column], column=column, row_number=row_number, errors=errors)
        if value is not None and value < 0:
            errors.append(f"row {row_number}: {column} must be nonnegative")


def _parse_int(
    value: object,
    *,
    column: str,
    row_number: int,
    errors: list[str],
) -> int | None:
    if isinstance(value, bool):
        errors.append(f"row {row_number}: {column} must be an integer")
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"row {row_number}: {column} must be an integer")
        return None
    return parsed


def _parse_float(
    value: object,
    *,
    column: str,
    row_number: int,
    errors: list[str],
) -> float | None:
    if isinstance(value, bool):
        errors.append(f"row {row_number}: {column} must be numeric")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"row {row_number}: {column} must be numeric")
        return None


def _parse_bool(
    value: object,
    *,
    column: str,
    row_number: int,
    errors: list[str],
) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    errors.append(f"row {row_number}: {column} must be boolean")
    return None


__all__ = [
    "REQUIRED_SYNTHETIC_EVENT_COLUMNS",
    "SchemaValidationError",
    "SchemaValidationResult",
    "ensure_valid_synthetic_event_rows",
    "parse_event_timestamp",
    "validate_synthetic_event_rows",
]

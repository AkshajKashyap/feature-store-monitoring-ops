"""Persistent JSONL telemetry for local prediction requests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from feature_store_monitoring_ops.paths import DEFAULT_PREDICTION_LOG_PATH


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=UTC)


@dataclass
class IncrementingClock:
    """Deterministic clock that advances by a fixed interval on every call."""

    current: datetime
    step: timedelta = timedelta(seconds=1)

    def __call__(self) -> datetime:
        timestamp = self.current
        self.current = self.current + self.step
        return timestamp


@dataclass
class PredictionTelemetryLogger:
    """Append prediction request telemetry rows to a local JSONL file."""

    log_path: Path = DEFAULT_PREDICTION_LOG_PATH
    now_fn: Callable[[], datetime] = utc_now
    request_counter: int = 0
    rows_written: int = 0

    def next_request_id(self) -> str:
        """Return a deterministic request ID for this logger instance."""

        self.request_counter += 1
        return f"req_{self.request_counter:06d}"

    def log_success(
        self,
        *,
        request_id: str,
        zone_id: str,
        as_of_timestamp: str,
        prediction: float,
        model_name: str | None,
        model_version: str,
        latency_ms: float,
    ) -> dict[str, Any]:
        """Write a successful prediction telemetry row."""

        timestamp = self.now_fn()
        row = _base_row(
            request_id=request_id,
            timestamp=timestamp,
            zone_id=zone_id,
            as_of_timestamp=as_of_timestamp,
            prediction=prediction,
            model_name=model_name,
            model_version=model_version,
            latency_ms=latency_ms,
            status="success",
            error_type=None,
        )
        row["feature_freshness_seconds"] = _feature_freshness_seconds(timestamp, as_of_timestamp)
        self.write_row(row)
        return row

    def log_error(
        self,
        *,
        request_id: str,
        zone_id: str,
        model_name: str | None,
        model_version: str,
        latency_ms: float,
        error_type: str,
        as_of_timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Write a failed prediction telemetry row."""

        timestamp = self.now_fn()
        row = _base_row(
            request_id=request_id,
            timestamp=timestamp,
            zone_id=zone_id,
            as_of_timestamp=as_of_timestamp,
            prediction=None,
            model_name=model_name,
            model_version=model_version,
            latency_ms=latency_ms,
            status="error",
            error_type=error_type,
        )
        row["feature_freshness_seconds"] = None
        if as_of_timestamp is not None:
            row["feature_freshness_seconds"] = _feature_freshness_seconds(timestamp, as_of_timestamp)
        self.write_row(row)
        return row

    def write_row(self, row: dict[str, Any]) -> None:
        """Append one telemetry row to JSONL."""

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, sort_keys=True) + "\n")
        self.rows_written += 1


@dataclass
class TelemetrySimulationResult:
    """Result from deterministic in-process traffic simulation."""

    log_path: Path
    total_requests: int
    successful_requests: int
    failed_requests: int
    zones_requested: list[str] = field(default_factory=list)


def read_prediction_logs(path: Path = DEFAULT_PREDICTION_LOG_PATH) -> list[dict[str, Any]]:
    """Read prediction telemetry JSONL rows."""

    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def reset_prediction_log(path: Path = DEFAULT_PREDICTION_LOG_PATH) -> None:
    """Remove the prediction log if it exists."""

    if path.exists():
        path.unlink()


def _base_row(
    *,
    request_id: str,
    timestamp: datetime,
    zone_id: str,
    as_of_timestamp: str | None,
    prediction: float | None,
    model_name: str | None,
    model_version: str,
    latency_ms: float,
    status: str,
    error_type: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "timestamp": timestamp.isoformat(),
        "zone_id": zone_id,
        "as_of_timestamp": as_of_timestamp,
        "prediction": prediction,
        "model_name": model_name,
        "model_version": model_version,
        "feature_freshness_seconds": None,
        "latency_ms": round(float(latency_ms), 6),
        "status": status,
        "error_type": error_type,
    }


def _feature_freshness_seconds(timestamp: datetime, as_of_timestamp: str) -> float:
    as_of = datetime.fromisoformat(as_of_timestamp.replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    return round((timestamp - as_of).total_seconds(), 6)


__all__ = [
    "IncrementingClock",
    "PredictionTelemetryLogger",
    "TelemetrySimulationResult",
    "read_prediction_logs",
    "reset_prediction_log",
    "utc_now",
]

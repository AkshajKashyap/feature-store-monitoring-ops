"""Prediction telemetry storage protocol and local implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Column, Float, MetaData, String, Table, create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from feature_store_monitoring_ops.paths import (
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_SQLITE_TELEMETRY_DB_PATH,
)

PREDICTION_TELEMETRY_COLUMNS: tuple[str, ...] = (
    "request_id",
    "timestamp",
    "zone_id",
    "as_of_timestamp",
    "prediction",
    "model_name",
    "model_version",
    "feature_freshness_seconds",
    "latency_ms",
    "status",
    "error_type",
)


class PredictionTelemetryStore(Protocol):
    """Minimal prediction telemetry store interface."""

    def append(self, row: dict[str, Any]) -> None:
        """Append or upsert one prediction telemetry row."""

    def append_many(self, rows: list[dict[str, Any]]) -> None:
        """Append or upsert many prediction telemetry rows."""

    def all_rows(self) -> list[dict[str, Any]]:
        """Return all stored telemetry rows."""

    def count(self) -> int:
        """Return stored row count."""

    def timestamp_bounds(self) -> tuple[str | None, str | None]:
        """Return minimum and maximum telemetry timestamps."""


@dataclass
class JsonlPredictionTelemetryStore:
    """JSONL-backed prediction telemetry store."""

    log_path: Path = DEFAULT_PREDICTION_LOG_PATH

    def append(self, row: dict[str, Any]) -> None:
        _validate_telemetry_row(row)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(_normalized_row(row), sort_keys=True) + "\n")

    def append_many(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.append(row)

    def all_rows(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                _validate_telemetry_row(row)
                rows.append(row)
        return rows

    def count(self) -> int:
        return len(self.all_rows())

    def timestamp_bounds(self) -> tuple[str | None, str | None]:
        timestamps = sorted(
            str(row["timestamp"])
            for row in self.all_rows()
            if row.get("timestamp") is not None
        )
        if not timestamps:
            return None, None
        return timestamps[0], timestamps[-1]


@dataclass
class SQLitePredictionTelemetryStore:
    """SQLite-backed prediction telemetry store implemented with SQLAlchemy."""

    db_path: Path = DEFAULT_SQLITE_TELEMETRY_DB_PATH
    engine: Engine | None = None
    metadata: MetaData = field(default_factory=MetaData, init=False)
    table: Table = field(init=False)

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        active_engine = self.engine or create_engine(
            f"sqlite:///{self.db_path}",
            future=True,
            poolclass=NullPool,
        )
        self.engine = active_engine
        self.table = Table(
            "prediction_telemetry",
            self.metadata,
            Column("request_id", String, primary_key=True),
            Column("timestamp", String, nullable=False),
            Column("zone_id", String, nullable=False),
            Column("as_of_timestamp", String, nullable=True),
            Column("prediction", Float, nullable=True),
            Column("model_name", String, nullable=True),
            Column("model_version", String, nullable=True),
            Column("feature_freshness_seconds", Float, nullable=True),
            Column("latency_ms", Float, nullable=True),
            Column("status", String, nullable=False),
            Column("error_type", String, nullable=True),
        )
        self.metadata.create_all(active_engine)

    def append(self, row: dict[str, Any]) -> None:
        self.append_many([row])

    def append_many(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        normalized_rows = [_normalized_row(row) for row in rows]
        for row in normalized_rows:
            _validate_telemetry_row(row)
        assert self.engine is not None
        with self.engine.begin() as connection:
            for row in normalized_rows:
                statement = sqlite_insert(self.table).values(row)
                statement = statement.on_conflict_do_update(
                    index_elements=["request_id"],
                    set_={column: statement.excluded[column] for column in PREDICTION_TELEMETRY_COLUMNS},
                )
                connection.execute(statement)

    def all_rows(self) -> list[dict[str, Any]]:
        assert self.engine is not None
        statement = select(self.table).order_by(self.table.c.timestamp, self.table.c.request_id)
        with self.engine.begin() as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]

    def count(self) -> int:
        assert self.engine is not None
        statement = select(func.count()).select_from(self.table)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())

    def timestamp_bounds(self) -> tuple[str | None, str | None]:
        assert self.engine is not None
        statement = select(func.min(self.table.c.timestamp), func.max(self.table.c.timestamp))
        with self.engine.begin() as connection:
            minimum, maximum = connection.execute(statement).one()
        return minimum, maximum


def _validate_telemetry_row(row: dict[str, Any]) -> None:
    missing = sorted(set(PREDICTION_TELEMETRY_COLUMNS).difference(row))
    if missing:
        raise ValueError(f"telemetry row missing columns: {', '.join(missing)}")
    if row["request_id"] is None:
        raise ValueError("telemetry row missing request_id")
    if row["timestamp"] is None:
        raise ValueError("telemetry row missing timestamp")
    if row["zone_id"] is None:
        raise ValueError("telemetry row missing zone_id")
    if row["status"] is None:
        raise ValueError("telemetry row missing status")


def _normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column) for column in PREDICTION_TELEMETRY_COLUMNS}


__all__ = [
    "JsonlPredictionTelemetryStore",
    "PREDICTION_TELEMETRY_COLUMNS",
    "PredictionTelemetryStore",
    "SQLitePredictionTelemetryStore",
]

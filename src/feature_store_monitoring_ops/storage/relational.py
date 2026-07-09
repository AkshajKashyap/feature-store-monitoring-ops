"""Relational event and feature storage backed by SQLAlchemy."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, create_engine
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    REQUIRED_OFFLINE_FEATURE_COLUMNS,
    TARGET_COLUMN,
    get_online_feature_columns,
)
from feature_store_monitoring_ops.features.offline import read_synthetic_events
from feature_store_monitoring_ops.paths import (
    DEFAULT_OFFLINE_FEATURES_PATH,
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH,
    DEFAULT_RELATIONAL_STORAGE_SYNC_REPORT_PATH,
    DEFAULT_SYNTHETIC_EVENTS_PATH,
)
from feature_store_monitoring_ops.storage.config import (
    DEFAULT_RELATIONAL_DATABASE_URL,
    StorageConfig,
)
from feature_store_monitoring_ops.storage.online import JsonBackedOnlineFeatureStore

EVENT_TABLE_COLUMNS: tuple[str, ...] = (
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

OFFLINE_FEATURE_TABLE_COLUMNS: tuple[str, ...] = REQUIRED_OFFLINE_FEATURE_COLUMNS

ONLINE_SNAPSHOT_TABLE_COLUMNS: tuple[str, ...] = (
    "snapshot_id",
    "created_at",
    "source_path",
    "row_count",
    "zone_count",
    "min_as_of_timestamp",
    "max_as_of_timestamp",
    "feature_columns_json",
    "zone_ids_json",
)

STORAGE_RUN_TABLE_COLUMNS: tuple[str, ...] = (
    "run_id",
    "run_type",
    "created_at",
    "database_backend",
    "events_path",
    "offline_features_path",
    "online_snapshot_path",
    "event_row_count",
    "offline_feature_row_count",
    "online_snapshot_row_count",
    "zone_count",
)


@dataclass(frozen=True)
class RelationalStorageSyncResult:
    """Result from syncing generated artifacts into relational storage."""

    report_path: Path
    database_url: str
    database_backend: str
    event_row_count: int
    offline_feature_row_count: int
    online_snapshot_row_count: int
    zone_count: int
    min_event_timestamp: str | None
    max_event_timestamp: str | None


@dataclass(frozen=True)
class RelationalStorageInspectionResult:
    """Result from inspecting relational event and feature storage."""

    report_path: Path
    database_url: str
    database_backend: str
    event_row_count: int
    offline_feature_row_count: int
    online_snapshot_row_count: int
    zone_count: int
    min_event_timestamp: str | None
    max_event_timestamp: str | None


@dataclass
class RelationalFeatureStore:
    """SQLAlchemy-backed store for raw events, offline features, and snapshot metadata."""

    database_url: str = DEFAULT_RELATIONAL_DATABASE_URL
    engine: Engine | None = None
    metadata: MetaData = field(default_factory=MetaData, init=False)
    events_table: Table = field(init=False)
    offline_features_table: Table = field(init=False)
    online_snapshots_table: Table = field(init=False)
    storage_run_metadata_table: Table = field(init=False)

    def __post_init__(self) -> None:
        _ensure_sqlite_parent(self.database_url)
        self.engine = self.engine or _create_engine(self.database_url)
        self.events_table = Table(
            "events",
            self.metadata,
            Column("event_id", String, primary_key=True),
            Column("timestamp", String, nullable=False),
            Column("zone_id", String, nullable=False, index=True),
            Column("user_id", String, nullable=False),
            Column("demand_count", Integer, nullable=False),
            Column("hour", Integer, nullable=False),
            Column("day_of_week", Integer, nullable=False),
            Column("is_weekend", Boolean, nullable=False),
            Column("base_demand", Float, nullable=False),
            Column("observed_demand", Float, nullable=False),
        )
        self.offline_features_table = Table(
            "offline_features",
            self.metadata,
            Column("event_id", String, primary_key=True),
            Column("timestamp", String, nullable=False),
            Column("zone_id", String, nullable=False, index=True),
            Column("hour", Integer, nullable=False),
            Column("day_of_week", Integer, nullable=False),
            Column("is_weekend", Boolean, nullable=False),
            Column("lag_1_observed_demand", Float, nullable=False),
            Column("lag_3_observed_demand", Float, nullable=False),
            Column("rolling_mean_3", Float, nullable=False),
            Column("rolling_mean_6", Float, nullable=False),
            Column("rolling_std_6", Float, nullable=False),
            Column("zone_hour_mean_demand", Float, nullable=False),
            Column(TARGET_COLUMN, Float, nullable=False),
        )
        self.online_snapshots_table = Table(
            "online_feature_snapshots",
            self.metadata,
            Column("snapshot_id", String, primary_key=True),
            Column("created_at", String, nullable=False),
            Column("source_path", String, nullable=False),
            Column("row_count", Integer, nullable=False),
            Column("zone_count", Integer, nullable=False),
            Column("min_as_of_timestamp", String, nullable=True),
            Column("max_as_of_timestamp", String, nullable=True),
            Column("feature_columns_json", String, nullable=False),
            Column("zone_ids_json", String, nullable=False),
        )
        self.storage_run_metadata_table = Table(
            "storage_run_metadata",
            self.metadata,
            Column("run_id", String, primary_key=True),
            Column("run_type", String, nullable=False),
            Column("created_at", String, nullable=False),
            Column("database_backend", String, nullable=False),
            Column("events_path", String, nullable=False),
            Column("offline_features_path", String, nullable=False),
            Column("online_snapshot_path", String, nullable=False),
            Column("event_row_count", Integer, nullable=False),
            Column("offline_feature_row_count", Integer, nullable=False),
            Column("online_snapshot_row_count", Integer, nullable=False),
            Column("zone_count", Integer, nullable=False),
        )

    @property
    def database_backend(self) -> str:
        """Return the SQLAlchemy backend name parsed from the database URL."""

        return relational_backend_from_url(self.database_url)

    def create_schema(self) -> None:
        """Create relational tables if they do not already exist."""

        assert self.engine is not None
        self.metadata.create_all(self.engine)

    def replace_all(
        self,
        *,
        event_rows: list[dict[str, Any]],
        offline_feature_rows: list[dict[str, Any]],
        online_snapshot_metadata: dict[str, Any],
        storage_run_metadata: dict[str, Any],
    ) -> None:
        """Replace all relational demo tables with one deterministic artifact sync."""

        self.create_schema()
        assert self.engine is not None
        with self.engine.begin() as connection:
            for table in (
                self.storage_run_metadata_table,
                self.online_snapshots_table,
                self.offline_features_table,
                self.events_table,
            ):
                connection.execute(delete(table))
            if event_rows:
                connection.execute(insert(self.events_table), event_rows)
            if offline_feature_rows:
                connection.execute(insert(self.offline_features_table), offline_feature_rows)
            connection.execute(insert(self.online_snapshots_table), online_snapshot_metadata)
            connection.execute(insert(self.storage_run_metadata_table), storage_run_metadata)

    def inspect(self) -> RelationalStorageInspectionResult:
        """Inspect current relational row counts and event timestamp bounds."""

        self.create_schema()
        assert self.engine is not None
        with self.engine.begin() as connection:
            event_count = int(
                connection.execute(select(func.count()).select_from(self.events_table)).scalar_one(),
            )
            offline_count = int(
                connection.execute(
                    select(func.count()).select_from(self.offline_features_table),
                ).scalar_one(),
            )
            snapshot_row_count = connection.execute(
                select(self.online_snapshots_table.c.row_count).where(
                    self.online_snapshots_table.c.snapshot_id == "latest",
                ),
            ).scalar_one_or_none()
            zone_count = int(
                connection.execute(select(func.count(func.distinct(self.events_table.c.zone_id)))).scalar_one(),
            )
            min_timestamp, max_timestamp = connection.execute(
                select(func.min(self.events_table.c.timestamp), func.max(self.events_table.c.timestamp)),
            ).one()
        return RelationalStorageInspectionResult(
            report_path=DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH,
            database_url=safe_database_url(self.database_url),
            database_backend=self.database_backend,
            event_row_count=event_count,
            offline_feature_row_count=offline_count,
            online_snapshot_row_count=int(snapshot_row_count or 0),
            zone_count=zone_count,
            min_event_timestamp=min_timestamp,
            max_event_timestamp=max_timestamp,
        )

    def table_names(self) -> set[str]:
        """Return declared relational table names."""

        return set(self.metadata.tables)


def sync_relational_store(
    *,
    database_url: str | None = None,
    events_path: Path = DEFAULT_SYNTHETIC_EVENTS_PATH,
    offline_features_path: Path = DEFAULT_OFFLINE_FEATURES_PATH,
    online_snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    report_path: Path = DEFAULT_RELATIONAL_STORAGE_SYNC_REPORT_PATH,
) -> RelationalStorageSyncResult:
    """Sync local generated artifacts into relational storage."""

    active_database_url = database_url or StorageConfig.from_env().relational_url
    events = _read_event_rows(events_path)
    offline_features = _read_offline_feature_rows(offline_features_path)
    online_rows = _read_online_rows(online_snapshot_path)
    snapshot_metadata = _build_online_snapshot_metadata(
        online_rows=online_rows,
        source_path=online_snapshot_path,
        created_at=_deterministic_sync_timestamp(events),
    )
    run_metadata = _build_storage_run_metadata(
        database_backend=relational_backend_from_url(active_database_url),
        events_path=events_path,
        offline_features_path=offline_features_path,
        online_snapshot_path=online_snapshot_path,
        event_row_count=len(events),
        offline_feature_row_count=len(offline_features),
        online_snapshot_row_count=len(online_rows),
        zone_count=len({str(row["zone_id"]) for row in events}),
        created_at=str(snapshot_metadata["created_at"]),
    )
    store = RelationalFeatureStore(database_url=active_database_url)
    store.replace_all(
        event_rows=events,
        offline_feature_rows=offline_features,
        online_snapshot_metadata=snapshot_metadata,
        storage_run_metadata=run_metadata,
    )
    min_timestamp, max_timestamp = _timestamp_bounds(events, "timestamp")
    result = RelationalStorageSyncResult(
        report_path=report_path,
        database_url=safe_database_url(active_database_url),
        database_backend=store.database_backend,
        event_row_count=len(events),
        offline_feature_row_count=len(offline_features),
        online_snapshot_row_count=len(online_rows),
        zone_count=len({str(row["zone_id"]) for row in events}),
        min_event_timestamp=min_timestamp,
        max_event_timestamp=max_timestamp,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_relational_storage_sync_report(result), encoding="utf-8")
    return result


def inspect_relational_store(
    *,
    database_url: str | None = None,
    report_path: Path = DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH,
) -> RelationalStorageInspectionResult:
    """Inspect relational storage and write a tracked Markdown report."""

    active_database_url = database_url or StorageConfig.from_env().relational_url
    store = RelationalFeatureStore(database_url=active_database_url)
    inspected = store.inspect()
    result = RelationalStorageInspectionResult(
        report_path=report_path,
        database_url=inspected.database_url,
        database_backend=inspected.database_backend,
        event_row_count=inspected.event_row_count,
        offline_feature_row_count=inspected.offline_feature_row_count,
        online_snapshot_row_count=inspected.online_snapshot_row_count,
        zone_count=inspected.zone_count,
        min_event_timestamp=inspected.min_event_timestamp,
        max_event_timestamp=inspected.max_event_timestamp,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_relational_storage_inspection_report(result), encoding="utf-8")
    return result


def build_relational_storage_sync_report(result: RelationalStorageSyncResult) -> str:
    """Build a Markdown summary for relational storage sync."""

    return "\n".join(
        [
            "# Relational Storage Sync Summary",
            "",
            "Synced raw events, offline feature rows, and online snapshot metadata into SQLAlchemy storage.",
            "",
            "## Database",
            "",
            f"- URL: `{result.database_url}`",
            f"- Backend: `{result.database_backend}`",
            "",
            "## Synced Rows",
            "",
            f"- Event rows: {result.event_row_count}",
            f"- Offline feature rows: {result.offline_feature_row_count}",
            f"- Online snapshot rows represented in metadata: {result.online_snapshot_row_count}",
            f"- Zone count: {result.zone_count}",
            f"- Min event timestamp: {_format_optional(result.min_event_timestamp)}",
            f"- Max event timestamp: {_format_optional(result.max_event_timestamp)}",
            "",
            "## Tables",
            "",
            "- `events` stores synthetic temporal demand events.",
            "- `offline_features` stores leakage-safe model-ready feature rows.",
            "- `online_feature_snapshots` stores latest online snapshot metadata.",
            "- `storage_run_metadata` stores the latest relational sync run metadata.",
            "",
        ],
    )


def build_relational_storage_inspection_report(
    result: RelationalStorageInspectionResult,
) -> str:
    """Build a Markdown summary for relational storage inspection."""

    return "\n".join(
        [
            "# Relational Storage Inspection Summary",
            "",
            "Inspected SQLAlchemy relational storage for raw events and feature snapshots.",
            "",
            "## Database",
            "",
            f"- URL: `{result.database_url}`",
            f"- Backend: `{result.database_backend}`",
            "",
            "## Inspection Results",
            "",
            f"- Event row count: {result.event_row_count}",
            f"- Offline feature row count: {result.offline_feature_row_count}",
            f"- Online snapshot row count: {result.online_snapshot_row_count}",
            f"- Zone count: {result.zone_count}",
            f"- Min event timestamp: {_format_optional(result.min_event_timestamp)}",
            f"- Max event timestamp: {_format_optional(result.max_event_timestamp)}",
            "",
        ],
    )


def relational_backend_from_url(database_url: str) -> str:
    """Parse a SQLAlchemy backend name without opening a database connection."""

    return make_url(database_url).get_backend_name()


def safe_database_url(database_url: str) -> str:
    """Render a database URL with credentials hidden for reports."""

    return make_url(database_url).render_as_string(hide_password=True)


def _read_event_rows(path: Path) -> list[dict[str, Any]]:
    events = read_synthetic_events(path)
    return [
        {
            "event_id": str(row["event_id"]),
            "timestamp": _timestamp_string(row["timestamp"]),
            "zone_id": str(row["zone_id"]),
            "user_id": str(row["user_id"]),
            "demand_count": int(row["demand_count"]),
            "hour": int(row["hour"]),
            "day_of_week": int(row["day_of_week"]),
            "is_weekend": bool(row["is_weekend"]),
            "base_demand": float(row["base_demand"]),
            "observed_demand": float(row["observed_demand"]),
        }
        for row in events.loc[:, EVENT_TABLE_COLUMNS].to_dict(orient="records")
    ]


def _read_offline_feature_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"offline features file not found: {path}")
    features = pd.read_parquet(path)
    missing = sorted(set(OFFLINE_FEATURE_TABLE_COLUMNS).difference(features.columns))
    if missing:
        raise ValueError(f"offline features missing required columns: {', '.join(missing)}")
    rows: list[dict[str, Any]] = []
    for raw_row in features.loc[:, OFFLINE_FEATURE_TABLE_COLUMNS].to_dict(orient="records"):
        row = {
            "event_id": str(raw_row["event_id"]),
            "timestamp": _timestamp_string(raw_row["timestamp"]),
            "zone_id": str(raw_row["zone_id"]),
            "hour": int(raw_row["hour"]),
            "day_of_week": int(raw_row["day_of_week"]),
            "is_weekend": bool(raw_row["is_weekend"]),
            "lag_1_observed_demand": float(raw_row["lag_1_observed_demand"]),
            "lag_3_observed_demand": float(raw_row["lag_3_observed_demand"]),
            "rolling_mean_3": float(raw_row["rolling_mean_3"]),
            "rolling_mean_6": float(raw_row["rolling_mean_6"]),
            "rolling_std_6": float(raw_row["rolling_std_6"]),
            "zone_hour_mean_demand": float(raw_row["zone_hour_mean_demand"]),
            TARGET_COLUMN: float(raw_row[TARGET_COLUMN]),
        }
        rows.append(row)
    return rows


def _read_online_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"online feature snapshot not found: {path}")
    return JsonBackedOnlineFeatureStore(snapshot_path=path).all_rows()


def _build_online_snapshot_metadata(
    *,
    online_rows: list[dict[str, object]],
    source_path: Path,
    created_at: str,
) -> dict[str, Any]:
    zone_ids = sorted(str(row["zone_id"]) for row in online_rows)
    min_timestamp, max_timestamp = _timestamp_bounds(online_rows, AS_OF_TIMESTAMP_COLUMN)
    return {
        "snapshot_id": "latest",
        "created_at": created_at,
        "source_path": str(source_path),
        "row_count": len(online_rows),
        "zone_count": len(zone_ids),
        "min_as_of_timestamp": min_timestamp,
        "max_as_of_timestamp": max_timestamp,
        "feature_columns_json": json.dumps(list(get_online_feature_columns()), sort_keys=True),
        "zone_ids_json": json.dumps(zone_ids, sort_keys=True),
    }


def _build_storage_run_metadata(
    *,
    database_backend: str,
    events_path: Path,
    offline_features_path: Path,
    online_snapshot_path: Path,
    event_row_count: int,
    offline_feature_row_count: int,
    online_snapshot_row_count: int,
    zone_count: int,
    created_at: str,
) -> dict[str, Any]:
    return {
        "run_id": "latest_relational_sync",
        "run_type": "sync_relational_store",
        "created_at": created_at,
        "database_backend": database_backend,
        "events_path": str(events_path),
        "offline_features_path": str(offline_features_path),
        "online_snapshot_path": str(online_snapshot_path),
        "event_row_count": event_row_count,
        "offline_feature_row_count": offline_feature_row_count,
        "online_snapshot_row_count": online_snapshot_row_count,
        "zone_count": zone_count,
    }


def _timestamp_bounds(rows: list[dict[str, Any]] | list[dict[str, object]], column: str) -> tuple[str | None, str | None]:
    timestamps = sorted(str(row[column]) for row in rows if row.get(column) is not None)
    if not timestamps:
        return None, None
    return timestamps[0], timestamps[-1]


def _deterministic_sync_timestamp(event_rows: list[dict[str, Any]]) -> str:
    _, max_timestamp = _timestamp_bounds(event_rows, "timestamp")
    return max_timestamp or "1970-01-01T00:00:00+00:00"


def _timestamp_string(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat()


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _create_engine(database_url: str) -> Engine:
    if relational_backend_from_url(database_url) == "sqlite":
        return create_engine(database_url, future=True, poolclass=NullPool)
    return create_engine(database_url, future=True)


def _format_optional(value: str | None) -> str:
    if value is None:
        return "n/a"
    return value


__all__ = [
    "EVENT_TABLE_COLUMNS",
    "OFFLINE_FEATURE_TABLE_COLUMNS",
    "ONLINE_SNAPSHOT_TABLE_COLUMNS",
    "RelationalFeatureStore",
    "RelationalStorageInspectionResult",
    "RelationalStorageSyncResult",
    "STORAGE_RUN_TABLE_COLUMNS",
    "build_relational_storage_inspection_report",
    "build_relational_storage_sync_report",
    "inspect_relational_store",
    "relational_backend_from_url",
    "safe_database_url",
    "sync_relational_store",
]

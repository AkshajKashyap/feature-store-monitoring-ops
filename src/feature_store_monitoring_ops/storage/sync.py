"""Storage sync and inspection workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from feature_store_monitoring_ops.paths import (
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_STORAGE_INSPECTION_REPORT_PATH,
    DEFAULT_STORAGE_SYNC_REPORT_PATH,
)
from feature_store_monitoring_ops.storage.config import (
    StorageConfig,
    build_online_feature_store,
    build_prediction_telemetry_store,
)
from feature_store_monitoring_ops.storage.online import JsonBackedOnlineFeatureStore
from feature_store_monitoring_ops.storage.telemetry import JsonlPredictionTelemetryStore


@dataclass(frozen=True)
class StorageSyncResult:
    """Result from syncing local artifacts into configured storage backends."""

    report_path: Path
    online_backend: str
    telemetry_backend: str
    online_feature_row_count: int
    telemetry_source_row_count: int
    telemetry_store_row_count: int
    zone_ids: list[str]


@dataclass(frozen=True)
class StorageInspectionResult:
    """Result from inspecting configured storage backends."""

    report_path: Path
    online_backend: str
    telemetry_backend: str
    online_feature_row_count: int
    telemetry_row_count: int
    zone_ids: list[str]
    min_telemetry_timestamp: str | None
    max_telemetry_timestamp: str | None


def sync_storage(
    *,
    config: StorageConfig,
    feature_snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    telemetry_log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Path = DEFAULT_STORAGE_SYNC_REPORT_PATH,
) -> StorageSyncResult:
    """Sync local online features and JSONL telemetry into configured stores."""

    if not feature_snapshot_path.exists():
        raise FileNotFoundError(f"online feature snapshot not found: {feature_snapshot_path}")

    source_feature_store = JsonBackedOnlineFeatureStore(snapshot_path=feature_snapshot_path)
    rows = source_feature_store.all_rows()
    online_store = build_online_feature_store(config, snapshot_path=feature_snapshot_path)
    online_store.put_many(rows)
    stored_rows = online_store.all_rows()

    telemetry_rows = JsonlPredictionTelemetryStore(log_path=telemetry_log_path).all_rows()
    telemetry_store = build_prediction_telemetry_store(config, log_path=telemetry_log_path)
    if config.telemetry_backend != "jsonl":
        telemetry_store.append_many(telemetry_rows)
    telemetry_store_row_count = telemetry_store.count()

    result = StorageSyncResult(
        report_path=report_path,
        online_backend=config.online_backend,
        telemetry_backend=config.telemetry_backend,
        online_feature_row_count=len(stored_rows),
        telemetry_source_row_count=len(telemetry_rows),
        telemetry_store_row_count=telemetry_store_row_count,
        zone_ids=online_store.zone_ids(),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_storage_sync_report(
            result=result,
            config=config,
            feature_snapshot_path=feature_snapshot_path,
            telemetry_log_path=telemetry_log_path,
        ),
        encoding="utf-8",
    )
    return result


def inspect_storage(
    *,
    config: StorageConfig,
    feature_snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    telemetry_log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Path = DEFAULT_STORAGE_INSPECTION_REPORT_PATH,
) -> StorageInspectionResult:
    """Inspect configured local storage backends."""

    online_store = build_online_feature_store(config, snapshot_path=feature_snapshot_path)
    telemetry_store = build_prediction_telemetry_store(config, log_path=telemetry_log_path)
    min_timestamp, max_timestamp = telemetry_store.timestamp_bounds()
    rows = online_store.all_rows()
    result = StorageInspectionResult(
        report_path=report_path,
        online_backend=config.online_backend,
        telemetry_backend=config.telemetry_backend,
        online_feature_row_count=len(rows),
        telemetry_row_count=telemetry_store.count(),
        zone_ids=online_store.zone_ids(),
        min_telemetry_timestamp=min_timestamp,
        max_telemetry_timestamp=max_timestamp,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_storage_inspection_report(
            result=result,
            config=config,
            feature_snapshot_path=feature_snapshot_path,
            telemetry_log_path=telemetry_log_path,
        ),
        encoding="utf-8",
    )
    return result


def build_storage_sync_report(
    *,
    result: StorageSyncResult,
    config: StorageConfig,
    feature_snapshot_path: Path,
    telemetry_log_path: Path,
) -> str:
    """Build a tracked Markdown report for storage sync."""

    zone_lines = _zone_lines(result.zone_ids)
    return "\n".join(
        [
            "# Storage Sync Summary",
            "",
            "Synced local online feature and prediction telemetry artifacts for Milestone 8.",
            "",
            "## Sources",
            "",
            f"- Online feature snapshot: `{feature_snapshot_path}`",
            f"- Prediction telemetry JSONL: `{telemetry_log_path}`",
            "",
            "## Backends",
            "",
            f"- Online feature backend: `{result.online_backend}`",
            f"- Telemetry backend: `{result.telemetry_backend}`",
            f"- SQLite path: `{config.sqlite_path}`",
            f"- Redis URL: `{config.redis_url}`",
            "",
            "## Sync Results",
            "",
            f"- Online feature rows synced: {result.online_feature_row_count}",
            f"- Telemetry source rows: {result.telemetry_source_row_count}",
            f"- Telemetry store rows: {result.telemetry_store_row_count}",
            "",
            "## Available Zone IDs",
            "",
            zone_lines,
            "",
            "## Notes",
            "",
            "- Default local sync keeps online features JSON-backed and copies JSONL telemetry to SQLite.",
            "- Redis support is adapter-level and requires an injected client or configured Redis server.",
            "",
        ],
    )


def build_storage_inspection_report(
    *,
    result: StorageInspectionResult,
    config: StorageConfig,
    feature_snapshot_path: Path,
    telemetry_log_path: Path,
) -> str:
    """Build a tracked Markdown report for storage inspection."""

    zone_lines = _zone_lines(result.zone_ids)
    return "\n".join(
        [
            "# Storage Inspection Summary",
            "",
            "Inspected configured online feature and prediction telemetry stores for Milestone 8.",
            "",
            "## Sources",
            "",
            f"- Online feature snapshot path: `{feature_snapshot_path}`",
            f"- Prediction telemetry JSONL path: `{telemetry_log_path}`",
            "",
            "## Backends",
            "",
            f"- Online feature backend: `{result.online_backend}`",
            f"- Telemetry backend: `{result.telemetry_backend}`",
            f"- SQLite path: `{config.sqlite_path}`",
            f"- Redis URL: `{config.redis_url}`",
            "",
            "## Inspection Results",
            "",
            f"- Online feature row count: {result.online_feature_row_count}",
            f"- Telemetry row count: {result.telemetry_row_count}",
            f"- Min telemetry timestamp: {_format_optional(result.min_telemetry_timestamp)}",
            f"- Max telemetry timestamp: {_format_optional(result.max_telemetry_timestamp)}",
            "",
            "## Available Zone IDs",
            "",
            zone_lines,
            "",
        ],
    )


def storage_inspection_payload(result: StorageInspectionResult) -> dict[str, Any]:
    """Return a JSON-friendly inspection payload for tests and future callers."""

    return {
        "online_backend": result.online_backend,
        "telemetry_backend": result.telemetry_backend,
        "online_feature_row_count": result.online_feature_row_count,
        "telemetry_row_count": result.telemetry_row_count,
        "zone_ids": result.zone_ids,
        "min_telemetry_timestamp": result.min_telemetry_timestamp,
        "max_telemetry_timestamp": result.max_telemetry_timestamp,
    }


def _zone_lines(zone_ids: list[str]) -> str:
    if not zone_ids:
        return "- No zone IDs available."
    return "\n".join(f"- `{zone_id}`" for zone_id in zone_ids)


def _format_optional(value: str | None) -> str:
    if value is None:
        return "n/a"
    return value


__all__ = [
    "StorageInspectionResult",
    "StorageSyncResult",
    "build_storage_inspection_report",
    "build_storage_sync_report",
    "inspect_storage",
    "storage_inspection_payload",
    "sync_storage",
]

"""Storage backend configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from feature_store_monitoring_ops.paths import (
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_SQLITE_TELEMETRY_DB_PATH,
)
from feature_store_monitoring_ops.storage.online import (
    InMemoryOnlineFeatureStore,
    JsonBackedOnlineFeatureStore,
    OnlineFeatureStore,
    RedisOnlineFeatureStore,
)
from feature_store_monitoring_ops.storage.telemetry import (
    JsonlPredictionTelemetryStore,
    PredictionTelemetryStore,
    SQLitePredictionTelemetryStore,
)

ONLINE_BACKEND_ENV = "FEATURE_STORE_OPS_ONLINE_BACKEND"
TELEMETRY_BACKEND_ENV = "FEATURE_STORE_OPS_TELEMETRY_BACKEND"
SQLITE_PATH_ENV = "FEATURE_STORE_OPS_SQLITE_PATH"
REDIS_URL_ENV = "FEATURE_STORE_OPS_REDIS_URL"

ONLINE_BACKENDS: tuple[str, ...] = ("json", "memory", "redis")
TELEMETRY_BACKENDS: tuple[str, ...] = ("jsonl", "sqlite")


@dataclass(frozen=True)
class StorageConfig:
    """Resolved local storage backend configuration."""

    online_backend: str = "json"
    telemetry_backend: str = "sqlite"
    sqlite_path: Path = DEFAULT_SQLITE_TELEMETRY_DB_PATH
    redis_url: str = "redis://localhost:6379/0"

    @classmethod
    def from_env(cls) -> StorageConfig:
        """Build storage config from environment variables."""

        return cls(
            online_backend=os.getenv(ONLINE_BACKEND_ENV, cls.online_backend),
            telemetry_backend=os.getenv(TELEMETRY_BACKEND_ENV, cls.telemetry_backend),
            sqlite_path=Path(os.getenv(SQLITE_PATH_ENV, str(cls.sqlite_path))),
            redis_url=os.getenv(REDIS_URL_ENV, cls.redis_url),
        ).validated()

    def with_overrides(
        self,
        *,
        online_backend: str | None = None,
        telemetry_backend: str | None = None,
        sqlite_path: Path | None = None,
        redis_url: str | None = None,
    ) -> StorageConfig:
        """Return a validated copy with optional CLI overrides."""

        return StorageConfig(
            online_backend=online_backend or self.online_backend,
            telemetry_backend=telemetry_backend or self.telemetry_backend,
            sqlite_path=sqlite_path or self.sqlite_path,
            redis_url=redis_url or self.redis_url,
        ).validated()

    def validated(self) -> StorageConfig:
        """Validate configured backend names."""

        if self.online_backend not in ONLINE_BACKENDS:
            raise ValueError(
                "online feature backend must be one of: " + ", ".join(ONLINE_BACKENDS),
            )
        if self.telemetry_backend not in TELEMETRY_BACKENDS:
            raise ValueError("telemetry backend must be one of: " + ", ".join(TELEMETRY_BACKENDS))
        return self


def build_online_feature_store(
    config: StorageConfig,
    *,
    snapshot_path: Path = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
) -> OnlineFeatureStore:
    """Create an online feature store for the configured backend."""

    if config.online_backend == "json":
        return JsonBackedOnlineFeatureStore(snapshot_path=snapshot_path)
    if config.online_backend == "memory":
        return InMemoryOnlineFeatureStore()
    if config.online_backend == "redis":
        return RedisOnlineFeatureStore(redis_url=config.redis_url)
    raise ValueError(f"unsupported online feature backend: {config.online_backend}")


def build_prediction_telemetry_store(
    config: StorageConfig,
    *,
    log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
) -> PredictionTelemetryStore:
    """Create a prediction telemetry store for the configured backend."""

    if config.telemetry_backend == "jsonl":
        return JsonlPredictionTelemetryStore(log_path=log_path)
    if config.telemetry_backend == "sqlite":
        return SQLitePredictionTelemetryStore(db_path=config.sqlite_path)
    raise ValueError(f"unsupported telemetry backend: {config.telemetry_backend}")


__all__ = [
    "ONLINE_BACKENDS",
    "ONLINE_BACKEND_ENV",
    "REDIS_URL_ENV",
    "SQLITE_PATH_ENV",
    "TELEMETRY_BACKENDS",
    "TELEMETRY_BACKEND_ENV",
    "StorageConfig",
    "build_online_feature_store",
    "build_prediction_telemetry_store",
]

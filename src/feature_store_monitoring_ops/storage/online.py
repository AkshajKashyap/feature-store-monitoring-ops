"""Online feature store protocol and local/Redis-compatible implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from feature_store_monitoring_ops.features.contract import (
    ENTITY_KEY_COLUMNS,
    TARGET_COLUMN,
    get_online_feature_columns,
)


class OnlineFeatureStore(Protocol):
    """Minimal online feature store interface."""

    def put_many(self, rows: list[dict[str, object]]) -> None:
        """Store online feature rows."""

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        """Return a feature row for an entity key mapping."""

    def all_rows(self) -> list[dict[str, object]]:
        """Return all stored feature rows."""

    def zone_ids(self) -> list[str]:
        """Return available zone IDs."""


@dataclass
class InMemoryOnlineFeatureStore:
    """In-memory online feature store for tests."""

    rows_by_key: dict[tuple[object, ...], dict[str, object]] = field(default_factory=dict)

    def put_many(self, rows: list[dict[str, object]]) -> None:
        _validate_online_rows(rows)
        self.rows_by_key.clear()
        for row in rows:
            self.rows_by_key[_entity_key_tuple(row)] = dict(row)

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        row = self.rows_by_key.get(_entity_key_tuple(entity_keys))
        if row is None:
            return None
        return dict(row)

    def all_rows(self) -> list[dict[str, object]]:
        return [dict(row) for _, row in sorted(self.rows_by_key.items())]

    def zone_ids(self) -> list[str]:
        return sorted(str(row["zone_id"]) for row in self.all_rows())


@dataclass
class JsonBackedOnlineFeatureStore:
    """JSON-backed online feature store for local development."""

    snapshot_path: Path

    def put_many(self, rows: list[dict[str, object]]) -> None:
        _validate_online_rows(rows)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(
            json.dumps(rows, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        key = _entity_key_tuple(entity_keys)
        for row in self.all_rows():
            if _entity_key_tuple(row) == key:
                return row
        return None

    def all_rows(self) -> list[dict[str, object]]:
        if not self.snapshot_path.exists():
            return []
        rows = list(json.loads(self.snapshot_path.read_text(encoding="utf-8")))
        _validate_online_rows(rows)
        return rows

    def zone_ids(self) -> list[str]:
        return sorted(str(row["zone_id"]) for row in self.all_rows())


@dataclass
class RedisOnlineFeatureStore:
    """Redis-compatible online feature store with injectable client support."""

    redis_url: str
    client: Any | None = None
    key_prefix: str = "feature_store_ops:online_features"

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        try:
            import redis
        except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime path
            raise RuntimeError(
                "Redis client package is not installed. Pass an injected client for tests "
                "or install redis to use the Redis online feature adapter.",
            ) from exc
        self.client = redis.Redis.from_url(self.redis_url)

    def put_many(self, rows: list[dict[str, object]]) -> None:
        _validate_online_rows(rows)
        self._clear_existing_rows()
        for row in rows:
            zone_id = str(row["zone_id"])
            self._client.set(self._feature_key(zone_id), json.dumps(row, sort_keys=True))
            self._client.sadd(self._zone_index_key, zone_id)

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        zone_id = str(_entity_key_tuple(entity_keys)[0])
        payload = self._client.get(self._feature_key(zone_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        row = json.loads(str(payload))
        _validate_online_rows([row])
        return row

    def all_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for zone_id in self.zone_ids():
            row = self.get({"zone_id": zone_id})
            if row is not None:
                rows.append(row)
        return rows

    def zone_ids(self) -> list[str]:
        raw_values = self._client.smembers(self._zone_index_key)
        zone_ids = [_decode_redis_value(value) for value in raw_values]
        return sorted(zone_ids)

    @property
    def _client(self) -> Any:
        if self.client is None:
            raise RuntimeError("Redis client was not initialized")
        return self.client

    @property
    def _zone_index_key(self) -> str:
        return f"{self.key_prefix}:zones"

    def _feature_key(self, zone_id: str) -> str:
        return f"{self.key_prefix}:zone:{zone_id}"

    def _clear_existing_rows(self) -> None:
        keys = [self._feature_key(zone_id) for zone_id in self.zone_ids()]
        keys.append(self._zone_index_key)
        if hasattr(self._client, "delete"):
            self._client.delete(*keys)


def _entity_key_tuple(row: dict[str, object]) -> tuple[object, ...]:
    missing = sorted(set(ENTITY_KEY_COLUMNS).difference(row))
    if missing:
        raise ValueError(f"online feature row missing entity keys: {', '.join(missing)}")
    return tuple(row[column] for column in ENTITY_KEY_COLUMNS)


def _validate_online_rows(rows: list[dict[str, object]]) -> None:
    expected_columns = set(get_online_feature_columns())
    for index, row in enumerate(rows, start=1):
        actual_columns = set(row)
        if actual_columns != expected_columns:
            missing = sorted(expected_columns.difference(actual_columns))
            unexpected = sorted(actual_columns.difference(expected_columns))
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ValueError(f"online row {index} does not match feature contract ({'; '.join(details)})")
        if TARGET_COLUMN in row:
            raise ValueError(f"online row {index} contains target column")
        _entity_key_tuple(row)


def _decode_redis_value(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


__all__ = [
    "InMemoryOnlineFeatureStore",
    "JsonBackedOnlineFeatureStore",
    "OnlineFeatureStore",
    "RedisOnlineFeatureStore",
]

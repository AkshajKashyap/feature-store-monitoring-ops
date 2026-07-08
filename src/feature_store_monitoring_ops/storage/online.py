"""Local online feature store implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from feature_store_monitoring_ops.features.contract import ENTITY_KEY_COLUMNS


class OnlineFeatureStore(Protocol):
    """Minimal local online feature store interface."""

    def put_many(self, rows: list[dict[str, object]]) -> None:
        """Store online feature rows."""

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        """Return a feature row for an entity key mapping."""

    def all_rows(self) -> list[dict[str, object]]:
        """Return all stored feature rows."""


@dataclass
class InMemoryOnlineFeatureStore:
    """In-memory online feature store for tests."""

    rows_by_key: dict[tuple[object, ...], dict[str, object]] = field(default_factory=dict)

    def put_many(self, rows: list[dict[str, object]]) -> None:
        for row in rows:
            self.rows_by_key[_entity_key_tuple(row)] = dict(row)

    def get(self, entity_keys: dict[str, object]) -> dict[str, object] | None:
        row = self.rows_by_key.get(_entity_key_tuple(entity_keys))
        if row is None:
            return None
        return dict(row)

    def all_rows(self) -> list[dict[str, object]]:
        return [dict(row) for _, row in sorted(self.rows_by_key.items())]


@dataclass
class JsonBackedOnlineFeatureStore:
    """JSON-backed online feature store for local development."""

    snapshot_path: Path

    def put_many(self, rows: list[dict[str, object]]) -> None:
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
        return list(json.loads(self.snapshot_path.read_text(encoding="utf-8")))


def _entity_key_tuple(row: dict[str, object]) -> tuple[object, ...]:
    missing = sorted(set(ENTITY_KEY_COLUMNS).difference(row))
    if missing:
        raise ValueError(f"online feature row missing entity keys: {', '.join(missing)}")
    return tuple(row[column] for column in ENTITY_KEY_COLUMNS)


__all__ = [
    "InMemoryOnlineFeatureStore",
    "JsonBackedOnlineFeatureStore",
    "OnlineFeatureStore",
]

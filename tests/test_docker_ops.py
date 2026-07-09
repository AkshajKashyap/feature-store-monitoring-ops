from __future__ import annotations

import os
from pathlib import Path

from feature_store_monitoring_ops.storage.config import (
    ONLINE_BACKEND_ENV,
    REDIS_URL_ENV,
    StorageConfig,
    build_online_feature_store,
)
from feature_store_monitoring_ops.storage.online import (
    JsonBackedOnlineFeatureStore,
    RedisOnlineFeatureStore,
)


def test_dockerfile_exists_and_uses_python_311() -> None:
    dockerfile = Path("Dockerfile")

    content = dockerfile.read_text(encoding="utf-8")

    assert dockerfile.exists()
    assert "FROM python:3.11-slim" in content
    assert "USER appuser" in content
    assert "EXPOSE 8000" in content


def test_docker_compose_defines_api_and_redis_services() -> None:
    compose = Path("docker-compose.yml")

    content = compose.read_text(encoding="utf-8")

    assert compose.exists()
    assert "services:" in content
    assert "  api:" in content
    assert "  redis:" in content
    assert "redis:7-alpine" in content


def test_docker_smoke_script_exists_and_is_executable() -> None:
    script = Path("scripts/docker_smoke_test.sh")

    assert script.exists()
    assert os.access(script, os.X_OK)
    assert "docker build" in script.read_text(encoding="utf-8")


def test_makefile_includes_docker_targets() -> None:
    makefile = "\n" + Path("Makefile").read_text(encoding="utf-8")

    assert "\ndocker-build:" in makefile
    assert "\ndocker-smoke:" in makefile


def test_config_selects_json_and_redis_without_live_redis(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ONLINE_BACKEND_ENV, "json")
    json_config = StorageConfig.from_env()
    json_store = build_online_feature_store(
        json_config,
        snapshot_path=tmp_path / "latest_features.json",
    )

    monkeypatch.setenv(ONLINE_BACKEND_ENV, "redis")
    monkeypatch.setenv(REDIS_URL_ENV, "redis://fake:6379/0")
    redis_config = StorageConfig.from_env()
    redis_store = build_online_feature_store(redis_config, redis_client=FakeRedis())

    assert isinstance(json_store, JsonBackedOnlineFeatureStore)
    assert isinstance(redis_store, RedisOnlineFeatureStore)
    assert redis_store.redis_url == "redis://fake:6379/0"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value)

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.sets.pop(key, None)

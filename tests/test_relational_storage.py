from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.features.offline import build_offline_features
from feature_store_monitoring_ops.features.online import (
    online_features_to_records,
    select_latest_online_features,
)
from feature_store_monitoring_ops.storage.config import RELATIONAL_URL_ENV, StorageConfig
from feature_store_monitoring_ops.storage.online import JsonBackedOnlineFeatureStore
from feature_store_monitoring_ops.storage.relational import (
    RelationalFeatureStore,
    inspect_relational_store,
    relational_backend_from_url,
    safe_database_url,
    sync_relational_store,
)
from feature_store_monitoring_ops.synthetic_events import (
    SyntheticEventConfig,
    generate_synthetic_events,
    write_synthetic_events_csv,
)


@dataclass(frozen=True)
class RelationalArtifactFixture:
    events_path: Path
    offline_features_path: Path
    online_snapshot_path: Path
    event_row_count: int
    offline_feature_row_count: int
    online_snapshot_row_count: int
    zone_count: int


def test_sqlite_relational_store_schema_creation(tmp_path) -> None:
    store = RelationalFeatureStore(database_url=f"sqlite:///{tmp_path / 'feature_store.db'}")

    store.create_schema()

    assert store.table_names() == {
        "events",
        "offline_features",
        "online_feature_snapshots",
        "storage_run_metadata",
    }


def test_event_sync_row_counts(tmp_path) -> None:
    artifacts = _write_relational_artifacts(tmp_path)

    result = sync_relational_store(
        database_url=f"sqlite:///{tmp_path / 'feature_store.db'}",
        events_path=artifacts.events_path,
        offline_features_path=artifacts.offline_features_path,
        online_snapshot_path=artifacts.online_snapshot_path,
        report_path=tmp_path / "relational_storage_sync_summary.md",
    )

    assert result.event_row_count == artifacts.event_row_count
    assert result.zone_count == artifacts.zone_count


def test_offline_feature_sync_row_counts(tmp_path) -> None:
    artifacts = _write_relational_artifacts(tmp_path)
    database_url = f"sqlite:///{tmp_path / 'feature_store.db'}"

    sync_relational_store(
        database_url=database_url,
        events_path=artifacts.events_path,
        offline_features_path=artifacts.offline_features_path,
        online_snapshot_path=artifacts.online_snapshot_path,
        report_path=tmp_path / "relational_storage_sync_summary.md",
    )
    result = inspect_relational_store(
        database_url=database_url,
        report_path=tmp_path / "relational_storage_inspection_summary.md",
    )

    assert result.offline_feature_row_count == artifacts.offline_feature_row_count
    assert result.event_row_count == artifacts.event_row_count


def test_online_snapshot_metadata_sync(tmp_path) -> None:
    artifacts = _write_relational_artifacts(tmp_path)
    database_url = f"sqlite:///{tmp_path / 'feature_store.db'}"

    sync_relational_store(
        database_url=database_url,
        events_path=artifacts.events_path,
        offline_features_path=artifacts.offline_features_path,
        online_snapshot_path=artifacts.online_snapshot_path,
        report_path=tmp_path / "relational_storage_sync_summary.md",
    )
    result = inspect_relational_store(
        database_url=database_url,
        report_path=tmp_path / "relational_storage_inspection_summary.md",
    )

    assert result.online_snapshot_row_count == artifacts.online_snapshot_row_count
    assert result.zone_count == artifacts.zone_count


def test_inspect_relational_store_cli_smoke_behavior(tmp_path) -> None:
    artifacts = _write_relational_artifacts(tmp_path)
    database_url = f"sqlite:///{tmp_path / 'feature_store.db'}"
    report_path = tmp_path / "relational_storage_inspection_summary.md"
    sync_relational_store(
        database_url=database_url,
        events_path=artifacts.events_path,
        offline_features_path=artifacts.offline_features_path,
        online_snapshot_path=artifacts.online_snapshot_path,
        report_path=tmp_path / "relational_storage_sync_summary.md",
    )
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "inspect-relational-store",
            "--database-url",
            database_url,
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert f"event row count: {artifacts.event_row_count}" in result.output
    assert f"offline feature row count: {artifacts.offline_feature_row_count}" in result.output
    assert report_path.exists()


def test_postgres_url_config_parses_without_connecting(monkeypatch) -> None:
    database_url = "postgresql+psycopg://feature_user:secret@localhost:5432/feature_store"
    monkeypatch.setenv(RELATIONAL_URL_ENV, database_url)

    config = StorageConfig.from_env()

    assert config.relational_url == database_url
    assert relational_backend_from_url(config.relational_url) == "postgresql"
    assert "secret" not in safe_database_url(config.relational_url)


def _write_relational_artifacts(tmp_path) -> RelationalArtifactFixture:
    events_path = tmp_path / "synthetic_events.csv"
    offline_features_path = tmp_path / "offline_features.parquet"
    online_snapshot_path = tmp_path / "latest_features.json"
    rows = generate_synthetic_events(
        SyntheticEventConfig(
            seed=303,
            zone_count=3,
            user_count=20,
            num_days=5,
            events_per_zone_per_day=4,
        ),
    )
    write_synthetic_events_csv(rows=rows, output_path=events_path)
    features = build_offline_features(pd.DataFrame(rows))
    offline_features_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(offline_features_path, index=False)
    online_rows = online_features_to_records(select_latest_online_features(features))
    JsonBackedOnlineFeatureStore(snapshot_path=online_snapshot_path).put_many(online_rows)
    return RelationalArtifactFixture(
        events_path=events_path,
        offline_features_path=offline_features_path,
        online_snapshot_path=online_snapshot_path,
        event_row_count=len(rows),
        offline_feature_row_count=len(features),
        online_snapshot_row_count=len(online_rows),
        zone_count=len({str(row["zone_id"]) for row in rows}),
    )

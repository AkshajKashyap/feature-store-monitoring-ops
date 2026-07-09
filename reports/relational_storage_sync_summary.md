# Relational Storage Sync Summary

Synced raw events, offline feature rows, and online snapshot metadata into SQLAlchemy storage.

## Database

- URL: `sqlite:////home/akshaj/Building/feature-store-monitoring-ops/artifacts/storage/feature_store.db`
- Backend: `sqlite`

## Synced Rows

- Event rows: 720
- Offline feature rows: 595
- Online snapshot rows represented in metadata: 5
- Zone count: 5
- Min event timestamp: 2026-01-01T00:00:00+00:00
- Max event timestamp: 2026-01-30T23:00:00+00:00

## Tables

- `events` stores synthetic temporal demand events.
- `offline_features` stores leakage-safe model-ready feature rows.
- `online_feature_snapshots` stores latest online snapshot metadata.
- `storage_run_metadata` stores the latest relational sync run metadata.

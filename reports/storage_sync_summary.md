# Storage Sync Summary

Synced local online feature and prediction telemetry artifacts for Milestone 8.

## Sources

- Online feature snapshot: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/latest_features.json`
- Prediction telemetry JSONL: `/home/akshaj/Building/feature-store-monitoring-ops/logs/predictions.jsonl`

## Backends

- Online feature backend: `json`
- Telemetry backend: `sqlite`
- SQLite path: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/storage/telemetry.db`
- Redis URL: `redis://localhost:6379/0`

## Sync Results

- Online feature rows synced: 5
- Telemetry source rows: 6
- Telemetry store rows: 6

## Available Zone IDs

- `zone_01`
- `zone_02`
- `zone_03`
- `zone_04`
- `zone_05`

## Notes

- Default local sync keeps online features JSON-backed and copies JSONL telemetry to SQLite.
- Redis support is adapter-level and requires an injected client or configured Redis server.

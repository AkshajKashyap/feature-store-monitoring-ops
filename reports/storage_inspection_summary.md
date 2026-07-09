# Storage Inspection Summary

Inspected configured online feature and prediction telemetry stores for Milestone 8.

## Sources

- Online feature snapshot path: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/latest_features.json`
- Prediction telemetry JSONL path: `/home/akshaj/Building/feature-store-monitoring-ops/logs/predictions.jsonl`

## Backends

- Online feature backend: `json`
- Telemetry backend: `sqlite`
- SQLite path: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/storage/telemetry.db`
- Redis URL: `redis://localhost:6379/0`

## Inspection Results

- Online feature row count: 5
- Telemetry row count: 6
- Min telemetry timestamp: 2026-02-01T00:00:00+00:00
- Max telemetry timestamp: 2026-02-01T00:00:05+00:00

## Available Zone IDs

- `zone_01`
- `zone_02`
- `zone_03`
- `zone_04`
- `zone_05`

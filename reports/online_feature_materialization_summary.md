# Online Feature Materialization Summary

Materialized the latest offline feature row per entity for Milestone 4.

## Artifacts

- Source offline features: `/home/akshaj/Building/feature-store-monitoring-ops/data/processed/offline_features.parquet`
- Online snapshot: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/latest_features.json`
- Manifest: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/manifest.json`

## Snapshot

- Row count: 5
- As-of column: `timestamp`

## Entity Keys

- `zone_id`

## Model Input Feature Columns

- `zone_id`
- `hour`
- `day_of_week`
- `is_weekend`
- `lag_1_observed_demand`
- `lag_3_observed_demand`
- `rolling_mean_3`
- `rolling_mean_6`
- `rolling_std_6`
- `zone_hour_mean_demand`

## Parity Notes

- Snapshot rows contain model input features plus entity/as-of metadata only.
- The latest valid offline feature row is selected per `zone_id`.
- Online values are validated against the corresponding latest offline rows.
- `target_next_observed_demand` is excluded from online features.

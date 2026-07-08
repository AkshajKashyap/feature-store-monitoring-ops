# Offline Feature Summary

Built deterministic offline temporal features for Milestone 2.

## Row Counts

- Offline features: 595
- train: 416 rows
- validation: 89 rows
- test: 90 rows

## Split Time Ranges

- train: 416 rows, 2026-01-02T04:00:00+00:00 to 2026-01-23T06:00:00+00:00
- validation: 89 rows, 2026-01-23T07:00:00+00:00 to 2026-01-27T00:00:00+00:00
- test: 90 rows, 2026-01-27T01:00:00+00:00 to 2026-01-30T22:00:00+00:00

## Feature Columns

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

## Target Summary

- Target column: `target_next_observed_demand`
- Non-null targets: 595
- Mean: 27.790
- Minimum: 9.893
- Maximum: 53.339

## Leakage Notes

- Rows are sorted chronologically before feature construction and splitting.
- Lag and rolling features are grouped by `zone_id` and shifted by one row first.
- `zone_hour_mean_demand` uses an expanding mean of prior matching zone-hour rows.
- `target_next_observed_demand` is the next future observed demand for the same zone.
- Chronological train/validation/test splits are created after target rows are filtered.

# Drift Monitoring Summary

Feature drift, prediction drift, and data quality checks for Milestone 7.

## Sources

- Reference features: `/home/akshaj/Building/feature-store-monitoring-ops/data/processed/train_features.parquet`
- Current features: `/home/akshaj/Building/feature-store-monitoring-ops/data/processed/test_features.parquet`
- Prediction logs: `/home/akshaj/Building/feature-store-monitoring-ops/logs/predictions.jsonl`
- Model metrics reference: `/home/akshaj/Building/feature-store-monitoring-ops/reports/model_metrics.json`

## Row Counts

- Reference feature rows: 416
- Current feature rows: 90
- Prediction log rows: 6

## Numeric Feature Drift

| Feature | Mean Shift | Std Shift | Missing Rate Difference | PSI |
| --- | ---: | ---: | ---: | ---: |
| `hour` | -0.166880 | -0.189263 | 0.000000 | 0.003869 |
| `day_of_week` | -0.468109 | -0.894278 | 0.000000 | 5.118269 |
| `is_weekend` | -0.262019 | -0.439733 | 0.000000 | 3.348596 |
| `lag_1_observed_demand` | 3.685972 | 0.854664 | 0.000000 | 0.414319 |
| `lag_3_observed_demand` | 3.678710 | 1.042218 | 0.000000 | 0.350197 |
| `rolling_mean_3` | 3.632255 | 0.928358 | 0.000000 | 0.725830 |
| `rolling_mean_6` | 3.363791 | 1.255804 | 0.000000 | 0.781236 |
| `rolling_std_6` | 0.627408 | -0.001315 | 0.000000 | 0.342578 |
| `zone_hour_mean_demand` | 1.424374 | -0.205767 | 0.000000 | 0.133230 |

## Coverage Drift

- `zone_id`: reference=5, current=5, lost=[], new=[]
- `hour`: reference=24, current=24, lost=[], new=[]
- `day_of_week`: reference=7, current=4, lost=[0, 5, 6], new=[]

## Prediction Drift

- Reference selected model: `hist_gradient_boosting`
- Reference mean prediction: 31.162596
- Current mean prediction: 28.197380
- Mean prediction shift: -2.965216
- Prediction count: 5
- Min prediction: 20.803178
- Max prediction: 34.800668

## Data Quality

- Reference: passed
- Current: passed

## Thresholds

- PSI: 0.200
- Prediction mean shift: 5.000
- Minimum prediction count: 10

## Warnings

- WARNING: Feature `day_of_week` PSI 5.118 exceeds threshold 0.200.
- WARNING: Feature `is_weekend` PSI 3.349 exceeds threshold 0.200.
- WARNING: Feature `lag_1_observed_demand` PSI 0.414 exceeds threshold 0.200.
- WARNING: Feature `lag_3_observed_demand` PSI 0.350 exceeds threshold 0.200.
- WARNING: Feature `rolling_mean_3` PSI 0.726 exceeds threshold 0.200.
- WARNING: Feature `rolling_mean_6` PSI 0.781 exceeds threshold 0.200.
- WARNING: Feature `rolling_std_6` PSI 0.343 exceeds threshold 0.200.
- WARNING: Prediction drift sample is too small to trust (5 < 10).

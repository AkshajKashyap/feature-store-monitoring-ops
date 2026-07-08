# Model Training Summary

Trained baseline demand forecasting models for Milestone 3.

## Selected Model

- Selected model: `hist_gradient_boosting`
- Selection metric: validation `mae`

## Row Counts

- Train: 416
- Validation: 89
- Test: 90

## Validation Metrics

| Model | MAE | RMSE | R2 | Mean prediction | Mean target |
| --- | ---: | ---: | ---: | ---: | ---: |
| naive_lag_1 | 9.902112 | 12.063071 | -1.137513 | 26.224955 | 25.216438 |
| zone_hour_mean | 8.555436 | 10.977073 | -0.769971 | 27.303594 | 25.216438 |
| ridge_regression | 6.370028 | 7.722740 | 0.123936 | 26.007366 | 25.216438 |
| hist_gradient_boosting | 5.660108 | 7.193382 | 0.239920 | 25.523123 | 25.216438 |

## Test Metrics

- mae: 6.298410
- rmse: 7.948043
- r2: 0.313692
- mean_prediction: 31.162596
- mean_target: 31.920733

## Input Features

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

## Leakage Notes

- Candidate models are trained on the train split only.
- Validation metrics select the model.
- The selected model is evaluated on the test split only after selection.
- `target_next_observed_demand` is never included as an input feature.

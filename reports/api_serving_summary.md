# API Serving Summary

Added a local FastAPI prediction service for Milestone 5.

## Artifacts

- Model: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/models/selected_model.joblib`
- Model manifest: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/models/model_manifest.json`
- Online features: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/latest_features.json`
- Online feature manifest: `/home/akshaj/Building/feature-store-monitoring-ops/artifacts/online_features/manifest.json`

## Endpoints

- `GET /health`
- `GET /model`
- `GET /features/{zone_id}`
- `POST /predict`
- `GET /metrics`

## Model

- Selected model: `hist_gradient_boosting`

## Model Input Features

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

## Smoke Test

- Status: passed

## Local Metrics

- Request count: 5
- Prediction count: 1
- Error count: 0
- Average prediction latency ms: 7.036459

## Notes

- Serving is local and uses JSON-backed online features.
- Predictions use exactly the shared model input feature columns.
- Metrics are in-memory only for this milestone.
- Redis, Postgres, Docker, and external serving infrastructure are not required yet.

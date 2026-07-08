# Feature Store Monitoring Ops

Production-style ML feature store and monitoring system with offline/online feature parity, Redis/Postgres serving, FastAPI predictions, drift detection, and Dockerized local ops.

## Goal

Build an end-to-end ML system around real temporal event data:
data ingestion -> offline features -> online feature store -> model training -> prediction API -> telemetry -> monitoring -> release gate.

## Milestone 1: Project Foundation

This milestone provides a clean Python package, a Typer CLI, schema checks, and a deterministic synthetic temporal event generator. It does not depend on external datasets or services.

### Install

```bash
python -m pip install -e ".[dev]"
```

### CLI

```bash
feature-store-ops --version
feature-store-ops project-info
feature-store-ops generate-synthetic-events
```

The default generator writes:

- `data/processed/synthetic_events.csv`
- `reports/synthetic_events_summary.md`

Useful options:

```bash
feature-store-ops generate-synthetic-events --events 720 --seed 42
feature-store-ops generate-synthetic-events --start 2026-01-01T00:00:00+00:00
```

Generated rows include:

- `event_id`
- `timestamp`
- `zone_id`
- `user_id`
- `demand_count`
- `hour`
- `day_of_week`
- `is_weekend`
- `base_demand`
- `observed_demand`

### Validate

```bash
pytest -q
ruff check .
```

## Milestone 2: Offline Feature Engineering

This milestone builds the offline feature layer from synthetic events. It uses deterministic chronological train/validation/test splits for temporal data.

### Build Offline Features

```bash
feature-store-ops generate-synthetic-events
feature-store-ops build-offline-features
```

The offline builder reads:

- `data/processed/synthetic_events.csv`

It writes:

- `data/processed/offline_features.parquet`
- `data/processed/train_features.parquet`
- `data/processed/validation_features.parquet`
- `data/processed/test_features.parquet`
- `reports/offline_feature_summary.md`

Offline feature columns include:

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
- `target_next_observed_demand`

Leakage rules:

- Lags and rolling features are grouped by `zone_id` and shifted before aggregation.
- `zone_hour_mean_demand` uses only prior rows for the same zone and hour.
- `target_next_observed_demand` is the next future observed demand for the same zone.
- Splits are chronological, never random.

## Milestone 3: Baseline Model Training

This milestone trains simple demand forecasting models on the offline train split, selects a model with validation metrics, and evaluates the selected model once on the test split.

### Train A Model

```bash
feature-store-ops generate-synthetic-events
feature-store-ops build-offline-features
feature-store-ops train-model
```

The trainer reads:

- `data/processed/train_features.parquet`
- `data/processed/validation_features.parquet`
- `data/processed/test_features.parquet`

It writes ignored model artifacts:

- `artifacts/models/selected_model.joblib`
- `artifacts/models/model_manifest.json`

It writes tracked reports:

- `reports/model_training_summary.md`
- `reports/model_metrics.json`

Candidate models:

- `naive_lag_1`
- `zone_hour_mean`
- `ridge_regression`
- `hist_gradient_boosting`

Metrics include MAE, RMSE, R2, mean prediction, and mean target.

Leakage rules:

- Candidate models train on the train split only.
- Validation metrics select the model.
- Test metrics are computed only once after model selection.
- `target_next_observed_demand` is never included as an input feature.

## Milestone 4: Online Feature Materialization

This milestone adds the first local feature-store layer. It materializes the latest offline feature row per entity and verifies offline/online feature parity without Redis, Postgres, FastAPI, or Docker.

### Materialize Online Features

```bash
feature-store-ops generate-synthetic-events
feature-store-ops build-offline-features
feature-store-ops train-model
feature-store-ops materialize-online-features
```

The materializer reads:

- `data/processed/offline_features.parquet`

It writes ignored local online artifacts:

- `artifacts/online_features/latest_features.json`
- `artifacts/online_features/manifest.json`

It writes a tracked report:

- `reports/online_feature_materialization_summary.md`

Feature contract:

- Entity key: `zone_id`
- As-of timestamp: `timestamp`
- Model input feature columns are shared by offline features, training, and online materialization.
- `target_next_observed_demand` is excluded from online feature snapshots.

Parity rules:

- The latest valid offline feature row is selected per `zone_id`.
- Online rows contain exactly model input features plus entity/as-of metadata.
- Online values are validated against the corresponding latest offline rows.
- The manifest records row count, feature columns, entity keys, as-of column, and source artifact path.

## Milestone 5: Local FastAPI Prediction Service

This milestone adds a local FastAPI serving layer that loads the selected model and online feature snapshot. It stays local and does not require Redis, Postgres, Docker, or a network server for tests.

### Serve Or Smoke Test The API

```bash
feature-store-ops generate-synthetic-events
feature-store-ops build-offline-features
feature-store-ops train-model
feature-store-ops materialize-online-features
feature-store-ops serve-api --smoke-test
```

To run a local server:

```bash
feature-store-ops serve-api --host 127.0.0.1 --port 8000
```

The API loads:

- `artifacts/models/selected_model.joblib`
- `artifacts/models/model_manifest.json`
- `artifacts/online_features/latest_features.json`
- `artifacts/online_features/manifest.json`

Endpoints:

- `GET /health`
- `GET /model`
- `GET /features/{zone_id}`
- `POST /predict`
- `GET /metrics`

Prediction behavior:

- `POST /predict` accepts a `zone_id`.
- The API retrieves the latest online feature row for that zone.
- The selected model receives exactly the shared model input feature columns.
- Responses include prediction, model metadata, as-of timestamp, and feature freshness metadata.

Local metrics:

- Request count
- Prediction count
- Error count
- Average prediction latency in milliseconds

The API smoke test writes:

- `reports/api_serving_summary.md`

## Milestone 6: Prediction Telemetry And Serving Monitoring

This milestone adds durable local JSONL telemetry for prediction requests plus an offline monitoring report over those logs. It still stays local and does not require Redis, Postgres, Docker, or cloud services.

### Simulate Traffic And Monitor Serving

```bash
feature-store-ops generate-synthetic-events
feature-store-ops build-offline-features
feature-store-ops train-model
feature-store-ops materialize-online-features
feature-store-ops serve-api --smoke-test
feature-store-ops simulate-traffic
feature-store-ops monitor-serving
```

Prediction telemetry is written to ignored local logs:

- `logs/predictions.jsonl`

Each JSONL row includes:

- `request_id`
- `timestamp`
- `zone_id`
- `as_of_timestamp`
- `prediction`
- `model_name`
- `model_version`
- `feature_freshness_seconds`
- `latency_ms`
- `status`
- `error_type`

The traffic simulator calls the API in-process for known zones and one unknown zone, producing both success and error telemetry.

Monitoring reads:

- `logs/predictions.jsonl`

It writes tracked reports:

- `reports/serving_monitoring_summary.md`
- `reports/serving_monitoring_metrics.json`

Serving monitoring metrics include total requests, successful and failed predictions, error rate, average and p95 latency, prediction summary statistics, request count by zone, and stale feature count.

Warnings are emitted when error rate, p95 latency, stale feature count, or small prediction sample size crosses configured thresholds.

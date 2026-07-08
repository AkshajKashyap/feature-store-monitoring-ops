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

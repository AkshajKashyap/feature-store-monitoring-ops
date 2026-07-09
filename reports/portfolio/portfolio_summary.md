# Portfolio Summary

This project demonstrates a production-style ML feature store and monitoring system in a deterministic local environment.

## What It Demonstrates

- Deterministic synthetic temporal demand event generation.
- Leakage-safe offline temporal feature engineering and chronological splits.
- Validation-only model selection with one-time test evaluation.
- Online feature materialization with offline/online parity checks.
- Local FastAPI prediction serving with typed request/response schemas.
- Durable JSONL telemetry plus SQLite telemetry storage sync.
- Serving, drift, prediction drift, and data quality monitoring reports.
- Adapter-level Redis-compatible online feature store interface.

## Current Metrics

- Workflow status: passed
- Current workflow preset: `default`
- Selected model: `hist_gradient_boosting`
- Test MAE: 6.29841
- Test RMSE: 7.948043
- Test R2: 0.313692
- Online feature rows: 5
- Simulated prediction requests: 6
- Serving error rate: 0.166667
- Drift warning count: 8
- SQLite telemetry rows: 6

## Reviewer Quickstart

```bash
python -m pip install -e ".[dev]"
make release-check
feature-store-ops run-demo-workflow --preset portfolio
cat reports/portfolio/portfolio_summary.md
```

## Limitations

- Synthetic data only; no external production data source is connected yet.
- Redis support is adapter-level unless a Redis server/client is configured.
- SQLite storage is local development storage, not a production telemetry warehouse.
- FastAPI serving is local; cloud deployment, auth, and autoscaling are intentionally out of scope.
- Models are baseline forecasting models intended to validate the system path, not maximize accuracy.

## Primary Reports

- `reports/portfolio/workflow_summary.md`
- `reports/portfolio/workflow_results.json`
- `reports/portfolio/portfolio_summary.md`
- `reports/portfolio/portfolio_scale_summary.md`
- `reports/model_metrics.json`
- `reports/serving_monitoring_metrics.json`
- `reports/drift_monitoring_metrics.json`

## Demo Paths

- Lightweight default: `feature-store-ops run-demo-workflow`
- Portfolio scale: `feature-store-ops run-demo-workflow --preset portfolio`

# Architecture

Feature Store Monitoring Ops is a deterministic local ML system that mirrors a production feature-store path without requiring external services.

## Components

- Synthetic temporal demand events: deterministic CSV generation with configurable default and portfolio-scale presets.
- Offline feature layer: leakage-safe lag, rolling, zone/hour aggregate, and future target features with chronological splits.
- Model layer: validation-only model selection across simple baselines and sklearn regressors, followed by one-time test evaluation.
- Online feature layer: latest-per-zone materialization with offline/online parity checks and JSON, memory, and Redis-compatible adapters.
- Serving layer: local FastAPI app with optional API key auth, freshness checks, and prediction warning metadata.
- Telemetry and monitoring: JSONL prediction logs, SQLite telemetry sync, serving monitoring, drift checks, and data quality checks.
- Storage layer: SQLAlchemy-backed relational storage for events, offline features, online snapshot metadata, and sync metadata.
- Workflow layer: one-command deterministic demo workflow, release verification, and release gate decisioning.

## Default Local Flow

```text
synthetic events
  -> offline features and temporal splits
  -> model training and validation selection
  -> online feature materialization
  -> FastAPI smoke prediction
  -> telemetry simulation
  -> serving and drift monitoring
  -> storage sync and inspection
  -> relational sync and inspection
  -> release gate decision
```

## Storage Boundaries

- Generated data and artifacts are ignored by git.
- Tracked reports under `reports/` document the latest verified run.
- SQLite is the default durable local storage backend.
- Redis and Postgres are optional adapter/configuration paths, not required dependencies for release checks.

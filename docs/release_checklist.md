# Release Checklist

This checklist covers the current local release-style gate for the Feature Store Monitoring Ops portfolio project.

## Verified By `make release-check`

- Unit tests pass with `pytest -q`.
- Ruff linting passes with `ruff check .`.
- The deterministic demo workflow runs end to end with `feature-store-ops run-demo-workflow`.
- Synthetic temporal demand events are generated locally.
- Offline temporal features and chronological train/validation/test splits are rebuilt.
- Baseline models are trained, selected with validation metrics, and evaluated on test data.
- Latest online features are materialized from offline features.
- The FastAPI prediction service passes an in-process smoke test.
- Deterministic traffic simulation writes prediction telemetry.
- Serving monitoring, drift monitoring, and data quality reports are generated.
- Online feature and telemetry artifacts are synced into configured local storage backends.
- Storage inspection confirms online feature row count, telemetry row count, zone IDs, and telemetry timestamp bounds.
- Synthetic events, offline features, and online snapshot metadata are synced into relational SQLAlchemy storage.
- Relational storage inspection confirms event row count, offline feature row count, online snapshot row count, zone count, and event timestamp bounds.
- Portfolio workflow and summary reports are written under `reports/portfolio/`.

## Optional Docker Checks

- `make docker-build` builds the local API image from `Dockerfile`.
- `make docker-smoke` starts Docker Compose with API + Redis.
- Docker smoke syncs online features into Redis before starting Redis-backed serving.
- Docker smoke checks `/health`, `/model`, `/predict`, and `/metrics` over localhost.
- Docker smoke writes `reports/portfolio/docker_smoke_summary.md`.
- Docker Compose is shut down cleanly by the smoke script.
- Docker Compose includes an optional `postgres` profile for relational storage experiments.

## Optional Portfolio-Scale Check

- `feature-store-ops run-demo-workflow --preset portfolio` runs the larger 50-zone, 30-day local scenario.
- The portfolio-scale run writes `reports/portfolio/portfolio_scale_summary.md`.
- Generated portfolio-scale data, artifacts, logs, and SQLite storage remain ignored by git.

## Intentionally Not Production-Ready Yet

- Docker Compose is local-only and is not a cloud deployment target.
- No Postgres or cloud services are required by default.
- Postgres support is SQLAlchemy URL-compatible, but live Postgres operation is optional and not required by tests.
- Redis support is included for Docker/local adapter smoke testing, not managed production Redis.
- SQLite telemetry and feature-store databases are local durable storage, not production warehouses.
- The model is a baseline forecaster intended to validate the system path, not a tuned production model.
- Authentication, authorization, rate limiting, and network deployment hardening are not implemented yet.
- Monitoring thresholds are local defaults and are not tied to incident response or alert routing.
- Synthetic data is used instead of an external production event source.

## Reviewer Path

```bash
python -m pip install -e ".[dev]"
make release-check
make docker-smoke
cat reports/portfolio/portfolio_summary.md
```

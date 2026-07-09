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
- Portfolio workflow and summary reports are written under `reports/portfolio/`.

## Intentionally Not Production-Ready Yet

- No Docker Compose or container images are included yet.
- No live Redis, Postgres, or cloud services are required by default.
- Redis support is adapter-level unless a Redis server/client is configured.
- SQLite telemetry storage is local durable storage, not a production telemetry warehouse.
- The model is a baseline forecaster intended to validate the system path, not a tuned production model.
- Authentication, authorization, rate limiting, and network deployment hardening are not implemented yet.
- Monitoring thresholds are local defaults and are not tied to incident response or alert routing.
- Synthetic data is used instead of an external production event source.

## Reviewer Path

```bash
python -m pip install -e ".[dev]"
make release-check
cat reports/portfolio/portfolio_summary.md
```

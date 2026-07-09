# Operations

This project is designed to run locally and deterministically on CPU.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Release Checks

```bash
make check
make release-check
make verify-release
feature-store-ops release-gate
```

- `make check` runs pytest with normal and warning-visible modes, then Ruff.
- `make release-check` runs tests, lint, and the default demo workflow.
- `make verify-release` refreshes `reports/portfolio/verification_0.1.0.md` and the release gate reports.
- `feature-store-ops release-gate` evaluates existing metrics and writes a pass/warn/hold decision.

## Demo Workflows

```bash
feature-store-ops run-demo-workflow
feature-store-ops run-demo-workflow --preset portfolio
```

The default workflow is lightweight. The portfolio preset increases temporal and zone coverage while remaining local.

## Optional Local Services

- Docker is optional. Use `make docker-smoke` only when Docker is available.
- Redis serving is optional through `FEATURE_STORE_OPS_ONLINE_BACKEND=redis`.
- Postgres relational storage is optional through `FEATURE_STORE_OPS_RELATIONAL_URL`.

## API Safety Controls

Local mode is unauthenticated by default. Set these environment variables to enable stricter serving behavior:

- `FEATURE_STORE_OPS_API_KEY`: requires `X-API-Key` for API endpoints except `/health`.
- `FEATURE_STORE_OPS_MAX_FEATURE_FRESHNESS_SECONDS`: freshness warning threshold.
- `FEATURE_STORE_OPS_REJECT_STALE_FEATURES`: reject stale feature rows when true.
- `FEATURE_STORE_OPS_MIN_PREDICTION` and `FEATURE_STORE_OPS_MAX_PREDICTION`: prediction warning bounds.
- `FEATURE_STORE_OPS_MAX_REQUEST_BODY_BYTES`: simple request body size limit.

Prediction responses include warning metadata when features are stale or predictions leave the configured expected range.

## Release Gate

The release gate reads model, serving, drift, storage, workflow, and verification evidence. Decisions are:

- `pass`: no hold or warning reasons.
- `warn`: evidence is acceptable for local portfolio review, with known limitations.
- `hold`: required evidence is missing or a hard threshold fails.

The expected v0.1.0 decision is `warn`, because the system uses synthetic data and local-only operations.

## Generated Files

The following remain ignored by git:

- `data/processed/`
- `artifacts/`
- `logs/`
- SQLite database files

Tracked Markdown and JSON reports under `reports/` are intended for review.

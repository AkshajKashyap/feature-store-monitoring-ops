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
```

- `make check` runs pytest with normal and warning-visible modes, then Ruff.
- `make release-check` runs tests, lint, and the default demo workflow.
- `make verify-release` refreshes `reports/portfolio/verification_0.1.0.md`.

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

## Generated Files

The following remain ignored by git:

- `data/processed/`
- `artifacts/`
- `logs/`
- SQLite database files

Tracked Markdown and JSON reports under `reports/` are intended for review.

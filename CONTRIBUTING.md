# Contributing

This repository is currently shaped as a portfolio/local-ops project. Contributions should preserve the deterministic local workflow and avoid adding external service requirements to the default test path.

## Local Setup

```bash
python -m pip install -e ".[dev]"
```

## Checks

Run these before proposing changes:

```bash
pytest -q
pytest -q -W default
ruff check .
make release-check
make verify-release
```

## Guidelines

- Keep default behavior CPU-only, deterministic, and local.
- Do not require Docker, Redis, Postgres, or cloud services for tests.
- Keep generated data, artifacts, logs, model files, and local databases out of git.
- Do not claim production readiness unless the release gate and docs support it.
- Prefer small modules, type hints, and narrow tests for the behavior changed.

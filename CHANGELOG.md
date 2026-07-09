# Changelog

All notable changes to this project are documented here.

## 0.1.0 - 2026-07-09

Initial portfolio/local-ops release.

### Added

- Deterministic synthetic temporal demand event generation with lightweight and portfolio-scale presets.
- Leakage-safe offline feature engineering with chronological train/validation/test splits.
- Validation-only model selection and one-time test evaluation for baseline demand forecasting models.
- Online feature materialization with offline/online feature parity checks.
- Local FastAPI prediction API with optional API key auth, request validation, feature freshness checks, and prediction warning metadata.
- Durable JSONL prediction telemetry, serving monitoring, drift monitoring, and data quality checks.
- JSON, in-memory, Redis-compatible, SQLite telemetry, and SQLAlchemy relational storage paths.
- One-command demo workflow, release verification report, GitHub Actions CI, and release gate reports.
- Docker Compose API + Redis local ops path, with Docker kept optional for release checks.

### Release Status

- `pytest -q`: passing.
- `pytest -q -W default`: passing with no warning noise.
- `ruff check .`: passing.
- `make release-check`: passing.
- `make verify-release`: passing.
- Release gate decision: `warn`.

### Production-Readiness Boundary

v0.1.0 is ready for portfolio review and local deterministic demonstration. It is not a production deployment: data is synthetic, serving is local, Docker/Redis/Postgres are optional, and full production controls such as identity, rate limiting, alerting, and cloud deployment are intentionally out of scope.

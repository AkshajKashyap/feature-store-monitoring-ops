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

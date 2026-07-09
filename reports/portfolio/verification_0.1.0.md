# Release Verification 0.1.0

Tracked release-quality verification report for the local deterministic system.

## Check Results

- `pytest -q`: passed (7.386s)
- `pytest -q -W default`: passed (7.097s)
- Warning status: clean: no warnings emitted
- `ruff check .`: passed (0.024s)
- Demo workflow: passed
- Docker availability: unavailable: The command 'docker' could not be found in this WSL 2 distro.

## Default Workflow Counts

- Synthetic rows: 720
- Offline feature rows: 595
- Online feature rows: 5
- Simulated prediction requests: 6
- SQLite telemetry rows: 6
- Relational event rows: 720
- Relational offline feature rows: 595
- Relational online snapshot rows: 5

## Portfolio-Scale Counts

- Synthetic Rows: 3000
- Configured Zones: 50
- Offline Feature Rows: 2800
- Online Feature Rows: 50
- Simulated Prediction Requests: 120
- Relational Event Rows: 3000
- Relational Offline Feature Rows: 2800
- Relational Online Snapshot Rows: 50

## Warning Policy

- Project-owned warnings fail tests through pytest warning filters.
- Known third-party deprecations are filtered narrowly by message, category, and module.
- The verification command records the visible-warning pytest result so new warning noise is caught.

## Known Limitations

- Synthetic data only; no external production event source is connected.
- FastAPI serving is local and does not include auth, rate limiting, or cloud deployment.
- Redis and Postgres paths are optional adapters and are not required by release checks.
- SQLite databases are local development stores, not production warehouses.
- Models are deterministic baselines for system validation, not tuned production forecasts.
- Docker smoke testing is optional and depends on local Docker availability.

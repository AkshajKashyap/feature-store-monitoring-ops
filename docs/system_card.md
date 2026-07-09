# System Card

## Purpose

Feature Store Monitoring Ops demonstrates a local production-style ML system path for temporal demand forecasting, feature parity, prediction serving, telemetry, monitoring, and storage verification.

## Intended Use

- Portfolio review of ML platform and MLOps engineering patterns.
- Local experimentation with deterministic synthetic temporal data.
- Demonstration of offline/online feature parity and monitoring workflows.

## Not Intended For

- Real production predictions.
- Safety-critical, financial, medical, or operational decision-making.
- Cloud deployment without additional hardening.

## Data

The system uses synthetic temporal demand events only. No external or sensitive datasets are required.

## Model

The selected model is chosen by validation metrics from simple deterministic candidates. It is intended to validate the system path, not maximize forecast accuracy.

## Monitoring

The project includes local serving telemetry, serving health metrics, feature drift checks, prediction drift checks, and data quality checks. Thresholds are local defaults and are not connected to alerting or incident response.

## API Safety Controls

The API supports optional API key authentication, request body size limits, feature freshness warnings or rejection, and prediction range warnings. These controls make local serving safer to inspect, but they are not a substitute for production gateway, identity, audit, or network controls.

## Release Gate

The release gate produces `pass`, `warn`, or `hold` decisions from tracked evidence. v0.1.0 is expected to be `warn`: the system is credible as a local portfolio and operations demo, but it is not production-hosted and uses synthetic evidence.

## Limitations

- Synthetic data may not reflect real-world seasonality, outages, or feedback loops.
- Local FastAPI serving has optional API key auth, but no full identity, authorization, or rate limiting.
- SQLite, JSON, Redis adapter, and Postgres-compatible paths are development-oriented.
- Docker, Redis, and Postgres are optional and not required for release checks.
- v0.1.0 is portfolio/local ops, not a production deployment.

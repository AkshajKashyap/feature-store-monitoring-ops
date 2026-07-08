# Feature Store Monitoring Ops

Production-style ML feature store and monitoring system with offline/online feature parity, Redis/Postgres serving, FastAPI predictions, drift detection, and Dockerized local ops.

## Goal

Build an end-to-end ML system around real temporal event data:
data ingestion -> offline features -> online feature store -> model training -> prediction API -> telemetry -> monitoring -> release gate.

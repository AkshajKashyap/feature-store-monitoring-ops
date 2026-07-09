# Release Gate 0.1.0

Operational release gate for the local portfolio release.

- Decision: `warn`
- Report: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/release_gate_0.1.0.md`
- Metrics JSON: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/release_gate_0.1.0.json`

## Evidence Summary

- Selected model: `hist_gradient_boosting`
- Test MAE: 6.29841
- Serving error rate: 0.166667
- Serving p95 latency ms: 30.451557
- Successful predictions: 5
- Drift warning count: 8
- Storage inspection available: True
- Verification status: available
- Docker availability: unavailable: The command 'docker' could not be found in this WSL 2 distro.

## Hold Reasons

- None.

## Warning Reasons

- Synthetic data only; no external production event source is connected.
- Local API is not production-hosted and has no deployment hardening.
- Serving error rate is nonzero (0.167).
- Successful prediction sample is small (5 < 10).
- Drift monitoring produced 8 warning(s).
- Docker is unavailable in this environment.

## Production-Readiness Boundary

- v0.1.0 is a deterministic local portfolio and operations demo.
- It is not a production deployment and does not claim production readiness.
- A `warn` decision is expected while evidence remains synthetic/local.

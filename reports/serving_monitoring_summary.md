# Serving Monitoring Summary

Offline monitoring over persisted local prediction telemetry for Milestone 6.

## Source

- Prediction log: `/home/akshaj/Building/feature-store-monitoring-ops/logs/predictions.jsonl`

## Metrics

- Total requests: 6
- Successful predictions: 5
- Failed predictions: 1
- Error rate: 0.167
- Average latency ms: 8.924492
- P95 latency ms: 13.926304
- Mean prediction: 28.197380
- Min prediction: 20.803178
- Max prediction: 34.800668
- Stale feature count: 0

## Request Count By Zone

- `unknown_zone`: 1
- `zone_01`: 1
- `zone_02`: 1
- `zone_03`: 1
- `zone_04`: 1
- `zone_05`: 1

## Thresholds

- Error rate: 0.100
- P95 latency ms: 250.000
- Feature freshness seconds: 172800.000
- Minimum prediction count: 10

## Warnings

- WARNING: Error rate 0.167 exceeds threshold 0.100.
- WARNING: Prediction count is too small to trust (5 < 10).

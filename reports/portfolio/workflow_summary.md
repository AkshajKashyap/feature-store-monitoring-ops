# Workflow Summary

One-command local demo workflow for Milestone 9.

- Overall status: passed
- Preset: `default`

## Stages

| Stage | Status | Key Metrics | Error |
| --- | --- | --- | --- |
| `generate_synthetic_events` | passed | `rows_written`=720, `seed`=42, `preset`=default, `zone_count`=5 |  |
| `build_offline_features` | passed | `offline`=595, `train`=416, `validation`=89, `test`=90 |  |
| `train_model` | passed | `selected_model`=hist_gradient_boosting, `test_mae`=6.29841, `test_rmse`=7.948043, `test_r2`=0.313692 |  |
| `materialize_online_features` | passed | `row_count`=5 |  |
| `api_smoke_test` | passed | `zone_id`=zone_01, `prediction`=20.803178, `smoke_test_passed`=True |  |
| `simulate_traffic` | passed | `total_requests`=6, `successful_requests`=5, `failed_requests`=1, `zones_requested`=['zone_01', 'zone_02', 'zone_03', 'zone_04', 'zone_05', 'unknown_zone'] |  |
| `monitor_serving` | passed | `total_requests`=6, `successful_predictions`=5, `failed_predictions`=1, `error_rate`=0.166667 |  |
| `monitor_drift` | passed | `reference_rows`=416, `current_rows`=90, `prediction_count`=5, `max_psi`=5.118269 |  |
| `sync_storage` | passed | `online_feature_row_count`=5, `telemetry_source_row_count`=6, `telemetry_store_row_count`=6, `zone_ids`=['zone_01', 'zone_02', 'zone_03', 'zone_04', 'zone_05'] |  |
| `inspect_storage` | passed | `online_feature_row_count`=5, `telemetry_row_count`=6, `zone_ids`=['zone_01', 'zone_02', 'zone_03', 'zone_04', 'zone_05'], `min_telemetry_timestamp`=2026-02-01T00:00:00+00:00 |  |

## Portfolio Outputs

- `workflow_summary`: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/workflow_summary.md`
- `workflow_results`: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/workflow_results.json`
- `portfolio_summary`: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/portfolio_summary.md`
- `portfolio_scale_summary`: `/home/akshaj/Building/feature-store-monitoring-ops/reports/portfolio/portfolio_scale_summary.md`

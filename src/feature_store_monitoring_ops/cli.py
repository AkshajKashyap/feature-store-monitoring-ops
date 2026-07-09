"""Typer command line interface for feature store monitoring ops."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.api.app import (
    create_app as create_api_app,
    run_api_traffic_simulation,
    run_api_smoke_test,
    write_api_serving_report,
)
from feature_store_monitoring_ops.api.service import ServingArtifacts
from feature_store_monitoring_ops.features.offline import build_and_save_offline_features
from feature_store_monitoring_ops.features.online import materialize_online_features
from feature_store_monitoring_ops.models.training import train_and_evaluate_models
from feature_store_monitoring_ops.monitoring.drift import (
    DriftMonitoringThresholds,
    monitor_drift,
)
from feature_store_monitoring_ops.monitoring.serving import (
    ServingMonitoringThresholds,
    monitor_prediction_logs,
)
from feature_store_monitoring_ops.monitoring.telemetry import (
    IncrementingClock,
    PredictionTelemetryLogger,
    reset_prediction_log,
)
from feature_store_monitoring_ops.paths import (
    DEFAULT_API_SERVING_REPORT_PATH,
    DEFAULT_DRIFT_MONITORING_METRICS_PATH,
    DEFAULT_DRIFT_MONITORING_REPORT_PATH,
    DEFAULT_MODEL_MANIFEST_PATH,
    DEFAULT_MODEL_METRICS_PATH,
    DEFAULT_MODEL_TRAINING_REPORT_PATH,
    DEFAULT_OFFLINE_FEATURE_REPORT_PATH,
    DEFAULT_OFFLINE_FEATURES_PATH,
    DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    DEFAULT_ONLINE_FEATURE_REPORT_PATH,
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_PREDICTION_LOG_PATH,
    DEFAULT_RELATIONAL_DB_PATH,
    DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH,
    DEFAULT_RELATIONAL_STORAGE_SYNC_REPORT_PATH,
    DEFAULT_PORTFOLIO_SCALE_SUMMARY_PATH,
    DEFAULT_PORTFOLIO_SUMMARY_PATH,
    DEFAULT_SELECTED_MODEL_PATH,
    DEFAULT_SERVING_MONITORING_METRICS_PATH,
    DEFAULT_SERVING_MONITORING_REPORT_PATH,
    DEFAULT_SQLITE_TELEMETRY_DB_PATH,
    DEFAULT_STORAGE_INSPECTION_REPORT_PATH,
    DEFAULT_STORAGE_SYNC_REPORT_PATH,
    DEFAULT_SYNTHETIC_EVENTS_PATH,
    DEFAULT_SYNTHETIC_REPORT_PATH,
    DEFAULT_TEST_FEATURES_PATH,
    DEFAULT_TRAIN_FEATURES_PATH,
    DEFAULT_VALIDATION_FEATURES_PATH,
    DEFAULT_WORKFLOW_RESULTS_PATH,
    DEFAULT_WORKFLOW_SUMMARY_PATH,
    PROJECT_ROOT,
)
from feature_store_monitoring_ops.storage.config import StorageConfig
from feature_store_monitoring_ops.storage.relational import (
    inspect_relational_store,
    sync_relational_store,
)
from feature_store_monitoring_ops.storage.sync import inspect_storage, sync_storage
from feature_store_monitoring_ops.synthetic_events import (
    SYNTHETIC_PRESETS,
    build_synthetic_event_config,
    generate_and_save_synthetic_events,
    parse_start_timestamp,
)
from feature_store_monitoring_ops.workflow import DemoWorkflowConfig, run_demo_workflow

APP_NAME = "feature-store-monitoring-ops"

app = typer.Typer(
    help="Local utilities for the Feature Store Monitoring Ops project.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{APP_NAME} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the CLI version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run project CLI commands."""


@app.command("project-info")
def project_info() -> None:
    """Print basic project metadata and default local artifact paths."""

    typer.echo(f"name: {APP_NAME}")
    typer.echo(f"version: {__version__}")
    typer.echo(f"project_root: {PROJECT_ROOT}")
    typer.echo(f"synthetic_events_path: {DEFAULT_SYNTHETIC_EVENTS_PATH}")
    typer.echo(f"synthetic_report_path: {DEFAULT_SYNTHETIC_REPORT_PATH}")
    typer.echo(f"offline_features_path: {DEFAULT_OFFLINE_FEATURES_PATH}")
    typer.echo(f"train_features_path: {DEFAULT_TRAIN_FEATURES_PATH}")
    typer.echo(f"validation_features_path: {DEFAULT_VALIDATION_FEATURES_PATH}")
    typer.echo(f"test_features_path: {DEFAULT_TEST_FEATURES_PATH}")
    typer.echo(f"offline_feature_report_path: {DEFAULT_OFFLINE_FEATURE_REPORT_PATH}")
    typer.echo(f"selected_model_path: {DEFAULT_SELECTED_MODEL_PATH}")
    typer.echo(f"model_manifest_path: {DEFAULT_MODEL_MANIFEST_PATH}")
    typer.echo(f"model_training_report_path: {DEFAULT_MODEL_TRAINING_REPORT_PATH}")
    typer.echo(f"model_metrics_path: {DEFAULT_MODEL_METRICS_PATH}")
    typer.echo(f"online_feature_snapshot_path: {DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH}")
    typer.echo(f"online_feature_manifest_path: {DEFAULT_ONLINE_FEATURE_MANIFEST_PATH}")
    typer.echo(f"online_feature_report_path: {DEFAULT_ONLINE_FEATURE_REPORT_PATH}")
    typer.echo(f"api_serving_report_path: {DEFAULT_API_SERVING_REPORT_PATH}")
    typer.echo(f"prediction_log_path: {DEFAULT_PREDICTION_LOG_PATH}")
    typer.echo(f"serving_monitoring_report_path: {DEFAULT_SERVING_MONITORING_REPORT_PATH}")
    typer.echo(f"serving_monitoring_metrics_path: {DEFAULT_SERVING_MONITORING_METRICS_PATH}")
    typer.echo(f"drift_monitoring_report_path: {DEFAULT_DRIFT_MONITORING_REPORT_PATH}")
    typer.echo(f"drift_monitoring_metrics_path: {DEFAULT_DRIFT_MONITORING_METRICS_PATH}")
    typer.echo(f"sqlite_telemetry_db_path: {DEFAULT_SQLITE_TELEMETRY_DB_PATH}")
    typer.echo(f"relational_db_path: {DEFAULT_RELATIONAL_DB_PATH}")
    typer.echo(f"storage_sync_report_path: {DEFAULT_STORAGE_SYNC_REPORT_PATH}")
    typer.echo(f"storage_inspection_report_path: {DEFAULT_STORAGE_INSPECTION_REPORT_PATH}")
    typer.echo(f"relational_storage_sync_report_path: {DEFAULT_RELATIONAL_STORAGE_SYNC_REPORT_PATH}")
    typer.echo(
        "relational_storage_inspection_report_path: "
        f"{DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH}",
    )
    typer.echo(f"workflow_summary_path: {DEFAULT_WORKFLOW_SUMMARY_PATH}")
    typer.echo(f"workflow_results_path: {DEFAULT_WORKFLOW_RESULTS_PATH}")
    typer.echo(f"portfolio_summary_path: {DEFAULT_PORTFOLIO_SUMMARY_PATH}")
    typer.echo(f"portfolio_scale_summary_path: {DEFAULT_PORTFOLIO_SCALE_SUMMARY_PATH}")


@app.command("generate-synthetic-events")
def generate_synthetic_events_command(
    preset: Annotated[
        str,
        typer.Option("--preset", help=f"Synthetic scale preset: {', '.join(SYNTHETIC_PRESETS)}."),
    ] = "default",
    events: Annotated[
        int | None,
        typer.Option("--events", help="Number of synthetic event rows to generate."),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Random seed used for deterministic generation."),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 start timestamp for the generated series."),
    ] = "2026-01-01T00:00:00+00:00",
    interval_minutes: Annotated[
        int | None,
        typer.Option("--interval-minutes", help="Minutes between generated event timestamps."),
    ] = None,
    zones: Annotated[
        int | None,
        typer.Option("--zones", help="Number of zone IDs to sample."),
    ] = None,
    users: Annotated[
        int | None,
        typer.Option("--users", help="Number of user IDs to sample."),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option("--days", help="Number of days for deterministic zone/day grid generation."),
    ] = None,
    events_per_zone_per_day: Annotated[
        int | None,
        typer.Option(
            "--events-per-zone-per-day",
            help="Rows per zone per day for deterministic zone/day grid generation.",
        ),
    ] = None,
    output_path: Annotated[
        Path,
        typer.Option("--output-path", help="CSV path for generated synthetic events."),
    ] = DEFAULT_SYNTHETIC_EVENTS_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Markdown summary report path."),
    ] = DEFAULT_SYNTHETIC_REPORT_PATH,
) -> None:
    """Generate deterministic synthetic temporal demand events."""

    try:
        config = build_synthetic_event_config(
            preset=preset,
            num_events=events,
            seed=seed,
            start_timestamp=parse_start_timestamp(start),
            interval_minutes=interval_minutes,
            zone_count=zones,
            user_count=users,
            num_days=days,
            events_per_zone_per_day=events_per_zone_per_day,
        )
        result = generate_and_save_synthetic_events(
            config=config,
            output_path=output_path,
            report_path=report_path,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"wrote {result.rows_written} synthetic events to {result.csv_path}")
    typer.echo(f"wrote summary report to {result.report_path}")


@app.command("build-offline-features")
def build_offline_features_command(
    input_path: Annotated[
        Path,
        typer.Option("--input-path", help="CSV path for synthetic events."),
    ] = DEFAULT_SYNTHETIC_EVENTS_PATH,
    output_path: Annotated[
        Path,
        typer.Option("--output-path", help="Parquet path for all offline feature rows."),
    ] = DEFAULT_OFFLINE_FEATURES_PATH,
    train_path: Annotated[
        Path,
        typer.Option("--train-path", help="Parquet path for train feature rows."),
    ] = DEFAULT_TRAIN_FEATURES_PATH,
    validation_path: Annotated[
        Path,
        typer.Option("--validation-path", help="Parquet path for validation feature rows."),
    ] = DEFAULT_VALIDATION_FEATURES_PATH,
    test_path: Annotated[
        Path,
        typer.Option("--test-path", help="Parquet path for test feature rows."),
    ] = DEFAULT_TEST_FEATURES_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Markdown offline feature summary path."),
    ] = DEFAULT_OFFLINE_FEATURE_REPORT_PATH,
    train_fraction: Annotated[
        float,
        typer.Option("--train-fraction", help="Chronological fraction assigned to train."),
    ] = 0.70,
    validation_fraction: Annotated[
        float,
        typer.Option(
            "--validation-fraction",
            help="Chronological fraction assigned to validation.",
        ),
    ] = 0.15,
) -> None:
    """Build deterministic offline temporal features and chronological splits."""

    try:
        result = build_and_save_offline_features(
            input_path=input_path,
            offline_features_path=output_path,
            train_features_path=train_path,
            validation_features_path=validation_path,
            test_features_path=test_path,
            report_path=report_path,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"wrote {result.row_counts['offline']} offline feature rows to {output_path}")
    typer.echo(f"wrote {result.row_counts['train']} train rows to {train_path}")
    typer.echo(f"wrote {result.row_counts['validation']} validation rows to {validation_path}")
    typer.echo(f"wrote {result.row_counts['test']} test rows to {test_path}")
    typer.echo(f"wrote summary report to {report_path}")


@app.command("train-model")
def train_model_command(
    train_path: Annotated[
        Path,
        typer.Option("--train-path", help="Parquet path for train feature rows."),
    ] = DEFAULT_TRAIN_FEATURES_PATH,
    validation_path: Annotated[
        Path,
        typer.Option("--validation-path", help="Parquet path for validation feature rows."),
    ] = DEFAULT_VALIDATION_FEATURES_PATH,
    test_path: Annotated[
        Path,
        typer.Option("--test-path", help="Parquet path for test feature rows."),
    ] = DEFAULT_TEST_FEATURES_PATH,
    model_path: Annotated[
        Path,
        typer.Option("--model-path", help="Joblib path for the selected model artifact."),
    ] = DEFAULT_SELECTED_MODEL_PATH,
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest-path", help="JSON path for the selected model manifest."),
    ] = DEFAULT_MODEL_MANIFEST_PATH,
    metrics_path: Annotated[
        Path,
        typer.Option("--metrics-path", help="Tracked JSON path for model metrics."),
    ] = DEFAULT_MODEL_METRICS_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown model training summary path."),
    ] = DEFAULT_MODEL_TRAINING_REPORT_PATH,
    random_state: Annotated[
        int,
        typer.Option("--random-state", help="Random state for deterministic sklearn models."),
    ] = 42,
) -> None:
    """Train baseline demand models and evaluate the validation-selected model."""

    try:
        result = train_and_evaluate_models(
            train_path=train_path,
            validation_path=validation_path,
            test_path=test_path,
            model_path=model_path,
            manifest_path=manifest_path,
            metrics_path=metrics_path,
            report_path=report_path,
            random_state=random_state,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"selected model: {result.selected_model_name}")
    typer.echo(f"test mae: {result.test_metrics['mae']:.6f}")
    typer.echo(f"test rmse: {result.test_metrics['rmse']:.6f}")
    typer.echo(f"test r2: {result.test_metrics['r2']:.6f}")
    typer.echo(f"wrote selected model to {result.model_path}")
    typer.echo(f"wrote model manifest to {result.manifest_path}")
    typer.echo(f"wrote metrics to {result.metrics_path}")
    typer.echo(f"wrote summary report to {result.report_path}")


@app.command("materialize-online-features")
def materialize_online_features_command(
    source_path: Annotated[
        Path,
        typer.Option("--source-path", help="Parquet path for all offline feature rows."),
    ] = DEFAULT_OFFLINE_FEATURES_PATH,
    snapshot_path: Annotated[
        Path,
        typer.Option("--snapshot-path", help="JSON path for the latest online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest-path", help="JSON path for online feature manifest metadata."),
    ] = DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown online materialization report path."),
    ] = DEFAULT_ONLINE_FEATURE_REPORT_PATH,
) -> None:
    """Materialize latest offline feature rows into a local online feature snapshot."""

    try:
        result = materialize_online_features(
            source_path=source_path,
            snapshot_path=snapshot_path,
            manifest_path=manifest_path,
            report_path=report_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"wrote {result.row_count} online feature rows to {result.snapshot_path}")
    typer.echo(f"wrote online feature manifest to {result.manifest_path}")
    typer.echo(f"wrote summary report to {result.report_path}")


@app.command("serve-api")
def serve_api_command(
    model_path: Annotated[
        Path,
        typer.Option("--model-path", help="Joblib path for the selected model artifact."),
    ] = DEFAULT_SELECTED_MODEL_PATH,
    model_manifest_path: Annotated[
        Path,
        typer.Option("--model-manifest-path", help="JSON path for selected model manifest."),
    ] = DEFAULT_MODEL_MANIFEST_PATH,
    feature_snapshot_path: Annotated[
        Path,
        typer.Option("--feature-snapshot-path", help="JSON path for online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    feature_manifest_path: Annotated[
        Path,
        typer.Option("--feature-manifest-path", help="JSON path for online feature manifest."),
    ] = DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown API serving report path."),
    ] = DEFAULT_API_SERVING_REPORT_PATH,
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    host: Annotated[
        str,
        typer.Option("--host", help="Host for local Uvicorn serving."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Port for local Uvicorn serving."),
    ] = 8000,
    smoke_test: Annotated[
        bool,
        typer.Option("--smoke-test", help="Run an in-process API smoke test and exit."),
    ] = False,
) -> None:
    """Serve the local FastAPI prediction API."""

    artifacts = ServingArtifacts(
        model_path=model_path,
        model_manifest_path=model_manifest_path,
        feature_snapshot_path=feature_snapshot_path,
        feature_manifest_path=feature_manifest_path,
    )
    api_app = create_api_app(artifacts=artifacts, telemetry_log_path=telemetry_log_path)

    if smoke_test:
        try:
            result = run_api_smoke_test(api_app)
        except RuntimeError as exc:
            write_api_serving_report(api_app, report_path=report_path, smoke_test_passed=False)
            raise typer.BadParameter(str(exc)) from exc
        write_api_serving_report(api_app, report_path=report_path, smoke_test_passed=True)
        typer.echo("api smoke test passed")
        typer.echo(f"smoke test zone_id: {result['zone_id']}")
        typer.echo(f"smoke test prediction: {result['prediction']}")
        typer.echo(f"wrote summary report to {report_path}")
        return

    write_api_serving_report(api_app, report_path=report_path, smoke_test_passed=None)
    typer.echo(f"serving API on http://{host}:{port}")
    import uvicorn

    uvicorn.run(api_app, host=host, port=port)


@app.command("simulate-traffic")
def simulate_traffic_command(
    model_path: Annotated[
        Path,
        typer.Option("--model-path", help="Joblib path for the selected model artifact."),
    ] = DEFAULT_SELECTED_MODEL_PATH,
    model_manifest_path: Annotated[
        Path,
        typer.Option("--model-manifest-path", help="JSON path for selected model manifest."),
    ] = DEFAULT_MODEL_MANIFEST_PATH,
    feature_snapshot_path: Annotated[
        Path,
        typer.Option("--feature-snapshot-path", help="JSON path for online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    feature_manifest_path: Annotated[
        Path,
        typer.Option("--feature-manifest-path", help="JSON path for online feature manifest."),
    ] = DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    base_timestamp: Annotated[
        str,
        typer.Option("--base-timestamp", help="ISO timestamp for deterministic simulated logs."),
    ] = "2026-02-01T00:00:00+00:00",
    unknown_zone_id: Annotated[
        str,
        typer.Option("--unknown-zone-id", help="Unknown zone used to generate an error log."),
    ] = "unknown_zone",
    requests: Annotated[
        int | None,
        typer.Option("--requests", help="Total simulated prediction requests, including one error."),
    ] = None,
    reset_log: Annotated[
        bool,
        typer.Option("--reset-log/--append-log", help="Reset telemetry log before simulation."),
    ] = True,
) -> None:
    """Generate deterministic local prediction telemetry with in-process API calls."""

    if reset_log:
        reset_prediction_log(telemetry_log_path)
    artifacts = ServingArtifacts(
        model_path=model_path,
        model_manifest_path=model_manifest_path,
        feature_snapshot_path=feature_snapshot_path,
        feature_manifest_path=feature_manifest_path,
    )
    logger = PredictionTelemetryLogger(
        log_path=telemetry_log_path,
        now_fn=IncrementingClock(_parse_cli_timestamp(base_timestamp)),
    )
    api_app = create_api_app(artifacts=artifacts, telemetry_logger=logger)
    try:
        result = run_api_traffic_simulation(
            api_app,
            unknown_zone_id=unknown_zone_id,
            request_count=requests,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"simulated {result.total_requests} prediction requests")
    typer.echo(f"successful requests: {result.successful_requests}")
    typer.echo(f"failed requests: {result.failed_requests}")
    typer.echo(f"wrote telemetry to {result.log_path}")


@app.command("monitor-serving")
def monitor_serving_command(
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown serving monitoring report path."),
    ] = DEFAULT_SERVING_MONITORING_REPORT_PATH,
    metrics_path: Annotated[
        Path,
        typer.Option("--metrics-path", help="Tracked JSON serving monitoring metrics path."),
    ] = DEFAULT_SERVING_MONITORING_METRICS_PATH,
    error_rate_threshold: Annotated[
        float,
        typer.Option("--error-rate-threshold", help="Warning threshold for serving error rate."),
    ] = 0.10,
    p95_latency_threshold_ms: Annotated[
        float,
        typer.Option("--p95-latency-threshold-ms", help="Warning threshold for p95 latency."),
    ] = 250.0,
    freshness_threshold_seconds: Annotated[
        float,
        typer.Option("--freshness-threshold-seconds", help="Warning threshold for stale features."),
    ] = 172800.0,
    min_prediction_count: Annotated[
        int,
        typer.Option("--min-prediction-count", help="Warning threshold for small samples."),
    ] = 10,
) -> None:
    """Build an offline serving monitoring report from prediction telemetry logs."""

    thresholds = ServingMonitoringThresholds(
        error_rate=error_rate_threshold,
        p95_latency_ms=p95_latency_threshold_ms,
        freshness_seconds=freshness_threshold_seconds,
        min_prediction_count=min_prediction_count,
    )
    result = monitor_prediction_logs(
        log_path=telemetry_log_path,
        report_path=report_path,
        metrics_path=metrics_path,
        thresholds=thresholds,
    )
    typer.echo(f"monitored {result.metrics['total_requests']} prediction requests")
    typer.echo(f"error rate: {result.metrics['error_rate']:.6f}")
    typer.echo(f"warnings: {len(result.warnings)}")
    typer.echo(f"wrote serving monitoring report to {result.report_path}")
    typer.echo(f"wrote serving monitoring metrics to {result.metrics_path}")


@app.command("monitor-drift")
def monitor_drift_command(
    reference_path: Annotated[
        Path,
        typer.Option("--reference-path", help="Reference feature window parquet or JSON path."),
    ] = DEFAULT_TRAIN_FEATURES_PATH,
    current_path: Annotated[
        Path,
        typer.Option("--current-path", help="Current feature window parquet or JSON path."),
    ] = DEFAULT_TEST_FEATURES_PATH,
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    model_metrics_path: Annotated[
        Path,
        typer.Option("--model-metrics-path", help="Model metrics JSON used as prediction reference."),
    ] = DEFAULT_MODEL_METRICS_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown drift monitoring report path."),
    ] = DEFAULT_DRIFT_MONITORING_REPORT_PATH,
    metrics_path: Annotated[
        Path,
        typer.Option("--metrics-path", help="Tracked JSON drift monitoring metrics path."),
    ] = DEFAULT_DRIFT_MONITORING_METRICS_PATH,
    psi_threshold: Annotated[
        float,
        typer.Option("--psi-threshold", help="Warning threshold for feature PSI."),
    ] = 0.20,
    prediction_mean_shift_threshold: Annotated[
        float,
        typer.Option(
            "--prediction-mean-shift-threshold",
            help="Warning threshold for absolute prediction mean shift.",
        ),
    ] = 5.0,
    min_prediction_count: Annotated[
        int,
        typer.Option("--min-prediction-count", help="Warning threshold for small prediction logs."),
    ] = 10,
) -> None:
    """Build feature drift, prediction drift, and data quality monitoring outputs."""

    thresholds = DriftMonitoringThresholds(
        psi=psi_threshold,
        prediction_mean_shift=prediction_mean_shift_threshold,
        min_prediction_count=min_prediction_count,
    )
    try:
        result = monitor_drift(
            reference_path=reference_path,
            current_path=current_path,
            telemetry_log_path=telemetry_log_path,
            model_metrics_path=model_metrics_path,
            report_path=report_path,
            metrics_path=metrics_path,
            thresholds=thresholds,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    psi_values = [
        float(values["psi"])
        for values in result.metrics["numeric_feature_drift"].values()
        if values["psi"] is not None
    ]
    typer.echo(
        "monitored feature drift rows: "
        f"reference={result.metrics['row_counts']['reference']} "
        f"current={result.metrics['row_counts']['current']}",
    )
    if psi_values:
        typer.echo(f"max feature psi: {max(psi_values):.6f}")
    typer.echo(f"prediction drift count: {result.metrics['prediction_drift']['count']}")
    typer.echo(f"warnings: {len(result.warnings)}")
    typer.echo(f"wrote drift monitoring report to {result.report_path}")
    typer.echo(f"wrote drift monitoring metrics to {result.metrics_path}")


@app.command("sync-storage")
def sync_storage_command(
    feature_snapshot_path: Annotated[
        Path,
        typer.Option("--feature-snapshot-path", help="JSON path for online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown storage sync report path."),
    ] = DEFAULT_STORAGE_SYNC_REPORT_PATH,
    online_backend: Annotated[
        str | None,
        typer.Option("--online-backend", help="Online feature backend: json, memory, or redis."),
    ] = None,
    telemetry_backend: Annotated[
        str | None,
        typer.Option("--telemetry-backend", help="Telemetry backend: jsonl or sqlite."),
    ] = None,
    sqlite_path: Annotated[
        Path | None,
        typer.Option("--sqlite-path", help="SQLite telemetry database path."),
    ] = None,
    redis_url: Annotated[
        str | None,
        typer.Option("--redis-url", help="Redis URL for the Redis online feature adapter."),
    ] = None,
) -> None:
    """Sync local feature and telemetry artifacts into configured storage backends."""

    try:
        config = _storage_config_from_options(
            online_backend=online_backend,
            telemetry_backend=telemetry_backend,
            sqlite_path=sqlite_path,
            redis_url=redis_url,
        )
        result = sync_storage(
            config=config,
            feature_snapshot_path=feature_snapshot_path,
            telemetry_log_path=telemetry_log_path,
            report_path=report_path,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"online backend: {result.online_backend}")
    typer.echo(f"telemetry backend: {result.telemetry_backend}")
    typer.echo(f"synced online feature rows: {result.online_feature_row_count}")
    typer.echo(f"synced telemetry rows: {result.telemetry_store_row_count}")
    typer.echo(f"available zone ids: {', '.join(result.zone_ids)}")
    typer.echo(f"wrote storage sync report to {result.report_path}")


@app.command("inspect-storage")
def inspect_storage_command(
    feature_snapshot_path: Annotated[
        Path,
        typer.Option("--feature-snapshot-path", help="JSON path for online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    telemetry_log_path: Annotated[
        Path,
        typer.Option("--telemetry-log-path", help="JSONL prediction telemetry log path."),
    ] = DEFAULT_PREDICTION_LOG_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown storage inspection report path."),
    ] = DEFAULT_STORAGE_INSPECTION_REPORT_PATH,
    online_backend: Annotated[
        str | None,
        typer.Option("--online-backend", help="Online feature backend: json, memory, or redis."),
    ] = None,
    telemetry_backend: Annotated[
        str | None,
        typer.Option("--telemetry-backend", help="Telemetry backend: jsonl or sqlite."),
    ] = None,
    sqlite_path: Annotated[
        Path | None,
        typer.Option("--sqlite-path", help="SQLite telemetry database path."),
    ] = None,
    redis_url: Annotated[
        str | None,
        typer.Option("--redis-url", help="Redis URL for the Redis online feature adapter."),
    ] = None,
) -> None:
    """Inspect configured online feature and prediction telemetry storage backends."""

    try:
        config = _storage_config_from_options(
            online_backend=online_backend,
            telemetry_backend=telemetry_backend,
            sqlite_path=sqlite_path,
            redis_url=redis_url,
        )
        result = inspect_storage(
            config=config,
            feature_snapshot_path=feature_snapshot_path,
            telemetry_log_path=telemetry_log_path,
            report_path=report_path,
        )
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"online backend: {result.online_backend}")
    typer.echo(f"telemetry backend: {result.telemetry_backend}")
    typer.echo(f"online feature row count: {result.online_feature_row_count}")
    typer.echo(f"telemetry row count: {result.telemetry_row_count}")
    typer.echo(f"available zone ids: {', '.join(result.zone_ids)}")
    typer.echo(f"min telemetry timestamp: {result.min_telemetry_timestamp or 'n/a'}")
    typer.echo(f"max telemetry timestamp: {result.max_telemetry_timestamp or 'n/a'}")
    typer.echo(f"wrote storage inspection report to {result.report_path}")


@app.command("sync-relational-store")
def sync_relational_store_command(
    events_path: Annotated[
        Path,
        typer.Option("--events-path", help="CSV path for synthetic temporal events."),
    ] = DEFAULT_SYNTHETIC_EVENTS_PATH,
    offline_features_path: Annotated[
        Path,
        typer.Option("--offline-features-path", help="Parquet path for all offline feature rows."),
    ] = DEFAULT_OFFLINE_FEATURES_PATH,
    online_snapshot_path: Annotated[
        Path,
        typer.Option("--online-snapshot-path", help="JSON path for online feature snapshot."),
    ] = DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown relational storage sync report path."),
    ] = DEFAULT_RELATIONAL_STORAGE_SYNC_REPORT_PATH,
    database_url: Annotated[
        str | None,
        typer.Option(
            "--database-url",
            help="SQLAlchemy database URL. Defaults to FEATURE_STORE_OPS_RELATIONAL_URL or SQLite.",
        ),
    ] = None,
) -> None:
    """Sync generated events and feature artifacts into relational storage."""

    try:
        result = sync_relational_store(
            database_url=database_url,
            events_path=events_path,
            offline_features_path=offline_features_path,
            online_snapshot_path=online_snapshot_path,
            report_path=report_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"relational backend: {result.database_backend}")
    typer.echo(f"event rows: {result.event_row_count}")
    typer.echo(f"offline feature rows: {result.offline_feature_row_count}")
    typer.echo(f"online snapshot rows: {result.online_snapshot_row_count}")
    typer.echo(f"zone count: {result.zone_count}")
    typer.echo(f"wrote relational storage sync report to {result.report_path}")


@app.command("inspect-relational-store")
def inspect_relational_store_command(
    report_path: Annotated[
        Path,
        typer.Option("--report-path", help="Tracked Markdown relational storage inspection report path."),
    ] = DEFAULT_RELATIONAL_STORAGE_INSPECTION_REPORT_PATH,
    database_url: Annotated[
        str | None,
        typer.Option(
            "--database-url",
            help="SQLAlchemy database URL. Defaults to FEATURE_STORE_OPS_RELATIONAL_URL or SQLite.",
        ),
    ] = None,
) -> None:
    """Inspect relational event and feature storage."""

    try:
        result = inspect_relational_store(database_url=database_url, report_path=report_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"relational backend: {result.database_backend}")
    typer.echo(f"event row count: {result.event_row_count}")
    typer.echo(f"offline feature row count: {result.offline_feature_row_count}")
    typer.echo(f"online snapshot row count: {result.online_snapshot_row_count}")
    typer.echo(f"zone count: {result.zone_count}")
    typer.echo(f"min event timestamp: {result.min_event_timestamp or 'n/a'}")
    typer.echo(f"max event timestamp: {result.max_event_timestamp or 'n/a'}")
    typer.echo(f"wrote relational storage inspection report to {result.report_path}")


@app.command("run-demo-workflow")
def run_demo_workflow_command(
    preset: Annotated[
        str,
        typer.Option("--preset", help=f"Workflow scale preset: {', '.join(SYNTHETIC_PRESETS)}."),
    ] = "default",
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root directory for demo workflow outputs."),
    ] = PROJECT_ROOT,
    events: Annotated[
        int | None,
        typer.Option("--events", help="Number of synthetic events for the demo workflow."),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Synthetic event seed for deterministic workflow runs."),
    ] = None,
    zones: Annotated[
        int | None,
        typer.Option("--zones", help="Number of synthetic zones for the demo workflow."),
    ] = None,
    users: Annotated[
        int | None,
        typer.Option("--users", help="Number of synthetic users for the demo workflow."),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option("--days", help="Number of days for zone/day grid synthetic generation."),
    ] = None,
    events_per_zone_per_day: Annotated[
        int | None,
        typer.Option("--events-per-zone-per-day", help="Rows per zone per day for grid generation."),
    ] = None,
    traffic_requests: Annotated[
        int | None,
        typer.Option("--traffic-requests", help="Total simulated prediction requests."),
    ] = None,
) -> None:
    """Run the full deterministic local demo workflow."""

    try:
        config = DemoWorkflowConfig.from_preset(
            preset=preset,
            output_root=output_root,
            num_events=events,
            seed=seed,
            zone_count=zones,
            user_count=users,
            num_days=days,
            events_per_zone_per_day=events_per_zone_per_day,
            traffic_request_count=traffic_requests,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = run_demo_workflow(config)
    for stage in result.stages:
        typer.echo(f"{stage.name}: {stage.status}")
        if stage.error_message:
            typer.echo(f"  error: {stage.error_message}")

    typer.echo(f"workflow status: {result.status}")
    typer.echo(f"wrote workflow summary to {result.workflow_summary_path}")
    typer.echo(f"wrote workflow results to {result.workflow_results_path}")
    typer.echo(f"wrote portfolio summary to {result.portfolio_summary_path}")
    if not result.passed:
        raise typer.Exit(code=1)


def _parse_cli_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def _storage_config_from_options(
    *,
    online_backend: str | None,
    telemetry_backend: str | None,
    sqlite_path: Path | None,
    redis_url: str | None,
) -> StorageConfig:
    return StorageConfig.from_env().with_overrides(
        online_backend=online_backend,
        telemetry_backend=telemetry_backend,
        sqlite_path=sqlite_path,
        redis_url=redis_url,
    )


__all__ = ["app"]

"""Typer command line interface for feature store monitoring ops."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.api.app import (
    create_app as create_api_app,
    run_api_smoke_test,
    write_api_serving_report,
)
from feature_store_monitoring_ops.api.service import ServingArtifacts
from feature_store_monitoring_ops.features.offline import build_and_save_offline_features
from feature_store_monitoring_ops.features.online import materialize_online_features
from feature_store_monitoring_ops.models.training import train_and_evaluate_models
from feature_store_monitoring_ops.paths import (
    DEFAULT_API_SERVING_REPORT_PATH,
    DEFAULT_MODEL_MANIFEST_PATH,
    DEFAULT_MODEL_METRICS_PATH,
    DEFAULT_MODEL_TRAINING_REPORT_PATH,
    DEFAULT_OFFLINE_FEATURE_REPORT_PATH,
    DEFAULT_OFFLINE_FEATURES_PATH,
    DEFAULT_ONLINE_FEATURE_MANIFEST_PATH,
    DEFAULT_ONLINE_FEATURE_REPORT_PATH,
    DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH,
    DEFAULT_SELECTED_MODEL_PATH,
    DEFAULT_SYNTHETIC_EVENTS_PATH,
    DEFAULT_SYNTHETIC_REPORT_PATH,
    DEFAULT_TEST_FEATURES_PATH,
    DEFAULT_TRAIN_FEATURES_PATH,
    DEFAULT_VALIDATION_FEATURES_PATH,
    PROJECT_ROOT,
)
from feature_store_monitoring_ops.synthetic_events import (
    SyntheticEventConfig,
    generate_and_save_synthetic_events,
    parse_start_timestamp,
)

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


@app.command("generate-synthetic-events")
def generate_synthetic_events_command(
    events: Annotated[
        int,
        typer.Option("--events", help="Number of synthetic event rows to generate."),
    ] = 720,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Random seed used for deterministic generation."),
    ] = 42,
    start: Annotated[
        str,
        typer.Option("--start", help="ISO-8601 start timestamp for the generated series."),
    ] = "2026-01-01T00:00:00+00:00",
    interval_minutes: Annotated[
        int,
        typer.Option("--interval-minutes", help="Minutes between generated event timestamps."),
    ] = 60,
    zones: Annotated[
        int,
        typer.Option("--zones", help="Number of zone IDs to sample."),
    ] = 5,
    users: Annotated[
        int,
        typer.Option("--users", help="Number of user IDs to sample."),
    ] = 200,
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
        config = SyntheticEventConfig(
            num_events=events,
            seed=seed,
            start_timestamp=parse_start_timestamp(start),
            interval_minutes=interval_minutes,
            zone_count=zones,
            user_count=users,
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
    api_app = create_api_app(artifacts=artifacts)

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


__all__ = ["app"]

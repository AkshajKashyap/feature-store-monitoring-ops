"""End-to-end local demo workflow orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from feature_store_monitoring_ops.api.app import (
    create_app as create_api_app,
    run_api_smoke_test,
    run_api_traffic_simulation,
    write_api_serving_report,
)
from feature_store_monitoring_ops.api.service import ServingArtifacts
from feature_store_monitoring_ops.features.offline import build_and_save_offline_features
from feature_store_monitoring_ops.features.online import materialize_online_features
from feature_store_monitoring_ops.models.training import train_and_evaluate_models
from feature_store_monitoring_ops.monitoring.drift import monitor_drift
from feature_store_monitoring_ops.monitoring.serving import monitor_prediction_logs
from feature_store_monitoring_ops.monitoring.telemetry import (
    IncrementingClock,
    PredictionTelemetryLogger,
    reset_prediction_log,
)
from feature_store_monitoring_ops.paths import PROJECT_ROOT
from feature_store_monitoring_ops.storage.config import StorageConfig
from feature_store_monitoring_ops.storage.sync import inspect_storage, sync_storage
from feature_store_monitoring_ops.synthetic_events import (
    DEFAULT_SYNTHETIC_PRESET,
    PORTFOLIO_SYNTHETIC_PRESET,
    SYNTHETIC_PRESETS,
    SyntheticEventConfig,
    build_synthetic_event_config,
    generate_and_save_synthetic_events,
)

WORKFLOW_STAGE_ORDER: tuple[str, ...] = (
    "generate_synthetic_events",
    "build_offline_features",
    "train_model",
    "materialize_online_features",
    "api_smoke_test",
    "simulate_traffic",
    "monitor_serving",
    "monitor_drift",
    "sync_storage",
    "inspect_storage",
)

STAGE_PASSED = "passed"
STAGE_FAILED = "failed"
STAGE_SKIPPED = "skipped"


@dataclass(frozen=True)
class DemoWorkflowConfig:
    """Configuration for the deterministic local demo workflow."""

    output_root: Path = PROJECT_ROOT
    preset: str = DEFAULT_SYNTHETIC_PRESET
    num_events: int = 720
    seed: int = 42
    start_timestamp: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    interval_minutes: int = 60
    zone_count: int = 5
    user_count: int = 200
    num_days: int | None = None
    events_per_zone_per_day: int | None = None
    traffic_base_timestamp: datetime = datetime(2026, 2, 1, tzinfo=UTC)
    traffic_request_count: int | None = None
    storage_config: StorageConfig = field(default_factory=StorageConfig)

    @classmethod
    def from_preset(
        cls,
        *,
        preset: str = DEFAULT_SYNTHETIC_PRESET,
        output_root: Path = PROJECT_ROOT,
        num_events: int | None = None,
        seed: int | None = None,
        zone_count: int | None = None,
        user_count: int | None = None,
        num_days: int | None = None,
        events_per_zone_per_day: int | None = None,
        traffic_request_count: int | None = None,
    ) -> DemoWorkflowConfig:
        """Build workflow config from a named synthetic scale preset."""

        synthetic_config = build_synthetic_event_config(
            preset=preset,
            num_events=num_events,
            seed=seed,
            zone_count=zone_count,
            user_count=user_count,
            num_days=num_days,
            events_per_zone_per_day=events_per_zone_per_day,
        )
        default_traffic_count = None
        if preset == PORTFOLIO_SYNTHETIC_PRESET:
            default_traffic_count = 120
        return cls(
            output_root=output_root,
            preset=preset,
            num_events=synthetic_config.num_events,
            seed=synthetic_config.seed,
            start_timestamp=synthetic_config.start_timestamp,
            interval_minutes=synthetic_config.interval_minutes,
            zone_count=synthetic_config.zone_count,
            user_count=synthetic_config.user_count,
            num_days=synthetic_config.num_days,
            events_per_zone_per_day=synthetic_config.events_per_zone_per_day,
            traffic_request_count=traffic_request_count or default_traffic_count,
        )

    @property
    def synthetic_events_path(self) -> Path:
        return self.output_root / "data" / "processed" / "synthetic_events.csv"

    @property
    def synthetic_report_path(self) -> Path:
        return self.output_root / "reports" / "synthetic_events_summary.md"

    @property
    def offline_features_path(self) -> Path:
        return self.output_root / "data" / "processed" / "offline_features.parquet"

    @property
    def train_features_path(self) -> Path:
        return self.output_root / "data" / "processed" / "train_features.parquet"

    @property
    def validation_features_path(self) -> Path:
        return self.output_root / "data" / "processed" / "validation_features.parquet"

    @property
    def test_features_path(self) -> Path:
        return self.output_root / "data" / "processed" / "test_features.parquet"

    @property
    def offline_feature_report_path(self) -> Path:
        return self.output_root / "reports" / "offline_feature_summary.md"

    @property
    def selected_model_path(self) -> Path:
        return self.output_root / "artifacts" / "models" / "selected_model.joblib"

    @property
    def model_manifest_path(self) -> Path:
        return self.output_root / "artifacts" / "models" / "model_manifest.json"

    @property
    def model_metrics_path(self) -> Path:
        return self.output_root / "reports" / "model_metrics.json"

    @property
    def model_training_report_path(self) -> Path:
        return self.output_root / "reports" / "model_training_summary.md"

    @property
    def online_feature_snapshot_path(self) -> Path:
        return self.output_root / "artifacts" / "online_features" / "latest_features.json"

    @property
    def online_feature_manifest_path(self) -> Path:
        return self.output_root / "artifacts" / "online_features" / "manifest.json"

    @property
    def online_feature_report_path(self) -> Path:
        return self.output_root / "reports" / "online_feature_materialization_summary.md"

    @property
    def api_serving_report_path(self) -> Path:
        return self.output_root / "reports" / "api_serving_summary.md"

    @property
    def prediction_log_path(self) -> Path:
        return self.output_root / "logs" / "predictions.jsonl"

    @property
    def serving_monitoring_report_path(self) -> Path:
        return self.output_root / "reports" / "serving_monitoring_summary.md"

    @property
    def serving_monitoring_metrics_path(self) -> Path:
        return self.output_root / "reports" / "serving_monitoring_metrics.json"

    @property
    def drift_monitoring_report_path(self) -> Path:
        return self.output_root / "reports" / "drift_monitoring_summary.md"

    @property
    def drift_monitoring_metrics_path(self) -> Path:
        return self.output_root / "reports" / "drift_monitoring_metrics.json"

    @property
    def storage_sync_report_path(self) -> Path:
        return self.output_root / "reports" / "storage_sync_summary.md"

    @property
    def storage_inspection_report_path(self) -> Path:
        return self.output_root / "reports" / "storage_inspection_summary.md"

    @property
    def workflow_summary_path(self) -> Path:
        return self.output_root / "reports" / "portfolio" / "workflow_summary.md"

    @property
    def workflow_results_path(self) -> Path:
        return self.output_root / "reports" / "portfolio" / "workflow_results.json"

    @property
    def portfolio_summary_path(self) -> Path:
        return self.output_root / "reports" / "portfolio" / "portfolio_summary.md"

    @property
    def portfolio_scale_summary_path(self) -> Path:
        return self.output_root / "reports" / "portfolio" / "portfolio_scale_summary.md"

    @property
    def sqlite_path(self) -> Path:
        return self.output_root / "artifacts" / "storage" / "telemetry.db"

    def resolved_storage_config(self) -> StorageConfig:
        """Return storage config scoped to this workflow output root."""

        return self.storage_config.with_overrides(sqlite_path=self.sqlite_path)

    def synthetic_event_config(self) -> SyntheticEventConfig:
        """Return the synthetic event generator config for this workflow."""

        return SyntheticEventConfig(
            num_events=self.num_events,
            seed=self.seed,
            start_timestamp=self.start_timestamp,
            interval_minutes=self.interval_minutes,
            zone_count=self.zone_count,
            user_count=self.user_count,
            num_days=self.num_days,
            events_per_zone_per_day=self.events_per_zone_per_day,
        )


@dataclass(frozen=True)
class WorkflowStageResult:
    """Structured result for one workflow stage."""

    name: str
    status: str
    output_paths: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly stage result."""

        return {
            "name": self.name,
            "status": self.status,
            "output_paths": self.output_paths,
            "metrics": self.metrics,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class DemoWorkflowResult:
    """Structured result for the full local demo workflow."""

    stages: list[WorkflowStageResult]
    workflow_summary_path: Path
    workflow_results_path: Path
    portfolio_summary_path: Path
    portfolio_scale_summary_path: Path | None = None
    preset: str = DEFAULT_SYNTHETIC_PRESET

    @property
    def status(self) -> str:
        if any(stage.status == STAGE_FAILED for stage in self.stages):
            return STAGE_FAILED
        if any(stage.status == STAGE_SKIPPED for stage in self.stages):
            return STAGE_SKIPPED
        return STAGE_PASSED

    @property
    def passed(self) -> bool:
        return self.status == STAGE_PASSED

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly workflow result."""

        return {
            "status": self.status,
            "stage_order": list(WORKFLOW_STAGE_ORDER),
            "stages": [stage.to_dict() for stage in self.stages],
            "output_paths": {
                "workflow_summary": str(self.workflow_summary_path),
                "workflow_results": str(self.workflow_results_path),
                "portfolio_summary": str(self.portfolio_summary_path),
                "portfolio_scale_summary": (
                    str(self.portfolio_scale_summary_path)
                    if self.portfolio_scale_summary_path is not None
                    else None
                ),
            },
        }


def run_demo_workflow(
    config: DemoWorkflowConfig | None = None,
    *,
    stop_on_failure: bool = True,
) -> DemoWorkflowResult:
    """Run the full deterministic local demo workflow and write portfolio reports."""

    active_config = config or DemoWorkflowConfig()
    stages: list[WorkflowStageResult] = []
    failure_seen = False

    for name, stage in _stage_functions():
        if failure_seen and stop_on_failure:
            stages.append(
                WorkflowStageResult(
                    name=name,
                    status=STAGE_SKIPPED,
                    error_message="skipped because an earlier stage failed",
                ),
            )
            continue
        try:
            stages.append(stage(active_config))
        except Exception as exc:  # pragma: no cover - exercised through integration behavior
            stages.append(
                WorkflowStageResult(
                    name=name,
                    status=STAGE_FAILED,
                    error_message=str(exc),
                ),
            )
            failure_seen = True

    result = DemoWorkflowResult(
        stages=stages,
        workflow_summary_path=active_config.workflow_summary_path,
        workflow_results_path=active_config.workflow_results_path,
        portfolio_summary_path=active_config.portfolio_summary_path,
        portfolio_scale_summary_path=active_config.portfolio_scale_summary_path,
        preset=active_config.preset,
    )
    _write_workflow_reports(result, active_config)
    return result


def build_workflow_summary(result: DemoWorkflowResult) -> str:
    """Build a Markdown summary for the demo workflow run."""

    rows = "\n".join(
        (
            f"| `{stage.name}` | {stage.status} | "
            f"{_format_metrics_for_table(stage.metrics)} | "
            f"{stage.error_message or ''} |"
        )
        for stage in result.stages
    )
    output_lines = "\n".join(
        f"- `{label}`: `{path}`" for label, path in result.to_dict()["output_paths"].items()
    )
    return "\n".join(
        [
            "# Workflow Summary",
            "",
            "One-command local demo workflow for Milestone 9.",
            "",
            f"- Overall status: {result.status}",
            f"- Preset: `{result.preset}`",
            "",
            "## Stages",
            "",
            "| Stage | Status | Key Metrics | Error |",
            "| --- | --- | --- | --- |",
            rows,
            "",
            "## Portfolio Outputs",
            "",
            output_lines,
            "",
        ],
    )


def build_portfolio_summary(result: DemoWorkflowResult) -> str:
    """Build the reviewer-facing portfolio summary report."""

    metrics = _final_metrics(result)
    component_lines = "\n".join(
        [
            "- Deterministic synthetic temporal demand event generation.",
            "- Leakage-safe offline temporal feature engineering and chronological splits.",
            "- Validation-only model selection with one-time test evaluation.",
            "- Online feature materialization with offline/online parity checks.",
            "- Local FastAPI prediction serving with typed request/response schemas.",
            "- Durable JSONL telemetry plus SQLite telemetry storage sync.",
            "- Serving, drift, prediction drift, and data quality monitoring reports.",
            "- Adapter-level Redis-compatible online feature store interface.",
        ],
    )
    quickstart = "\n".join(
        [
            "```bash",
            "python -m pip install -e \".[dev]\"",
            "make release-check",
            "feature-store-ops run-demo-workflow --preset portfolio",
            "cat reports/portfolio/portfolio_summary.md",
            "```",
        ],
    )
    limitations = "\n".join(
        [
            "- Synthetic data only; no external production data source is connected yet.",
            "- Redis support is adapter-level unless a Redis server/client is configured.",
            "- SQLite storage is local development storage, not a production telemetry warehouse.",
            "- FastAPI serving is local; cloud deployment, auth, and autoscaling are intentionally out of scope.",
            "- Models are baseline forecasting models intended to validate the system path, not maximize accuracy.",
        ],
    )

    return "\n".join(
        [
            "# Portfolio Summary",
            "",
            "This project demonstrates a production-style ML feature store and monitoring system "
            "in a deterministic local environment.",
            "",
            "## What It Demonstrates",
            "",
            component_lines,
            "",
            "## Current Metrics",
            "",
            f"- Workflow status: {result.status}",
            f"- Current workflow preset: `{result.preset}`",
            f"- Selected model: `{metrics.get('selected_model', 'n/a')}`",
            f"- Test MAE: {_format_optional_metric(metrics.get('test_mae'))}",
            f"- Test RMSE: {_format_optional_metric(metrics.get('test_rmse'))}",
            f"- Test R2: {_format_optional_metric(metrics.get('test_r2'))}",
            f"- Online feature rows: {_format_optional_metric(metrics.get('online_feature_rows'))}",
            f"- Simulated prediction requests: "
            f"{_format_optional_metric(metrics.get('simulated_requests'))}",
            f"- Serving error rate: {_format_optional_metric(metrics.get('serving_error_rate'))}",
            f"- Drift warning count: {_format_optional_metric(metrics.get('drift_warnings'))}",
            f"- SQLite telemetry rows: {_format_optional_metric(metrics.get('telemetry_rows'))}",
            "",
            "## Reviewer Quickstart",
            "",
            quickstart,
            "",
            "## Limitations",
            "",
            limitations,
            "",
            "## Primary Reports",
            "",
            "- `reports/portfolio/workflow_summary.md`",
            "- `reports/portfolio/workflow_results.json`",
            "- `reports/portfolio/portfolio_summary.md`",
            "- `reports/portfolio/portfolio_scale_summary.md`",
            "- `reports/model_metrics.json`",
            "- `reports/serving_monitoring_metrics.json`",
            "- `reports/drift_monitoring_metrics.json`",
            "",
            "## Demo Paths",
            "",
            "- Lightweight default: `feature-store-ops run-demo-workflow`",
            "- Portfolio scale: `feature-store-ops run-demo-workflow --preset portfolio`",
            "",
        ],
    )


def build_portfolio_scale_summary(result: DemoWorkflowResult) -> str:
    """Build a focused report for the portfolio-scale workflow preset."""

    metrics = _final_metrics(result)
    return "\n".join(
        [
            "# Portfolio Scale Summary",
            "",
            "Portfolio-scale deterministic workflow run with richer temporal and zone coverage.",
            "",
            f"- Workflow status: {result.status}",
            f"- Preset: `{result.preset}`",
            f"- Synthetic rows: {_format_optional_metric(metrics.get('synthetic_rows'))}",
            f"- Configured zones: {_format_optional_metric(metrics.get('configured_zones'))}",
            f"- Configured users: {_format_optional_metric(metrics.get('configured_users'))}",
            f"- Configured days: {_format_optional_metric(metrics.get('configured_days'))}",
            f"- Events per zone per day: "
            f"{_format_optional_metric(metrics.get('events_per_zone_per_day'))}",
            f"- Offline feature rows: {_format_optional_metric(metrics.get('offline_rows'))}",
            f"- Online feature rows: {_format_optional_metric(metrics.get('online_feature_rows'))}",
            f"- Simulated prediction requests: "
            f"{_format_optional_metric(metrics.get('simulated_requests'))}",
            f"- SQLite telemetry rows: {_format_optional_metric(metrics.get('telemetry_rows'))}",
            "",
            "## Notes",
            "",
            "- Generated data, model artifacts, logs, and SQLite files remain ignored by git.",
            "- This preset is larger than the default demo but remains local and CPU-only.",
            "",
        ],
    )


def _stage_functions() -> list[tuple[str, Callable[[DemoWorkflowConfig], WorkflowStageResult]]]:
    return [
        ("generate_synthetic_events", _stage_generate_synthetic_events),
        ("build_offline_features", _stage_build_offline_features),
        ("train_model", _stage_train_model),
        ("materialize_online_features", _stage_materialize_online_features),
        ("api_smoke_test", _stage_api_smoke_test),
        ("simulate_traffic", _stage_simulate_traffic),
        ("monitor_serving", _stage_monitor_serving),
        ("monitor_drift", _stage_monitor_drift),
        ("sync_storage", _stage_sync_storage),
        ("inspect_storage", _stage_inspect_storage),
    ]


def _stage_generate_synthetic_events(config: DemoWorkflowConfig) -> WorkflowStageResult:
    synthetic_config = config.synthetic_event_config()
    result = generate_and_save_synthetic_events(
        config=synthetic_config,
        output_path=config.synthetic_events_path,
        report_path=config.synthetic_report_path,
    )
    return WorkflowStageResult(
        name="generate_synthetic_events",
        status=STAGE_PASSED,
        output_paths={
            "synthetic_events": str(result.csv_path),
            "summary_report": str(result.report_path),
        },
        metrics={
            "rows_written": result.rows_written,
            "seed": config.seed,
            "preset": config.preset,
            "zone_count": config.zone_count,
            "user_count": config.user_count,
            "num_days": config.num_days,
            "events_per_zone_per_day": config.events_per_zone_per_day,
        },
    )


def _stage_build_offline_features(config: DemoWorkflowConfig) -> WorkflowStageResult:
    result = build_and_save_offline_features(
        input_path=config.synthetic_events_path,
        offline_features_path=config.offline_features_path,
        train_features_path=config.train_features_path,
        validation_features_path=config.validation_features_path,
        test_features_path=config.test_features_path,
        report_path=config.offline_feature_report_path,
    )
    return WorkflowStageResult(
        name="build_offline_features",
        status=STAGE_PASSED,
        output_paths={
            "offline_features": str(result.offline_features_path),
            "train_features": str(result.train_features_path),
            "validation_features": str(result.validation_features_path),
            "test_features": str(result.test_features_path),
            "summary_report": str(result.report_path),
        },
        metrics=result.row_counts,
    )


def _stage_train_model(config: DemoWorkflowConfig) -> WorkflowStageResult:
    result = train_and_evaluate_models(
        train_path=config.train_features_path,
        validation_path=config.validation_features_path,
        test_path=config.test_features_path,
        model_path=config.selected_model_path,
        manifest_path=config.model_manifest_path,
        metrics_path=config.model_metrics_path,
        report_path=config.model_training_report_path,
    )
    return WorkflowStageResult(
        name="train_model",
        status=STAGE_PASSED,
        output_paths={
            "selected_model": str(result.model_path),
            "model_manifest": str(result.manifest_path),
            "metrics": str(result.metrics_path),
            "summary_report": str(result.report_path),
        },
        metrics={
            "selected_model": result.selected_model_name,
            "test_mae": result.test_metrics["mae"],
            "test_rmse": result.test_metrics["rmse"],
            "test_r2": result.test_metrics["r2"],
            "train_rows": result.row_counts["train"],
            "validation_rows": result.row_counts["validation"],
            "test_rows": result.row_counts["test"],
        },
    )


def _stage_materialize_online_features(config: DemoWorkflowConfig) -> WorkflowStageResult:
    result = materialize_online_features(
        source_path=config.offline_features_path,
        snapshot_path=config.online_feature_snapshot_path,
        manifest_path=config.online_feature_manifest_path,
        report_path=config.online_feature_report_path,
    )
    return WorkflowStageResult(
        name="materialize_online_features",
        status=STAGE_PASSED,
        output_paths={
            "snapshot": str(result.snapshot_path),
            "manifest": str(result.manifest_path),
            "summary_report": str(result.report_path),
        },
        metrics={"row_count": result.row_count},
    )


def _stage_api_smoke_test(config: DemoWorkflowConfig) -> WorkflowStageResult:
    app = create_api_app(
        artifacts=_serving_artifacts(config),
        telemetry_logger=PredictionTelemetryLogger(
            log_path=config.prediction_log_path,
            now_fn=IncrementingClock(datetime(2026, 1, 31, tzinfo=UTC)),
        ),
    )
    smoke_result = run_api_smoke_test(app)
    write_api_serving_report(app, report_path=config.api_serving_report_path, smoke_test_passed=True)
    return WorkflowStageResult(
        name="api_smoke_test",
        status=STAGE_PASSED,
        output_paths={"summary_report": str(config.api_serving_report_path)},
        metrics={
            "zone_id": smoke_result["zone_id"],
            "prediction": smoke_result["prediction"],
            "smoke_test_passed": True,
        },
    )


def _stage_simulate_traffic(config: DemoWorkflowConfig) -> WorkflowStageResult:
    reset_prediction_log(config.prediction_log_path)
    app = create_api_app(
        artifacts=_serving_artifacts(config),
        telemetry_logger=PredictionTelemetryLogger(
            log_path=config.prediction_log_path,
            now_fn=IncrementingClock(config.traffic_base_timestamp),
        ),
    )
    result = run_api_traffic_simulation(app, request_count=config.traffic_request_count)
    return WorkflowStageResult(
        name="simulate_traffic",
        status=STAGE_PASSED,
        output_paths={"prediction_log": str(result.log_path)},
        metrics={
            "total_requests": result.total_requests,
            "successful_requests": result.successful_requests,
            "failed_requests": result.failed_requests,
            "zones_requested": result.zones_requested,
        },
    )


def _stage_monitor_serving(config: DemoWorkflowConfig) -> WorkflowStageResult:
    result = monitor_prediction_logs(
        log_path=config.prediction_log_path,
        report_path=config.serving_monitoring_report_path,
        metrics_path=config.serving_monitoring_metrics_path,
    )
    return WorkflowStageResult(
        name="monitor_serving",
        status=STAGE_PASSED,
        output_paths={
            "summary_report": str(result.report_path),
            "metrics": str(result.metrics_path),
        },
        metrics={
            "total_requests": result.metrics["total_requests"],
            "successful_predictions": result.metrics["successful_predictions"],
            "failed_predictions": result.metrics["failed_predictions"],
            "error_rate": result.metrics["error_rate"],
            "warnings": len(result.warnings),
        },
    )


def _stage_monitor_drift(config: DemoWorkflowConfig) -> WorkflowStageResult:
    result = monitor_drift(
        reference_path=config.train_features_path,
        current_path=config.test_features_path,
        telemetry_log_path=config.prediction_log_path,
        model_metrics_path=config.model_metrics_path,
        report_path=config.drift_monitoring_report_path,
        metrics_path=config.drift_monitoring_metrics_path,
    )
    psi_values = [
        float(values["psi"])
        for values in result.metrics["numeric_feature_drift"].values()
        if values["psi"] is not None
    ]
    return WorkflowStageResult(
        name="monitor_drift",
        status=STAGE_PASSED,
        output_paths={
            "summary_report": str(result.report_path),
            "metrics": str(result.metrics_path),
        },
        metrics={
            "reference_rows": result.metrics["row_counts"]["reference"],
            "current_rows": result.metrics["row_counts"]["current"],
            "prediction_count": result.metrics["prediction_drift"]["count"],
            "max_psi": max(psi_values) if psi_values else None,
            "warnings": len(result.warnings),
        },
    )


def _stage_sync_storage(config: DemoWorkflowConfig) -> WorkflowStageResult:
    storage_config = config.resolved_storage_config()
    if storage_config.telemetry_backend == "sqlite" and storage_config.sqlite_path.exists():
        storage_config.sqlite_path.unlink()
    result = sync_storage(
        config=storage_config,
        feature_snapshot_path=config.online_feature_snapshot_path,
        telemetry_log_path=config.prediction_log_path,
        report_path=config.storage_sync_report_path,
    )
    return WorkflowStageResult(
        name="sync_storage",
        status=STAGE_PASSED,
        output_paths={"summary_report": str(result.report_path), "sqlite": str(storage_config.sqlite_path)},
        metrics={
            "online_feature_row_count": result.online_feature_row_count,
            "telemetry_source_row_count": result.telemetry_source_row_count,
            "telemetry_store_row_count": result.telemetry_store_row_count,
            "zone_ids": result.zone_ids,
        },
    )


def _stage_inspect_storage(config: DemoWorkflowConfig) -> WorkflowStageResult:
    storage_config = config.resolved_storage_config()
    result = inspect_storage(
        config=storage_config,
        feature_snapshot_path=config.online_feature_snapshot_path,
        telemetry_log_path=config.prediction_log_path,
        report_path=config.storage_inspection_report_path,
    )
    return WorkflowStageResult(
        name="inspect_storage",
        status=STAGE_PASSED,
        output_paths={"summary_report": str(result.report_path)},
        metrics={
            "online_feature_row_count": result.online_feature_row_count,
            "telemetry_row_count": result.telemetry_row_count,
            "zone_ids": result.zone_ids,
            "min_telemetry_timestamp": result.min_telemetry_timestamp,
            "max_telemetry_timestamp": result.max_telemetry_timestamp,
        },
    )


def _write_workflow_reports(result: DemoWorkflowResult, config: DemoWorkflowConfig) -> None:
    config.workflow_summary_path.parent.mkdir(parents=True, exist_ok=True)
    config.workflow_summary_path.write_text(build_workflow_summary(result), encoding="utf-8")
    config.workflow_results_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config.portfolio_summary_path.write_text(build_portfolio_summary(result), encoding="utf-8")
    if config.preset == PORTFOLIO_SYNTHETIC_PRESET:
        config.portfolio_scale_summary_path.write_text(
            build_portfolio_scale_summary(result),
            encoding="utf-8",
        )


def _serving_artifacts(config: DemoWorkflowConfig) -> ServingArtifacts:
    return ServingArtifacts(
        model_path=config.selected_model_path,
        model_manifest_path=config.model_manifest_path,
        feature_snapshot_path=config.online_feature_snapshot_path,
        feature_manifest_path=config.online_feature_manifest_path,
    )


def _final_metrics(result: DemoWorkflowResult) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for stage in result.stages:
        if stage.name == "generate_synthetic_events":
            metrics["synthetic_rows"] = stage.metrics.get("rows_written")
            metrics["configured_zones"] = stage.metrics.get("zone_count")
            metrics["configured_users"] = stage.metrics.get("user_count")
            metrics["configured_days"] = stage.metrics.get("num_days")
            metrics["events_per_zone_per_day"] = stage.metrics.get("events_per_zone_per_day")
        elif stage.name == "build_offline_features":
            metrics["offline_rows"] = stage.metrics.get("offline")
        elif stage.name == "train_model":
            metrics["selected_model"] = stage.metrics.get("selected_model")
            metrics["test_mae"] = stage.metrics.get("test_mae")
            metrics["test_rmse"] = stage.metrics.get("test_rmse")
            metrics["test_r2"] = stage.metrics.get("test_r2")
        elif stage.name == "materialize_online_features":
            metrics["online_feature_rows"] = stage.metrics.get("row_count")
        elif stage.name == "simulate_traffic":
            metrics["simulated_requests"] = stage.metrics.get("total_requests")
        elif stage.name == "monitor_serving":
            metrics["serving_error_rate"] = stage.metrics.get("error_rate")
        elif stage.name == "monitor_drift":
            metrics["drift_warnings"] = stage.metrics.get("warnings")
        elif stage.name == "inspect_storage":
            metrics["telemetry_rows"] = stage.metrics.get("telemetry_row_count")
    return metrics


def _format_metrics_for_table(metrics: dict[str, Any]) -> str:
    if not metrics:
        return ""
    items = list(metrics.items())[:4]
    return ", ".join(f"`{key}`={value}" for key, value in items)


def _format_optional_metric(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)


__all__ = [
    "DemoWorkflowConfig",
    "DemoWorkflowResult",
    "PORTFOLIO_SYNTHETIC_PRESET",
    "SYNTHETIC_PRESETS",
    "STAGE_FAILED",
    "STAGE_PASSED",
    "STAGE_SKIPPED",
    "WORKFLOW_STAGE_ORDER",
    "WorkflowStageResult",
    "build_portfolio_summary",
    "build_portfolio_scale_summary",
    "build_workflow_summary",
    "run_demo_workflow",
]

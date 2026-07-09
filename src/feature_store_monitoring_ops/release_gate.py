"""Release gate decisioning for local portfolio releases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.paths import (
    DEFAULT_DRIFT_MONITORING_METRICS_PATH,
    DEFAULT_MODEL_METRICS_PATH,
    DEFAULT_RELEASE_GATE_METRICS_PATH,
    DEFAULT_RELEASE_GATE_REPORT_PATH,
    DEFAULT_RELEASE_VERIFICATION_REPORT_PATH,
    DEFAULT_SERVING_MONITORING_METRICS_PATH,
    DEFAULT_STORAGE_INSPECTION_REPORT_PATH,
    DEFAULT_WORKFLOW_RESULTS_PATH,
)

RELEASE_GATE_DECISIONS: tuple[str, ...] = ("pass", "warn", "hold")


@dataclass(frozen=True)
class ReleaseGatePaths:
    """Input and output paths for release gate evaluation."""

    model_metrics_path: Path = DEFAULT_MODEL_METRICS_PATH
    serving_metrics_path: Path = DEFAULT_SERVING_MONITORING_METRICS_PATH
    drift_metrics_path: Path = DEFAULT_DRIFT_MONITORING_METRICS_PATH
    storage_inspection_report_path: Path = DEFAULT_STORAGE_INSPECTION_REPORT_PATH
    workflow_results_path: Path = DEFAULT_WORKFLOW_RESULTS_PATH
    verification_report_path: Path = DEFAULT_RELEASE_VERIFICATION_REPORT_PATH
    report_path: Path = DEFAULT_RELEASE_GATE_REPORT_PATH
    metrics_path: Path = DEFAULT_RELEASE_GATE_METRICS_PATH


@dataclass(frozen=True)
class ReleaseGateThresholds:
    """Operational thresholds for release gate decisioning."""

    max_error_rate_hold: float = 0.50
    max_p95_latency_ms_hold: float = 1000.0
    max_drift_warning_count_warn: int = 0
    min_successful_predictions_warn: int = 10


@dataclass(frozen=True)
class ReleaseGateResult:
    """Structured release gate result."""

    decision: str
    report_path: Path
    metrics_path: Path
    hold_reasons: list[str] = field(default_factory=list)
    warning_reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_for_release(self) -> bool:
        return self.decision in {"pass", "warn"}


def run_release_gate(
    *,
    paths: ReleaseGatePaths | None = None,
    thresholds: ReleaseGateThresholds | None = None,
) -> ReleaseGateResult:
    """Evaluate release evidence and write release gate reports."""

    active_paths = paths or ReleaseGatePaths()
    active_thresholds = thresholds or ReleaseGateThresholds()
    evidence, hold_reasons, warning_reasons = _collect_evidence(active_paths, active_thresholds)
    decision = _decide(hold_reasons, warning_reasons)
    result = ReleaseGateResult(
        decision=decision,
        report_path=active_paths.report_path,
        metrics_path=active_paths.metrics_path,
        hold_reasons=hold_reasons,
        warning_reasons=warning_reasons,
        evidence=evidence,
    )
    _write_json(release_gate_payload(result), active_paths.metrics_path)
    active_paths.report_path.parent.mkdir(parents=True, exist_ok=True)
    active_paths.report_path.write_text(build_release_gate_report(result), encoding="utf-8")
    return result


def build_release_gate_report(result: ReleaseGateResult) -> str:
    """Build a Markdown release gate report."""

    hold_lines = _reason_lines(result.hold_reasons)
    warning_lines = _reason_lines(result.warning_reasons)
    evidence = result.evidence
    return "\n".join(
        [
            f"# Release Gate {__version__}",
            "",
            "Operational release gate for the local portfolio release.",
            "",
            f"- Decision: `{result.decision}`",
            f"- Report: `{result.report_path}`",
            f"- Metrics JSON: `{result.metrics_path}`",
            "",
            "## Evidence Summary",
            "",
            f"- Selected model: `{evidence.get('selected_model', 'n/a')}`",
            f"- Test MAE: {_format_optional(evidence.get('test_mae'))}",
            f"- Serving error rate: {_format_optional(evidence.get('serving_error_rate'))}",
            f"- Serving p95 latency ms: {_format_optional(evidence.get('p95_latency_ms'))}",
            f"- Successful predictions: {_format_optional(evidence.get('successful_predictions'))}",
            f"- Drift warning count: {_format_optional(evidence.get('drift_warning_count'))}",
            f"- Storage inspection available: {evidence.get('storage_inspection_available', False)}",
            f"- Verification status: {_format_optional(evidence.get('verification_status'))}",
            f"- Docker availability: {_format_optional(evidence.get('docker_status'))}",
            "",
            "## Hold Reasons",
            "",
            hold_lines,
            "",
            "## Warning Reasons",
            "",
            warning_lines,
            "",
            "## Production-Readiness Boundary",
            "",
            "- v0.1.0 is a deterministic local portfolio and operations demo.",
            "- It is not a production deployment and does not claim production readiness.",
            "- A `warn` decision is expected while evidence remains synthetic/local.",
            "",
        ],
    )


def release_gate_payload(result: ReleaseGateResult) -> dict[str, Any]:
    """Return JSON-friendly release gate payload."""

    return {
        "decision": result.decision,
        "version": __version__,
        "hold_reasons": result.hold_reasons,
        "warning_reasons": result.warning_reasons,
        "evidence": result.evidence,
    }


def _collect_evidence(
    paths: ReleaseGatePaths,
    thresholds: ReleaseGateThresholds,
) -> tuple[dict[str, Any], list[str], list[str]]:
    evidence: dict[str, Any] = {}
    holds: list[str] = []
    warnings: list[str] = [
        "Synthetic data only; no external production event source is connected.",
        "Local API is not production-hosted and has no deployment hardening.",
    ]

    model_metrics = _read_json(paths.model_metrics_path, holds, "model metrics")
    serving_metrics = _read_json(paths.serving_metrics_path, holds, "serving monitoring metrics")
    drift_metrics = _read_json(paths.drift_metrics_path, holds, "drift monitoring metrics")
    workflow_results = _read_json(paths.workflow_results_path, holds, "workflow results")

    storage_available = paths.storage_inspection_report_path.exists()
    evidence["storage_inspection_available"] = storage_available
    if not storage_available:
        holds.append(f"Missing storage inspection report: {paths.storage_inspection_report_path}")

    _evaluate_model_metrics(model_metrics, evidence, holds)
    _evaluate_serving_metrics(serving_metrics, thresholds, evidence, holds, warnings)
    _evaluate_drift_metrics(drift_metrics, thresholds, evidence, warnings)
    _evaluate_workflow_results(workflow_results, evidence, holds)
    _evaluate_verification_report(paths.verification_report_path, evidence, warnings)

    return evidence, holds, warnings


def _evaluate_model_metrics(
    metrics: dict[str, Any],
    evidence: dict[str, Any],
    holds: list[str],
) -> None:
    if not metrics:
        return
    evidence["selected_model"] = metrics.get("selected_model")
    test_metrics = metrics.get("test_metrics", {})
    evidence["test_mae"] = test_metrics.get("mae")
    evidence["test_rmse"] = test_metrics.get("rmse")
    evidence["test_r2"] = test_metrics.get("r2")
    if metrics.get("selected_model") is None:
        holds.append("Model metrics do not identify a selected model.")


def _evaluate_serving_metrics(
    metrics: dict[str, Any],
    thresholds: ReleaseGateThresholds,
    evidence: dict[str, Any],
    holds: list[str],
    warnings: list[str],
) -> None:
    if not metrics:
        return
    error_rate = float(metrics.get("error_rate", 0.0))
    p95_latency = float(metrics.get("p95_latency_ms", 0.0))
    successful_predictions = int(metrics.get("successful_predictions", 0))
    evidence["serving_error_rate"] = error_rate
    evidence["p95_latency_ms"] = p95_latency
    evidence["successful_predictions"] = successful_predictions
    evidence["serving_warning_count"] = len(metrics.get("warnings", []))

    if error_rate > thresholds.max_error_rate_hold:
        holds.append(
            f"Serving error rate {error_rate:.3f} exceeds hold threshold "
            f"{thresholds.max_error_rate_hold:.3f}.",
        )
    elif error_rate > 0:
        warnings.append(f"Serving error rate is nonzero ({error_rate:.3f}).")
    if p95_latency > thresholds.max_p95_latency_ms_hold:
        holds.append(
            f"Serving p95 latency {p95_latency:.3f}ms exceeds hold threshold "
            f"{thresholds.max_p95_latency_ms_hold:.3f}ms.",
        )
    if successful_predictions < thresholds.min_successful_predictions_warn:
        warnings.append(
            "Successful prediction sample is small "
            f"({successful_predictions} < {thresholds.min_successful_predictions_warn}).",
        )


def _evaluate_drift_metrics(
    metrics: dict[str, Any],
    thresholds: ReleaseGateThresholds,
    evidence: dict[str, Any],
    warnings: list[str],
) -> None:
    if not metrics:
        return
    drift_warning_count = len(metrics.get("warnings", []))
    evidence["drift_warning_count"] = drift_warning_count
    if drift_warning_count > thresholds.max_drift_warning_count_warn:
        warnings.append(f"Drift monitoring produced {drift_warning_count} warning(s).")
    data_quality = metrics.get("data_quality", {})
    evidence["data_quality_passed"] = all(
        bool(window.get("passed", False)) for window in data_quality.values()
    )
    if data_quality and not evidence["data_quality_passed"]:
        warnings.append("Data quality checks did not all pass.")


def _evaluate_workflow_results(
    results: dict[str, Any],
    evidence: dict[str, Any],
    holds: list[str],
) -> None:
    if not results:
        return
    status = results.get("status")
    evidence["workflow_status"] = status
    if status != "passed":
        holds.append(f"Demo workflow status is {status!r}, expected 'passed'.")
    stage_names = [stage.get("name") for stage in results.get("stages", [])]
    evidence["release_gate_in_workflow"] = "release_gate" in stage_names


def _evaluate_verification_report(
    path: Path,
    evidence: dict[str, Any],
    warnings: list[str],
) -> None:
    if not path.exists():
        evidence["verification_status"] = "missing"
        warnings.append("Release verification report is not available.")
        return
    text = path.read_text(encoding="utf-8")
    evidence["verification_status"] = "available"
    docker_line = next(
        (line.removeprefix("- Docker availability: ").strip() for line in text.splitlines() if line.startswith("- Docker availability: ")),
        "unknown",
    )
    evidence["docker_status"] = docker_line
    if "Warning status: clean" not in text:
        warnings.append("Release verification report does not show clean warning status.")
    if "Docker availability: unavailable" in text:
        warnings.append("Docker is unavailable in this environment.")


def _decide(holds: list[str], warnings: list[str]) -> str:
    if holds:
        return "hold"
    if warnings:
        return "warn"
    return "pass"


def _read_json(path: Path, holds: list[str], label: str) -> dict[str, Any]:
    if not path.exists():
        holds.append(f"Missing {label}: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        holds.append(f"Invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        holds.append(f"Invalid {label}: expected JSON object")
        return {}
    return payload


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _reason_lines(reasons: list[str]) -> str:
    if not reasons:
        return "- None."
    return "\n".join(f"- {reason}" for reason in reasons)


def _format_optional(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)


__all__ = [
    "RELEASE_GATE_DECISIONS",
    "ReleaseGatePaths",
    "ReleaseGateResult",
    "ReleaseGateThresholds",
    "build_release_gate_report",
    "release_gate_payload",
    "run_release_gate",
]

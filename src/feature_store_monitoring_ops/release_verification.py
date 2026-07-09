"""Release verification report generation."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from feature_store_monitoring_ops import __version__
from feature_store_monitoring_ops.paths import (
    DEFAULT_PORTFOLIO_SCALE_SUMMARY_PATH,
    DEFAULT_RELEASE_VERIFICATION_REPORT_PATH,
    PROJECT_ROOT,
)
from feature_store_monitoring_ops.workflow import DemoWorkflowResult, run_demo_workflow


@dataclass(frozen=True)
class ReleaseCommandResult:
    """Result from one release verification shell command."""

    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    @property
    def command_text(self) -> str:
        return " ".join(self.command)


@dataclass(frozen=True)
class ReleaseVerificationResult:
    """Structured result from release verification."""

    report_path: Path
    pytest_result: ReleaseCommandResult
    warning_result: ReleaseCommandResult
    ruff_result: ReleaseCommandResult
    workflow_status: str
    warning_status: str
    docker_status: str

    @property
    def passed(self) -> bool:
        return (
            self.pytest_result.passed
            and self.warning_result.passed
            and self.ruff_result.passed
            and self.workflow_status == "passed"
            and self.warning_status.startswith("clean")
        )


CommandRunner = Callable[[Sequence[str]], ReleaseCommandResult]


def generate_release_verification_report(
    *,
    report_path: Path = DEFAULT_RELEASE_VERIFICATION_REPORT_PATH,
    command_runner: CommandRunner | None = None,
    workflow_result: DemoWorkflowResult | None = None,
    docker_status: str | None = None,
) -> ReleaseVerificationResult:
    """Run release checks and write the tracked verification report."""

    runner = command_runner or _run_command
    pytest_result = runner(_tool_command("pytest", "-q"))
    warning_result = runner(_tool_command("pytest", "-q", "-W", "default"))
    ruff_result = runner(_tool_command("ruff", "check", "."))
    active_workflow_result = workflow_result or run_demo_workflow()
    active_docker_status = docker_status or detect_docker_status()
    warning_status = _warning_status(warning_result)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_release_verification_report(
            pytest_result=pytest_result,
            warning_result=warning_result,
            ruff_result=ruff_result,
            workflow_result=active_workflow_result,
            warning_status=warning_status,
            docker_status=active_docker_status,
            portfolio_scale_metrics=_read_portfolio_scale_metrics(DEFAULT_PORTFOLIO_SCALE_SUMMARY_PATH),
        ),
        encoding="utf-8",
    )
    return ReleaseVerificationResult(
        report_path=report_path,
        pytest_result=pytest_result,
        warning_result=warning_result,
        ruff_result=ruff_result,
        workflow_status=active_workflow_result.status,
        warning_status=warning_status,
        docker_status=active_docker_status,
    )


def build_release_verification_report(
    *,
    pytest_result: ReleaseCommandResult,
    warning_result: ReleaseCommandResult,
    ruff_result: ReleaseCommandResult,
    workflow_result: DemoWorkflowResult,
    warning_status: str,
    docker_status: str,
    portfolio_scale_metrics: dict[str, str],
) -> str:
    """Build the Markdown release verification report."""

    metrics = _workflow_metrics(workflow_result)
    portfolio_lines = _metric_lines(portfolio_scale_metrics)
    if not portfolio_lines:
        portfolio_lines = "- Portfolio-scale counts: not available in current tracked reports."
    limitations = "\n".join(
        [
            "- Synthetic data only; no external production event source is connected.",
            "- FastAPI serving is local; optional API key auth exists, but full identity, rate limiting, and cloud deployment are out of scope.",
            "- Redis and Postgres paths are optional adapters and are not required by release checks.",
            "- SQLite databases are local development stores, not production warehouses.",
            "- Models are deterministic baselines for system validation, not tuned production forecasts.",
            "- Docker smoke testing is optional and depends on local Docker availability.",
        ],
    )
    return "\n".join(
        [
            f"# Release Verification {__version__}",
            "",
            "Tracked release-quality verification report for the local deterministic system.",
            "",
            "## Check Results",
            "",
            f"- `pytest -q`: {_check_status(pytest_result)}",
            f"- `pytest -q -W default`: {_check_status(warning_result)}",
            f"- Warning status: {warning_status}",
            f"- `ruff check .`: {_check_status(ruff_result)}",
            f"- Demo workflow: {workflow_result.status}",
            f"- Docker availability: {docker_status}",
            "",
            "## Default Workflow Counts",
            "",
            f"- Synthetic rows: {_format_metric(metrics.get('synthetic_rows'))}",
            f"- Offline feature rows: {_format_metric(metrics.get('offline_rows'))}",
            f"- Online feature rows: {_format_metric(metrics.get('online_feature_rows'))}",
            f"- Simulated prediction requests: {_format_metric(metrics.get('simulated_requests'))}",
            f"- SQLite telemetry rows: {_format_metric(metrics.get('telemetry_rows'))}",
            f"- Relational event rows: {_format_metric(metrics.get('relational_event_rows'))}",
            f"- Relational offline feature rows: "
            f"{_format_metric(metrics.get('relational_offline_feature_rows'))}",
            f"- Relational online snapshot rows: "
            f"{_format_metric(metrics.get('relational_online_snapshot_rows'))}",
            "",
            "## Portfolio-Scale Counts",
            "",
            portfolio_lines,
            "",
            "## Warning Policy",
            "",
            "- Project-owned warnings fail tests through pytest warning filters.",
            "- Known third-party deprecations are filtered narrowly by message, category, and module.",
            "- The verification command records the visible-warning pytest result so new warning noise is caught.",
            "",
            "## Known Limitations",
            "",
            limitations,
            "",
        ],
    )


def detect_docker_status() -> str:
    """Return a lightweight Docker availability status without requiring Docker."""

    docker = shutil.which("docker")
    if docker is None:
        return "unavailable: docker command not found"
    result = _run_command((docker, "--version"))
    if result.passed:
        return result.stdout.strip() or "available"
    detail = (result.stdout or result.stderr).strip().splitlines()
    if detail:
        return f"unavailable: {detail[0]}"
    return "unavailable: docker command failed"


def _run_command(command: Sequence[str]) -> ReleaseCommandResult:
    start = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return ReleaseCommandResult(
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=round(time.perf_counter() - start, 3),
    )


def _tool_command(tool_name: str, *args: str) -> tuple[str, ...]:
    candidate = Path(sys.executable).parent / tool_name
    executable = str(candidate) if candidate.exists() else tool_name
    return (executable, *args)


def _warning_status(result: ReleaseCommandResult) -> str:
    output = f"{result.stdout}\n{result.stderr}".lower()
    if not result.passed:
        return "failed: warning-visible pytest run did not pass"
    if "warnings summary" in output or re.search(r"\b\d+\s+warnings?\b", output):
        return "warnings emitted"
    return "clean: no warnings emitted"


def _check_status(result: ReleaseCommandResult) -> str:
    status = "passed" if result.passed else "failed"
    return f"{status} ({result.duration_seconds:.3f}s)"


def _workflow_metrics(result: DemoWorkflowResult) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for stage in result.stages:
        if stage.name == "generate_synthetic_events":
            metrics["synthetic_rows"] = stage.metrics.get("rows_written")
        elif stage.name == "build_offline_features":
            metrics["offline_rows"] = stage.metrics.get("offline")
        elif stage.name == "materialize_online_features":
            metrics["online_feature_rows"] = stage.metrics.get("row_count")
        elif stage.name == "simulate_traffic":
            metrics["simulated_requests"] = stage.metrics.get("total_requests")
        elif stage.name == "inspect_storage":
            metrics["telemetry_rows"] = stage.metrics.get("telemetry_row_count")
        elif stage.name == "inspect_relational_store":
            metrics["relational_event_rows"] = stage.metrics.get("event_row_count")
            metrics["relational_offline_feature_rows"] = stage.metrics.get(
                "offline_feature_row_count",
            )
            metrics["relational_online_snapshot_rows"] = stage.metrics.get(
                "online_snapshot_row_count",
            )
    return metrics


def _read_portfolio_scale_metrics(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    metrics: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"- ([A-Za-z -]+): (.+)", line)
        if match:
            key = match.group(1).strip().lower().replace(" ", "_").replace("-", "_")
            metrics[key] = match.group(2).strip()
    return metrics


def _metric_lines(metrics: dict[str, str]) -> str:
    desired_keys = (
        "synthetic_rows",
        "configured_zones",
        "offline_feature_rows",
        "online_feature_rows",
        "simulated_prediction_requests",
        "relational_event_rows",
        "relational_offline_feature_rows",
        "relational_online_snapshot_rows",
    )
    lines = [
        f"- {key.replace('_', ' ').title()}: {metrics[key]}"
        for key in desired_keys
        if key in metrics
    ]
    return "\n".join(lines)


def _format_metric(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)


__all__ = [
    "ReleaseCommandResult",
    "ReleaseVerificationResult",
    "build_release_verification_report",
    "detect_docker_status",
    "generate_release_verification_report",
]

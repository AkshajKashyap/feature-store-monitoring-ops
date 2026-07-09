from __future__ import annotations

import tomllib
import json
from pathlib import Path
from typing import Sequence

from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.release_verification import (
    ReleaseCommandResult,
    generate_release_verification_report,
)
from feature_store_monitoring_ops.release_gate import (
    RELEASE_GATE_DECISIONS,
    ReleaseGatePaths,
    run_release_gate,
)
from feature_store_monitoring_ops.workflow import (
    STAGE_PASSED,
    DemoWorkflowResult,
    WorkflowStageResult,
)


def test_ci_workflow_file_exists_and_runs_release_path() -> None:
    workflow = Path(".github/workflows/ci.yml")
    content = workflow.read_text(encoding="utf-8")

    assert workflow.exists()
    assert 'python-version: "3.11"' in content
    assert "pytest -q" in content
    assert "pytest -q -W default" in content
    assert "ruff check ." in content
    assert "feature-store-ops run-demo-workflow" in content


def test_verification_report_generation(tmp_path) -> None:
    report_path = tmp_path / "verification_0.1.0.md"

    result = generate_release_verification_report(
        report_path=report_path,
        command_runner=_fake_command_runner,
        workflow_result=_fake_workflow_result(tmp_path),
        docker_status="unavailable: test docker not installed",
    )

    content = report_path.read_text(encoding="utf-8")
    assert result.passed
    assert "Release Verification 0.1.0" in content
    assert "`pytest -q`: passed" in content
    assert "Warning status: clean: no warnings emitted" in content
    assert "Relational event rows: 20" in content
    assert "Docker availability: unavailable: test docker not installed" in content


def test_project_info_command_includes_capabilities_and_limitations() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_app, ["project-info"])

    assert result.exit_code == 0
    assert "core_capabilities:" in result.output
    assert "relational storage" in result.output
    assert "workflow verification" in result.output
    assert "current_limitations:" in result.output
    assert "release_verification_report_path:" in result.output


def test_release_gate_report_generation(tmp_path) -> None:
    paths = _write_release_gate_inputs(tmp_path)

    result = run_release_gate(paths=paths)

    assert result.decision == "warn"
    assert result.report_path.exists()
    assert result.metrics_path.exists()
    assert "Decision: `warn`" in result.report_path.read_text(encoding="utf-8")
    payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "warn"
    assert payload["evidence"]["selected_model"] == "hist_gradient_boosting"


def test_release_gate_decision_is_valid(tmp_path) -> None:
    paths = _write_release_gate_inputs(tmp_path)

    result = run_release_gate(paths=paths)

    assert result.decision in RELEASE_GATE_DECISIONS


def test_warning_filters_are_narrow_not_blanket_ignores() -> None:
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")
    config = tomllib.loads(pyproject_text)
    filters = config["tool"]["pytest"]["ini_options"]["filterwarnings"]

    assert "Release warning budget" in pyproject_text
    assert "joblib 1.x" in pyproject_text
    assert "error::Warning:feature_store_monitoring_ops.*" in filters
    assert any(
        filter_rule.startswith("ignore:Setting the shape on a NumPy array")
        and ":DeprecationWarning:joblib\\.numpy_pickle" in filter_rule
        for filter_rule in filters
    )
    assert not any(filter_rule.startswith("ignore::") for filter_rule in filters)
    assert not any(filter_rule.startswith("ignore:.*") for filter_rule in filters)


def test_docs_expected_by_readme_exist() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    expected_docs = (
        "docs/architecture.md",
        "docs/operations.md",
        "docs/system_card.md",
        "docs/release_checklist.md",
    )

    for doc_path in expected_docs:
        assert doc_path in readme
        assert Path(doc_path).exists()


def _fake_command_runner(command: Sequence[str]) -> ReleaseCommandResult:
    output = "70 passed in 1.00s\n"
    if "ruff" in command[0]:
        output = "All checks passed!\n"
    return ReleaseCommandResult(
        command=tuple(command),
        returncode=0,
        stdout=output,
        duration_seconds=0.01,
    )


def _fake_workflow_result(tmp_path: Path) -> DemoWorkflowResult:
    return DemoWorkflowResult(
        stages=[
            WorkflowStageResult(
                name="generate_synthetic_events",
                status=STAGE_PASSED,
                metrics={"rows_written": 24},
            ),
            WorkflowStageResult(
                name="build_offline_features",
                status=STAGE_PASSED,
                metrics={"offline": 18},
            ),
            WorkflowStageResult(
                name="materialize_online_features",
                status=STAGE_PASSED,
                metrics={"row_count": 3},
            ),
            WorkflowStageResult(
                name="simulate_traffic",
                status=STAGE_PASSED,
                metrics={"total_requests": 4},
            ),
            WorkflowStageResult(
                name="inspect_storage",
                status=STAGE_PASSED,
                metrics={"telemetry_row_count": 4},
            ),
            WorkflowStageResult(
                name="inspect_relational_store",
                status=STAGE_PASSED,
                metrics={
                    "event_row_count": 20,
                    "offline_feature_row_count": 18,
                    "online_snapshot_row_count": 3,
                },
            ),
        ],
        workflow_summary_path=tmp_path / "workflow_summary.md",
        workflow_results_path=tmp_path / "workflow_results.json",
        portfolio_summary_path=tmp_path / "portfolio_summary.md",
    )


def _write_release_gate_inputs(tmp_path: Path) -> ReleaseGatePaths:
    model_metrics_path = tmp_path / "model_metrics.json"
    serving_metrics_path = tmp_path / "serving_monitoring_metrics.json"
    drift_metrics_path = tmp_path / "drift_monitoring_metrics.json"
    storage_report_path = tmp_path / "storage_inspection_summary.md"
    workflow_results_path = tmp_path / "workflow_results.json"
    verification_report_path = tmp_path / "verification_0.1.0.md"
    report_path = tmp_path / "release_gate_0.1.0.md"
    metrics_path = tmp_path / "release_gate_0.1.0.json"
    _write_json(
        model_metrics_path,
        {
            "selected_model": "hist_gradient_boosting",
            "test_metrics": {"mae": 6.2, "rmse": 7.9, "r2": 0.3},
        },
    )
    _write_json(
        serving_metrics_path,
        {
            "error_rate": 0.1,
            "p95_latency_ms": 20.0,
            "successful_predictions": 5,
            "warnings": ["small sample"],
        },
    )
    _write_json(
        drift_metrics_path,
        {
            "warnings": ["sample too small"],
            "data_quality": {"reference": {"passed": True}, "current": {"passed": True}},
        },
    )
    storage_report_path.write_text("# Storage Inspection Summary\n", encoding="utf-8")
    _write_json(
        workflow_results_path,
        {
            "status": "passed",
            "stages": [{"name": "inspect_storage"}, {"name": "inspect_relational_store"}],
        },
    )
    verification_report_path.write_text(
        "\n".join(
            [
                "# Release Verification 0.1.0",
                "- Warning status: clean: no warnings emitted",
                "- Docker availability: unavailable: docker command not found",
            ],
        ),
        encoding="utf-8",
    )
    return ReleaseGatePaths(
        model_metrics_path=model_metrics_path,
        serving_metrics_path=serving_metrics_path,
        drift_metrics_path=drift_metrics_path,
        storage_inspection_report_path=storage_report_path,
        workflow_results_path=workflow_results_path,
        verification_report_path=verification_report_path,
        report_path=report_path,
        metrics_path=metrics_path,
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

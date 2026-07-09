from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app as cli_app
from feature_store_monitoring_ops.workflow import (
    PORTFOLIO_SYNTHETIC_PRESET,
    STAGE_PASSED,
    WORKFLOW_STAGE_ORDER,
    DemoWorkflowConfig,
    DemoWorkflowResult,
    WorkflowStageResult,
    run_demo_workflow,
)


def test_workflow_stage_ordering() -> None:
    assert WORKFLOW_STAGE_ORDER == (
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
        "sync_relational_store",
        "inspect_relational_store",
    )


def test_workflow_result_object_structure(tmp_path) -> None:
    stage = WorkflowStageResult(
        name="example",
        status=STAGE_PASSED,
        output_paths={"report": str(tmp_path / "report.md")},
        metrics={"rows": 1},
    )
    result = DemoWorkflowResult(
        stages=[stage],
        workflow_summary_path=tmp_path / "workflow_summary.md",
        workflow_results_path=tmp_path / "workflow_results.json",
        portfolio_summary_path=tmp_path / "portfolio_summary.md",
    )

    payload = result.to_dict()

    assert payload["status"] == STAGE_PASSED
    assert payload["stages"][0]["name"] == "example"
    assert payload["stages"][0]["metrics"] == {"rows": 1}
    assert set(payload["output_paths"]) == {
        "portfolio_scale_summary",
        "workflow_summary",
        "workflow_results",
        "portfolio_summary",
    }


def test_workflow_writes_markdown_and_json_reports(tmp_path) -> None:
    result = run_demo_workflow(DemoWorkflowConfig(output_root=tmp_path, num_events=168, seed=77))

    assert result.passed
    assert result.workflow_summary_path.exists()
    assert result.workflow_results_path.exists()
    assert result.portfolio_summary_path.exists()
    assert "Workflow Summary" in result.workflow_summary_path.read_text(encoding="utf-8")
    assert "Portfolio Summary" in result.portfolio_summary_path.read_text(encoding="utf-8")

    payload = json.loads(result.workflow_results_path.read_text(encoding="utf-8"))
    assert payload["status"] == STAGE_PASSED
    assert [stage["name"] for stage in payload["stages"]] == list(WORKFLOW_STAGE_ORDER)
    assert all(stage["status"] == STAGE_PASSED for stage in payload["stages"])
    assert (tmp_path / "reports" / "relational_storage_sync_summary.md").exists()
    assert (tmp_path / "reports" / "relational_storage_inspection_summary.md").exists()


def test_run_demo_workflow_cli_smoke_behavior(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "run-demo-workflow",
            "--output-root",
            str(tmp_path),
            "--events",
            "168",
            "--seed",
            "88",
        ],
    )

    assert result.exit_code == 0
    assert "workflow status: passed" in result.output
    assert "generate_synthetic_events: passed" in result.output
    assert "sync_relational_store: passed" in result.output
    assert "inspect_relational_store: passed" in result.output
    assert (tmp_path / "reports" / "portfolio" / "workflow_summary.md").exists()
    assert (tmp_path / "reports" / "portfolio" / "workflow_results.json").exists()
    assert (tmp_path / "reports" / "portfolio" / "portfolio_summary.md").exists()


def test_workflow_accepts_portfolio_preset_and_increases_online_rows(tmp_path) -> None:
    result = run_demo_workflow(
        DemoWorkflowConfig.from_preset(
            preset=PORTFOLIO_SYNTHETIC_PRESET,
            output_root=tmp_path,
            zone_count=8,
            num_days=6,
            events_per_zone_per_day=2,
            traffic_request_count=12,
        ),
    )

    assert result.passed
    payload = json.loads(result.workflow_results_path.read_text(encoding="utf-8"))
    materialize_stage = next(
        stage for stage in payload["stages"] if stage["name"] == "materialize_online_features"
    )
    traffic_stage = next(stage for stage in payload["stages"] if stage["name"] == "simulate_traffic")

    assert payload["status"] == STAGE_PASSED
    assert materialize_stage["metrics"]["row_count"] == 8
    assert materialize_stage["metrics"]["row_count"] > 5
    assert traffic_stage["metrics"]["total_requests"] == 12
    assert (tmp_path / "reports" / "portfolio" / "portfolio_scale_summary.md").exists()


def test_workflow_includes_relational_storage_stages() -> None:
    assert "sync_relational_store" in WORKFLOW_STAGE_ORDER
    assert "inspect_relational_store" in WORKFLOW_STAGE_ORDER
    assert WORKFLOW_STAGE_ORDER.index("sync_relational_store") > WORKFLOW_STAGE_ORDER.index(
        "inspect_storage",
    )
    assert WORKFLOW_STAGE_ORDER.index("inspect_relational_store") > WORKFLOW_STAGE_ORDER.index(
        "sync_relational_store",
    )


def test_makefile_target_names_exist() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    target_text = "\n" + makefile

    for target in ("install", "check", "demo", "smoke", "release-check"):
        assert f"\n{target}:" in target_text

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from feature_store_monitoring_ops.cli import app
from feature_store_monitoring_ops.features.offline import (
    TARGET_COLUMN,
    build_offline_features,
    split_chronologically,
)
from feature_store_monitoring_ops.models.training import (
    METRIC_KEYS,
    compute_regression_metrics,
    get_model_input_columns,
    select_model_from_validation_metrics,
    split_features_and_target,
    train_and_evaluate_models,
)
from feature_store_monitoring_ops.synthetic_events import SyntheticEventConfig, generate_synthetic_events


def test_target_column_excluded_from_model_input_features() -> None:
    features = build_offline_features(
        pd.DataFrame(generate_synthetic_events(SyntheticEventConfig(num_events=144, seed=101))),
    )

    inputs, target = split_features_and_target(features)

    assert TARGET_COLUMN not in get_model_input_columns()
    assert TARGET_COLUMN not in inputs.columns
    assert len(inputs) == len(target)


def test_metrics_contain_required_keys() -> None:
    metrics = compute_regression_metrics(
        target=pd.Series([10.0, 12.0, 14.0]),
        predictions=pd.Series([9.0, 13.0, 14.0]),
    )

    assert set(METRIC_KEYS) == set(metrics)


def test_selected_model_uses_validation_metrics_not_test_metrics() -> None:
    validation_metrics = {
        "validation_winner": {"mae": 1.0, "rmse": 1.5, "r2": 0.8},
        "test_would_have_won": {"mae": 5.0, "rmse": 5.5, "r2": 0.2},
    }
    test_metrics = {
        "validation_winner": {"mae": 10.0},
        "test_would_have_won": {"mae": 0.1},
    }

    selected_model = select_model_from_validation_metrics(validation_metrics)

    assert selected_model == "validation_winner"
    assert test_metrics["test_would_have_won"]["mae"] < test_metrics["validation_winner"]["mae"]


def test_model_artifact_and_manifest_are_written(tmp_path) -> None:
    paths = _write_feature_split_parquets(tmp_path)
    model_path = tmp_path / "selected_model.joblib"
    manifest_path = tmp_path / "model_manifest.json"
    metrics_path = tmp_path / "model_metrics.json"
    report_path = tmp_path / "model_training_summary.md"

    result = train_and_evaluate_models(
        train_path=paths["train"],
        validation_path=paths["validation"],
        test_path=paths["test"],
        model_path=model_path,
        manifest_path=manifest_path,
        metrics_path=metrics_path,
        report_path=report_path,
    )

    assert model_path.exists()
    assert manifest_path.exists()
    assert metrics_path.exists()
    assert report_path.exists()
    assert result.selected_model_name in result.validation_metrics

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["selected_model"] == result.selected_model_name
    assert TARGET_COLUMN not in manifest["input_features"]


def test_train_model_cli_smoke(tmp_path) -> None:
    runner = CliRunner()
    paths = _write_feature_split_parquets(tmp_path)
    model_path = tmp_path / "selected_model.joblib"
    manifest_path = tmp_path / "model_manifest.json"
    metrics_path = tmp_path / "model_metrics.json"
    report_path = tmp_path / "model_training_summary.md"

    result = runner.invoke(
        app,
        [
            "train-model",
            "--train-path",
            str(paths["train"]),
            "--validation-path",
            str(paths["validation"]),
            "--test-path",
            str(paths["test"]),
            "--model-path",
            str(model_path),
            "--manifest-path",
            str(manifest_path),
            "--metrics-path",
            str(metrics_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "selected model:" in result.output
    assert model_path.exists()
    assert manifest_path.exists()
    assert metrics_path.exists()
    assert report_path.exists()


def _write_feature_split_parquets(tmp_path: Path) -> dict[str, Path]:
    events = pd.DataFrame(
        generate_synthetic_events(
            SyntheticEventConfig(num_events=168, seed=202, zone_count=2, user_count=20),
        ),
    )
    features = build_offline_features(events)
    splits = split_chronologically(features, train_fraction=0.60, validation_fraction=0.20)
    paths = {
        "train": tmp_path / "train_features.parquet",
        "validation": tmp_path / "validation_features.parquet",
        "test": tmp_path / "test_features.parquet",
    }
    for name, path in paths.items():
        splits[name].to_parquet(path, index=False)
    return paths

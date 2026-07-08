"""Baseline model training and validation-only model selection."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from feature_store_monitoring_ops.features.offline import OFFLINE_FEATURE_COLUMNS, TARGET_COLUMN
from feature_store_monitoring_ops.paths import (
    DEFAULT_MODEL_MANIFEST_PATH,
    DEFAULT_MODEL_METRICS_PATH,
    DEFAULT_MODEL_TRAINING_REPORT_PATH,
    DEFAULT_SELECTED_MODEL_PATH,
    DEFAULT_TEST_FEATURES_PATH,
    DEFAULT_TRAIN_FEATURES_PATH,
    DEFAULT_VALIDATION_FEATURES_PATH,
)

METRIC_KEYS: tuple[str, ...] = ("mae", "rmse", "r2", "mean_prediction", "mean_target")
MODEL_SELECTION_METRIC = "mae"


class ColumnBaselineRegressor(BaseEstimator, RegressorMixin):
    """Baseline regressor that predicts directly from one existing feature column."""

    def __init__(self, column: str) -> None:
        self.column = column

    def fit(self, features: pd.DataFrame, target: pd.Series | None = None) -> ColumnBaselineRegressor:
        if self.column not in features.columns:
            raise ValueError(f"baseline column missing from features: {self.column}")
        return self

    def predict(self, features: pd.DataFrame) -> pd.Series:
        if self.column not in features.columns:
            raise ValueError(f"baseline column missing from features: {self.column}")
        return pd.to_numeric(features[self.column], errors="raise")


@dataclass(frozen=True)
class ModelTrainingResult:
    """Artifacts and metrics from training and evaluating baseline models."""

    selected_model_name: str
    validation_metrics: dict[str, dict[str, float]]
    test_metrics: dict[str, float]
    model_path: Path
    manifest_path: Path
    metrics_path: Path
    report_path: Path
    input_features: tuple[str, ...]
    row_counts: dict[str, int]


def get_model_input_columns() -> tuple[str, ...]:
    """Return model input columns, explicitly excluding the target."""

    if TARGET_COLUMN in OFFLINE_FEATURE_COLUMNS:
        raise ValueError("target column must not be part of model input features")
    return OFFLINE_FEATURE_COLUMNS


def load_feature_splits(
    *,
    train_path: Path = DEFAULT_TRAIN_FEATURES_PATH,
    validation_path: Path = DEFAULT_VALIDATION_FEATURES_PATH,
    test_path: Path = DEFAULT_TEST_FEATURES_PATH,
) -> dict[str, pd.DataFrame]:
    """Load chronological feature splits from parquet files."""

    return {
        "train": _read_feature_split(train_path),
        "validation": _read_feature_split(validation_path),
        "test": _read_feature_split(test_path),
    }


def train_and_evaluate_models(
    *,
    train_path: Path = DEFAULT_TRAIN_FEATURES_PATH,
    validation_path: Path = DEFAULT_VALIDATION_FEATURES_PATH,
    test_path: Path = DEFAULT_TEST_FEATURES_PATH,
    model_path: Path = DEFAULT_SELECTED_MODEL_PATH,
    manifest_path: Path = DEFAULT_MODEL_MANIFEST_PATH,
    metrics_path: Path = DEFAULT_MODEL_METRICS_PATH,
    report_path: Path = DEFAULT_MODEL_TRAINING_REPORT_PATH,
    random_state: int = 42,
) -> ModelTrainingResult:
    """Train candidate models, select by validation metrics, then evaluate test once."""

    splits = load_feature_splits(
        train_path=train_path,
        validation_path=validation_path,
        test_path=test_path,
    )
    result = train_and_evaluate_feature_splits(
        train_features=splits["train"],
        validation_features=splits["validation"],
        test_features=splits["test"],
        random_state=random_state,
    )
    selected_model = result["fitted_models"][result["selected_model_name"]]
    validation_metrics = result["validation_metrics"]
    test_metrics = result["test_metrics"]
    selected_model_name = result["selected_model_name"]
    input_features = get_model_input_columns()
    row_counts = {name: len(frame) for name, frame in splits.items()}

    _write_model_artifact(selected_model, model_path)
    manifest = build_model_manifest(
        selected_model_name=selected_model_name,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        input_features=input_features,
        row_counts=row_counts,
    )
    _write_json(manifest, manifest_path)
    _write_json(
        {
            "selected_model": selected_model_name,
            "selection_metric": MODEL_SELECTION_METRIC,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
        },
        metrics_path,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_model_training_summary(
            selected_model_name=selected_model_name,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            input_features=input_features,
            row_counts=row_counts,
        ),
        encoding="utf-8",
    )

    return ModelTrainingResult(
        selected_model_name=selected_model_name,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        model_path=model_path,
        manifest_path=manifest_path,
        metrics_path=metrics_path,
        report_path=report_path,
        input_features=input_features,
        row_counts=row_counts,
    )


def train_and_evaluate_feature_splits(
    *,
    train_features: pd.DataFrame,
    validation_features: pd.DataFrame,
    test_features: pd.DataFrame,
    random_state: int = 42,
) -> dict[str, Any]:
    """Train model candidates and evaluate the selected model on test data."""

    train_x, train_y = split_features_and_target(train_features)
    validation_x, validation_y = split_features_and_target(validation_features)
    test_x, test_y = split_features_and_target(test_features)

    fitted_models: dict[str, BaseEstimator] = {}
    validation_metrics: dict[str, dict[str, float]] = {}
    for name, model in create_model_candidates(random_state=random_state).items():
        fitted_model = model.fit(train_x, train_y)
        validation_predictions = fitted_model.predict(validation_x)
        validation_metrics[name] = compute_regression_metrics(validation_y, validation_predictions)
        fitted_models[name] = fitted_model

    selected_model_name = select_model_from_validation_metrics(validation_metrics)
    test_predictions = fitted_models[selected_model_name].predict(test_x)
    test_metrics = compute_regression_metrics(test_y, test_predictions)

    return {
        "selected_model_name": selected_model_name,
        "fitted_models": fitted_models,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
    }


def split_features_and_target(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Split a feature frame into model inputs and target, preventing target leakage."""

    input_columns = get_model_input_columns()
    required = set(input_columns).union({TARGET_COLUMN})
    missing = sorted(required.difference(features.columns))
    if missing:
        raise ValueError(f"feature split missing required columns: {', '.join(missing)}")
    inputs = features.loc[:, input_columns].copy()
    if TARGET_COLUMN in inputs.columns:
        raise ValueError("target column leaked into model inputs")
    target = pd.to_numeric(features[TARGET_COLUMN], errors="raise")
    return inputs, target


def create_model_candidates(random_state: int = 42) -> dict[str, BaseEstimator]:
    """Create deterministic candidate forecasting models."""

    return {
        "naive_lag_1": ColumnBaselineRegressor("lag_1_observed_demand"),
        "zone_hour_mean": ColumnBaselineRegressor("zone_hour_mean_demand"),
        "ridge_regression": Pipeline(
            [
                ("preprocess", _build_preprocessor()),
                ("model", Ridge(alpha=1.0)),
            ],
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("preprocess", _build_preprocessor()),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        learning_rate=0.08,
                        max_iter=120,
                        max_leaf_nodes=15,
                        random_state=random_state,
                    ),
                ),
            ],
        ),
    }


def compute_regression_metrics(
    target: pd.Series,
    predictions: pd.Series | list[float] | Any,
) -> dict[str, float]:
    """Compute deterministic regression metrics for model comparison."""

    target_values = pd.to_numeric(pd.Series(target), errors="raise")
    prediction_values = pd.to_numeric(pd.Series(predictions), errors="raise")
    mae = mean_absolute_error(target_values, prediction_values)
    rmse = math.sqrt(mean_squared_error(target_values, prediction_values))
    r2 = r2_score(target_values, prediction_values)
    return {
        "mae": round(float(mae), 6),
        "rmse": round(float(rmse), 6),
        "r2": round(float(r2), 6),
        "mean_prediction": round(float(prediction_values.mean()), 6),
        "mean_target": round(float(target_values.mean()), 6),
    }


def select_model_from_validation_metrics(
    validation_metrics: dict[str, dict[str, float]],
    *,
    metric_name: str = MODEL_SELECTION_METRIC,
) -> str:
    """Select the best model by validation metrics only."""

    if not validation_metrics:
        raise ValueError("validation metrics are required for model selection")
    return min(validation_metrics, key=lambda name: validation_metrics[name][metric_name])


def build_model_manifest(
    *,
    selected_model_name: str,
    validation_metrics: dict[str, dict[str, float]],
    test_metrics: dict[str, float],
    input_features: tuple[str, ...],
    row_counts: dict[str, int],
) -> dict[str, Any]:
    """Build the selected model manifest saved beside the model artifact."""

    return {
        "selected_model": selected_model_name,
        "selection_metric": MODEL_SELECTION_METRIC,
        "input_features": list(input_features),
        "target_column": TARGET_COLUMN,
        "row_counts": row_counts,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "leakage_notes": [
            "Candidate models are trained on the train split only.",
            "Model selection uses validation metrics only.",
            "The test split is evaluated once after model selection.",
            f"`{TARGET_COLUMN}` is excluded from model input features.",
        ],
    }


def build_model_training_summary(
    *,
    selected_model_name: str,
    validation_metrics: dict[str, dict[str, float]],
    test_metrics: dict[str, float],
    input_features: tuple[str, ...],
    row_counts: dict[str, int],
) -> str:
    """Build a tracked Markdown report for model training and evaluation."""

    validation_rows = "\n".join(
        (
            f"| {name} | {metrics['mae']:.6f} | {metrics['rmse']:.6f} | "
            f"{metrics['r2']:.6f} | {metrics['mean_prediction']:.6f} | "
            f"{metrics['mean_target']:.6f} |"
        )
        for name, metrics in validation_metrics.items()
    )
    test_rows = "\n".join(f"- {key}: {value:.6f}" for key, value in test_metrics.items())
    feature_lines = "\n".join(f"- `{column}`" for column in input_features)

    return "\n".join(
        [
            "# Model Training Summary",
            "",
            "Trained baseline demand forecasting models for Milestone 3.",
            "",
            "## Selected Model",
            "",
            f"- Selected model: `{selected_model_name}`",
            f"- Selection metric: validation `{MODEL_SELECTION_METRIC}`",
            "",
            "## Row Counts",
            "",
            f"- Train: {row_counts['train']}",
            f"- Validation: {row_counts['validation']}",
            f"- Test: {row_counts['test']}",
            "",
            "## Validation Metrics",
            "",
            "| Model | MAE | RMSE | R2 | Mean prediction | Mean target |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            validation_rows,
            "",
            "## Test Metrics",
            "",
            test_rows,
            "",
            "## Input Features",
            "",
            feature_lines,
            "",
            "## Leakage Notes",
            "",
            "- Candidate models are trained on the train split only.",
            "- Validation metrics select the model.",
            "- The selected model is evaluated on the test split only after selection.",
            f"- `{TARGET_COLUMN}` is never included as an input feature.",
            "",
        ],
    )


def _build_preprocessor() -> ColumnTransformer:
    input_columns = get_model_input_columns()
    categorical_columns = ["zone_id"]
    numeric_columns = [column for column in input_columns if column not in categorical_columns]
    return ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_columns),
            ("numeric", StandardScaler(), numeric_columns),
        ],
        remainder="drop",
    )


def _read_feature_split(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"feature split not found: {path}")
    return pd.read_parquet(path)


def _write_model_artifact(model: BaseEstimator, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "METRIC_KEYS",
    "MODEL_SELECTION_METRIC",
    "ColumnBaselineRegressor",
    "ModelTrainingResult",
    "build_model_manifest",
    "build_model_training_summary",
    "compute_regression_metrics",
    "create_model_candidates",
    "get_model_input_columns",
    "load_feature_splits",
    "select_model_from_validation_metrics",
    "split_features_and_target",
    "train_and_evaluate_feature_splits",
    "train_and_evaluate_models",
]

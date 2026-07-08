"""Project paths used by the local CLI."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNTHETIC_EVENTS_PATH = PROJECT_ROOT / "data" / "processed" / "synthetic_events.csv"
DEFAULT_SYNTHETIC_REPORT_PATH = PROJECT_ROOT / "reports" / "synthetic_events_summary.md"
DEFAULT_OFFLINE_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "offline_features.parquet"
DEFAULT_TRAIN_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "train_features.parquet"
DEFAULT_VALIDATION_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "validation_features.parquet"
DEFAULT_TEST_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "test_features.parquet"
DEFAULT_OFFLINE_FEATURE_REPORT_PATH = PROJECT_ROOT / "reports" / "offline_feature_summary.md"
DEFAULT_SELECTED_MODEL_PATH = PROJECT_ROOT / "artifacts" / "models" / "selected_model.joblib"
DEFAULT_MODEL_MANIFEST_PATH = PROJECT_ROOT / "artifacts" / "models" / "model_manifest.json"
DEFAULT_MODEL_TRAINING_REPORT_PATH = PROJECT_ROOT / "reports" / "model_training_summary.md"
DEFAULT_MODEL_METRICS_PATH = PROJECT_ROOT / "reports" / "model_metrics.json"

__all__ = [
    "DEFAULT_MODEL_MANIFEST_PATH",
    "DEFAULT_MODEL_METRICS_PATH",
    "DEFAULT_MODEL_TRAINING_REPORT_PATH",
    "DEFAULT_OFFLINE_FEATURE_REPORT_PATH",
    "DEFAULT_OFFLINE_FEATURES_PATH",
    "DEFAULT_SELECTED_MODEL_PATH",
    "DEFAULT_SYNTHETIC_EVENTS_PATH",
    "DEFAULT_SYNTHETIC_REPORT_PATH",
    "DEFAULT_TEST_FEATURES_PATH",
    "DEFAULT_TRAIN_FEATURES_PATH",
    "DEFAULT_VALIDATION_FEATURES_PATH",
    "PROJECT_ROOT",
]

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
DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH = (
    PROJECT_ROOT / "artifacts" / "online_features" / "latest_features.json"
)
DEFAULT_ONLINE_FEATURE_MANIFEST_PATH = (
    PROJECT_ROOT / "artifacts" / "online_features" / "manifest.json"
)
DEFAULT_ONLINE_FEATURE_REPORT_PATH = (
    PROJECT_ROOT / "reports" / "online_feature_materialization_summary.md"
)
DEFAULT_API_SERVING_REPORT_PATH = PROJECT_ROOT / "reports" / "api_serving_summary.md"
DEFAULT_PREDICTION_LOG_PATH = PROJECT_ROOT / "logs" / "predictions.jsonl"
DEFAULT_SERVING_MONITORING_REPORT_PATH = PROJECT_ROOT / "reports" / "serving_monitoring_summary.md"
DEFAULT_SERVING_MONITORING_METRICS_PATH = PROJECT_ROOT / "reports" / "serving_monitoring_metrics.json"
DEFAULT_DRIFT_MONITORING_REPORT_PATH = PROJECT_ROOT / "reports" / "drift_monitoring_summary.md"
DEFAULT_DRIFT_MONITORING_METRICS_PATH = PROJECT_ROOT / "reports" / "drift_monitoring_metrics.json"
DEFAULT_SQLITE_TELEMETRY_DB_PATH = PROJECT_ROOT / "artifacts" / "storage" / "telemetry.db"
DEFAULT_STORAGE_SYNC_REPORT_PATH = PROJECT_ROOT / "reports" / "storage_sync_summary.md"
DEFAULT_STORAGE_INSPECTION_REPORT_PATH = (
    PROJECT_ROOT / "reports" / "storage_inspection_summary.md"
)

__all__ = [
    "DEFAULT_API_SERVING_REPORT_PATH",
    "DEFAULT_DRIFT_MONITORING_METRICS_PATH",
    "DEFAULT_DRIFT_MONITORING_REPORT_PATH",
    "DEFAULT_MODEL_MANIFEST_PATH",
    "DEFAULT_MODEL_METRICS_PATH",
    "DEFAULT_MODEL_TRAINING_REPORT_PATH",
    "DEFAULT_ONLINE_FEATURE_MANIFEST_PATH",
    "DEFAULT_ONLINE_FEATURE_REPORT_PATH",
    "DEFAULT_ONLINE_FEATURE_SNAPSHOT_PATH",
    "DEFAULT_OFFLINE_FEATURE_REPORT_PATH",
    "DEFAULT_OFFLINE_FEATURES_PATH",
    "DEFAULT_PREDICTION_LOG_PATH",
    "DEFAULT_SELECTED_MODEL_PATH",
    "DEFAULT_SERVING_MONITORING_METRICS_PATH",
    "DEFAULT_SERVING_MONITORING_REPORT_PATH",
    "DEFAULT_SQLITE_TELEMETRY_DB_PATH",
    "DEFAULT_STORAGE_INSPECTION_REPORT_PATH",
    "DEFAULT_STORAGE_SYNC_REPORT_PATH",
    "DEFAULT_SYNTHETIC_EVENTS_PATH",
    "DEFAULT_SYNTHETIC_REPORT_PATH",
    "DEFAULT_TEST_FEATURES_PATH",
    "DEFAULT_TRAIN_FEATURES_PATH",
    "DEFAULT_VALIDATION_FEATURES_PATH",
    "PROJECT_ROOT",
]

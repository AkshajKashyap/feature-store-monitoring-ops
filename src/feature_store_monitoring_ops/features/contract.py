"""Shared feature contract for offline, online, and model training layers."""

from __future__ import annotations

ENTITY_KEY_COLUMNS: tuple[str, ...] = ("zone_id",)
AS_OF_TIMESTAMP_COLUMN = "timestamp"
TARGET_COLUMN = "target_next_observed_demand"

MODEL_INPUT_FEATURE_COLUMNS: tuple[str, ...] = (
    "zone_id",
    "hour",
    "day_of_week",
    "is_weekend",
    "lag_1_observed_demand",
    "lag_3_observed_demand",
    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_std_6",
    "zone_hour_mean_demand",
)

OFFLINE_METADATA_COLUMNS: tuple[str, ...] = ("event_id", AS_OF_TIMESTAMP_COLUMN)
REQUIRED_OFFLINE_FEATURE_COLUMNS: tuple[str, ...] = (
    *OFFLINE_METADATA_COLUMNS,
    *MODEL_INPUT_FEATURE_COLUMNS,
    TARGET_COLUMN,
)
ONLINE_METADATA_COLUMNS: tuple[str, ...] = (
    *ENTITY_KEY_COLUMNS,
    AS_OF_TIMESTAMP_COLUMN,
)
ONLINE_FEATURE_COLUMNS: tuple[str, ...] = (
    *ENTITY_KEY_COLUMNS,
    AS_OF_TIMESTAMP_COLUMN,
    *(column for column in MODEL_INPUT_FEATURE_COLUMNS if column not in ENTITY_KEY_COLUMNS),
)


def get_model_input_columns() -> tuple[str, ...]:
    """Return model input columns, explicitly excluding the target."""

    if TARGET_COLUMN in MODEL_INPUT_FEATURE_COLUMNS:
        raise ValueError("target column must not be part of model input features")
    return MODEL_INPUT_FEATURE_COLUMNS


def get_online_feature_columns() -> tuple[str, ...]:
    """Return online snapshot columns with entity and as-of metadata included once."""

    if TARGET_COLUMN in ONLINE_FEATURE_COLUMNS:
        raise ValueError("target column must not be part of online feature columns")
    return ONLINE_FEATURE_COLUMNS


__all__ = [
    "AS_OF_TIMESTAMP_COLUMN",
    "ENTITY_KEY_COLUMNS",
    "MODEL_INPUT_FEATURE_COLUMNS",
    "OFFLINE_METADATA_COLUMNS",
    "ONLINE_FEATURE_COLUMNS",
    "ONLINE_METADATA_COLUMNS",
    "REQUIRED_OFFLINE_FEATURE_COLUMNS",
    "TARGET_COLUMN",
    "get_model_input_columns",
    "get_online_feature_columns",
]

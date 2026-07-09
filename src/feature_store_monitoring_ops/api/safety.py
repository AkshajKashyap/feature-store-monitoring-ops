"""Configurable API safety controls for local serving."""

from __future__ import annotations

import os
from dataclasses import dataclass

API_KEY_ENV = "FEATURE_STORE_OPS_API_KEY"
MAX_FEATURE_FRESHNESS_ENV = "FEATURE_STORE_OPS_MAX_FEATURE_FRESHNESS_SECONDS"
REJECT_STALE_FEATURES_ENV = "FEATURE_STORE_OPS_REJECT_STALE_FEATURES"
MIN_PREDICTION_ENV = "FEATURE_STORE_OPS_MIN_PREDICTION"
MAX_PREDICTION_ENV = "FEATURE_STORE_OPS_MAX_PREDICTION"
MAX_REQUEST_BODY_BYTES_ENV = "FEATURE_STORE_OPS_MAX_REQUEST_BODY_BYTES"


@dataclass(frozen=True)
class ApiSafetySettings:
    """Resolved API safety settings.

    Local mode remains unauthenticated by default. Setting `api_key` enables API key checks
    for serving endpoints while leaving `/health` public.
    """

    api_key: str | None = None
    max_feature_freshness_seconds: float = 172800.0
    reject_stale_features: bool = False
    min_prediction: float = 0.0
    max_prediction: float = 500.0
    max_request_body_bytes: int = 2048

    @classmethod
    def from_env(cls) -> ApiSafetySettings:
        """Build safety settings from environment variables."""

        return cls(
            api_key=_empty_to_none(os.getenv(API_KEY_ENV)),
            max_feature_freshness_seconds=_float_env(
                MAX_FEATURE_FRESHNESS_ENV,
                cls.max_feature_freshness_seconds,
            ),
            reject_stale_features=_bool_env(
                REJECT_STALE_FEATURES_ENV,
                cls.reject_stale_features,
            ),
            min_prediction=_float_env(MIN_PREDICTION_ENV, cls.min_prediction),
            max_prediction=_float_env(MAX_PREDICTION_ENV, cls.max_prediction),
            max_request_body_bytes=_int_env(
                MAX_REQUEST_BODY_BYTES_ENV,
                cls.max_request_body_bytes,
            ),
        ).validated()

    @property
    def api_key_required(self) -> bool:
        """Return whether API key auth is enabled."""

        return self.api_key is not None

    def validated(self) -> ApiSafetySettings:
        """Validate safety settings."""

        if self.max_feature_freshness_seconds < 0:
            raise ValueError("max feature freshness seconds must be nonnegative")
        if self.min_prediction > self.max_prediction:
            raise ValueError("min prediction must be less than or equal to max prediction")
        if self.max_request_body_bytes <= 0:
            raise ValueError("max request body bytes must be greater than zero")
        return self

    def authenticate(self, supplied_api_key: str | None) -> bool:
        """Return whether a supplied API key satisfies the configured key."""

        if self.api_key is None:
            return True
        return supplied_api_key == self.api_key

    def stale_feature_warning(self, freshness_seconds: float | None) -> str | None:
        """Return a warning when feature freshness exceeds the configured threshold."""

        if freshness_seconds is None:
            return "feature freshness could not be computed"
        if freshness_seconds > self.max_feature_freshness_seconds:
            return (
                "feature row is stale: "
                f"{freshness_seconds:.3f}s exceeds {self.max_feature_freshness_seconds:.3f}s"
            )
        return None

    def prediction_warning(self, prediction: float) -> str | None:
        """Return a warning when prediction is outside the expected local range."""

        if prediction < self.min_prediction:
            return (
                f"prediction {prediction:.6f} is below expected minimum "
                f"{self.min_prediction:.6f}"
            )
        if prediction > self.max_prediction:
            return (
                f"prediction {prediction:.6f} is above expected maximum "
                f"{self.max_prediction:.6f}"
            )
        return None


def _empty_to_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


__all__ = [
    "API_KEY_ENV",
    "MAX_FEATURE_FRESHNESS_ENV",
    "MAX_PREDICTION_ENV",
    "MAX_REQUEST_BODY_BYTES_ENV",
    "MIN_PREDICTION_ENV",
    "REJECT_STALE_FEATURES_ENV",
    "ApiSafetySettings",
]

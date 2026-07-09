"""Pydantic schemas for the local prediction API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    ready: bool
    errors: list[str]


class ModelResponse(BaseModel):
    selected_model: str | None
    model_version: str
    input_features: list[str]
    target_column: str
    model_manifest_path: str


class FeatureResponse(BaseModel):
    zone_id: str
    as_of_timestamp: str
    features: dict[str, Any]
    feature_columns: list[str]


class PredictRequest(BaseModel):
    zone_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class PredictionResponse(BaseModel):
    zone_id: str
    prediction: float
    as_of_timestamp: str
    model_name: str | None
    model_version: str
    feature_freshness: dict[str, Any]
    feature_columns: list[str]
    warnings: list[str] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    request_count: int
    prediction_count: int
    error_count: int
    average_prediction_latency_ms: float


__all__ = [
    "FeatureResponse",
    "HealthResponse",
    "MetricsResponse",
    "ModelResponse",
    "PredictRequest",
    "PredictionResponse",
]

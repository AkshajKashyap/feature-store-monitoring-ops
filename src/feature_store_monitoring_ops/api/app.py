"""FastAPI app for local demand prediction serving."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
import httpx

from feature_store_monitoring_ops.api.schemas import (
    FeatureResponse,
    HealthResponse,
    MetricsResponse,
    ModelResponse,
    PredictRequest,
    PredictionResponse,
)
from feature_store_monitoring_ops.api.service import (
    ApiMetrics,
    ServingArtifacts,
    ServingContext,
    build_api_serving_summary,
    build_feature_freshness,
    extract_model_features,
    get_feature_row,
    load_serving_context,
    predict_for_zone,
)
from feature_store_monitoring_ops.features.contract import (
    AS_OF_TIMESTAMP_COLUMN,
    TARGET_COLUMN,
    get_model_input_columns,
)
from feature_store_monitoring_ops.monitoring.telemetry import (
    PredictionTelemetryLogger,
    TelemetrySimulationResult,
    utc_now,
)
from feature_store_monitoring_ops.paths import (
    DEFAULT_API_SERVING_REPORT_PATH,
    DEFAULT_PREDICTION_LOG_PATH,
)
from feature_store_monitoring_ops.storage.config import StorageConfig
from feature_store_monitoring_ops.storage.online import OnlineFeatureStore


def create_app(
    artifacts: ServingArtifacts | None = None,
    *,
    feature_store: OnlineFeatureStore | None = None,
    storage_config: StorageConfig | None = None,
    telemetry_logger: PredictionTelemetryLogger | None = None,
    telemetry_log_path: Path = DEFAULT_PREDICTION_LOG_PATH,
    telemetry_now_fn: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Create the local FastAPI prediction app."""

    serving_context = load_serving_context(
        artifacts,
        feature_store=feature_store,
        storage_config=storage_config,
    )
    metrics = ApiMetrics()
    telemetry = telemetry_logger or PredictionTelemetryLogger(
        log_path=telemetry_log_path,
        now_fn=telemetry_now_fn or utc_now,
    )
    app = FastAPI(title="Feature Store Monitoring Ops API", version="0.1.0")
    app.state.serving_context = serving_context
    app.state.metrics = metrics
    app.state.telemetry = telemetry

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        metrics.record_request()
        try:
            response = await call_next(request)
        except Exception:
            metrics.record_error()
            raise
        if response.status_code >= 400:
            metrics.record_error()
        return response

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        context = _get_context(app)
        status = "ok" if context.is_ready else "degraded"
        return HealthResponse(status=status, ready=context.is_ready, errors=context.load_errors)

    @app.get("/model", response_model=ModelResponse)
    async def model() -> ModelResponse:
        context = _get_context(app)
        if context.model is None:
            raise HTTPException(status_code=503, detail="model artifact is not loaded")
        return ModelResponse(
            selected_model=context.selected_model,
            model_version=context.model_version,
            input_features=list(get_model_input_columns()),
            target_column=TARGET_COLUMN,
            model_manifest_path=str(context.artifacts.model_manifest_path),
        )

    @app.get("/features/{zone_id}", response_model=FeatureResponse)
    async def features(zone_id: str) -> FeatureResponse:
        context = _get_context(app)
        try:
            row = get_feature_row(context, zone_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        model_features = extract_model_features(row)
        return FeatureResponse(
            zone_id=str(row["zone_id"]),
            as_of_timestamp=str(row[AS_OF_TIMESTAMP_COLUMN]),
            features=model_features,
            feature_columns=list(model_features),
        )

    @app.post("/predict", response_model=PredictionResponse)
    async def predict(request: PredictRequest) -> PredictionResponse:
        context = _get_context(app)
        telemetry = _get_telemetry(app)
        request_id = telemetry.next_request_id()
        request_start = time.perf_counter()
        if not context.is_ready:
            telemetry.log_error(
                request_id=request_id,
                zone_id=request.zone_id,
                model_name=context.selected_model,
                model_version=context.model_version,
                latency_ms=_elapsed_ms(request_start),
                error_type="not_ready",
            )
            raise HTTPException(
                status_code=503,
                detail="serving artifacts are not ready: " + "; ".join(context.load_errors),
            )
        try:
            prediction, row, latency_ms = predict_for_zone(context, request.zone_id)
        except RuntimeError as exc:
            telemetry.log_error(
                request_id=request_id,
                zone_id=request.zone_id,
                model_name=context.selected_model,
                model_version=context.model_version,
                latency_ms=_elapsed_ms(request_start),
                error_type="serving_error",
            )
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            telemetry.log_error(
                request_id=request_id,
                zone_id=request.zone_id,
                model_name=context.selected_model,
                model_version=context.model_version,
                latency_ms=_elapsed_ms(request_start),
                error_type="unknown_zone",
            )
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            telemetry.log_error(
                request_id=request_id,
                zone_id=request.zone_id,
                model_name=context.selected_model,
                model_version=context.model_version,
                latency_ms=_elapsed_ms(request_start),
                error_type="feature_error",
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        _get_metrics(app).record_prediction(latency_ms)
        telemetry_row = telemetry.log_success(
            request_id=request_id,
            zone_id=str(row["zone_id"]),
            as_of_timestamp=str(row[AS_OF_TIMESTAMP_COLUMN]),
            prediction=prediction,
            model_name=context.selected_model,
            model_version=context.model_version,
            latency_ms=latency_ms,
        )
        return PredictionResponse(
            zone_id=str(row["zone_id"]),
            prediction=prediction,
            as_of_timestamp=str(row[AS_OF_TIMESTAMP_COLUMN]),
            model_name=context.selected_model,
            model_version=context.model_version,
            feature_freshness=build_feature_freshness(
                context,
                row,
                feature_freshness_seconds=telemetry_row["feature_freshness_seconds"],
            ),
            feature_columns=list(get_model_input_columns()),
        )

    @app.get("/metrics", response_model=MetricsResponse)
    async def metrics_endpoint() -> MetricsResponse:
        return MetricsResponse(**_get_metrics(app).snapshot())

    return app


def run_api_smoke_test(app: FastAPI) -> dict[str, object]:
    """Run an in-process API smoke test without opening a network socket."""

    return asyncio.run(_run_api_smoke_test_async(app))


def run_api_traffic_simulation(
    app: FastAPI,
    *,
    unknown_zone_id: str = "unknown_zone",
) -> TelemetrySimulationResult:
    """Run deterministic in-process prediction traffic against known zones plus one unknown zone."""

    return asyncio.run(_run_api_traffic_simulation_async(app, unknown_zone_id=unknown_zone_id))


def write_api_serving_report(
    app: FastAPI,
    *,
    report_path: Path = DEFAULT_API_SERVING_REPORT_PATH,
    smoke_test_passed: bool | None = None,
) -> None:
    """Write a tracked Markdown summary for API serving."""

    context = _get_context(app)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_api_serving_summary(
            artifacts=context.artifacts,
            smoke_test_passed=smoke_test_passed,
            selected_model=context.selected_model,
            metrics=_get_metrics(app).snapshot(),
        ),
        encoding="utf-8",
    )


def _get_context(app: FastAPI) -> ServingContext:
    return app.state.serving_context


def _get_metrics(app: FastAPI) -> ApiMetrics:
    return app.state.metrics


def _get_telemetry(app: FastAPI) -> PredictionTelemetryLogger:
    return app.state.telemetry


async def _run_api_smoke_test_async(app: FastAPI) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health_response = await client.get("/health")
        _assert_success(health_response.status_code, "/health")
        if not health_response.json()["ready"]:
            raise RuntimeError(f"API is not ready: {health_response.json()['errors']}")

        model_response = await client.get("/model")
        _assert_success(model_response.status_code, "/model")

        context = _get_context(app)
        assert context.feature_store is not None
        rows = context.feature_store.all_rows()
        if not rows:
            raise RuntimeError("online feature snapshot has no rows")
        zone_id = str(rows[0]["zone_id"])

        feature_response = await client.get(f"/features/{zone_id}")
        _assert_success(feature_response.status_code, f"/features/{zone_id}")

        prediction_response = await client.post("/predict", json={"zone_id": zone_id})
        _assert_success(prediction_response.status_code, "/predict")

        metrics_response = await client.get("/metrics")
        _assert_success(metrics_response.status_code, "/metrics")
        metrics_payload = metrics_response.json()
        if metrics_payload["prediction_count"] < 1:
            raise RuntimeError("smoke test did not record a prediction")

        return {
            "passed": True,
            "zone_id": zone_id,
            "prediction": prediction_response.json()["prediction"],
            "metrics": metrics_payload,
        }


async def _run_api_traffic_simulation_async(
    app: FastAPI,
    *,
    unknown_zone_id: str,
) -> TelemetrySimulationResult:
    context = _get_context(app)
    if not context.is_ready:
        raise RuntimeError(f"API is not ready: {context.load_errors}")
    assert context.feature_store is not None
    known_zones = sorted(str(row["zone_id"]) for row in context.feature_store.all_rows())
    zones = [*known_zones, unknown_zone_id]
    successful_requests = 0
    failed_requests = 0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for zone_id in zones:
            response = await client.post("/predict", json={"zone_id": zone_id})
            if response.status_code < 400:
                successful_requests += 1
            else:
                failed_requests += 1

    return TelemetrySimulationResult(
        log_path=_get_telemetry(app).log_path,
        total_requests=len(zones),
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        zones_requested=zones,
    )


def _assert_success(status_code: int, endpoint: str) -> None:
    if status_code >= 400:
        raise RuntimeError(f"smoke test request failed for {endpoint}: HTTP {status_code}")


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


__all__ = [
    "create_app",
    "run_api_traffic_simulation",
    "run_api_smoke_test",
    "write_api_serving_report",
]

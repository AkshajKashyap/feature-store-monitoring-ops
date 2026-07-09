#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_NAME="${IMAGE_NAME:-feature-store-monitoring-ops-api:local}"
REPORT_PATH="${REPORT_PATH:-reports/portfolio/docker_smoke_summary.md}"
FEATURE_STORE_OPS="${FEATURE_STORE_OPS:-}"
COMPOSE=(docker compose)
STATUS="failed"
DETAIL="Smoke test did not complete."
REDIS_BACKED_SERVING="not run"
HEALTH_PAYLOAD=""
MODEL_PAYLOAD=""
PREDICT_PAYLOAD=""
METRICS_PAYLOAD=""

if [[ -z "${FEATURE_STORE_OPS}" ]]; then
  if [[ -x ".venv/bin/feature-store-ops" ]]; then
    FEATURE_STORE_OPS=".venv/bin/feature-store-ops"
  else
    FEATURE_STORE_OPS="feature-store-ops"
  fi
fi

write_report() {
  mkdir -p "$(dirname "${REPORT_PATH}")"
  cat > "${REPORT_PATH}" <<EOF
# Docker Smoke Summary

Dockerized local API + Redis smoke path for Milestone 10.

## Result

- Status: ${STATUS}
- Detail: ${DETAIL}
- Image: \`${IMAGE_NAME}\`
- Redis-backed serving path: ${REDIS_BACKED_SERVING}

## Checks

- Health payload: \`${HEALTH_PAYLOAD:-n/a}\`
- Model payload: \`${MODEL_PAYLOAD:-n/a}\`
- Predict payload: \`${PREDICT_PAYLOAD:-n/a}\`
- Metrics payload: \`${METRICS_PAYLOAD:-n/a}\`

## Notes

- The script builds the local API image, starts Redis with Docker Compose, syncs online features into Redis, and checks the API over localhost.
- Docker is optional for normal development and release checks.
EOF
}

cleanup() {
  "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  if [[ "${STATUS}" != "passed" ]]; then
    write_report
  fi
}
trap cleanup EXIT

DETAIL="Checking Docker and Docker Compose availability."
docker --version >/dev/null
"${COMPOSE[@]}" version >/dev/null

DETAIL="Building Docker image."
docker build -t "${IMAGE_NAME}" .

DETAIL="Running deterministic local workflow to create artifacts."
"${FEATURE_STORE_OPS}" run-demo-workflow

export HOST_UID
export HOST_GID
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
export FEATURE_STORE_OPS_ONLINE_BACKEND=redis
export FEATURE_STORE_OPS_REDIS_URL=redis://redis:6379/0

DETAIL="Starting Redis service."
"${COMPOSE[@]}" up -d redis

DETAIL="Syncing online feature snapshot into Redis."
"${COMPOSE[@]}" run --rm \
  -e FEATURE_STORE_OPS_ONLINE_BACKEND=redis \
  -e FEATURE_STORE_OPS_REDIS_URL=redis://redis:6379/0 \
  api feature-store-ops sync-storage \
    --online-backend redis \
    --telemetry-backend sqlite \
    --redis-url redis://redis:6379/0

DETAIL="Starting API service with Redis-backed online features."
"${COMPOSE[@]}" up -d api

DETAIL="Waiting for API health check."
for _ in {1..60}; do
  if HEALTH_PAYLOAD="$(curl -fsS http://localhost:8000/health 2>/dev/null)" \
    && [[ "${HEALTH_PAYLOAD}" == *'"ready":true'* ]]; then
    break
  fi
  sleep 1
done
if [[ "${HEALTH_PAYLOAD}" != *'"ready":true'* ]]; then
  "${COMPOSE[@]}" logs api || true
  DETAIL="API did not become ready."
  exit 1
fi

DETAIL="Checking model endpoint."
MODEL_PAYLOAD="$(curl -fsS http://localhost:8000/model)"
if [[ "${MODEL_PAYLOAD}" != *'"selected_model"'* ]]; then
  DETAIL="Model endpoint did not return model metadata."
  exit 1
fi

DETAIL="Checking prediction endpoint."
PREDICT_PAYLOAD="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -d '{"zone_id":"zone_01"}' \
    http://localhost:8000/predict
)"
if [[ "${PREDICT_PAYLOAD}" != *'"prediction"'* ]]; then
  DETAIL="Predict endpoint did not return a prediction."
  exit 1
fi

DETAIL="Checking metrics endpoint."
METRICS_PAYLOAD="$(curl -fsS http://localhost:8000/metrics)"
if [[ "${METRICS_PAYLOAD}" != *'"prediction_count"'* ]]; then
  DETAIL="Metrics endpoint did not return prediction counters."
  exit 1
fi

STATUS="passed"
DETAIL="Docker API + Redis smoke test passed."
REDIS_BACKED_SERVING="passed"
write_report
"${COMPOSE[@]}" down --remove-orphans
trap - EXIT

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(shell if [ -x .venv/bin/pytest ]; then echo .venv/bin/pytest; else echo pytest; fi)
RUFF ?= $(shell if [ -x .venv/bin/ruff ]; then echo .venv/bin/ruff; else echo ruff; fi)
FEATURE_STORE_OPS ?= $(shell if [ -x .venv/bin/feature-store-ops ]; then echo .venv/bin/feature-store-ops; else echo feature-store-ops; fi)
DOCKER_IMAGE ?= feature-store-monitoring-ops-api:local

.PHONY: install check demo smoke release-check docker-build docker-smoke format

install:
	$(PIP) install -e ".[dev]"

check:
	$(PYTEST) -q
	$(RUFF) check .

demo:
	$(FEATURE_STORE_OPS) run-demo-workflow

smoke:
	$(FEATURE_STORE_OPS) run-demo-workflow

release-check:
	$(PYTEST) -q
	$(RUFF) check .
	$(FEATURE_STORE_OPS) run-demo-workflow

docker-build:
	docker build -t $(DOCKER_IMAGE) .

docker-smoke:
	IMAGE_NAME=$(DOCKER_IMAGE) scripts/docker_smoke_test.sh

format:
	$(RUFF) format .

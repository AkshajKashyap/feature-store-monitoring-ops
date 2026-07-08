install:
	python -m pip install -e ".[dev]"

check:
	pytest -q
	ruff check .

format:
	ruff format .

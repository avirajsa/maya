.PHONY: run test lint format check

run:
	uv run python -m maya.main

test:
	uv run pytest

format:
	uv run ruff format .

lint:
	uv run ruff check .

check:
	uv run ruff check .
	uv run pytest

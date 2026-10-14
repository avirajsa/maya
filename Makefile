.PHONY: run ui dev test lint format check install clean

# Install/sync dependencies
install:
	uv sync

# Run Maya's main application
run:
	uv run python -m maya.main

# Run Chainlit UI normally
ui:
	uv run chainlit run src/maya/ui/app.py

# Run Chainlit UI with hot reload
dev:
	uv run chainlit run src/maya/ui/app.py -w

# Run tests
test:
	uv run pytest src/tests/ -v

# Lint Python code
lint:
	uv run ruff check .

# Format Python code
format:
	uv run ruff format .

# Run lint and tests
check:
	uv run ruff check .
	uv run pytest src/tests/ -v

# Remove Python cache files
clean:
	find src -type d -name __pycache__ -prune -exec rm -rf {} +
	find src -type f -name "*.pyc" -delete


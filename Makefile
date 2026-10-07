.PHONY: install check ingest catalog demo
install:
	uv sync --frozen --extra dev
check:
	uv run ruff check .
	uv run mypy src
	uv run pytest -q
ingest:
	uv run commodity-data ingest worldbank
catalog:
	uv run commodity-data catalog
demo:
	uv run commodity-data continuous examples/contracts.csv

.PHONY: help sync lint test all skill clean

help:
	@echo "Targets: sync test lint all skill clean"

sync:
	uv sync --all-packages

lint:
	uv run ruff check .

test:
	uv run pytest -q

all: sync lint test

skill:
	cd skills && zip -r ../grace-pmo-director.skill grace-pmo-director/ -x "**/.DS_Store"

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -f grace-pmo-director.skill

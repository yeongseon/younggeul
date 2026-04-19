.PHONY: install lint format test test-all test-contract clean help demo docs docs-serve

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv pip install -e ".[dev]"

lint: ## Run linters (ruff + mypy)
	ruff check .
	ruff format --check .
	mypy core/src/ apps/kr-seoul-apartment/src/

format: ## Auto-format code
	ruff check --fix .
	ruff format .

test: ## Run unit tests only
	pytest -m "not slow and not integration and not live" --cov

test-all: ## Run all tests including integration
	pytest -m "not live" --cov

test-contract: ## Run contract tests only
	PYTHONPATH=core/src:benchmarks/kr-housing/src python3 -m pytest core/tests/contract/ benchmarks/kr-housing/tests/ -v

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ coverage.xml .coverage

demo: ## Run end-to-end demo
	bash scripts/demo.sh

docs: ## Build documentation
	mkdocs build

docs-serve: ## Serve documentation locally
	mkdocs serve

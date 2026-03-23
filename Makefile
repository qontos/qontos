.PHONY: help install install-dev lint format typecheck test check build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package
	pip install -e .

install-dev: ## Install with development dependencies
	pip install -e ".[dev]"

lint: ## Run linter
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Auto-format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck: ## Run type checker
	mypy src/

test: ## Run tests
	pytest tests/ -v

test-cov: ## Run tests with coverage
	pytest tests/ -v --cov=qontos --cov-report=term-missing --cov-report=html

check: lint typecheck test ## Run all checks

build: ## Build distribution packages
	python -m build

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

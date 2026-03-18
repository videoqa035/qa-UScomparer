.PHONY: install dev test test-cov lint format clean help

help:                 ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:              ## Install package (production deps only)
	pip install -e .

dev:                  ## Install package with dev/test dependencies
	pip install -e ".[dev]"

test:                 ## Run test suite
	pytest tests/ -v --tb=short

test-cov:             ## Run tests with HTML coverage report
	pytest tests/ --cov=qa_uscomparer --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

lint:                 ## Lint with ruff + mypy
	ruff check src/ tests/
	mypy src/

format:               ## Auto-format with ruff
	ruff format src/ tests/
	ruff check --fix src/ tests/

clean:                ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info .mypy_cache .ruff_cache

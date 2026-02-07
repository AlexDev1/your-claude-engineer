# Makefile for Claude Agent Dashboard
# =====================================
#
# Test and development commands

.PHONY: help test test-api test-e2e test-agent test-security test-all coverage lint format clean dev preflight diagnose

# Default target
help:
	@echo "Available targets:"
	@echo "  test          - Run all tests"
	@echo "  test-api      - Run API tests only"
	@echo "  test-e2e      - Run E2E tests only"
	@echo "  test-agent    - Run agent integration tests"
	@echo "  test-security - Run security tests"
	@echo "  coverage      - Run tests with coverage report"
	@echo "  lint          - Run linters"
	@echo "  format        - Format code"
	@echo "  clean         - Clean up temporary files"
	@echo "  dev           - Start development servers"
	@echo "  install       - Install all dependencies"
	@echo "  preflight     - Run preflight checks"
	@echo "  diagnose      - Run self-diagnostics"

# Run preflight checks
preflight:
	python preflight.py

# Run self-diagnostics
diagnose:
	python self_diagnostics.py

# Install dependencies
install:
	pip install -r requirements.txt
	pip install -r analytics_server/requirements.txt
	pip install pytest pytest-cov pytest-asyncio pytest-playwright httpx
	cd dashboard && npm install
	playwright install chromium

# Run all tests
test: test-api test-agent test-security
	@echo "All tests completed"

# Run API tests
test-api:
	@echo "Running API tests..."
	pytest tests/api/ -v --tb=short

# Run E2E tests (requires running servers)
test-e2e:
	@echo "Running E2E tests..."
	@echo "Make sure dashboard (port 5173) and API (port 8003) are running"
	HEADLESS=true pytest tests/e2e/ -v --tb=short

# Run agent integration tests
test-agent:
	@echo "Running agent integration tests..."
	pytest tests/integration/ -v --tb=short

# Run security tests
test-security:
	@echo "Running security tests..."
	python test_security.py
	pytest test_github_integration.py -v

# Run all tests with coverage
coverage:
	@echo "Running tests with coverage..."
	pytest tests/api/ tests/integration/ -v \
		--cov=analytics_server \
		--cov=agents \
		--cov=agent \
		--cov=security \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=80
	@echo "Coverage report generated in htmlcov/"

# Run linters
lint:
	@echo "Running linters..."
	-ruff check .
	-mypy analytics_server/ agents/ --ignore-missing-imports

# Format code
format:
	@echo "Formatting code..."
	-ruff format .
	-isort .

# Clean up
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__ .pytest_cache htmlcov .coverage
	rm -rf tests/__pycache__ tests/api/__pycache__ tests/e2e/__pycache__ tests/integration/__pycache__
	rm -rf analytics_server/__pycache__ agents/__pycache__
	rm -rf dashboard/dist dashboard/node_modules/.cache
	find . -name "*.pyc" -delete
	find . -name ".DS_Store" -delete

# Start development servers
dev:
	@echo "Starting development servers..."
	@echo "API server: http://localhost:8003"
	@echo "Dashboard:  http://localhost:5173"
	@echo ""
	@echo "Run in separate terminals:"
	@echo "  Terminal 1: python -m analytics_server.server"
	@echo "  Terminal 2: cd dashboard && npm run dev"

# Start API server only
dev-api:
	python -m analytics_server.server

# Start dashboard only
dev-dashboard:
	cd dashboard && npm run dev

# Run E2E tests with visible browser
test-e2e-headed:
	@echo "Running E2E tests with visible browser..."
	HEADLESS=false SLOW_MO=500 pytest tests/e2e/ -v -x --tb=short

# Quick test (fast feedback)
test-quick:
	@echo "Running quick tests..."
	pytest tests/api/test_analytics_api.py::TestHealthEndpoint -v
	pytest tests/api/test_issues_api.py::TestListIssues -v

# CI test command (used in GitHub Actions)
test-ci:
	pytest tests/api/ tests/integration/ -v --tb=short --cov=analytics_server --cov-report=xml

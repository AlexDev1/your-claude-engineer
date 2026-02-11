# Makefile for Claude Agent Dashboard
# =====================================
#
# Test and development commands

.PHONY: help test test-unit test-api test-e2e test-agent test-security test-all coverage lint format clean dev preflight diagnose

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
	.venv/bin/python -m axon_agent.tools.preflight

# Run self-diagnostics
diagnose:
	.venv/bin/python -m axon_agent.tools.diagnostics

# Install dependencies
install:
	uv pip install -e ".[dev]"
	cd dashboard && npm install
	playwright install chromium

# Run all tests
test: test-unit test-api test-agent test-security
	@echo "All tests completed"

# Run unit tests
test-unit:
	@echo "Running unit tests..."
	.venv/bin/pytest tests/unit/ -v --tb=short

# Run API tests
test-api:
	@echo "Running API tests..."
	.venv/bin/pytest tests/api/ -v --tb=short

# Run E2E tests (requires running servers)
test-e2e:
	@echo "Running E2E tests..."
	@echo "Make sure dashboard (port 5173) and API (port 8003) are running"
	HEADLESS=true .venv/bin/pytest tests/e2e/ -v --tb=short

# Run agent integration tests
test-agent:
	@echo "Running agent integration tests..."
	.venv/bin/pytest tests/integration/ -v --tb=short

# Run security tests
test-security:
	@echo "Running security tests..."
	.venv/bin/pytest tests/unit/test_security.py tests/unit/test_github_integration.py -v

# Run all tests with coverage
coverage:
	@echo "Running tests with coverage..."
	.venv/bin/pytest tests/ -v \
		--cov=src/axon_agent \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=80
	@echo "Coverage report generated in htmlcov/"

# Run linters
lint:
	@echo "Running linters..."
	-.venv/bin/ruff check src/
	-.venv/bin/mypy src/axon_agent/ --ignore-missing-imports

# Format code
format:
	@echo "Formatting code..."
	-.venv/bin/ruff format .
	-.venv/bin/ruff check --fix .

# Clean up
clean:
	@echo "Cleaning up..."
	rm -rf __pycache__ .pytest_cache htmlcov .coverage
	rm -rf tests/__pycache__ tests/api/__pycache__ tests/e2e/__pycache__ tests/integration/__pycache__ tests/unit/__pycache__
	rm -rf src/axon_agent/__pycache__
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
	@echo "  Terminal 1: .venv/bin/python -m axon_agent.dashboard.api"
	@echo "  Terminal 2: cd dashboard && npm run dev"

# Start API server only
dev-api:
	.venv/bin/python -m axon_agent.dashboard.api

# Start dashboard only
dev-dashboard:
	cd dashboard && npm run dev

# Run E2E tests with visible browser
test-e2e-headed:
	@echo "Running E2E tests with visible browser..."
	HEADLESS=false SLOW_MO=500 .venv/bin/pytest tests/e2e/ -v -x --tb=short

# Quick test (fast feedback)
test-quick:
	@echo "Running quick tests..."
	.venv/bin/pytest tests/api/test_analytics_api.py::TestHealthEndpoint -v
	.venv/bin/pytest tests/api/test_issues_api.py::TestListIssues -v

# CI test command (used in GitHub Actions)
test-ci:
	.venv/bin/pytest tests/api/ tests/integration/ tests/unit/ -v --tb=short --cov=src/axon_agent --cov-report=xml

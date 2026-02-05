# =============================================================================
# MCP Servers - Makefile
# =============================================================================
#
# Usage:
#   make build     - Build all Docker images
#   make deploy    - Deploy stack (with secrets validation)
#   make down      - Stop all services
#   make logs      - View logs
#   make health    - Check service health
#   make backup-db - Backup PostgreSQL database
#
# =============================================================================

.PHONY: help build deploy down logs health backup-db security-scan clean

# Default target
help:
	@echo "MCP Servers - Available Commands"
	@echo "================================="
	@echo ""
	@echo "  make build          Build all Docker images"
	@echo "  make deploy         Deploy stack (validates secrets first)"
	@echo "  make down           Stop all services"
	@echo "  make restart        Restart all services"
	@echo "  make logs           View logs (follow mode)"
	@echo "  make logs-task      View task-mcp logs"
	@echo "  make logs-telegram  View telegram-mcp logs"
	@echo "  make logs-postgres  View postgres logs"
	@echo "  make health         Check health of all services"
	@echo "  make ps             Show running containers"
	@echo "  make backup-db      Backup PostgreSQL database"
	@echo "  make restore-db     Restore PostgreSQL from backup"
	@echo "  make security-scan  Scan images with Trivy"
	@echo "  make clean          Remove containers, volumes, and images"
	@echo "  make secrets-check  Verify secrets are configured"
	@echo ""

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

COMPOSE := docker compose
BACKUP_DIR := ./backups
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------

build:
	@echo "Building Docker images..."
	$(COMPOSE) build --no-cache

build-task:
	@echo "Building task-mcp image..."
	$(COMPOSE) build --no-cache task-mcp

build-telegram:
	@echo "Building telegram-mcp image..."
	$(COMPOSE) build --no-cache telegram-mcp

# -----------------------------------------------------------------------------
# Deploy
# -----------------------------------------------------------------------------

secrets-check:
	@echo "Checking secrets configuration..."
	@test -f ./secrets/db_password.txt || (echo "ERROR: secrets/db_password.txt not found" && exit 1)
	@test -f ./secrets/telegram_bot_token.txt || (echo "ERROR: secrets/telegram_bot_token.txt not found" && exit 1)
	@test -f ./secrets/telegram_chat_id.txt || (echo "ERROR: secrets/telegram_chat_id.txt not found" && exit 1)
	@echo "All secrets configured."

deploy: secrets-check
	@echo "Deploying MCP stack..."
	$(COMPOSE) up -d
	@echo ""
	@echo "Waiting for services to start..."
	@sleep 5
	@$(MAKE) health

deploy-dev:
	@echo "Deploying in development mode (with override)..."
	$(COMPOSE) -f docker-compose.yml -f docker-compose.override.yml up -d

down:
	@echo "Stopping services..."
	$(COMPOSE) down

restart:
	@echo "Restarting services..."
	$(COMPOSE) restart

# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------

logs:
	$(COMPOSE) logs -f

logs-task:
	$(COMPOSE) logs -f task-mcp

logs-telegram:
	$(COMPOSE) logs -f telegram-mcp

logs-postgres:
	$(COMPOSE) logs -f postgres

# -----------------------------------------------------------------------------
# Health Checks
# -----------------------------------------------------------------------------

health:
	@echo "Checking service health..."
	@echo ""
	@echo "PostgreSQL:"
	@$(COMPOSE) exec -T postgres pg_isready -U agent -d tasks 2>/dev/null && echo "  Status: healthy" || echo "  Status: unhealthy"
	@echo ""
	@echo "Task MCP Server:"
	@curl -sf http://localhost:8001/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  Status: unhealthy or not reachable"
	@echo ""
	@echo "Telegram MCP Server:"
	@curl -sf http://localhost:8002/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  Status: unhealthy or not reachable"

ps:
	$(COMPOSE) ps

# -----------------------------------------------------------------------------
# Database Operations
# -----------------------------------------------------------------------------

backup-db:
	@echo "Creating PostgreSQL backup..."
	@mkdir -p $(BACKUP_DIR)
	$(COMPOSE) exec -T postgres pg_dump -U agent -d tasks > $(BACKUP_DIR)/tasks_$(TIMESTAMP).sql
	@echo "Backup created: $(BACKUP_DIR)/tasks_$(TIMESTAMP).sql"
	@ls -lh $(BACKUP_DIR)/tasks_$(TIMESTAMP).sql

restore-db:
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "Usage: make restore-db BACKUP_FILE=backups/tasks_YYYYMMDD_HHMMSS.sql"; \
		exit 1; \
	fi
	@echo "Restoring from $(BACKUP_FILE)..."
	@echo "WARNING: This will overwrite current data!"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(COMPOSE) exec -T postgres psql -U agent -d tasks < $(BACKUP_FILE)
	@echo "Restore completed."

db-shell:
	$(COMPOSE) exec postgres psql -U agent -d tasks

# -----------------------------------------------------------------------------
# Security
# -----------------------------------------------------------------------------

security-scan:
	@echo "Scanning images with Trivy..."
	@command -v trivy >/dev/null 2>&1 || (echo "Trivy not installed. Install: https://trivy.dev" && exit 1)
	@echo ""
	@echo "Scanning task-mcp-server..."
	trivy image axoncode/task-mcp-server:latest --severity HIGH,CRITICAL
	@echo ""
	@echo "Scanning telegram-mcp-server..."
	trivy image axoncode/telegram-mcp-server:latest --severity HIGH,CRITICAL

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------

clean:
	@echo "Stopping and removing containers..."
	$(COMPOSE) down -v --rmi local
	@echo "Cleanup completed."

clean-all:
	@echo "WARNING: This will remove all data including volumes!"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(COMPOSE) down -v --rmi all
	@echo "Full cleanup completed."

# -----------------------------------------------------------------------------
# Development Helpers
# -----------------------------------------------------------------------------

shell-task:
	$(COMPOSE) exec task-mcp /bin/bash

shell-telegram:
	$(COMPOSE) exec telegram-mcp /bin/bash

test-task-api:
	@echo "Testing Task MCP API..."
	@curl -s http://localhost:8001/health | python3 -m json.tool
	@echo ""
	@curl -s http://localhost:8001/sse -H "Accept: text/event-stream" --max-time 2 || true

test-telegram-api:
	@echo "Testing Telegram MCP API..."
	@curl -s http://localhost:8002/health | python3 -m json.tool
	@echo ""
	@curl -s http://localhost:8002/sse -H "Accept: text/event-stream" --max-time 2 || true

# =============================================================================
# Task MCP Server - Multi-stage Production Dockerfile
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies in virtual environment
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Production - Minimal runtime image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Labels for organization
LABEL org.opencontainers.image.title="Task MCP Server" \
      org.opencontainers.image.description="Task management MCP server with PostgreSQL backend" \
      org.opencontainers.image.vendor="AxonCode" \
      org.opencontainers.image.source="https://github.com/AxonCode/your-claude-engineer"

# Install runtime dependencies
# - curl: for healthcheck
# - tini: for proper signal handling (PID 1)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only necessary application files
COPY --chown=appuser:appgroup server.py .
COPY --chown=appuser:appgroup database.py .
COPY --chown=appuser:appgroup models.py .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run server (--loop asyncio to avoid uvloop DNS caching issues)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]

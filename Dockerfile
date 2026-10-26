FROM python:3.12-slim AS builder

# Build arguments
ARG VERSION=5.3.0
ARG BUILD_DATE

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies (skip MT5 as it's Windows-only)
RUN pip install --upgrade pip && \
    grep -v "MetaTrader5" requirements.txt > requirements-linux.txt && \
    pip install --prefix=/install -r requirements-linux.txt

# Production image
FROM python:3.12-slim

ARG VERSION=5.3.0
ARG BUILD_DATE

# Labels for GHCR
LABEL org.opencontainers.image.title="Cthulu Trading System" \
    org.opencontainers.image.description="Advanced multi-strategy autonomous trading system with ML/RL intelligence" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.source="https://github.com/amuzetnoM/cthulu" \
    org.opencontainers.image.vendor="Artifact Virtual" \
    org.opencontainers.image.licenses="AGPL-3.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CTHULU_VERSION=${VERSION}

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -r -s /bin/false -d /app cthulu && \
    mkdir -p /app/data /app/logs /app/configs /app/metrics && \
    chown -R cthulu:cthulu /app

WORKDIR /app

# Copy application code
COPY --chown=cthulu:cthulu . .

# Switch to non-root user
USER cthulu

# Create volume mount points
VOLUME ["/app/data", "/app/logs", "/app/configs", "/app/metrics"]

# Expose RPC server port
EXPOSE 8181

# Health check - verify RPC server responds
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8181/health', timeout=5)" || exit 1

# Default command
CMD ["python", "-m", "cthulu", "--config", "config.json", "--skip-setup", "--no-prompt"]





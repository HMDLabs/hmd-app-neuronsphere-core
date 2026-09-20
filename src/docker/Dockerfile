# syntax=docker/dockerfile:1.4

# Build stage for Python dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY src/docker/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# Production stage
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=deployment_gui.settings.production

WORKDIR /app

# Install runtime dependencies. (graphviz, for the deployment DAG layout, is the
# premium overlay's -- hmd-app-neuronsphere adds it on top of this image.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' --uid 1000 appuser

# Copy wheels from builder and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copy application code
COPY src/python/ /app/

# Copy gunicorn config
COPY src/docker/gunicorn.conf.py /app/

# Create static files directory and collect static
RUN mkdir -p /app/staticfiles \
    && python manage.py collectstatic --noinput --settings=deployment_gui.settings.base

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# Run with gunicorn driving uvicorn workers. The ASGI entry point mounts the MCP
# server at /mcp beside the Django app; see deployment_gui/asgi.py. To roll back
# to the previous WSGI path, set GUNICORN_WORKER_CLASS=sync and swap asgi->wsgi.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "deployment_gui.asgi:application"]

# Licence texts travel with the image: BUSL 1.1 requires the licence to be
# conspicuously displayed on every copy, and an image is a copy.
COPY LICENSE.txt LICENSE-Apache-2.0.txt NOTICE /licenses/hmd-app-neuronsphere-core/
LABEL org.opencontainers.image.licenses="BUSL-1.1 AND Apache-2.0"

# Python 3.14 official slim image
FROM python:3.14-slim

# Python runtime configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Application directory
WORKDIR /app

# Install dependencies separately to improve Docker build caching
COPY requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Create a non-root application user and writable data directory
RUN mkdir -p /app/data \
    && chown -R 10001:10001 /app

# Copy application source
COPY --chown=10001:10001 app ./app

# Run as non-root user
USER 10001:10001

# Application port
EXPOSE 8000

# Container health check
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3)"]

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

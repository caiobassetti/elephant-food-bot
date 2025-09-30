FROM python:3.12-slim

# No .pyc files and immediate stdout (for logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /app/

# Install runtime dependencies + dev dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir -r /app/requirements-dev.txt

# Copy application and entrypoint
COPY app /app/app
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

FROM python:3.12-slim

# No .pyc files and immediate stdout (for logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Azure persistent storage for containers is /home
# SQLite DB will live at /home/data/db.sqlite3
RUN mkdir -p /home/data

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install dependencies + WSGI + static helper
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir gunicorn whitenoise

# Copy application and entrypoint
COPY app /app/app
COPY docker/entrypoint.azure.sh /entrypoint.sh

# Collect static at build time to bake it on image
ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-time-secret \
    ALLOWED_HOSTS="*"
RUN python - <<'PY'
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE"))
sys.path.append("/app/app")
from django.core.management import execute_from_command_line
execute_from_command_line(["manage.py","collectstatic","--noinput"])
PY

# Entrypoint runs migrations and starts gunicorn
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]

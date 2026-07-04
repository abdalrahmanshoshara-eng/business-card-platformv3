FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for Pillow and psycopg2-binary at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Collect static files at build time (no DB needed for this step)
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000

# Use gunicorn for production; PORT is injected by Render (default 10000) or docker-compose
CMD sh -c "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --log-file -"

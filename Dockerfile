# syntax=docker/dockerfile:1

# 1. Откатываемся на стабильную и поддерживаемую ML-экосистемой версию
FROM python:3.12-slim

# --- Python runtime behaviour ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- System dependencies ---
# build-essential + libpq-dev are needed to build/run the psycopg2 driver.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-kaz cmake curl unzip \
    && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies (layer cached unless requirements change) ---
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip "setuptools<70" wheel \
    && pip install --no-cache-dir --no-build-isolation openai-whisper==20240930 \
    && pip install --no-cache-dir -r requirements.txt

# --- Application code ---
COPY . .

EXPOSE 8000

# Default command runs the production WSGI server. docker-compose overrides
# this for local development (migrate + runserver).
CMD ["gunicorn", "ai_media_watch.wsgi:application", "--bind", "0.0.0.0:8000"]

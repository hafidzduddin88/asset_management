# ---------- Build Stage ----------
FROM python:3.12.11-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    postgresql-dev \
    libffi-dev \
    jpeg-dev \
    zlib-dev \
    freetype-dev

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt \
 && apk del .build-deps

# ---------- Final Runtime Stage ----------
FROM python:3.12.11-alpine

WORKDIR /app

# Install runtime libraries only
RUN apk add --no-cache \
    libpq \
    libjpeg \
    zlib \
    freetype \
    libffi

# Copy virtualenv
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN adduser -D -s /bin/sh appuser && chown -R appuser:appuser /app
USER appuser

# Expose FastAPI default port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

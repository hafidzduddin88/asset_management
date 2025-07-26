# ---------- Build Stage ----------
FROM python:3.12.11-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    build-base \
    libpq-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev \
    freetype-dev \
    openblas-dev \
    tiff-dev \
    lcms2-dev \
    libwebp-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    python3-dev

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

# ---------- Final Runtime Stage ----------
FROM python:3.12.11-alpine

WORKDIR /app

# Install runtime libraries only
RUN apk add --no-cache \
    libpq \
    libjpeg \
    zlib \
    freetype \
    openblas \
    tiff \
    lcms2 \
    libwebp \
    libxml2 \
    libxslt \
    libffi

# Copy virtualenv
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY app/ ./app/
COPY requirements.txt .  

# Expose FastAPI default port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

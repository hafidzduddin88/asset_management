FROM python:3.12.11-alpine

# Install dependencies
RUN apk add --no-cache \
    gcc musl-dev libffi-dev postgresql-dev build-base \
    postgresql-libs curl dumb-init

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Create app user
RUN adduser -D -s /bin/sh app

# Set work directory
WORKDIR /home/app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application
COPY --chown=app:app . .

# Switch to app user
USER app

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
ENTRYPOINT ["dumb-init", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-keep-alive", "30"]
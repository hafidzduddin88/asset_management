# ---------- Build Stage ----------
FROM python:3.12.11-alpine AS builder

# Install build dependencies in single layer
RUN apk add --no-cache --virtual .build-deps \
    gcc musl-dev libffi-dev postgresql-dev build-base \
    && python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -type d -exec rm -rf {} + || true

# ---------- Production Stage ----------
FROM python:3.12.11-alpine

# Install runtime deps and create user in single layer
RUN apk add --no-cache postgresql-libs curl dumb-init && \
    adduser -D -s /bin/sh app && \
    rm -rf /var/cache/apk/*

# Copy optimized venv
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/home/app

# Switch to app user and set workdir
USER app
WORKDIR /home/app

# Copy app files (exclude unnecessary files)
COPY --chown=app:app app/ ./app/
COPY --chown=app:app requirements.txt ./

# Precompile Python files for faster startup
RUN python -m compileall -b app/ && \
    find app/ -name "*.py" -delete || true

EXPOSE 8000

# Optimized health check
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=2 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use dumb-init for proper signal handling and optimized uvicorn settings
ENTRYPOINT ["dumb-init", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout-keep-alive", "30", "--no-access-log"]
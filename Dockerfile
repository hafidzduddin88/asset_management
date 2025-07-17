FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p app/static/img

# Run any setup scripts if they exist
RUN if [ -f clean.py ]; then python clean.py; fi

# Set environment variables
ENV PORT=8000

# Command to run the application
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 30
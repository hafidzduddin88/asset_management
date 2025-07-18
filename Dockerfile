FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (layer jarang berubah → diletakkan di awal)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (untuk memaksimalkan cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories (kalau foldernya memang tidak dikommit)
RUN mkdir -p app/static/img

# Run setup script only if exists (lebih aman & cepat)
RUN test -f clean.py && python clean.py || echo "clean.py skipped"

# Set environment variables
ENV PORT=8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "30"]
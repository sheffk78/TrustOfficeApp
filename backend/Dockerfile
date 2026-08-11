FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code. Keep the knowledge router as an explicit source path:
# Railway has previously produced an image from a stale/incomplete COPY layer
# even though this file was present in the Git tree. An explicit COPY makes the
# file part of the layer checksum and the assertion below turns this into a
# build-time failure instead of a runtime crash.
COPY . /app/
COPY routers/knowledge.py /app/routers/knowledge.py

# Fail the build if the runtime image does not contain the imported router.
RUN test -f /app/routers/knowledge.py \
    && python -m py_compile /app/routers/knowledge.py

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the application
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}

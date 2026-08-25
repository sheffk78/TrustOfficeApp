FROM python:3.11-slim

# Cache bust — forces Railway to rebuild image from scratch
ARG CACHE_BUST=2026-08-24-chat-fix-v1
RUN echo "Cache bust: $CACHE_BUST"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code. The explicit per-file COPY lines below ensure each
# router file is part of the Docker layer checksum, preventing stale build
# cache from producing an image missing files that are present in the git tree.
COPY . /app/

# Explicitly copy all router files to bust stale cache layers
COPY routers/ /app/routers/

# Fail the build if any imported module is missing from the runtime image.
# Also verify the knowledge router specifically (previously lost to stale cache).
# Also verify services/ directory (knowledge_retrieval imports from services).
RUN ls /app/routers/knowledge.py /app/routers/messaging.py /app/routers/performance.py \
    && ls /app/services/__init__.py /app/services/trust_knowledge.py \
    && python -m py_compile /app/routers/knowledge.py \
    && python -m py_compile /app/routers/messaging.py \
    && python -m py_compile /app/routers/performance.py \
    && python -m py_compile /app/routers/knowledge_retrieval.py \
    && python -m py_compile /app/services/trust_knowledge.py

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the application
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
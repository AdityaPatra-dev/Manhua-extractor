# Universal Manhua Extractor & Web Reader Dockerfile
FROM python:3.11-slim

# Labels / Metadata
LABEL maintainer="Aditya Patra <adityapatra.dev>"
LABEL org.opencontainers.image.title="Universal Manhua Extractor"
LABEL org.opencontainers.image.description="All-in-one manga/manhua downloader, web reader, OPDS catalog, and backup sync server."
LABEL org.opencontainers.image.version="1.0.5"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/AdityaPatra-dev/Manhua-extractor"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MANHUA_DB_PATH=/app/data/library.db \
    MANHUA_DOWNLOADS_DIR=/app/downloads \
    MANHUA_BACKUPS_DIR=/app/backups \
    PORT=8000 \
    HOST=0.0.0.0

# Install runtime system dependencies (curl for healthcheck, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency definition and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt numpy

# Copy application source code
COPY app.py manhua.py ./
COPY core/ ./core/
COPY database/ ./database/
COPY extractors/ ./extractors/
COPY static/ ./static/
COPY docs/logos/ ./docs/logos/

# Create persistent mount directories
RUN mkdir -p /app/data /app/downloads /app/backups

# Expose Web GUI and OPDS port
EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Declare persistent volumes
VOLUME ["/app/data", "/app/downloads", "/app/backups"]

# Default entrypoint to run Web GUI mode
CMD ["python3", "manhua.py", "--web", "--host", "0.0.0.0", "--port", "8000"]

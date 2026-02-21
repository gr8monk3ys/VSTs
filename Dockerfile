# Free VST Plugins Downloader
# Multi-stage build for minimal image size

FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy only what's needed
COPY plugins.json .
COPY scripts/download-plugins.py scripts/

# Create downloads directory
RUN mkdir -p /downloads

# Set the downloads directory as default
ENV DOWNLOAD_DIR=/downloads

# Create a non-root user for security
RUN useradd -m -s /bin/bash vst && \
    chown -R vst:vst /app /downloads

USER vst

# Default entrypoint runs the download script
ENTRYPOINT ["python", "scripts/download-plugins.py", "--dir", "/downloads"]

# Default command shows help if no args provided
CMD ["--help"]

# Labels for container metadata
LABEL org.opencontainers.image.title="Free VST Plugins Downloader" \
      org.opencontainers.image.description="Cross-platform downloader for free VST plugins" \
      org.opencontainers.image.source="https://github.com/gr8monk3ys/free-vst-plugins" \
      org.opencontainers.image.licenses="MIT"

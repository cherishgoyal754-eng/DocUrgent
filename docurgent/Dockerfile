# ==============================================================================
# DocUrgent 24/7 — Production Containerfile (Google Cloud Run / Kubernetes)
# Minimal, secure, non-root user execution with zero bloat
# ==============================================================================

FROM python:3.11-slim-bullseye

# System setup & security hardening
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8095

WORKDIR /app

# Create unprivileged application user
RUN groupadd -r docurgent && useradd -r -g docurgent -d /app docurgent

# Copy application files
COPY . /app

# Ensure correct permissions on persistent directories
RUN mkdir -p /app/uploads /app/backups/db /app/backups/files && \
    chown -R docurgent:docurgent /app

# Switch to non-root execution
USER docurgent

# Expose server port
EXPOSE 8095

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8095/api/health')" || exit 1

# Launch DocUrgent Server
CMD ["python3", "server.py"]

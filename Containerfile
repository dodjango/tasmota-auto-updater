ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies and tini
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev tini && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -name '*.pyc' -delete || true && \
    find /opt/venv -name '__pycache__' -delete || true

# Create application directory structure
RUN mkdir -p /app/logs /app/app/tasmota/cache

###############################################

# Second stage: runtime image with minimal size
FROM python:${PYTHON_VERSION}-slim AS runtime

# Set working directory
WORKDIR /app

# Copy necessary files from the builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/bin/tini /usr/bin/tini
COPY --from=builder /app/logs /app/logs
COPY --from=builder /app/app/tasmota/cache /app/app/tasmota/cache

# Set environment variables in a single layer
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=5001

# Copy only necessary application files
COPY server.py wsgi.py gunicorn.conf.py /app/
COPY app/ /app/app/

# Create non-root user and set permissions
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 5001

# Container healthcheck — the slim image has no curl, so use the Python stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')" || exit 1

# Use tini as init process to handle signals properly
ENTRYPOINT ["/usr/bin/tini", "--"]

# Command to run the application with Gunicorn in production
# Use shell form to allow environment variable substitution
CMD gunicorn -c gunicorn.conf.py wsgi:app

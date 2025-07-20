ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -name '*.pyc' -delete || true && \
    find /opt/venv -name '__pycache__' -delete || true

# Second stage: runtime image with minimal size
FROM python:${PYTHON_VERSION}-slim AS runtime

# Set working directory
WORKDIR /app

# Copy only the necessary files from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Set environment variables in a single layer
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=5001

# Copy application code
COPY . .

# Create necessary directories and set up user in a single layer
RUN mkdir -p logs app/tasmota/cache && \
    apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 5001

# Use tini as init process to handle signals properly
ENTRYPOINT ["/usr/bin/tini", "--"]

# Command to run the application with Gunicorn in production
# Use shell form to allow environment variable substitution
CMD gunicorn --bind 0.0.0.0:5001 --workers ${GUNICORN_WORKERS:-4} --access-logfile - --error-logfile - wsgi:app

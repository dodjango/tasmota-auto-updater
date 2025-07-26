# Container Setup

This guide explains how to run Tasmota Remote Updater in a container using Docker or Podman.

## Prerequisites

- Docker or Podman installed on your system
- Basic knowledge of container concepts

## Quick Start

### Option 1: Build from source

The simplest way to run the application in a container is using Docker Compose or Podman Compose:

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Using Docker
docker compose up -d

# OR using Podman
podman-compose up -d
```

### Option 2: Pull from container registry

You can also pull the pre-built image directly from Docker Hub or GitHub Container Registry:

#### Docker Hub

```bash
# Pull the latest image
docker pull dodjango/tasmota-updater:latest

# Run the container
docker run -d -p 5001:5001 \
  -v $(pwd)/devices.yaml:/app/devices.yaml \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater dodjango/tasmota-updater:latest
```

#### GitHub Container Registry

```bash
# Pull the latest image
docker pull ghcr.io/dodjango/tasmota-updater:latest

# Run the container
docker run -d -p 5001:5001 \
  -v $(pwd)/devices.yaml:/app/devices.yaml \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater ghcr.io/dodjango/tasmota-updater:latest
```

> **Note:** You'll need to create a `devices.yaml` file in your current directory before running the container. See the [Configuration Options](configuration.md) documentation for details.

## Manual Container Setup

If you prefer to build and run the container manually:

### Using Docker

```bash
# Build the container image
docker build -f Containerfile -t tasmota-updater .

# Run the container
docker run -d -p 5001:5001 \
  -v $(pwd)/devices.yaml:/app/devices.yaml \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater tasmota-updater
```

### Using Podman

```bash
# Build the container image
podman build -f Containerfile -t tasmota-updater .

# Run the container
podman run -d -p 5001:5001 \
  -v $(pwd)/devices.yaml:/app/devices.yaml:Z \
  -v $(pwd)/logs:/app/logs:Z \
  --name tasmota-updater tasmota-updater
```

> **Note:** The `:Z` suffix on volume mounts is specific to Podman when running on systems with SELinux enabled (like Fedora, RHEL, CentOS). It automatically relabels the content with a private unshared label so the container can access it. Use `:z` (lowercase) instead if you want to share the volume between multiple containers.

## Environment Variables

The application can be configured using environment variables in the `compose.yml` file. For production deployments, the configuration follows these best practices:

```yaml
environment:
  - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
  - PORT=5001
  - HOST=0.0.0.0
  - DEVICES_FILE=${DEVICES_FILE:-devices.yaml}
  - DEV_MODE=false
  - GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}
  - ENV_FILE=
```

### Configuration Best Practices

1. **Variable Substitution**: Values like `${SECRET_KEY:-default-value}` will use the environment variable if set, or fall back to the default value.

2. **External Secrets**: For production, store sensitive values in an external environment file:
   ```bash
   # Create a production.env file (not committed to version control)
   echo "SECRET_KEY=your-secure-production-key" > production.env
   
   # Use it when deploying
   docker compose --env-file ./production.env up -d
   # OR
   podman-compose --env-file ./production.env up -d
   ```

3. **Development vs. Production**: 
   - For development: Use the `.env` file and set `ENV_FILE=.env`
   - For production: Use environment variables and set `ENV_FILE=` (empty)

## Volumes

The container setup includes two volumes:

- `./devices.yaml:/app/devices.yaml` - Maps your local devices configuration file into the container
- `./logs:/app/logs` - Maps the logs directory to persist logs outside the container

You can add additional volumes as needed for your specific use case.

## Production Deployment

For production deployments, the container uses Gunicorn as the WSGI server. You can configure the number of worker processes using the `GUNICORN_WORKERS` environment variable:

```bash
docker run -d -p 5001:5001 \
  -e GUNICORN_WORKERS=8 \
  -v $(pwd)/devices.yaml:/app/devices.yaml \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater tasmota-updater
```

## Container Health Checks

The container includes a health check that verifies the application is running properly. You can view the health status with:

```bash
# Using Docker
docker inspect --format='{{.State.Health.Status}}' tasmota-updater

# Using Podman
podman healthcheck run tasmota-updater
```

## Updating the Container

To update to a newer version of the application:

```bash
# Pull the latest code
git pull

# Rebuild and restart the container
docker compose up -d --build
# OR
podman-compose up -d --build
```

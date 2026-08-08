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
git clone https://github.com/dodjango/tasmota-updater.git
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
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater dodjango/tasmota-updater:latest
```

#### GitHub Container Registry

```bash
# Pull the latest image
docker pull ghcr.io/dodjango/tasmota-updater:latest

# Run the container
docker run -d -p 5001:5001 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater ghcr.io/dodjango/tasmota-updater:latest
```

> **Note:** You'll need a `devices.yaml` file in a `config` directory next to
> the container (e.g. `./config/devices.yaml`) before running it. The image
> looks for it at `/app/config/devices.yaml` by default — matching the mount
> shown above — so no `DEVICES_FILE` setting is needed unless you use a
> different path. See the [Configuration Options](configuration.md)
> documentation for details.
>
> **Migrating from an older version?** If you used to bind-mount
> `devices.yaml` directly (`-v $(pwd)/devices.yaml:/app/devices.yaml`), it
> still works — but the web UI's device editor stays read-only and says so,
> because replacing a bind-mounted *file* fails with `EBUSY`. Move
> `devices.yaml` into a directory and mount that directory instead, as shown
> above; the default `DEVICES_FILE` already expects it there, so only set
> that variable yourself if you choose a different path.

## Device Discovery and the Network Mode

The web UI can find Tasmota devices for you ("Find Devices" in the *Manage
Devices* section). It offers two ways to search, and **only one of them works
in the default container setup**:

| Method | Bridge network (default) | `network_mode: host` |
|---|---|---|
| **Scan network** (IP range) | Works | Works |
| **Search via mDNS** | Finds nothing, ever | Works |

The scan needs nothing special: the container can reach your LAN through the
bridge, so probing a range of addresses works exactly as it does on the host.

mDNS is different, and the reason is worth stating plainly: mDNS relies on
multicast traffic, and multicast does not cross a container bridge. This is not
a bug and no setting inside the application can fix it. In a bridge-network
container the mDNS search will always come back empty — the UI says so rather
than claiming that no devices exist.

### Enabling mDNS with host networking

If you want mDNS, the container has to share the host's network stack:

```yaml
services:
  tasmota-updater:
    image: ghcr.io/dodjango/tasmota-updater:latest
    # Required for mDNS. Read the trade-offs below before enabling this.
    network_mode: host
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    environment:
      - DEVICES_FILE=/app/config/devices.yaml
      - HOST=0.0.0.0
      - PORT=5001
    restart: unless-stopped
```

What you give up by doing this:

- **No network isolation.** The container shares the host's network namespace.
  It can reach anything the host can reach, and services it opens are host
  services.
- **No port mapping.** The `ports:` section stops applying — the app binds
  `PORT` on the host directly, so that port must be free.
- **Linux only.** On Docker Desktop for macOS and Windows, `network_mode: host`
  does not give the container the LAN's multicast traffic, so it does not
  actually solve the problem there.

**Our recommendation:** keep the default bridge network and use the range scan.
It finds the same devices, needs no privileges, and costs nothing in isolation.
Turn on host networking only if you specifically want mDNS and understand the
trade-off above.

### What the scanner is allowed to do

The scan is fenced server-side and cannot be widened from the browser:

- private IPv4 ranges only — a scan of public address space is rejected
- at most a `/22` (1024 addresses)
- 64 probes in parallel, 1.5 s timeout each, no retries
- no credentials are ever sent; a password-protected device is reported as
  such and left alone

## Manual Container Setup

If you prefer to build and run the container manually:

### Using Docker

```bash
# Build the container image
docker build -f Containerfile -t tasmota-updater .

# Run the container
docker run -d -p 5001:5001 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater tasmota-updater
```

### Using Podman

```bash
# Build the container image
podman build -f Containerfile -t tasmota-updater .

# Run the container
podman run -d -p 5001:5001 \
  -v $(pwd)/config:/app/config:Z \
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
  - DEVICES_FILE=${DEVICES_FILE:-/app/config/devices.yaml}
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

You can either use the . env fule or set the environment variables in the complse configuration.

Recommendation:
   - For development: Use the `.env` file and set `ENV_FILE=.env`
   - For production: Use environment variables and set `ENV_FILE=` (empty)

## Volumes

The container setup includes two volumes:

- `./config:/app/config` - Maps a local directory holding `devices.yaml` into the container. The
  *directory* is mounted, not the file, so the built-in devices editor can replace the file
  atomically when you save changes in the UI — replacing a bind-mounted single file fails with
  `EBUSY`.
- `./logs:/app/logs` - Maps the logs directory to persist logs outside the container

You can add additional volumes as needed for your specific use case.

## Production Deployment

For production deployments, the container uses Gunicorn as the WSGI server. You can configure the number of worker processes using the `GUNICORN_WORKERS` environment variable:

```bash
docker run -d -p 5001:5001 \
  -e GUNICORN_WORKERS=8 \
  -v $(pwd)/config:/app/config \
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

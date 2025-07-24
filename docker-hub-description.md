# Tasmota Remote Updater

Keep your Tasmota devices up to date with a single command or click. Tasmota Remote Updater is a tool that automatically updates multiple Tasmota devices to the latest firmware over your network.

## Features

- **Command-Line Interface**: Update multiple devices with a single command
- **Web Interface**: Modern dashboard with one-click updates and real-time monitoring
- **RESTful API**: Programmatic access with Swagger documentation

## Quick Start

### 1. Create a devices.yaml file

Create a `devices.yaml` file with your Tasmota device information:

```yaml
devices:
  - ip: 192.168.1.100
    username: admin  # optional
    password: secret  # optional
  - ip: 192.168.1.101
    username: admin  # optional
    password: secret  # optional
```

Alternatively, you can run the interactive configuration wizard:

```bash
docker run -it --rm -v $(pwd):/app dodjango/tasmota-updater python tasmota_updater.py --configure
```

### 2. Run the container

```bash
# Using Docker run
docker run -d -p 5001:5001 \
  -v $(pwd)/devices.yaml:/app/devices.yaml \
  -v $(pwd)/logs:/app/logs \
  --name tasmota-updater dodjango/tasmota-updater

# OR using Docker Compose
docker compose up -d
```

Example docker-compose.yml:
```yaml
services:
  tasmota-updater:
    image: dodjango/tasmota-updater:latest
    container_name: tasmota-updater
    ports:
      - "5001:5001"
    volumes:
      - ./devices.yaml:/app/devices.yaml
      - ./logs:/app/logs
    environment:
      - DEVICES_FILE=devices.yaml
      - SECRET_KEY=change-me-in-production
    restart: unless-stopped
```

## Environment Variables

- `DEVICES_FILE`: Path to devices configuration file (default: devices.yaml)
- `SECRET_KEY`: Secret key for session encryption
- `LOGGING_LEVEL`: Set logging level (default: INFO)
- `GUNICORN_WORKERS`: Number of Gunicorn workers (default: 4)

## Links

- [GitHub Repository](https://github.com/dodjango/tasmota-auto-updater)
- [Documentation](https://dodjango.github.io/tasmota-auto-updater/)
- [Issues & Feature Requests](https://github.com/dodjango/tasmota-auto-updater/issues)

## License

This project is licensed under the MIT License.

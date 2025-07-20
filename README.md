# Tasmota Remote Updater

![Tasmota Logo](https://tasmota.github.io/docs/_media/logo.png)

> Keep your Tasmota devices up to date with a single command or click

Tasmota Remote Updater is a very simple tool that automatically updates multiple Tasmota devices to the latest firmware over your network. No more manual updates or complex scripts - just point it at your devices and let it handle the rest.

[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

**Two powerful interfaces in one tool:**

### 🖥️ Command-Line
- Update multiple devices with a single command
- Automatic version checking and smart updates
- Detailed reporting and logging

### 🌐 Web Interface
- Modern, responsive dashboard
- Real-time status monitoring
- One-click updates for individual or all devices
- RESTful API with Swagger documentation

![Screenshot](docs/images/dashboard.png)

## 🚀 Web Interface Quick Start

### Local Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Create a virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the web interface
python app.py
```

Then visit http://localhost:5001 in your browser.

### Container Installation

The application can be run using either Docker or Podman with identical commands.

#### Using Docker

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Build and run with Docker Compose
docker compose up -d
```

Or build and run the container manually:

```bash
# Build the container image
docker build -f Containerfile -t tasmota-updater .

# Run the container
docker run -d -p 5001:5001 -v $(pwd)/devices.yaml:/app/devices.yaml -v $(pwd)/logs:/app/logs --name tasmota-updater tasmota-updater
```

#### Using Podman

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Build and run with Podman Compose
podman-compose up -d
```

Or build and run the container manually:

```bash
# Build the container image
podman build -f Containerfile -t tasmota-updater .

# Run the container
podman run -d -p 5001:5001 -v $(pwd)/devices.yaml:/app/devices.yaml:Z -v $(pwd)/logs:/app/logs:Z --name tasmota-updater tasmota-updater
```

> **Note:** The `:Z` suffix on volume mounts is specific to Podman when running on systems with SELinux enabled (like Fedora, RHEL, CentOS). It automatically relabels the content with a private unshared label so the container can access it. Use `:z` (lowercase) instead if you want to share the volume between multiple containers.

Then visit http://localhost:5001 in your browser.

## 🔄 Development with VS Code

This project includes VS Code tasks:

1. **Automatic Development Server**: The Flask development server starts automatically when you open the project in VS Code.

2. **Additional Tasks**: You can also run these tasks manually from the VS Code Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`):
   - `Start Flask Development Server`: Basic Flask server with auto-reload
   - `Setup Development Environment`: Install required dependencies

The development server will automatically reload when code changes are detected, making the development process faster and more efficient.

## 🐳 Container Configuration

The application can be run in a container using the provided Containerfile and compose.yml files. Both Docker and Podman are supported for containerization.

### Environment Variables

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

#### Configuration Best Practices

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

### Volumes

The Docker setup includes two volumes:

- `./devices.yaml:/app/devices.yaml` - Maps your local devices configuration file into the container
- `./logs:/app/logs` - Maps the logs directory to persist logs outside the container

You can add additional volumes as needed for your specific use case.

## 🧪 Development Mode

The application includes a development mode that uses fake devices instead of connecting to real Tasmota devices. This is useful for testing the UI and functionality without needing actual hardware.

### Using Development Mode

You can enable development mode by setting the `DEV_MODE` environment variable to `true` or by using the provided `.env.dev` file:

```bash
# Use the development environment configuration
ENV_FILE=.env.dev python app.py
```

In development mode:

1. The application loads devices from `devices-dev.yaml` instead of `devices.yaml`
2. No actual API calls are made to physical devices
3. Fake device information is used for testing all features

### Environment Configuration

The application uses `.env` files for configuration:

- `.env` - Default configuration (production mode)
- `.env.dev` - Development configuration with fake devices

You can specify which environment file to use with the `ENV_FILE` environment variable:

```bash
ENV_FILE=.env.dev python app.py
```

### Configuring Fake Devices

Fake devices are defined in `devices-dev.yaml` with the following structure:

```yaml
devices:
  - ip: 192.168.100.101
    username: admin
    password: password
    fake: true
    dns_name: fake-tasmota-light1.local
    firmware_info:
      version: "12.0.2"
      core_version: "2.7.4.9"
      sdk_version: "3.0.2"
      is_minimal: false
```

You can modify this file to simulate different device configurations and firmware versions.

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Command-Line Usage](docs/cli-usage.md)
- [Web Interface Guide](docs/web-interface.md)
- [API Documentation](docs/api.md)
- [Configuration Options](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🤝 Contributing

Contributions are welcome! See our [Contributing Guide](docs/contributing.md) for more details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Tasmota](https://tasmota.github.io/docs/) - For their excellent open-source firmware
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Bulma](https://bulma.io/) - CSS framework
- [Alpine.js](https://alpinejs.dev/) - JavaScript framework

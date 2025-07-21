# Tasmota Remote Updater

![Screenshot](docs/images/dashboard.png)
> Keep your Tasmota devices up to date with a single command or click

Tasmota Remote Updater is a tool that automatically updates multiple Tasmota devices to the latest firmware over your network. No more manual updates or complex scripts - just point it at your devices and let it handle the rest.

[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

**Three powerful interfaces in one tool:**

- **Command-Line Interface**: Update multiple devices with a single command
- **Web Interface**: Modern dashboard with one-click updates and real-time monitoring
- **RESTful API**: Programmatic access with Swagger documentation

## 🚀 Quick Start

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
python server.py
```

Then visit http://localhost:5001 in your browser.

### Container Installation

```bash
# Clone the repository and run with Docker or Podman
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Using Docker
docker compose up -d

# OR using Podman
podman-compose up -d
```

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Command-Line Usage](docs/cli-usage.md)
- [Web Interface Guide](docs/web-interface.md)
- [API Documentation](docs/api.md)
- [Configuration Options](docs/configuration.md)
- [Container Setup](docs/container-setup.md)
- [Development Guide](docs/development.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🤝 Contributing

Contributions are welcome! See our [Contributing Guide](docs/contributing.md) for more details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Tasmota](https://tasmota.github.io/docs/) - For their excellent open-source firmware
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Gunicorn](https://gunicorn.org/) - WSGI HTTP Server for UNIX
- [Bulma](https://bulma.io/) - CSS framework
- [Alpine.js](https://alpinejs.dev/) - JavaScript framework

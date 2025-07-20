# Development Guide

This guide explains how to set up and work with the Tasmota Remote Updater codebase for development purposes.

## Project Structure

The Tasmota Remote Updater follows a modular structure:

```
tasmota-updater/
├── app/                    # Main application package
│   ├── __init__.py         # Package initialization
│   ├── static/             # Static assets (CSS, JS)
│   ├── templates/          # HTML templates
│   └── tasmota/            # Tasmota-specific functionality
│       ├── __init__.py
│       ├── api.py          # API endpoints
│       ├── updater.py      # Core update functionality
│       └── utils.py        # Utility functions
├── docs/                   # Documentation
├── server.py               # Main application entry point
├── tasmota_updater.py      # Command-line interface
└── wsgi.py                 # WSGI entry point for production
```

## Setting Up the Development Environment

### Prerequisites

- Python 3.6 or higher
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Create a virtual environment using uv (recommended)
uv venv

# Activate the virtual environment
source .venv/bin/activate  # For bash/zsh
# OR
source .venv/bin/activate.fish  # For fish shell
# OR
.venv\Scripts\activate  # For Windows

# Install the required dependencies
uv pip install -r requirements.txt
```

## Running the Application in Development Mode

### Starting the Web Server

```bash
# Run the development server
python server.py
```

The server will start on http://localhost:5001 by default.

### Using Development Mode with Fake Devices

For development without real Tasmota devices, you can use the built-in development mode:

```bash
# Set development mode environment variable
export DEV_MODE=true

# Or use the development environment file
ENV_FILE=.env.dev python server.py
```

In development mode:

1. The application loads devices from `devices-dev.yaml` instead of `devices.yaml`
2. No actual API calls are made to physical devices
3. Fake device information is used for testing all features

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

## Environment Configuration

The application uses `.env` files for configuration:

- `.env` - Default configuration (production mode)
- `.env.dev` - Development configuration with fake devices

You can specify which environment file to use with the `ENV_FILE` environment variable:

```bash
ENV_FILE=.env.dev python server.py
```

## Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=app
```

## Code Style and Linting

This project follows PEP 8 style guidelines. You can check your code style with:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run flake8
flake8 app tests

# Run black (code formatter)
black app tests
```

## Debugging

The application uses Python's built-in logging module. You can increase verbosity by setting the `LOG_LEVEL` environment variable:

```bash
LOG_LEVEL=DEBUG python server.py
```

## Building Documentation

The documentation is written in Markdown and stored in the `docs/` directory.

# Development Guide

This guide explains how to set up and work with the Tasmota Remote Updater codebase for development purposes.

## Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/). When making changes to the codebase, consider how your changes impact the version number:

- **MAJOR version**: Increment when you make incompatible API changes
- **MINOR version**: Increment when you add functionality in a backward-compatible manner
- **PATCH version**: Increment when you make backward-compatible bug fixes

The version is defined in `app/version.py` and should be updated as part of the release process. When releasing a new version, follow these steps:

1. Update the version in `app/version.py`
2. Commit the change with a message like "Bump version to x.y.z"
3. Create a git tag with the version number: `git tag -a vx.y.z -m "Release version x.y.z"`
4. Push the changes and tag

For more details, see the release workflow: `/release-version`

## Project Structure

The Tasmota Remote Updater follows a modular structure:

```
tasmota-updater/
├── .github/                # GitHub configuration files
│   ├── dependabot.yml      # Dependabot configuration
│   └── workflows/          # GitHub Actions workflows
│       ├── dependabot-auto-merge.yml  # Auto-merge for Dependabot PRs
│       ├── publish-container.yml      # Container image publishing
│       └── update-dockerhub-description.yml  # Update Docker Hub description
├── .windsurf/             # Windsurf development tools
│   └── workflows/         # Windsurf workflows
│       └── release-version.md  # Release workflow
├── app/                   # Main application package
│   ├── __init__.py        # Package initialization
│   ├── static/            # Static assets (CSS, JS)
│   ├── templates/         # HTML templates
│   ├── version.py         # Version information (SemVer)
│   └── tasmota/           # Tasmota-specific functionality
│       ├── __init__.py
│       ├── api.py         # API endpoints
│       ├── updater.py     # Core update functionality
│       └── utils.py       # Utility functions
├── docs/                  # Documentation
├── server.py              # Main application entry point
├── tasmota_updater.py     # Command-line interface
└── wsgi.py                # WSGI entry point for production
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

### Using Fake Devices for Development

For development without real Tasmota devices, you can use fake devices:

```bash
# Use the development environment file which points to devices-dev.yaml
ENV_FILE=.env.dev python server.py
```

When using fake devices:

1. The application loads devices from `devices-dev.yaml` (configured in `.env.dev`) instead of `devices.yaml`
2. Devices marked as `fake: true` in the configuration will not make actual API calls to physical devices
3. Simulated responses are used for testing all features, including firmware updates
4. Updates to fake devices are simulated with a random delay of 2-5 seconds

### Configuring Fake Devices

Fake devices are defined in `devices-dev.yaml` with the following structure:

```yaml
devices:
  - ip: 192.168.100.101
    username: admin
    password: password
    fake: true                    # This flag marks the device as fake
    dns_name: fake-tasmota-light1.local
    firmware_info:                # Pre-configured firmware information
      version: "12.0.2"           # Simulated firmware version
      core_version: "2.7.4.9"     # Simulated core version
      sdk_version: "3.0.2"        # Simulated SDK version
      is_minimal: false           # Whether this is a minimal version
```

You can modify this file to simulate different device configurations and firmware versions. The key configuration options are:

- `fake: true` - This is the critical flag that marks a device as fake
- `firmware_info` - Pre-configured firmware information that will be returned instead of making API calls
- `dns_name` - Optional DNS name for the fake device

You can create multiple fake devices with different configurations to test various scenarios, such as:

- Devices with outdated firmware that need updates
- Devices already on the latest firmware
- Devices with minimal firmware versions
- Devices with different authentication requirements

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

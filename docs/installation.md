# Installation Guide

This guide will help you install and set up Tasmota Remote Updater on your system.

## Prerequisites

- Python 3.6 or higher
- Network access to your Tasmota devices
- Tasmota devices with OTA updates enabled
- Modern web browser for the web interface (Chrome, Firefox, Safari, or Edge)
- Sufficient permissions to install Python packages and create files

## What are OTA Updates?

OTA (Over-The-Air) updates refer to the ability to update firmware wirelessly, without requiring a physical connection. Tasmota devices have built-in OTA update functionality that can be accessed through their web interface, MQTT commands, or HTTP API commands (which this application uses).

To check if OTA updates are enabled on your Tasmota device:
1. Access the Tasmota web interface by entering the device's IP address in a browser
2. Go to Configuration → Configure Other
3. Look for the "Allow OTA Updates" option and ensure it's enabled

## Installation Options

### Option 1: Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a modern Python package manager and virtual environment tool that's faster than traditional tools.

```bash
# Clone this repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Create a virtual environment
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

### Option 2: Using pip and venv

```bash
# Clone this repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate  # For bash/zsh
# OR
source venv/bin/activate.fish  # For fish shell
# OR
venv\Scripts\activate  # For Windows

# Install the required dependencies
pip install -r requirements.txt
```

### Option 3: Manual Installation

1. Download the script files
2. Install the required dependencies:

```bash
pip install requests pyyaml flask flask-cors flasgger
```

## Verifying Installation

After installation, you can verify that everything is working correctly by running:

```bash
# For the web interface
python server.py

# For the command-line tool
python tasmota_updater.py --example
```

## Next Steps

- [Configure your devices](configuration.md)
- [Learn how to use the command-line tool](cli-usage.md)
- [Explore the web interface](web-interface.md)

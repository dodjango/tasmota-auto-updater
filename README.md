# Tasmota Remote Updater

A simple Python script to remotely update Tasmota devices over your network using Tasmota's HTTP API.

## Features

- Update multiple Tasmota devices using their IP addresses from a file
- Support for both official releases and custom firmware
- Automatic verification of device status after update
- Simple command-line interface
- Error handling and status reporting
- Summary report of successful and failed updates

## Prerequisites

- Python 3.6 or higher
- `requests` library
- `pyyaml` library
- Network access to your Tasmota devices
- Tasmota devices with web updates enabled

## Installation

1. Clone this repository or download the files
2. Install the required dependencies:

```bash
pip install requests pyyaml
```

## Usage

### Setting Up Device List

1. Create a YAML file named `devices.yaml` in the same directory as the script
2. Add your devices in YAML format:

```yaml
devices:
  - ip: 192.168.1.100
    username: admin  # optional
    password: secret # optional
  - ip: 192.168.1.101
  - ip: 192.168.1.102
    username: admin
    password: mypass
```

### Running Updates

1. Run the script:

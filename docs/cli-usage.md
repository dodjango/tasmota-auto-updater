# Command-Line Usage Guide

The Tasmota Remote Updater includes a powerful command-line interface that allows you to update multiple devices at once, check firmware versions, and more.

## Basic Usage

```bash
# If using a virtual environment, make sure it's activated first
source venv/bin/activate  # For standard venv (bash/zsh)
# OR
source .venv/bin/activate  # For uv (bash/zsh)

# Then run the script
python tasmota_updater.py
```

## Setting Up Device List

The script uses a YAML file named `devices.yaml` to store your Tasmota device information.

### Interactive Configuration Wizard

When you run the script for the first time, an interactive configuration wizard will guide you through setting up your devices:

1. The wizard will prompt you to enter the IP address for each device
2. For each device, you can optionally provide authentication credentials (username and password)
3. When you're finished adding devices, simply press Enter without typing an IP address

**Example of the interactive wizard:**

```
=== Tasmota Device Configuration Wizard ===

This wizard will help you create a configuration file for your Tasmota devices.
You'll be prompted to enter information for each device.
When you're finished adding devices, just press Enter without typing an IP address.

--- Device #1 ---
Enter device IP address (or press Enter to finish): 192.168.1.100

Authentication (leave empty if not required):
Username (default: empty): admin
Password (default: empty): secret
Device #1 added successfully!

--- Device #2 ---
Enter device IP address (or press Enter to finish): 192.168.1.101

Authentication (leave empty if not required):
Username (default: empty): 
Password (default: empty): 
Device #2 added successfully!

--- Device #3 ---
Enter device IP address (or press Enter to finish): 

Configuration saved to devices.yaml
Found 2 device(s) in the configuration
```

### Manual Configuration

If you prefer to create or edit the file manually, use this format:

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

> **Note:** The `devices.yaml` file is excluded from version control in the `.gitignore` file to prevent accidentally committing your device credentials.

## Command-line Arguments

The script supports several command-line arguments:

```
usage: tasmota_updater.py [-h] [-f FILE] [--example] [--non-interactive] [--dry-run] [--check-only] [--update-all] [--log-file LOG_FILE] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

Update Tasmota devices over your network

options:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  Path to devices configuration file (default: devices.yaml)
  --example             Create an example configuration file and exit
  --non-interactive     Don't use interactive prompts, create example file if needed
  --dry-run             Simulate the update process without making any changes
  --check-only          Only check firmware versions without updating any devices
  --update-all          Update all devices even if they are already running the latest version
  --log-file LOG_FILE   Path to log file (default: logs/tasmota_updater.log)
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging level (default: INFO)
```

## Common Use Cases

### Creating an Example Configuration

```bash
python tasmota_updater.py --example
```

### Using a Custom Configuration File

```bash
python tasmota_updater.py -f my_devices.yaml
```

### Dry Run Mode (Simulation)

```bash
python tasmota_updater.py --dry-run
```

### Check Firmware Versions Without Updating

```bash
python tasmota_updater.py --check-only
```

### Update All Devices (Even Up-to-Date Ones)

```bash
python tasmota_updater.py --update-all
```

### Specify Custom Log File

```bash
python tasmota_updater.py --log-file /var/log/tasmota_updates.log
```

### Use Debug Logging Level

```bash
python tasmota_updater.py --log-level DEBUG
```

## Logging

The script logs all operations to both the console and a log file. By default, logs are stored in `logs/tasmota_updater.log`.

Log levels available:

- **DEBUG**: Detailed information, typically useful for diagnosing problems
- **INFO**: Confirmation that things are working as expected (default)
- **WARNING**: Indication that something unexpected happened, but the script is still working
- **ERROR**: Due to a more serious problem, the script has not been able to perform some function
- **CRITICAL**: A serious error, indicating that the script may be unable to continue running

## Automation

You can schedule regular updates using cron jobs:

```bash
# Example cron job to run updates every Sunday at 3 AM
0 3 * * 0 cd /path/to/tasmota-updater && python tasmota_updater.py >> /var/log/tasmota_updates.log 2>&1
```

## Next Steps

- [Web Interface Guide](web-interface.md)
- [Configuration Options](configuration.md)
- [Troubleshooting](troubleshooting.md)

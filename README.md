# Tasmota Remote Updater

A simple Python script to remotely update Tasmota devices over your network using Tasmota's HTTP API. This tool helps you keep multiple Tasmota devices up to date with the latest firmware without having to manually update each one.

![Tasmota Logo](https://tasmota.github.io/docs/_media/logo.png)

## Features

- ✅ Update multiple Tasmota devices simultaneously using their IP addresses
- 🔄 Automatic update to the latest official Tasmota release
- 🔍 Automatic verification of device status after update
- 📊 Detailed status reporting for each device
- 📝 Summary report of successful and failed updates
- 🔐 Support for devices with authentication
- 🔎 Check current firmware versions on devices without updating
- 🔄 Skip updates for devices already running the latest version
- 📋 Compare installed versions with the latest official release

## Prerequisites

- Python 3.6 or higher
- Network access to your Tasmota devices
- Tasmota devices with web updates enabled

## Installation

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
pip install requests pyyaml
```

## Usage

### Setting Up Device List

The script uses a YAML file named `devices.yaml` to store your Tasmota device information.

#### Interactive Configuration Wizard

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

#### Manual Configuration

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

### Running Updates

To update all your devices:

```bash
# If using a virtual environment, make sure it's activated first
source .venv/bin/activate  # For uv (bash/zsh)
# OR
source venv/bin/activate  # For standard venv (bash/zsh)

# Then run the script
python tasmota_updater.py
```

#### One-liner with uv (no activation needed)

```bash
uv run python tasmota_updater.py
```

#### Command-line Arguments

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

##### Examples

```bash
# Create an example configuration file without running updates
uv run python tasmota_updater.py --example

# Use a custom configuration file
uv run python tasmota_updater.py -f my_devices.yaml

# Non-interactive mode (useful for scripts or environments without input)
uv run python tasmota_updater.py --non-interactive

# Dry run mode - simulate updates without making changes
uv run python tasmota_updater.py --dry-run

# Check firmware versions without updating
uv run python tasmota_updater.py --check-only

# Update all devices even if they're already on the latest version
uv run python tasmota_updater.py --update-all

# Specify a custom log file
uv run python tasmota_updater.py --log-file /var/log/tasmota_updates.log

# Use debug logging level for more detailed logs
uv run python tasmota_updater.py --log-level DEBUG

# Combine options
uv run python tasmota_updater.py --dry-run --log-level DEBUG
```

#### Dry Run Mode

The script supports a dry run mode that simulates the update process without making any actual changes to your devices. This is useful for testing your configuration and checking device connectivity before performing real updates.

In dry run mode, the script will:

1. Read your device configuration file
2. Check if each device is reachable (connectivity test)
3. Show what actions would be performed during a real update
4. Provide a summary of which devices would be updated successfully

To use dry run mode, add the `--dry-run` flag:

```bash
uv run python tasmota_updater.py --dry-run
```

Example dry run output:

```
2025-07-05 09:13:10 - INFO - Starting Tasmota Updater in DRY RUN mode (no changes will be made)
2025-07-05 09:13:10 - INFO - Using configuration file: devices.yaml
2025-07-05 09:13:10 - INFO - Found 8 devices that would be updated (DRY RUN)
2025-07-05 09:13:10 - INFO - 
Would update device at 192.168.8.191 (DRY RUN)
2025-07-05 09:13:10 - INFO - Processing device: 192.168.8.191 (DRY RUN)
2025-07-05 09:13:10 - DEBUG - No authentication provided for 192.168.8.191
2025-07-05 09:13:10 - INFO - 192.168.8.191: Would upgrade to latest official release (DRY RUN)
2025-07-05 09:13:10 - INFO - 192.168.8.191: Would wait for device to restart and come back online (DRY RUN)
2025-07-05 09:13:10 - INFO - 192.168.8.191: Device is reachable, status code: 200 (DRY RUN)

...

2025-07-05 09:13:15 - INFO - 
DRY RUN Summary:
2025-07-05 09:13:15 - INFO - ----------------------------------------
2025-07-05 09:13:15 - INFO - Would successfully update: 6/8 devices
2025-07-05 09:13:15 - WARNING - Devices that would fail:
2025-07-05 09:13:15 - WARNING - - 192.168.8.197 (not reachable in dry run test)
2025-07-05 09:13:15 - WARNING - - 192.168.8.198 (not reachable in dry run test)
2025-07-05 09:13:15 - INFO - Tasmota Updater finished (DRY RUN mode - no changes were made)
```

#### Logging

The script logs all operations to both the console and a log file. By default, logs are stored in `logs/tasmota_updater.log`, but you can specify a different location using the `--log-file` option.

Log levels available:

- **DEBUG**: Detailed information, typically useful for diagnosing problems
- **INFO**: Confirmation that things are working as expected (default)
- **WARNING**: Indication that something unexpected happened, but the script is still working
- **ERROR**: Due to a more serious problem, the script has not been able to perform some function
- **CRITICAL**: A serious error, indicating that the script may be unable to continue running

Example log output:

```
2025-07-05 09:08:23 - INFO - Starting Tasmota Updater
2025-07-05 09:08:23 - INFO - Using configuration file: devices.yaml
2025-07-05 09:08:23 - INFO - Found 8 devices to update
2025-07-05 09:08:23 - INFO - 
Updating device at 192.168.8.191
2025-07-05 09:08:23 - INFO - Processing device: 192.168.8.191
2025-07-05 09:08:23 - DEBUG - No authentication provided for 192.168.8.191
2025-07-05 09:08:23 - INFO - 192.168.8.191: Upgrading to latest official release
2025-07-05 09:08:23 - DEBUG - 192.168.8.191: Sending request to http://192.168.8.191/cm with params {'cmnd': 'Upgrade 1'}
2025-07-05 09:08:28 - ERROR - 192.168.8.191: Error connecting to device: HTTPConnectionPool(host='192.168.8.191', port=80): Max retries exceeded with url: /cm?cmnd=Upgrade+1
```

The script will:
1. Read the device list from `devices.yaml`
2. Connect to each device and initiate the firmware update
3. Wait for the update to complete and the device to restart
4. Verify if the device is back online
5. Provide a summary of successful and failed updates

## Example Output

```
Found 3 devices to update

Updating device at 192.168.1.100
Upgrading to latest official release
Initiating update for Tasmota device at 192.168.1.100
Update command sent successfully
Device will restart automatically after update
Waiting for device to come back online...
Device is back online!

Updating device at 192.168.1.101
Upgrading to latest official release
Initiating update for Tasmota device at 192.168.1.101
Update command sent successfully
Device will restart automatically after update
Waiting for device to come back online...
Device is back online!

Updating device at 192.168.1.102
Upgrading to latest official release
Initiating update for Tasmota device at 192.168.1.102
Update command sent successfully
Device will restart automatically after update
Waiting for device to come back online...
Device is back online!

Update Summary:
----------------------------------------
Successfully updated: 3/3 devices
```

## Troubleshooting

### Common Issues

1. **Device Not Found**: Ensure the IP address is correct and the device is connected to the network.
2. **Authentication Failed**: Double-check the username and password in the `devices.yaml` file.
3. **Update Timeout**: If the script reports a device as failed, it might still be updating. Check the device manually after a few minutes.
4. **Connection Refused**: Make sure the Tasmota device has web updates enabled and is accessible over HTTP.

### Logs

The script outputs detailed logs to the console. For persistent logs, redirect the output to a file:

```bash
python tasmota_updater.py > update_log.txt 2>&1
```

## Advanced Usage

### Custom Firmware

To use custom firmware, modify the `update_tasmota` function in the script to point to your firmware URL.

### Scheduled Updates

You can schedule regular updates using cron jobs:

```bash
# Example cron job to run updates every Sunday at 3 AM
0 3 * * 0 cd /path/to/tasmota-updater && uv run python tasmota_updater.py >> /var/log/tasmota_updates.log 2>&1
```

### Managing Dependencies with uv

#### Adding New Dependencies

```bash
uv pip install package_name
```

#### Updating Dependencies

```bash
uv pip install --upgrade package_name
```

#### Updating requirements.txt

```bash
uv pip freeze > requirements.txt
```

#### Checking for Outdated Packages

```bash
uv pip list --outdated
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. The MIT License is a permissive license that allows for reuse with few restrictions.

## Acknowledgments

- [Tasmota](https://tasmota.github.io/docs/) - For their excellent open-source firmware
- All contributors and users of this tool
- This project's entire codebase was created by vibe coding using [Windsurf AI](https://www.windsurfai.com/)

# Configuration Options

This guide explains the various configuration options available in Tasmota Remote Updater.

## Device Configuration

The primary configuration file is `devices.yaml`, which contains the list of Tasmota devices to manage.

### Basic Structure

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

### Required Fields

- `ip`: The IP address of the Tasmota device

### Optional Fields

- `username`: Username for authentication (if the device requires it)
- `password`: Password for authentication (if the device requires it)

## Editing Devices in the Web UI

The web interface includes a devices editor (under "Manage Devices") that reads and writes
`devices.yaml` directly — no need to edit the file by hand or restart the app. It manages the
same fields as the YAML file: `ip`, `dns_name`, `username`, `password` and `timeout`. Fields the
editor does not manage (such as `fake` and cached `firmware_info`) are preserved as-is.

A few behaviours are easy to miss:

- **The password field is write-only.** The server never sends stored passwords back to the
  browser, so the field always starts empty. Leave it blank and save to keep the existing
  password; use "Remove password" to delete it explicitly.
- **Changing a device's IP address creates a new device.** The editor matches existing entries by
  IP to know which stored password belongs to which device. If you change the IP, the password is
  not carried over — enter it again after the IP change.
- **Comments in `devices.yaml` are lost when the UI saves.** The editor rewrites the whole file
  from its in-memory model, so any hand-written comments in the YAML will not survive a save made
  through the web UI.
- **One backup generation is kept.** Every save copies the previous file to `devices.yaml.bak`
  before writing the new one, so only the file from immediately before the last save is
  recoverable — each subsequent save overwrites that backup in turn.
- **The editor can be read-only.** If `devices.yaml` is bind-mounted into the container as a
  single file rather than as part of a mounted directory, the file cannot be replaced atomically
  (`EBUSY`) and the editor disables itself with an explanation. See
  [Container Setup](container-setup.md) for the directory-mount migration.

## Environment Variables

The application supports the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Secret key for Flask sessions | `dev` |
| `DEVICES_FILE` | Path to the devices configuration file | `devices.yaml` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FILE` | Path to the log file | `logs/tasmota_updater.log` |

Example usage:

```bash
SECRET_KEY=mysecretkey DEVICES_FILE=/path/to/mydevices.yaml python app.py
```

## Web Application Configuration

The web application's configuration is defined in `server.py`:

```python
app.config.from_mapping(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
    DEVICES_FILE=os.environ.get('DEVICES_FILE', 'devices.yaml'),
    # Security settings
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 't'),
    SESSION_COOKIE_HTTPONLY=os.environ.get('SESSION_COOKIE_HTTPONLY', 'true').lower() in ('true', '1', 't'),
    SWAGGER={
        'title': 'Tasmota Updater API',
        'description': 'API for managing and updating Tasmota devices',
        'version': '1.0.0',
        'uiversion': 3,
    }
)
```

### API Configuration

The application uses Flask-RESTful for creating the API endpoints. The API is configured in the `app/tasmota/api.py` file:

```python
from flask_restful import Api, Resource

# API initialization
api = Api(app, prefix='/api')

# Register API endpoints
api.add_resource(DeviceResource, '/devices/<string:device_id>')
api.add_resource(DeviceListResource, '/devices')
api.add_resource(UpdateResource, '/update/<string:device_id>')
api.add_resource(UpdateAllResource, '/update/all')
```

### Customizing the Web Interface

To customize the web interface, you can modify the following files:

- `app/templates/index.html`: Main HTML template
- `app/static/css/styles.css`: Custom CSS styles
- `app/static/js/app.js`: Frontend JavaScript code

## Command-Line Options

The command-line tool supports various options that can be specified when running the script:

```
usage: tasmota_updater.py [-h] [-f FILE] [--example] [--non-interactive] [--dry-run] [--check-only] [--update-all] [--log-file LOG_FILE] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
```

| Option | Description | Default |
|--------|-------------|---------|
| `-f, --file` | Path to devices configuration file | `devices.yaml` |
| `--example` | Create an example configuration file and exit | - |
| `--non-interactive` | Don't use interactive prompts | - |
| `--dry-run` | Simulate the update process without making changes | - |
| `--check-only` | Only check firmware versions without updating | - |
| `--update-all` | Update all devices even if already on latest version | - |
| `--log-file` | Path to log file | `logs/tasmota_updater.log` |
| `--log-level` | Logging level | `INFO` |

## Logging Configuration

Logging is configured in both the command-line tool and the web application:

### Log Levels

- `DEBUG`: Detailed information for diagnosing problems
- `INFO`: Confirmation that things are working as expected
- `WARNING`: Indication that something unexpected happened
- `ERROR`: Due to a more serious problem, some function was not performed
- `CRITICAL`: A serious error, indicating that the program may be unable to continue

### Log File Structure

Logs are written in the following format:

```
YYYY-MM-DD HH:MM:SS - LEVEL - Message
```

Example:

```
2025-07-05 09:08:23 - INFO - Starting Tasmota Updater
2025-07-05 09:08:23 - INFO - Using configuration file: devices.yaml
2025-07-05 09:08:23 - INFO - Found 8 devices to update
```

## Advanced Configuration

### Custom Firmware Sources

By default, the application uses the official Tasmota releases from GitHub. To use custom firmware sources, you would need to modify the `fetch_latest_tasmota_release` function in `app/tasmota/updater.py`.

### Update Behavior

You can customize the update behavior by modifying the following parameters in `app/tasmota/updater.py`:

- `max_wait`: Maximum time to wait for a device to come back online after update (default: 60 seconds)
- `wait_interval`: Interval between checks when waiting for a device (default: 5 seconds)

## Next Steps

- [Troubleshooting](troubleshooting.md)
- [Contributing Guide](contributing.md)

# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Tasmota Remote Updater.

## Common Issues

### Connection Problems

#### Device Not Found or Unreachable

**Symptoms:**
- "Device is not reachable" error
- "Failed to get current firmware version" message

**Possible Causes:**
1. Incorrect IP address in configuration
2. Device is offline or powered down
3. Network connectivity issues
4. Firewall blocking connections

**Solutions:**
1. Verify the IP address is correct in `devices.yaml`
2. Ensure the device is powered on and connected to the network
3. Try to ping the device: `ping 192.168.1.100`
4. Check if you can access the device's web interface directly in a browser
5. Verify firewall settings allow HTTP traffic to the device

#### Authentication Failed

**Symptoms:**
- "Authentication failed" error
- HTTP 401 Unauthorized errors in logs

**Solutions:**
1. Check username and password in `devices.yaml`
2. Try accessing the device's web interface with the same credentials
3. Reset the device's credentials if necessary

### Update Problems

#### Update Timeout

**Symptoms:**
- "Update initiated but device did not come back online within timeout period" message
- Update appears to start but never completes

**Possible Causes:**
1. Device is taking longer than expected to update and restart
2. Update failed and device is in recovery mode
3. Network connectivity issues during update

**Solutions:**
1. Increase the timeout period in the code (modify `max_wait` in `update_device_firmware`)
2. Check the device manually after a few minutes
3. If the device is unresponsive, you may need to perform a manual recovery

#### OTA Updates Disabled

**Symptoms:**
- "Failed to send upgrade command" message
- Updates consistently fail on specific devices

**Solutions:**
1. Access the device's web interface
2. Go to Configuration → Configure Other
3. Ensure "Allow OTA Updates" is enabled
4. Save configuration and try again

### Web Interface Issues

#### Web Interface Not Loading

**Symptoms:**
- Cannot access the web interface at http://localhost:5001
- Browser shows connection refused error

**Possible Causes:**
1. Web application is not running
2. Application is running on a different port
3. Firewall blocking access

**Solutions:**
1. Check if the application is running: `ps aux | grep app.py`
2. Start the application: `python app.py`
3. Check the console output for any error messages
4. Verify the port is not in use by another application

#### API Errors

**Symptoms:**
- API calls return errors
- Web interface shows error messages

**Solutions:**
1. Check the application logs for detailed error information
2. Verify the API is working using curl: `curl http://localhost:5001/api/v1/devices`
3. Restart the web application

## Logging and Debugging

### Enabling Debug Logging

For more detailed logs, run the application with debug logging enabled:

```bash
# For the command-line tool
python tasmota_updater.py --log-level DEBUG

# For the web application
LOG_LEVEL=DEBUG python app.py
```

### Checking Logs

Logs are stored in `logs/tasmota_updater.log` by default. You can view them with:

```bash
tail -f logs/tasmota_updater.log
```

### Common Log Messages and Solutions

#### "Failed to get firmware version. Status code: 503"

This indicates the device is not responding properly to API requests.

**Solutions:**
1. Check if the device is overloaded
2. Verify the device is running Tasmota firmware
3. Try accessing the device's web interface directly

#### "Error connecting to device: HTTPConnectionPool(...): Max retries exceeded"

This indicates network connectivity issues.

**Solutions:**
1. Verify network connectivity
2. Check if the device is online
3. Ensure no firewall is blocking the connection

## Recovery Procedures

### Recovering Bricked Devices

If a device becomes unresponsive after an update attempt:

1. Try power cycling the device (unplug and plug back in)
2. Wait at least 5 minutes for any automatic recovery procedures
3. If the device has a physical reset button, try using it
4. As a last resort, you may need to flash the firmware using a serial connection

### Restoring Previous Firmware

Tasmota doesn't provide an automatic way to roll back to previous firmware versions. If you need to downgrade:

1. Download the specific firmware version you need from the [Tasmota GitHub releases](https://github.com/arendst/Tasmota/releases)
2. Use the web interface's "Firmware Upgrade" option to upload the specific firmware file

## Getting More Help

If you're still experiencing issues:

1. Check the [GitHub Issues](https://github.com/yourusername/tasmota-updater/issues) for similar problems
2. Create a new issue with detailed information:
   - Exact error messages
   - Steps to reproduce
   - Log output with debug logging enabled
   - Your environment details (OS, Python version, etc.)

## Next Steps

- [Contributing Guide](contributing.md) - Help improve the project

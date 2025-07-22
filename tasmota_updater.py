import sys
import argparse
import logging
import os
import yaml
from pathlib import Path

# Import functions from the refactored modules
from app.tasmota.updater import (
    get_device_firmware_version,
    fetch_latest_tasmota_release,
    compare_versions,
    update_device_firmware,
    get_dns_name
)
from app.tasmota.updater import sanitize_data
from app.tasmota.utils import load_devices_from_file, setup_logging

# Note: The following functions have been imported from app.tasmota.updater and app.tasmota.utils modules:
# - get_dns_name
# - get_device_firmware_version
# - fetch_latest_tasmota_release
# - compare_versions
# - update_device_firmware


def update_tasmota(device_config, dry_run=False, skip_up_to_date=True, latest_release_info=None):
    """
    Update Tasmota device remotely via HTTP API
    
    Args:
        device_config (dict): Device configuration containing IP and optional credentials
        dry_run (bool): If True, simulate the update process without making changes
        skip_up_to_date (bool): If True, skip devices that are already up to date
        latest_release_info (dict): Information about the latest release, if already fetched
    Returns:
        bool: True if update was successful (or would be in dry run mode), False otherwise
        dict: Additional result information including version details
    """
    logger = logging.getLogger()
    ip_address = device_config.get('ip')
    username = device_config.get('username')
    password = device_config.get('password')
    
    # Get DNS name if available
    dns_name = get_dns_name(ip_address)
    if dns_name:
        logger.debug(f"{ip_address}: DNS name: {dns_name}")
    
    result = {
        'success': False,
        'message': '',
        'current_version': 'Unknown',
        'latest_version': 'Unknown',
        'dns_name': dns_name
    }
    
    # In dry run mode, just check if the device is reachable
    if dry_run:
        try:
            logger.info(f"{ip_address}: Checking device connectivity (DRY RUN)")
            response = requests.get(f"http://{ip_address}", timeout=5)
            logger.info(f"{ip_address}: Device is reachable, status code: {response.status_code} (DRY RUN)")
            result['success'] = True
            result['message'] = f"Device is reachable (DRY RUN)"
            return True, result
        except requests.exceptions.RequestException as e:
            logger.warning(f"{ip_address}: Device is not reachable: {e} (DRY RUN)")
            result['message'] = f"Device is not reachable (DRY RUN)"
            return False, result
    
    # Get current firmware version
    firmware_info = get_device_firmware_version(ip_address, username, password)
    if not firmware_info:
        result['message'] = "Could not determine current firmware version"
        return False, result
    
    result['current_version'] = firmware_info['version']
    
    # Get latest release information if not provided
    if not latest_release_info:
        latest_release_info = fetch_latest_tasmota_release()
        if not latest_release_info:
            result['message'] = "Could not fetch latest release information"
            return False, result
    
    result['latest_version'] = latest_release_info['version']
    
    # Check if update is needed
    needs_update = compare_versions(firmware_info['version'], latest_release_info['version'])
    
    # Skip if already up to date and skip_up_to_date is True
    if not needs_update and skip_up_to_date:
        logger.info(f"{ip_address}: Already running latest version {firmware_info['version']}, skipping")
        result['success'] = True
        result['message'] = f"Already running latest version {firmware_info['version']}"
        return True, result
    
    # Use the update_device_firmware function from the imported module
    update_result = update_device_firmware(ip_address, username, password)
    
    # Update the result with the update_result information
    result.update(update_result)
    
    return update_result['success'], result


def compare_versions(device_version, latest_version):
    """
    Compare device firmware version with latest available version
    
    Args:
        device_version (str): Current device firmware version
        latest_version (str): Latest available firmware version
    
    Returns:
        bool: True if update is needed, False if device is up to date
    """
    logger = logging.getLogger()
    
    # Handle unknown versions
    if device_version == "Unknown" or not latest_version:
        logger.debug("Cannot compare versions: device version unknown or latest version not available")
        return True  # Recommend update if we can't determine versions
    
    # Clean up version strings to extract just the version numbers
    # Tasmota versions typically look like "9.5.0" or "tasmota-9.5.0"
    device_version_clean = re.search(r'(\d+\.\d+\.\d+)', device_version)
    latest_version_clean = re.search(r'(\d+\.\d+\.\d+)', latest_version)
    
    if not device_version_clean or not latest_version_clean:
        logger.debug(f"Cannot parse version numbers: device={device_version}, latest={latest_version}")
        return True  # Recommend update if we can't parse versions
    
    device_version_clean = device_version_clean.group(1)
    latest_version_clean = latest_version_clean.group(1)
    
    # Split versions into components and convert to integers for comparison
    device_parts = [int(part) for part in device_version_clean.split('.')]
    latest_parts = [int(part) for part in latest_version_clean.split('.')]
    
    # Compare version components
    for i in range(min(len(device_parts), len(latest_parts))):
        if device_parts[i] < latest_parts[i]:
            logger.debug(f"Update needed: device version {device_version_clean} is older than latest version {latest_version_clean}")
            return True  # Update needed
        elif device_parts[i] > latest_parts[i]:
            logger.debug(f"No update needed: device version {device_version_clean} is newer than latest version {latest_version_clean}")
            return False  # Device is newer (beta/development version)
    
    # If we get here, the versions are equal up to the common length
    if len(device_parts) < len(latest_parts):
        logger.debug(f"Update needed: device version {device_version_clean} is older than latest version {latest_version_clean}")
        return True  # Device has fewer version components, consider it older
    
    logger.debug(f"No update needed: device version {device_version_clean} is up to date with latest version {latest_version_clean}")
    return False  # Device is up to date

def update_tasmota(device_config, dry_run=False, skip_up_to_date=True, latest_release_info=None):
    """
    Update Tasmota device remotely via HTTP API
    
    Args:
        device_config (dict): Device configuration containing IP and optional credentials
        dry_run (bool): If True, simulate the update process without making changes
        skip_up_to_date (bool): If True, skip devices that are already up to date
        latest_release_info (dict): Information about the latest release, if already fetched
    Returns:
        bool: True if update was successful (or would be in dry run mode), False otherwise
        dict: Additional result information including version details
    """
    logger = logging.getLogger()
    ip_address = device_config['ip']
    username = device_config.get('username')
    password = device_config.get('password')
    
    # Try to get DNS name
    dns_name = get_dns_name(ip_address)
    device_info = ip_address
    if dns_name:
        device_info = f"{ip_address} ({dns_name})"
    
    if dry_run:
        logger.info(f"Processing device: {device_info} (DRY RUN)")
    else:
        logger.info(f"Processing device: {device_info}")
    
    # Get current firmware version from device
    current_version_info = get_device_firmware_version(ip_address, username, password)
    
    # If we couldn't get the current version, log a warning but continue
    if not current_version_info:
        logger.warning(f"{device_info}: Could not determine current firmware version")
        current_version = "Unknown"
    else:
        current_version = current_version_info['version']
        logger.info(f"{device_info}: Current firmware version: {current_version}")
    
    # Get latest release info if not provided
    if not latest_release_info:
        latest_release_info = fetch_latest_tasmota_release()
    
    # If we couldn't get the latest release info, log an error but continue with update
    if not latest_release_info:
        logger.error("Could not fetch latest release information, proceeding with update anyway")
        latest_version = None
    else:
        latest_version = latest_release_info['version']
        logger.info(f"Latest Tasmota release: {latest_version} (released on {latest_release_info['release_date']})")
    
    # Check if update is needed
    if skip_up_to_date and current_version != "Unknown" and latest_version:
        update_needed = compare_versions(current_version, latest_version)
        if not update_needed:
            logger.info(f"{device_info}: Device is already up to date (running version {current_version}), skipping update")
            return True, {
                'status': 'skipped',
                'reason': 'already_up_to_date',
                'current_version': current_version,
                'latest_version': latest_version
            }
    
    # Construct base URL with authentication if provided
    if username and password:
        base_url = f"http://{username}:{password}@{ip_address}/cm"
        logger.debug(f"Using authentication for {device_info}")
    else:
        base_url = f"http://{ip_address}/cm"
        logger.debug(f"No authentication provided for {device_info}")
    
    # Command parameters
    params = {"cmnd": "Upgrade 1"}
    
    if dry_run:
        # In dry run mode, we don't actually send any requests
        if current_version != "Unknown" and latest_version and not compare_versions(current_version, latest_version):
            logger.info(f"{device_info}: Would skip update as device is already running version {current_version} (DRY RUN)")
            return True, {
                'status': 'would_skip',
                'reason': 'already_up_to_date',
                'current_version': current_version,
                'latest_version': latest_version
            }
        else:
            logger.info(f"{device_info}: Would upgrade from version {current_version} to {latest_version or 'latest'} (DRY RUN)")
            logger.debug(f"{device_info}: Would send request to {base_url.replace(password or '', '****')} with params {params}")
            logger.info(f"{device_info}: Would wait for device to restart and come back online (DRY RUN)")
        
        # Check if the device is reachable at all
        try:
            check_url = f"http://{ip_address}"
            if username and password:
                check_url = f"http://{username}:{password}@{ip_address}"
            
            logger.debug(f"{device_info}: Checking if device is reachable (DRY RUN connectivity test)")
            status_response = requests.get(check_url, timeout=5)
            
            logger.info(f"{device_info}: Device is reachable, status code: {status_response.status_code} (DRY RUN)")
            return True, {
                'status': 'would_update',
                'current_version': current_version,
                'latest_version': latest_version
            }
        except requests.exceptions.RequestException as e:
            logger.warning(f"{device_info}: Device is not reachable: {e} (DRY RUN)")
            return False, {
                'status': 'error',
                'reason': 'not_reachable',
                'current_version': current_version,
                'latest_version': latest_version
            }
    else:
        # Normal mode - actually perform the update
        try:
            # Direct upgrade to latest release
            logger.info(f"{device_info}: Upgrading from version {current_version} to {latest_version or 'latest'}")
            logger.debug(f"{device_info}: Sending request to {base_url.replace(password or '', '****')} with params {params}")
            
            response = requests.get(base_url, params=params, timeout=5)
            
            logger.info(f"{device_info}: Initiating update, status code: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"{device_info}: Update command sent successfully")
                logger.info(f"{device_info}: Device will restart automatically after update")
                logger.info(f"{device_info}: Waiting for device to come back online...")
                
                # Wait for device to update and restart
                time.sleep(90)  # Increased wait time for safety
                
                # Try to check if device is back online
                try:
                    check_url = f"http://{ip_address}"
                    if username and password:
                        check_url = f"http://{username}:{password}@{ip_address}"
                    
                    logger.debug(f"{device_info}: Checking if device is back online")
                    status_response = requests.get(check_url, timeout=5)
                    
                    if status_response.status_code == 200:
                        logger.info(f"{device_info}: Device is back online!")
                        
                        # Try to get the new firmware version
                        new_version_info = get_device_firmware_version(ip_address, username, password)
                        new_version = new_version_info['version'] if new_version_info else "Unknown"
                        
                        if new_version != "Unknown" and new_version != current_version:
                            logger.info(f"{device_info}: Successfully updated from {current_version} to {new_version}")
                        else:
                            logger.info(f"{device_info}: Device is back online, new version: {new_version}")
                            
                        return True, {
                            'status': 'updated',
                            'previous_version': current_version,
                            'new_version': new_version
                        }
                    else:
                        logger.warning(f"{device_info}: Device responded with status code {status_response.status_code}")
                        return False, {
                            'status': 'error',
                            'reason': f"device_responded_with_status_{status_response.status_code}"
                        }
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"{device_info}: Could not verify if device is back online: {e}")
                    return False, {
                        'status': 'error',
                        'reason': 'verification_failed',
                        'error': str(e)
                    }
                    
            else:
                logger.error(f"{device_info}: Failed to initiate update. Status code: {response.status_code}")
                return False, {
                    'status': 'error',
                    'reason': f"failed_to_initiate_update_status_{response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"{device_info}: Error connecting to device: {e}")
            return False, {
                'status': 'error',
                'reason': 'connection_error',
                'error': str(e)
            }

def update_devices_from_file(filename, dry_run=False, check_only=False, skip_up_to_date=True):
    """
    Update multiple Tasmota devices from a YAML file
    
    Args:
        filename (str): Path to YAML file containing device configurations
        dry_run (bool): If True, simulate the update process without making changes
        check_only (bool): If True, only check firmware versions without updating
        skip_up_to_date (bool): If True, skip devices that are already up to date
    
    Returns:
        dict: Summary of results including counts of devices in different states
    """
    logger = logging.getLogger()
    
    try:
        logger.debug(f"Opening configuration file: {filename}")
        with open(filename, 'r') as f:
            config = yaml.safe_load(f)
            
        if not config or 'devices' not in config or not config['devices']:
            logger.warning("No devices found in the configuration file")
            return {"total": 0, "successful": 0, "failed": 0, "results": {}}
        
        devices = config['devices']
        
        # Fetch latest release info once to avoid multiple API calls
        latest_release_info = fetch_latest_tasmota_release()
        if not latest_release_info:
            logger.error("Failed to fetch latest release information")
            if check_only:
                logger.error("Cannot perform version check without latest release information")
                return {"total": 0, "successful": 0, "failed": 0, "results": {}}
            logger.warning("Proceeding with updates without version comparison")
        else:
            latest_version = latest_release_info['version']
            release_date = latest_release_info['release_date']
            logger.info(f"Latest Tasmota release: {latest_version} (released on {release_date})")
            if latest_release_info.get('release_notes'):
                logger.debug("Release notes:")
                for line in latest_release_info['release_notes'].split('\n')[:10]:  # Show first 10 lines
                    if line.strip():
                        logger.debug(f"  {line.strip()}")
        
        if check_only:
            logger.info(f"Found {len(devices)} devices to check for updates")
        elif dry_run:
            logger.info(f"Found {len(devices)} devices that would be updated (DRY RUN)")
        else:
            logger.info(f"Found {len(devices)} devices to update")
        
        results = {}
        device_dns_map = {}
        device_versions = {}
        update_status = {
            'up_to_date': 0,
            'needs_update': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'unreachable': 0
        }
        
        for device in devices:
            ip = device['ip']
            
            # Try to get DNS name
            dns_name = get_dns_name(ip)
            device_info = ip
            if dns_name:
                device_info = f"{ip} ({dns_name})"
                device_dns_map[ip] = dns_name
            
            if check_only:
                logger.info(f"\nChecking device at {device_info}")
                # Only get version info without updating
                current_version_info = get_device_firmware_version(ip, device.get('username'), device.get('password'))
                
                if not current_version_info:
                    logger.warning(f"{device_info}: Could not determine current firmware version")
                    results[ip] = (False, {'status': 'error', 'reason': 'version_check_failed'})
                    update_status['unreachable'] += 1
                    continue
                
                current_version = current_version_info['version']
                device_versions[ip] = current_version
                logger.info(f"{device_info}: Current firmware version: {current_version}")
                
                if latest_release_info:
                    update_needed = compare_versions(current_version, latest_release_info['version'])
                    if update_needed:
                        sanitized_version_info = sanitize_data(current_version_info)
                        logger.info(f"{device_info}: Update available: Firmware version update from {sanitized_version_info['version']} to {latest_release_info['version']}")
                        results[ip] = (True, {
                            'status': 'needs_update',
                            'current_version': current_version,
                            'latest_version': latest_release_info['version']
                        })
                        update_status['needs_update'] += 1
                    else:
                        logger.info(f"{device_info}: Up to date (running version {current_version})")
                        results[ip] = (True, {
                            'status': 'up_to_date',
                            'current_version': current_version,
                            'latest_version': latest_release_info['version']
                        })
                        update_status['up_to_date'] += 1
            else:
                # Perform update or dry run
                if dry_run:
                    logger.info(f"\nWould process device at {device_info} (DRY RUN)")
                else:
                    logger.info(f"\nProcessing device at {device_info}")
                
                success, result_info = update_tasmota(
                    device, 
                    dry_run=dry_run, 
                    skip_up_to_date=skip_up_to_date, 
                    latest_release_info=latest_release_info
                )
                
                results[ip] = (success, result_info)
                
                # Update status counters
                if success:
                    if result_info.get('status') == 'skipped' or result_info.get('status') == 'would_skip':
                        update_status['up_to_date'] += 1
                        update_status['skipped'] += 1
                    elif result_info.get('status') == 'updated':
                        update_status['updated'] += 1
                    elif result_info.get('status') == 'would_update':
                        update_status['needs_update'] += 1
                else:
                    if result_info.get('reason') == 'not_reachable':
                        update_status['unreachable'] += 1
                    update_status['failed'] += 1
                
                # Store version info
                if 'current_version' in result_info:
                    device_versions[ip] = result_info['current_version']
        
        # Log summary
        if check_only:
            logger.info("\nFirmware Check Summary:")
            logger.info("-" * 40)
            logger.info(f"Devices checked: {len(results)}")
            logger.info(f"Up to date: {update_status['up_to_date']}")
            logger.info(f"Updates available: {update_status['needs_update']}")
            logger.info(f"Unreachable devices: {update_status['unreachable']}")
            
            if update_status['needs_update'] > 0:
                logger.info("\nDevices that need updates:")
                for ip, (success, info) in results.items():
                    if success and info.get('status') == 'needs_update':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        current = info.get('current_version', 'Unknown')
                        latest = info.get('latest_version', 'Unknown')
                        logger.info(f"- {device_info}: {current} -> {latest}")
            
            if update_status['unreachable'] > 0:
                logger.warning("\nUnreachable devices:")
                for ip, (success, info) in results.items():
                    if not success:
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        logger.warning(f"- {device_info}")
                        
        elif dry_run:
            logger.info("\nDRY RUN Summary:")
            logger.info("-" * 40)
            logger.info(f"Devices checked: {len(results)}")
            logger.info(f"Would skip (up to date): {update_status['skipped']}")
            logger.info(f"Would update: {update_status['needs_update']}")
            logger.info(f"Unreachable devices: {update_status['unreachable']}")
            
            if update_status['needs_update'] > 0:
                logger.info("\nDevices that would be updated:")
                for ip, (success, info) in results.items():
                    if success and info.get('status') == 'would_update':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        current = info.get('current_version', 'Unknown')
                        latest = info.get('latest_version', 'Unknown')
                        logger.info(f"- {device_info}: {current} -> {latest}")
            
            if update_status['skipped'] > 0:
                logger.info("\nDevices that would be skipped (already up to date):")
                for ip, (success, info) in results.items():
                    if success and info.get('status') == 'would_skip':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        version = info.get('current_version', 'Unknown')
                        logger.info(f"- {device_info}: {version}")
            
            if update_status['unreachable'] > 0:
                logger.warning("\nUnreachable devices:")
                for ip, (success, info) in results.items():
                    if not success and info.get('reason') == 'not_reachable':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        logger.warning(f"- {device_info} (not reachable in dry run test)")
        else:
            logger.info("\nUpdate Summary:")
            logger.info("-" * 40)
            logger.info(f"Devices processed: {len(results)}")
            logger.info(f"Skipped (up to date): {update_status['skipped']}")
            logger.info(f"Successfully updated: {update_status['updated']}")
            logger.info(f"Failed updates: {update_status['failed']}")
            
            if update_status['updated'] > 0:
                logger.info("\nSuccessfully updated devices:")
                for ip, (success, info) in results.items():
                    if success and info.get('status') == 'updated':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        prev_version = info.get('previous_version', 'Unknown')
                        new_version = info.get('new_version', 'Unknown')
                        logger.info(f"- {device_info}: {prev_version} -> {new_version}")
            
            if update_status['skipped'] > 0:
                logger.info("\nSkipped devices (already up to date):")
                for ip, (success, info) in results.items():
                    if success and info.get('status') == 'skipped':
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        version = info.get('current_version', 'Unknown')
                        logger.info(f"- {device_info}: {version}")
            
            if update_status['failed'] > 0:
                logger.warning("\nFailed updates:")
                for ip, (success, info) in results.items():
                    if not success:
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        reason = info.get('reason', 'unknown_error')
                        logger.warning(f"- {device_info}: {reason}")
        
        # Return results for potential further processing
        return {
            "total": len(results),
            "successful": update_status['updated'] + update_status['skipped'] if not check_only else update_status['up_to_date'] + update_status['needs_update'],
            "failed": update_status['failed'],
            "up_to_date": update_status['up_to_date'],
            "needs_update": update_status['needs_update'],
            "updated": update_status['updated'],
            "skipped": update_status['skipped'],
            "unreachable": update_status['unreachable'],
            "results": results
        }
                    
    except FileNotFoundError:
        logger.error(f"Error: File '{filename}' not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        logger.debug("Exception details:", exc_info=True)
        sys.exit(1)

def create_devices_file_interactively(devices_file):
    """
    Create devices file by interactively asking the user for device information
    
    Args:
        devices_file (str): Path to devices file
    """
    logger = logging.getLogger()
    
    # For interactive prompts, we'll still use print for better user experience
    # but log the actions as well
    logger.info("Starting interactive device configuration wizard")
    
    print("\n=== Tasmota Device Configuration Wizard ===\n")
    print("This wizard will help you create a configuration file for your Tasmota devices.")
    print("You'll be prompted to enter information for each device.")
    print("When you're finished adding devices, just press Enter without typing an IP address.\n")
    
    devices = []
    device_count = 0
    
    while True:
        device_count += 1
        print(f"\n--- Device #{device_count} ---")
        
        # Get IP address
        while True:
            ip = input("Enter device IP address (or press Enter to finish): ").strip()
            if not ip:
                if device_count == 1:  # No devices added yet
                    print("You need to add at least one device.")
                    logger.debug("User tried to finish without adding any devices")
                    continue
                else:
                    logger.debug("User finished adding devices")
                    break  # Exit the loop if user is done adding devices
            
            # Validate IP format
            ip_parts = ip.split('.')
            if len(ip_parts) != 4 or not all(part.isdigit() and 0 <= int(part) <= 255 for part in ip_parts):
                print("Invalid IP address format. Please use format: xxx.xxx.xxx.xxx")
                logger.debug(f"User entered invalid IP format: {ip}")
                continue
            
            logger.debug(f"Valid IP entered: {ip}")
            break  # Valid IP, exit the validation loop
        
        if not ip:  # User is done adding devices
            break
        
        # Get authentication info
        print("\nAuthentication (leave empty if not required):")
        username = input("Username (default: empty): ").strip()
        password = input("Password (default: empty): ").strip()
        
        # Create device entry
        device = {"ip": ip}
        if username:
            device["username"] = username
            logger.debug(f"Username provided for device {ip}")
        if password:
            device["password"] = password
            logger.debug(f"Password provided for device {ip}")
        
        devices.append(device)
        logger.info(f"Device added: {ip}")
        print(f"Device #{device_count} added successfully!")
    
    # Write to YAML file
    try:
        logger.debug(f"Writing configuration to {devices_file}")
        with open(devices_file, 'w') as f:
            yaml.dump({"devices": devices}, f, default_flow_style=False)
        
        logger.info(f"Configuration saved to {devices_file} with {len(devices)} device(s)")
        print(f"\nConfiguration saved to {devices_file}")
        print(f"Found {len(devices)} device(s) in the configuration")
        
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        print(f"Error saving configuration: {e}")
        sys.exit(1)

def create_example_devices_file(devices_file):
    """
    Create an example devices file with placeholder values
    
    Args:
        devices_file (str): Path to devices file
    """
    logger = logging.getLogger()
    
    example_config = {
        "devices": [
            {
                "ip": "192.168.1.100",
                "username": "admin",  # Optional
                "password": "password"  # Optional
            },
            {
                "ip": "192.168.1.101"
            }
        ]
    }
    
    try:
        logger.debug(f"Creating example configuration file: {devices_file}")
        with open(devices_file, 'w') as f:
            yaml.dump(example_config, f, default_flow_style=False)
        
        logger.info(f"Created example configuration file: {devices_file}")
        print(f"Created example configuration file: {devices_file}")
        print("Please edit this file with your actual device information.")
        print("Then run the script again to update your devices.")
    except Exception as e:
        logger.error(f"Error creating example file: {e}")
        print(f"Error creating example file: {e}")
        sys.exit(1)

def ensure_devices_file_exists(devices_file, interactive=True):
    """
    Check if devices file exists, if not create it interactively or from example
    
    Args:
        devices_file (str): Path to devices file
        interactive (bool): Whether to create the file interactively
    """
    logger = logging.getLogger()
    
    if not Path(devices_file).exists():
        logger.warning(f"Device configuration file '{devices_file}' not found")
        print(f"Device configuration file '{devices_file}' not found.")
        
        if interactive:
            logger.info("Starting interactive configuration mode")
            try:
                create_devices_file_interactively(devices_file)
            except (EOFError, KeyboardInterrupt):
                logger.warning("Interactive input not available or canceled")
                print("\nInteractive input not available or canceled.")
                print("Creating example configuration file instead.")
                create_example_devices_file(devices_file)
                sys.exit(0)
        else:
            logger.info("Using non-interactive mode, creating example configuration")
            create_example_devices_file(devices_file)
            sys.exit(0)
    else:
        logger.info(f"Using existing configuration file: {devices_file}")

def setup_logging(log_file=None, log_level=logging.INFO):
    """
    Set up logging configuration
    
    Args:
        log_file (str): Path to log file, if None logs to console only
        log_level (int): Logging level
        
    Returns:
        logger: Configured logger
    """
    # Create logs directory if it doesn't exist
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear any existing handlers
    for handler in logger.handlers[:]:  
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if log_file is provided)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Tasmota devices over your network")
    parser.add_argument(
        "-f", "--file", 
        default="devices.yaml", 
        help="Path to devices configuration file (default: devices.yaml)"
    )
    parser.add_argument(
        "--example", 
        action="store_true", 
        help="Create an example configuration file and exit"
    )
    parser.add_argument(
        "--non-interactive", 
        action="store_true", 
        help="Don't use interactive prompts, create example file if needed"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the update process without making any changes"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check firmware versions without updating any devices"
    )
    parser.add_argument(
        "--update-all",
        action="store_true",
        help="Update all devices even if they are already running the latest version"
    )
    parser.add_argument(
        "--log-file", 
        default="logs/tasmota_updater.log", 
        help="Path to log file (default: logs/tasmota_updater.log)"
    )
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO", 
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = getattr(logging, args.log_level)
    logger = setup_logging(args.log_file, log_level)
    
    # Determine the operation mode
    if args.check_only:
        logger.info("Starting Tasmota Updater in CHECK ONLY mode (only checking firmware versions)")
    elif args.dry_run:
        logger.info("Starting Tasmota Updater in DRY RUN mode (no changes will be made)")
    else:
        logger.info("Starting Tasmota Updater")
    
    # If example flag is set, create example file and exit
    if args.example:
        logger.info("Creating example configuration file")
        create_example_devices_file(args.file)
        sys.exit(0)
    
    # Check if devices file exists, create it if needed
    ensure_devices_file_exists(args.file, not args.non_interactive)
    
    # Update devices
    logger.info(f"Using configuration file: {args.file}")
    
    # Determine whether to skip up-to-date devices
    skip_up_to_date = not args.update_all
    if not skip_up_to_date and not args.check_only:
        logger.info("Will attempt to update all devices, even those already on the latest version")
    
    # Process devices
    result = update_devices_from_file(
        args.file, 
        dry_run=args.dry_run, 
        check_only=args.check_only,
        skip_up_to_date=skip_up_to_date
    )
    
    # Final status message
    if args.check_only:
        logger.info(f"Tasmota Updater finished checking {result['total']} devices: "
                   f"{result['up_to_date']} up to date, {result['needs_update']} need updates, "
                   f"{result['unreachable']} unreachable")
    elif args.dry_run:
        logger.info("Tasmota Updater finished (DRY RUN mode - no changes were made)")
    else:
        logger.info(f"Tasmota Updater finished: {result['updated']} updated, {result['skipped']} skipped, "
                   f"{result['failed']} failed")
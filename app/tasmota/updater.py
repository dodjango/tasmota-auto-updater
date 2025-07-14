"""Tasmota device updater module

Refactored from tasmota_updater.py to be used as a module in the web application.
"""

import requests
import time
import sys
import yaml
import logging
import os
import socket
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from app.tasmota.utils import is_fake_device

# Setup module logger
logger = logging.getLogger(__name__)


def get_dns_name(ip_address, device=None):
    """
    Try to get the DNS name for an IP address
    
    Args:
        ip_address (str): IP address to lookup
        device (dict, optional): Device configuration dictionary
    Returns:
        str: DNS name if found, otherwise None
    """
    # If this is a fake device with a pre-configured DNS name, use that
    if device and is_fake_device(device) and 'dns_name' in device:
        return device['dns_name']
    
    # For real devices, try to resolve the DNS name
    try:
        dns_name = socket.getfqdn(ip_address)
        if dns_name != ip_address:
            return dns_name
    except Exception:
        pass
    return None


def get_device_firmware_version(ip_address, username=None, password=None, device=None):
    """
    Get the current firmware version from a Tasmota device
    
    Args:
        ip_address (str): IP address of the device
        username (str, optional): Username for authentication
        password (str, optional): Password for authentication
        device (dict, optional): Complete device configuration dictionary
    
    Returns:
        dict: Dictionary containing version information or None if failed
              Keys: 'version', 'core_version', 'sdk_version', 'is_minimal'
    """
    
    # Check if this is a fake device with pre-configured firmware info
    if device and is_fake_device(device):
        if 'firmware_info' in device:
            logger.debug(f"{ip_address}: Using pre-configured firmware info for fake device")
            return device['firmware_info']
        else:
            logger.warning(f"{ip_address}: Fake device has no firmware_info configured")
            # Return a default fake version
            return {
                'version': '12.0.0',
                'core_version': '2.7.4.9',
                'sdk_version': '3.0.2',
                'is_minimal': False
            }
    
    # For real devices, proceed with the API call
    # Construct base URL with authentication if provided
    if username and password:
        base_url = f"http://{username}:{password}@{ip_address}/cm"
    else:
        base_url = f"http://{ip_address}/cm"
    
    # Command parameters to get status
    params = {"cmnd": "Status 2"}
    
    try:
        logger.debug(f"{ip_address}: Requesting firmware version information")
        response = requests.get(base_url, params=params, timeout=5)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'StatusFWR' in data:
                    fw_data = data['StatusFWR']
                    version = fw_data.get('Version', 'Unknown')
                    
                    # Extract core and SDK versions if available
                    core_version = fw_data.get('Core', 'Unknown')
                    sdk_version = fw_data.get('SDK', 'Unknown')
                    
                    # Check if it's a minimal version (tasmota-minimal)
                    is_minimal = 'minimal' in version.lower() if version != 'Unknown' else False
                    
                    logger.debug(f"{ip_address}: Firmware version: {version}, Core: {core_version}, SDK: {sdk_version}")
                    
                    return {
                        'version': version,
                        'core_version': core_version,
                        'sdk_version': sdk_version,
                        'is_minimal': is_minimal
                    }
                else:
                    logger.warning(f"{ip_address}: StatusFWR not found in device response")
            except ValueError:
                logger.warning(f"{ip_address}: Invalid JSON response from device")
        else:
            logger.warning(f"{ip_address}: Failed to get firmware version. Status code: {response.status_code}")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"{ip_address}: Error connecting to device: {e}")
    
    return None


def compare_versions(device_version, latest_version):
    """
    Compare device firmware version with latest available version
    
    Args:
        device_version (str): Current device firmware version
        latest_version (str): Latest available firmware version
    
    Returns:
        bool: True if update is needed, False if device is up to date
    """
    # If we couldn't determine the device version, assume update is needed
    if device_version == "Unknown":
        logger.warning("Device version is unknown, assuming update is needed")
        return True
        
    # Clean up version strings
    device_version = device_version.strip()
    latest_version = latest_version.strip()
    
    # Extract version numbers using regex
    # Tasmota versions follow pattern like 8.5.1, 9.1.0, etc.
    device_match = re.search(r'(\d+)\.(\d+)\.(\d+)', device_version)
    latest_match = re.search(r'(\d+)\.(\d+)\.(\d+)', latest_version)
    
    if not device_match or not latest_match:
        logger.warning(f"Could not parse version numbers: Device: {device_version}, Latest: {latest_version}")
        # If we can't parse versions, assume update is needed
        return True
    
    # Extract major, minor, and patch numbers
    device_major, device_minor, device_patch = map(int, device_match.groups())
    latest_major, latest_minor, latest_patch = map(int, latest_match.groups())
    
    # Compare versions
    if latest_major > device_major:
        return True
    elif latest_major == device_major and latest_minor > device_minor:
        return True
    elif latest_major == device_major and latest_minor == device_minor and latest_patch > device_patch:
        return True
    
    # Device is up to date
    return False


def get_cached_data(cache_name: str, max_age_days: int = 1) -> tuple[dict, bool]:
    """
    Get data from cache if it exists and is not expired
    
    Args:
        cache_name: Name of the cache file (without extension)
        max_age_days: Maximum age of cache in days before it's considered expired
        
    Returns:
        tuple: (cached_data, is_valid)
            - cached_data: The cached data or None if not available
            - is_valid: True if cache is valid and not expired, False otherwise
    """
    # Cache file path
    cache_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "cache"
    cache_file = cache_dir / f"{cache_name}.json"
    
    # Create cache directory if it doesn't exist
    if not cache_dir.exists():
        cache_dir.mkdir(exist_ok=True)
    
    # Check if cache exists and is valid
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                
            # Check if cache is still valid
            cache_timestamp = datetime.fromisoformat(cache_data['cache_timestamp'])
            if datetime.now() - cache_timestamp < timedelta(days=max_age_days):
                logger.debug(f"Using cached data for {cache_name} (cached at {cache_timestamp})")
                return cache_data['data'], True
            else:
                logger.debug(f"Cache expired for {cache_name}, fetching fresh data")
        except Exception as e:
            logger.warning(f"Error reading cache file {cache_name}: {e}")
    
    return None, False


def save_to_cache(cache_name: str, data: dict) -> bool:
    """
    Save data to cache file
    
    Args:
        cache_name: Name of the cache file (without extension)
        data: Data to cache
        
    Returns:
        bool: True if successfully saved to cache, False otherwise
    """
    # Cache file path
    cache_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "cache"
    cache_file = cache_dir / f"{cache_name}.json"
    
    # Create cache directory if it doesn't exist
    if not cache_dir.exists():
        cache_dir.mkdir(exist_ok=True)
    
    try:
        cache_data = {
            'cache_timestamp': datetime.now().isoformat(),
            'data': data
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        logger.debug(f"Saved data to cache: {cache_name}")
        return True
    except Exception as e:
        logger.warning(f"Failed to write cache file {cache_name}: {e}")
        return False


def fetch_latest_tasmota_release():
    """
    Fetch information about the latest official Tasmota release from GitHub
    Results are cached for one day to prevent GitHub API rate limit issues
    
    Returns:
        dict: Dictionary containing release information or None if failed
              Keys: 'version', 'release_date', 'release_notes', 'download_url'
    """
    # Hard-coded URL for release notes
    RELEASE_NOTES_URL = "https://github.com/arendst/Tasmota/releases/"
    
    # Try to get data from cache
    cached_data, is_valid = get_cached_data('latest_release')
    if is_valid and cached_data:
        return cached_data
    
    # Cache doesn't exist, is invalid, or couldn't be read - fetch fresh data
    try:
        # GitHub API URL for Tasmota releases
        url = "https://api.github.com/repos/arendst/Tasmota/releases/latest"
        
        logger.debug("Fetching latest Tasmota release information from GitHub")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            release_data = response.json()
            
            # Extract version from tag name (remove 'v' prefix if present)
            version = release_data['tag_name']
            if version.startswith('v'):
                version = version[1:]
            
            # Extract release date and format it
            release_date_str = release_data['published_at'].split('T')[0]
            
            # Extract download URL for the main firmware binary
            download_url = None
            for asset in release_data['assets']:
                if asset['name'].lower() == 'tasmota.bin':
                    download_url = asset['browser_download_url']
                    break
            
            # If we couldn't find tasmota.bin, use the first .bin file
            if not download_url:
                for asset in release_data['assets']:
                    if asset['name'].lower().endswith('.bin'):
                        download_url = asset['browser_download_url']
                        break
            
            logger.info(f"Latest Tasmota release: {version}, published on {release_date_str}")
            
            release_info = {
                'version': version,
                'release_date': release_date_str,
                'release_notes': release_data['body'],
                'download_url': download_url,
                'release_url': RELEASE_NOTES_URL  # Use the hard-coded URL instead of the dynamic one
            }
            
            # Save to cache
            save_to_cache('latest_release', release_info)
            
            return release_info
        else:
            logger.error(f"Failed to fetch latest release. Status code: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error fetching latest release: {e}")
    
    return None


def update_device_firmware(device_ip, username=None, password=None, check_only=False, device=None):
    """
    Update firmware on a single Tasmota device
    
    Args:
        device_ip (str): IP address of the device
        username (str, optional): Username for authentication
        password (str, optional): Password for authentication
        check_only (bool): If True, only check firmware version without updating
    
    Returns:
        dict: Result information including success status and version details
    """
    result = {
        "ip": device_ip,
        "success": False,
        "message": "",
        "current_version": "Unknown",
        "latest_version": "Unknown",
        "needs_update": False,
        "dns_name": get_dns_name(device_ip, device)
    }
    
    # Get current firmware version
    firmware_info = get_device_firmware_version(device_ip, username, password, device)
    if not firmware_info:
        result["message"] = "Failed to get current firmware version"
        return result
    
    result["current_version"] = firmware_info["version"]
    
    # Get latest release information
    latest_release = fetch_latest_tasmota_release()
    if not latest_release:
        result["message"] = "Failed to get latest release information"
        return result
    
    result["latest_version"] = latest_release["version"]
    
    # Check if update is needed
    needs_update = compare_versions(firmware_info["version"], latest_release["version"])
    result["needs_update"] = needs_update
    
    if not needs_update:
        result["message"] = "Device is already running the latest version"
        result["success"] = True
        return result
    
    # If only checking version or this is a fake device, return the result without updating
    if check_only or (device and is_fake_device(device)):
        if device and is_fake_device(device):
            result["message"] = "Fake device would need an update, but no actual update will be performed"
            logger.info(f"{device_ip}: {result['message']}")
        else:
            result["message"] = "Update available"
        
        result["success"] = True
        return result
    
    # Construct base URL with authentication if provided
    if username and password:
        base_url = f"http://{username}:{password}@{device_ip}/cm"
    else:
        base_url = f"http://{device_ip}/cm"
    
    try:
        # Send upgrade command
        logger.info(f"{device_ip}: Upgrading to latest official release")
        params = {"cmnd": "Upgrade 1"}
        response = requests.get(base_url, params=params, timeout=5)
        
        if response.status_code != 200:
            result["message"] = f"Failed to send upgrade command. Status code: {response.status_code}"
            return result
        
        # Wait for device to restart (typically takes 10-30 seconds)
        logger.info(f"{device_ip}: Waiting for device to restart and come back online")
        time.sleep(5)  # Initial wait to allow device to start update
        
        # Check if device comes back online
        max_wait = 60  # Maximum wait time in seconds
        wait_interval = 5  # Check interval in seconds
        for _ in range(max_wait // wait_interval):
            try:
                check_response = requests.get(f"http://{device_ip}", timeout=2)
                if check_response.status_code == 200:
                    # Device is back online
                    result["success"] = True
                    result["message"] = "Update successful"
                    
                    # Get new firmware version
                    new_firmware_info = get_device_firmware_version(device_ip, username, password)
                    if new_firmware_info:
                        result["current_version"] = new_firmware_info["version"]
                    
                    return result
            except requests.exceptions.RequestException:
                # Device still not reachable, continue waiting
                pass
            
            time.sleep(wait_interval)
        
        # If we get here, device did not come back online in time
        result["message"] = "Update initiated but device did not come back online within timeout period"
        
    except requests.exceptions.RequestException as e:
        result["message"] = f"Error connecting to device: {e}"
    
    return result

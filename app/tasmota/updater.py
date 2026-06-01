"""Tasmota device updater module

Refactored from tasmota_updater.py to be used as a module in the web application.

Security Notes:
- All sensitive data (passwords, credentials) is sanitized before logging
- Error messages are sanitized to prevent information disclosure
- Authentication credentials are not logged
- Follows OWASP A09:2021 - Security Logging and Monitoring Failures guidelines
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
import ipaddress
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from app.tasmota.utils import is_fake_device
from urllib.parse import urlparse

# Setup module logger
logger = logging.getLogger(__name__)


class TimeoutPhase(Enum):
    """Enumeration for different timeout phases during firmware update"""
    INITIAL_WAIT = "initial_wait"
    RESTART_VERIFICATION = "restart_verification"
    FIRMWARE_DOWNLOAD = "firmware_download"
    FIRMWARE_FLASH = "firmware_flash"
    DEVICE_REBOOT = "device_reboot"


@dataclass
class TimeoutConfig:
    """Configuration for different timeout phases"""
    total_timeout: int = 240  # Total timeout in seconds (default 4 minutes)
    initial_wait: int = 10    # Initial wait before checking device status
    min_check_interval: float = 1.0  # Minimum check interval
    max_check_interval: float = 30.0  # Maximum check interval
    backoff_multiplier: float = 1.5   # Exponential backoff multiplier
    request_timeout: int = 5          # Individual request timeout

    def __post_init__(self):
        """Validate timeout configuration"""
        if self.total_timeout < 30:
            raise ValueError("Total timeout must be at least 30 seconds")
        if self.total_timeout > 600:
            raise ValueError("Total timeout cannot exceed 600 seconds (10 minutes)")
        if self.initial_wait >= self.total_timeout:
            raise ValueError("Initial wait must be less than total timeout")
        if self.min_check_interval >= self.max_check_interval:
            raise ValueError("Min check interval must be less than max check interval")


@dataclass
class TimeoutReport:
    """Detailed timeout information for API responses"""
    total_timeout: int
    elapsed_time: float
    phase: TimeoutPhase
    attempts: int
    last_check_interval: float
    timed_out: bool
    error_type: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'total_timeout': self.total_timeout,
            'elapsed_time': round(self.elapsed_time, 2),
            'phase': self.phase.value,
            'attempts': self.attempts,
            'last_check_interval': round(self.last_check_interval, 2),
            'timed_out': self.timed_out,
            'error_type': self.error_type,
            'details': self.details
        }


def sanitize_log_data(data):
    """
    Sanitize sensitive data before logging
    
    Args:
        data (str): Data to sanitize
        
    Returns:
        str: Sanitized data safe for logging
    """
    if data is None:
        return None
        
    # Convert to string if not already
    if not isinstance(data, str):
        data = str(data)
    
    # Mask passwords in URLs (http://user:pass@host)
    data = re.sub(r'(http[s]?://[^:]+:)([^@]+)(@)', r'\1********\3', data)
    
    # Mask passwords in explicit password parameters
    data = re.sub(r'(["\']password["\']\s*:\s*["\'])([^"\']*)(["\'])', r'\1********\3', data)
    
    # Mask any JSON password fields
    data = re.sub(r'("password"\s*:\s*")([^"]*)(")' , r'\1********\3', data)
    
    return data


def is_valid_ip_address(ip_address):
    """
    Validate if the given string is a valid IP address and not in a reserved range
    
    Args:
        ip_address (str): IP address to validate
        
    Returns:
        bool: True if valid and not in reserved range, False otherwise
    """
    try:
        # Try to create an IPv4Address object
        ip = ipaddress.ip_address(ip_address)
        
        # Check if the IP is in a reserved range
        if ip.is_loopback or ip.is_multicast or ip.is_reserved or ip.is_link_local:
            logger.warning(f"IP address {ip_address} is in a reserved range")
            return False
            
        # Check if the IP is private (RFC 1918)
        if not ip.is_private:
            logger.warning(f"IP address {ip_address} is NOT in a private range")
            # You might want to allow private IPs in some cases, depending on your use case
            # For this application, we'll allow private IPs since Tasmota devices are typically on local networks
            return True
            
        return True
    except ValueError:
        # Not a valid IP address
        logger.warning(f"{ip_address} is not a valid IP address")
        return False


def build_device_url(device_config, path="/cm"):
    """
    Safely build a URL for a Tasmota device with proper validation
    
    Args:
        device_config (dict or str): Device configuration dictionary containing:
            - ip (str): IP address of the device
            - username (str, optional): Username for authentication
            - password (str, optional): Password for authentication
            OR a string containing just the IP address
        path (str, optional): URL path
        
    Returns:
        str: Properly formatted URL or None if invalid
    """
    
    # Handle the case where device_config is just an IP address string (for backward compatibility)
    if isinstance(device_config, str):
        ip_address = device_config
        username = None
        password = None
    elif isinstance(device_config, dict) and 'ip' in device_config:
        ip_address = device_config['ip']
        username = device_config.get('username')
        password = device_config.get('password')
    else:
        logger.error("Invalid device configuration: missing IP address")
        return None
    # Validate the IP address
    if not is_valid_ip_address(ip_address):
        logger.error(f"Invalid IP address: {ip_address}")
        return None
        
    # Ensure path starts with a slash
    if not path.startswith('/'):
        path = '/' + path
        
    # Build the URL
    if username and password:
        # For security, don't log the actual URL with credentials
        logger.debug(f"Building URL for {ip_address} with authentication")
        return f"http://{username}:{password}@{ip_address}{path}"
    else:
        return f"http://{ip_address}{path}"


def get_dns_name(device_config):
    """
    Try to get the DNS name for an IP address
    
    Args:
        device_config (dict or str): Device configuration dictionary containing:
            - ip (str): IP address of the device
            - dns_name (str, optional): Pre-configured DNS name for fake devices
            OR a string containing just the IP address
    Returns:
        str: DNS name if found, otherwise None
    """
    
    # Handle the case where device_config is just an IP address string (for backward compatibility)
    if isinstance(device_config, str):
        ip_address = device_config
        is_fake = False
        dns_name = None
    elif isinstance(device_config, dict) and 'ip' in device_config:
        ip_address = device_config['ip']
        is_fake = is_fake_device(device_config)
        dns_name = device_config.get('dns_name')
    else:
        logger.error("Invalid device configuration: missing IP address")
        return None
    # If this is a fake device with a pre-configured DNS name, use that
    if is_fake and dns_name:
        return dns_name
    
    # For real devices, try to resolve the DNS name
    try:
        dns_name = socket.getfqdn(ip_address)
        if dns_name != ip_address:
            return dns_name
    except Exception:
        pass
    return None


def get_device_firmware_version(device_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get the current firmware version from a Tasmota device

    Args:
        device_config: Device configuration dictionary containing:
            - ip (str): IP address of the device (required)
            - username (str, optional): Username for authentication
            - password (str, optional): Password for authentication
            - firmware_info (dict, optional): Pre-configured firmware info for fake devices
            - timeout (int, optional): Request timeout in seconds (default: 60)

    Returns:
        Dictionary containing version information or None if failed
        Keys: 'version', 'core_version', 'sdk_version', 'is_minimal'
    """
    
    # Validate required fields in device_config
    if not device_config or not isinstance(device_config, dict) or 'ip' not in device_config:
        logger.error("Invalid device configuration: missing IP address")
        return None
    
    # Extract device information
    ip_address = device_config['ip']
    timeout = device_config.get('timeout', 60)
    # Ensure timeout is reasonable for version check
    if timeout > 30:
        timeout = 30  # Version check should be quick
    
    # Check if this is a fake device with pre-configured firmware info
    if is_fake_device(device_config):
        if 'firmware_info' in device_config:
            logger.debug(f"{ip_address}: Using pre-configured firmware info for fake device")
            return device_config['firmware_info']
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
    base_url = build_device_url(device_config)
    if not base_url:
        logger.error(f"Failed to build valid URL for device {ip_address}")
        return None
    
    # Command parameters to get status
    params = {"cmnd": "Status 2"}
    
    try:
        logger.debug(f"{ip_address}: Requesting firmware version information")
        response = requests.get(base_url, params=params, timeout=timeout)
        
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
        # Sanitize error message to avoid leaking sensitive data
        error_msg = sanitize_log_data(str(e))
        logger.error(f"{ip_address}: Error connecting to device: {error_msg}")
    
    return None


def verify_device_restart_with_backoff(
    device_config: Dict[str, Any],
    timeout_config: TimeoutConfig
) -> Tuple[bool, TimeoutReport]:
    """
    Verify device restart with exponential backoff and detailed timeout reporting

    Args:
        device_config: Device configuration dictionary
        timeout_config: Timeout configuration for the verification process

    Returns:
        Tuple of (success, timeout_report)
        - success: True if device came back online, False if timed out
        - timeout_report: Detailed information about the timeout process
    """
    ip_address = device_config['ip']
    base_url = build_device_url(device_config)

    if not base_url:
        return False, TimeoutReport(
            total_timeout=timeout_config.total_timeout,
            elapsed_time=0,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=0,
            last_check_interval=0,
            timed_out=True,
            error_type="invalid_url",
            details={"message": "Failed to build valid device URL"}
        )

    start_time = time.time()
    attempts = 0
    current_interval = timeout_config.min_check_interval

    logger.info(f"{ip_address}: Starting device restart verification with exponential backoff")
    logger.debug(f"{ip_address}: Timeout config - total: {timeout_config.total_timeout}s, "
                f"initial wait: {timeout_config.initial_wait}s, "
                f"interval range: {timeout_config.min_check_interval}-{timeout_config.max_check_interval}s")

    # Initial wait to allow device to start the update process
    logger.debug(f"{ip_address}: Initial wait of {timeout_config.initial_wait} seconds")
    time.sleep(timeout_config.initial_wait)

    while time.time() - start_time < timeout_config.total_timeout:
        attempts += 1
        elapsed = time.time() - start_time

        logger.debug(f"{ip_address}: Attempt {attempts} after {elapsed:.1f}s (interval: {current_interval:.1f}s)")

        try:
            response = requests.get(
                base_url,
                timeout=timeout_config.request_timeout,
                params={"cmnd": "Status"}  # Simple status check
            )

            if response.status_code == 200:
                # Device is back online
                elapsed_time = time.time() - start_time
                logger.info(f"{ip_address}: Device restart verified successfully after {elapsed_time:.1f}s "
                           f"({attempts} attempts)")

                return True, TimeoutReport(
                    total_timeout=timeout_config.total_timeout,
                    elapsed_time=elapsed_time,
                    phase=TimeoutPhase.RESTART_VERIFICATION,
                    attempts=attempts,
                    last_check_interval=current_interval,
                    timed_out=False,
                    error_type="none",
                    details={
                        "success": True,
                        "final_status_code": response.status_code
                    }
                )

        except requests.exceptions.Timeout:
            logger.debug(f"{ip_address}: Request timeout on attempt {attempts}")
        except requests.exceptions.ConnectionError:
            logger.debug(f"{ip_address}: Connection error on attempt {attempts} (device still rebooting)")
        except requests.exceptions.RequestException as e:
            logger.debug(f"{ip_address}: Request error on attempt {attempts}: {sanitize_log_data(str(e))}")

        # Wait before next attempt with exponential backoff
        time.sleep(current_interval)

        # Increase interval for next attempt
        current_interval = min(
            current_interval * timeout_config.backoff_multiplier,
            timeout_config.max_check_interval
        )

    # Timeout reached
    elapsed_time = time.time() - start_time
    logger.warning(f"{ip_address}: Device restart verification timed out after {elapsed_time:.1f}s "
                   f"({attempts} attempts)")

    return False, TimeoutReport(
        total_timeout=timeout_config.total_timeout,
        elapsed_time=elapsed_time,
        phase=TimeoutPhase.RESTART_VERIFICATION,
        attempts=attempts,
        last_check_interval=current_interval,
        timed_out=True,
        error_type="restart_timeout",
        details={
            "message": f"Device did not come back online within {timeout_config.total_timeout} seconds",
            "final_interval": current_interval
        }
    )


def create_timeout_config(device_config: Dict[str, Any]) -> TimeoutConfig:
    """
    Create timeout configuration from device config with validation

    Args:
        device_config: Device configuration dictionary

    Returns:
        TimeoutConfig with validated parameters
    """
    # Get timeout from device config or use default (align with frontend default)
    total_timeout = device_config.get('timeout', 240)

    # Ensure minimum timeout for firmware updates
    if total_timeout < 60:
        logger.warning(f"Timeout {total_timeout}s is too low for firmware updates, using 60s minimum")
        total_timeout = 60

    # Cap maximum timeout
    if total_timeout > 600:
        logger.warning(f"Timeout {total_timeout}s exceeds maximum, capping at 600s")
        total_timeout = 600

    # Adjust initial wait based on total timeout
    initial_wait = min(10, total_timeout // 12)  # At most 1/12 of total timeout, max 10s

    # Adjust check intervals based on total timeout
    min_interval = 1.0 if total_timeout <= 120 else 2.0
    max_interval = min(30.0, total_timeout // 6)  # At most 1/6 of total timeout

    return TimeoutConfig(
        total_timeout=total_timeout,
        initial_wait=initial_wait,
        min_check_interval=min_interval,
        max_check_interval=max_interval,
        backoff_multiplier=1.5,
        request_timeout=5
    )


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
        # Optional GitHub auth raises the unauthenticated 60 req/hr rate
        # limit to 5000 req/hr. Set GITHUB_TOKEN to enable.
        headers = {"Accept": "application/vnd.github+json"}
        github_token = os.environ.get("GITHUB_TOKEN", "").strip()
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        response = requests.get(url, headers=headers, timeout=10)
        
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


def update_device_firmware(device_config: Dict[str, Any], check_only: bool = False) -> Dict[str, Any]:
    """
    Update firmware on a single Tasmota device with enhanced timeout handling

    Args:
        device_config: Device configuration dictionary containing:
            - ip (str): IP address of the device (required)
            - username (str, optional): Username for authentication
            - password (str, optional): Password for authentication
            - timeout (int, optional): Total timeout for the update operation in seconds (60-600)
        check_only: If True, only check firmware version without updating

    Returns:
        Result dictionary with success status, version details, and timeout information
    """
    # Validate required fields in device_config
    if not device_config or not isinstance(device_config, dict) or 'ip' not in device_config:
        return {
            "ip": "unknown",
            "success": False,
            "message": "Invalid device configuration: missing IP address",
            "current_version": "Unknown",
            "latest_version": "Unknown",
            "needs_update": False
        }
    
    # Extract device information
    device_ip = device_config['ip']
    
    # Create timeout configuration
    timeout_config = create_timeout_config(device_config)

    result = {
        "ip": device_ip,
        "success": False,
        "message": "",
        "current_version": "Unknown",
        "latest_version": "Unknown",
        "needs_update": False,
        "dns_name": get_dns_name(device_config),
        "timeout_config": {
            "total_timeout": timeout_config.total_timeout,
            "initial_wait": timeout_config.initial_wait,
            "min_check_interval": timeout_config.min_check_interval,
            "max_check_interval": timeout_config.max_check_interval
        },
        "timeout_report": None
    }
    
    # Get current firmware version
    firmware_info = get_device_firmware_version(device_config)
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
    
    # If only checking version, return the result without updating
    if check_only:
        result["message"] = "Update available"
        result["success"] = True
        return result
        
    # Handle fake devices with simulated update delay
    if device_config and is_fake_device(device_config):
        # Import random module only when needed for fake device simulation
        import random
        
        # Simulate an update with a random delay between 2-5 seconds
        random_delay = random.uniform(2, 5)
        logger.info(f"{device_ip}: Simulating update for fake device with {random_delay:.1f} second delay")
        
        # Sleep for the random delay to simulate update time
        time.sleep(random_delay)
        
        result["message"] = f"Fake device updated successfully (simulated in {random_delay:.1f} seconds)"
        result["success"] = True
        return result
    
    # Construct base URL with authentication if provided
    base_url = build_device_url(device_config)
    if not base_url:
        result["message"] = f"Invalid device IP address: {device_ip}"
        result["timeout_report"] = TimeoutReport(
            total_timeout=timeout_config.total_timeout,
            elapsed_time=0,
            phase=TimeoutPhase.INITIAL_WAIT,
            attempts=0,
            last_check_interval=0,
            timed_out=False,
            error_type="invalid_url",
            details={"message": "Invalid device URL"}
        ).to_dict()
        return result

    try:
        # Send upgrade command with timeout
        logger.info(f"{device_ip}: Initiating firmware upgrade to latest official release")
        logger.debug(f"{device_ip}: Using timeout configuration: {timeout_config.total_timeout}s total")

        params = {"cmnd": "Upgrade 1"}
        start_time = time.time()

        try:
            response = requests.get(
                base_url,
                params=params,
                timeout=timeout_config.request_timeout
            )
        except requests.exceptions.Timeout:
            elapsed_time = time.time() - start_time
            result["message"] = "Timeout sending upgrade command to device"
            result["timeout_report"] = TimeoutReport(
                total_timeout=timeout_config.total_timeout,
                elapsed_time=elapsed_time,
                phase=TimeoutPhase.INITIAL_WAIT,
                attempts=1,
                last_check_interval=0,
                timed_out=True,
                error_type="command_timeout",
                details={"message": "Device did not respond to upgrade command"}
            ).to_dict()
            return result

        if response.status_code != 200:
            elapsed_time = time.time() - start_time
            result["message"] = f"Failed to send upgrade command. Status code: {response.status_code}"
            result["timeout_report"] = TimeoutReport(
                total_timeout=timeout_config.total_timeout,
                elapsed_time=elapsed_time,
                phase=TimeoutPhase.INITIAL_WAIT,
                attempts=1,
                last_check_interval=0,
                timed_out=False,
                error_type="command_error",
                details={
                    "message": "Upgrade command failed",
                    "status_code": response.status_code
                }
            ).to_dict()
            return result

        logger.info(f"{device_ip}: Upgrade command sent successfully, waiting for device restart")

        # Verify device restart with exponential backoff
        restart_success, timeout_report = verify_device_restart_with_backoff(
            device_config, timeout_config
        )

        # Add timeout report to result
        result["timeout_report"] = timeout_report.to_dict()

        if restart_success:
            # Device is back online - get new firmware version
            result["success"] = True
            result["message"] = "Firmware update completed successfully"

            logger.info(f"{device_ip}: Verifying firmware update completion")
            new_firmware_info = get_device_firmware_version(device_config)
            if new_firmware_info:
                result["current_version"] = new_firmware_info["version"]
                logger.info(f"{device_ip}: New firmware version: {new_firmware_info['version']}")
            else:
                logger.warning(f"{device_ip}: Could not verify new firmware version")
        else:
            # Timeout or other error during restart verification
            if timeout_report.error_type == "restart_timeout":
                result["message"] = (
                    f"Firmware update initiated but device did not come back online "
                    f"within {timeout_config.total_timeout} seconds. "
                    f"The update may still be in progress."
                )
            else:
                result["message"] = f"Firmware update failed: {timeout_report.details.get('message', 'Unknown error')}"

    except requests.exceptions.RequestException as e:
        # Handle network errors during upgrade command
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        error_msg = sanitize_log_data(str(e))
        logger.error(f"{device_ip}: Network error during firmware update: {error_msg}")

        result["message"] = f"Network error during firmware update: {error_msg}"
        result["timeout_report"] = TimeoutReport(
            total_timeout=timeout_config.total_timeout,
            elapsed_time=elapsed_time,
            phase=TimeoutPhase.INITIAL_WAIT,
            attempts=1,
            last_check_interval=0,
            timed_out=False,
            error_type="network_error",
            details={
                "message": "Network error during upgrade",
                "error": error_msg
            }
        ).to_dict()

    return result

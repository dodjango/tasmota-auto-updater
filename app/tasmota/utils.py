"""Utility functions for the Tasmota updater"""

import yaml
import os
import logging
import socket
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)


def resolve_dns_name(ip_address: str, device: dict = None) -> str:
    """
    Resolve an IP address to its DNS name
    
    Args:
        ip_address (str): The IP address to resolve
        device (dict, optional): The device configuration dictionary
        
    Returns:
        str: The DNS name if found, None otherwise
    """
    # If this is a fake device with a pre-configured DNS name, use that
    if device and is_fake_device(device) and 'dns_name' in device:
        return device['dns_name']
        
    # For real devices, try to resolve the DNS name
    try:
        hostname, _, _ = socket.gethostbyaddr(ip_address)
        return hostname if hostname != ip_address else None
    except (socket.herror, socket.gaierror):
        # Failed to resolve, return None
        return None


def load_devices_from_file(filename: str) -> List[Dict[str, Any]]:
    """
    Load device configurations from a YAML file
    
    Args:
        filename (str): Path to YAML file containing device configurations
    
    Returns:
        list: List of device configurations as dictionaries
    """
    try:
        with open(filename, 'r') as file:
            config = yaml.safe_load(file)
            
        if not config or not isinstance(config, dict) or 'devices' not in config:
            logger.error(f"Invalid configuration file format: {filename}")
            return []
            
        devices = config['devices']
        if not isinstance(devices, list):
            logger.error(f"'devices' must be a list in configuration file: {filename}")
            return []
            
        # Validate each device has at least an IP address
        valid_devices = []
        for i, device in enumerate(devices):
            if not isinstance(device, dict):
                logger.warning(f"Device #{i+1} is not a dictionary, skipping")
                continue
                
            if 'ip' not in device:
                logger.warning(f"Device #{i+1} has no IP address, skipping")
                continue
                
            valid_devices.append(device)
            
        logger.info(f"Loaded {len(valid_devices)} device(s) from {filename}")
        return valid_devices
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {filename}")
        return []
        
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {filename}: {e}")
        return []
        
    except Exception as e:
        logger.error(f"Unexpected error loading devices from {filename}: {e}")
        return []


def is_fake_device(device: Dict[str, Any]) -> bool:
    """
    Check if a device is a fake (development) device
    
    Args:
        device (dict): Device configuration dictionary
        
    Returns:
        bool: True if the device is fake, False otherwise
    """
    return device.get('fake', False) is True


def get_device_firmware_info(device: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get firmware information for a device
    
    For fake devices, returns the pre-configured firmware info.
    For real devices, returns None (should be fetched from the device).
    
    Args:
        device (dict): Device configuration dictionary
        
    Returns:
        dict: Firmware information or None
    """
    if is_fake_device(device) and 'firmware_info' in device:
        return device['firmware_info']
    return None


def setup_logging(log_file=None, log_level=logging.INFO):
    """
    Set up logging configuration
    
    Args:
        log_file (str): Path to log file, if None logs to console only
        log_level (int): Logging level
        
    Returns:
        logger: Configured logger
    """
    # Create logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Create file handler if log file is specified
    if log_file:
        # Create directory for log file if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger

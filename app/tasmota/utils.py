"""Utility functions for the Tasmota updater"""

import yaml
import os
import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_dns_name(ip_address: str) -> str:
    """
    Resolve an IP address to its DNS name
    
    Args:
        ip_address (str): The IP address to resolve
        
    Returns:
        str: The DNS name if found, None otherwise
    """
    try:
        hostname, _, _ = socket.gethostbyaddr(ip_address)
        return hostname if hostname != ip_address else None
    except (socket.herror, socket.gaierror):
        # Failed to resolve, return None
        return None


def load_devices_from_file(filename):
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

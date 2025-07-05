import requests
import time
import sys
import yaml
import argparse
import logging
import os
import socket
from datetime import datetime
from pathlib import Path

def get_dns_name(ip_address):
    """
    Try to get the DNS name for an IP address
    
    Args:
        ip_address (str): IP address to lookup
    Returns:
        str: DNS name if found, otherwise None
    """
    try:
        dns_name = socket.getfqdn(ip_address)
        if dns_name != ip_address:
            return dns_name
    except Exception:
        pass
    return None

def update_tasmota(device_config, dry_run=False):
    """
    Update Tasmota device remotely via HTTP API
    
    Args:
        device_config (dict): Device configuration containing IP and optional credentials
        dry_run (bool): If True, simulate the update process without making changes
    Returns:
        bool: True if update was successful (or would be in dry run mode), False otherwise
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
        logger.info(f"{device_info}: Would upgrade to latest official release (DRY RUN)")
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
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"{device_info}: Device is not reachable: {e} (DRY RUN)")
            return False
    else:
        # Normal mode - actually perform the update
        try:
            # Direct upgrade to latest release
            logger.info(f"{device_info}: Upgrading to latest official release")
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
                        return True
                    else:
                        logger.warning(f"{device_info}: Device responded with status code {status_response.status_code}")
                        return False
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"{device_info}: Could not verify if device is back online: {e}")
                    return False
                    
            else:
                logger.error(f"{device_info}: Failed to initiate update. Status code: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"{device_info}: Error connecting to device: {e}")
            return False

def update_devices_from_file(filename, dry_run=False):
    """
    Update multiple Tasmota devices from a YAML file
    
    Args:
        filename (str): Path to YAML file containing device configurations
        dry_run (bool): If True, simulate the update process without making changes
    """
    logger = logging.getLogger()
    
    try:
        logger.debug(f"Opening configuration file: {filename}")
        with open(filename, 'r') as f:
            config = yaml.safe_load(f)
            
        if not config or 'devices' not in config or not config['devices']:
            logger.warning("No devices found in the configuration file")
            return
        
        devices = config['devices']
        if dry_run:
            logger.info(f"Found {len(devices)} devices that would be updated (DRY RUN)")
        else:
            logger.info(f"Found {len(devices)} devices to update")
        
        results = {}
        device_dns_map = {}
        for device in devices:
            ip = device['ip']
            
            # Try to get DNS name
            dns_name = get_dns_name(ip)
            device_info = ip
            if dns_name:
                device_info = f"{ip} ({dns_name})"
                device_dns_map[ip] = dns_name
            
            if dry_run:
                logger.info(f"\nWould update device at {device_info} (DRY RUN)")
            else:
                logger.info(f"\nUpdating device at {device_info}")
            success = update_tasmota(device, dry_run=dry_run)
            results[ip] = success
        
        # Log summary
        if dry_run:
            logger.info("\nDRY RUN Summary:")
            logger.info("-" * 40)
            successful = sum(1 for success in results.values() if success)
            logger.info(f"Would successfully update: {successful}/{len(results)} devices")
            
            if len(results) != successful:
                logger.warning("Devices that would fail:")
                for ip, success in results.items():
                    if not success:
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        logger.warning(f"- {device_info} (not reachable in dry run test)")
        else:
            logger.info("\nUpdate Summary:")
            logger.info("-" * 40)
            successful = sum(1 for success in results.values() if success)
            logger.info(f"Successfully updated: {successful}/{len(results)} devices")
            
            if len(results) != successful:
                logger.warning("Failed updates:")
                for ip, success in results.items():
                    if not success:
                        device_info = ip
                        if ip in device_dns_map:
                            device_info = f"{ip} ({device_dns_map[ip]})"
                        logger.warning(f"- {device_info}")
        
        # Return results for potential further processing
        return {
            "total": len(results),
            "successful": successful,
            "failed": len(results) - successful,
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
    
    if args.dry_run:
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
    update_devices_from_file(args.file, dry_run=args.dry_run)
    
    if args.dry_run:
        logger.info("Tasmota Updater finished (DRY RUN mode - no changes were made)")
    else:
        logger.info("Tasmota Updater finished")
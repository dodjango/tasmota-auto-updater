import requests
import time
import sys
import yaml
from pathlib import Path

def update_tasmota(device_config):
    """
    Update Tasmota device remotely via HTTP API
    
    Args:
        device_config (dict): Device configuration containing IP and optional credentials
    Returns:
        bool: True if update was successful, False otherwise
    """
    ip_address = device_config['ip']
    username = device_config.get('username')
    password = device_config.get('password')
    
    # Construct base URL with authentication if provided
    if username and password:
        base_url = f"http://{username}:{password}@{ip_address}/cm"
    else:
        base_url = f"http://{ip_address}/cm"
    
    try:
        # Direct upgrade to latest release
        print("Upgrading to latest official release")
        params = {"cmnd": "Upgrade 1"}
        response = requests.get(base_url, params=params, timeout=5)
        
        print(f"Initiating update for Tasmota device at {ip_address}")
        
        if response.status_code == 200:
            print("Update command sent successfully")
            print("Device will restart automatically after update")
            print("Waiting for device to come back online...")
            
            # Wait for device to update and restart
            time.sleep(90)  # Increased wait time for safety
            
            # Try to check if device is back online
            try:
                check_url = f"http://{ip_address}"
                if username and password:
                    check_url = f"http://{username}:{password}@{ip_address}"
                status_response = requests.get(check_url, timeout=5)
                if status_response.status_code == 200:
                    print("Device is back online!")
                    return True
            except requests.exceptions.RequestException:
                print("Could not verify if device is back online. Please check manually.")
                
        else:
            print(f"Failed to initiate update. Status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to device: {e}")
        return False

def update_devices_from_file(filename):
    """
    Update multiple Tasmota devices from a YAML file
    
    Args:
        filename (str): Path to YAML file containing device configurations
    """
    try:
        with open(filename, 'r') as f:
            config = yaml.safe_load(f)
            
        if not config or 'devices' not in config or not config['devices']:
            print("No devices found in the configuration file")
            return
        
        devices = config['devices']
        print(f"Found {len(devices)} devices to update")
        
        results = {}
        for device in devices:
            ip = device['ip']
            print(f"\nUpdating device at {ip}")
            success = update_tasmota(device)
            results[ip] = success
        
        # Print summary
        print("\nUpdate Summary:")
        print("-" * 40)
        successful = sum(1 for success in results.values() if success)
        print(f"Successfully updated: {successful}/{len(results)} devices")
        
        if len(results) != successful:
            print("\nFailed updates:")
            for ip, success in results.items():
                if not success:
                    print(f"- {ip}")
                    
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    devices_file = "devices.yaml"
    update_devices_from_file(devices_file) 
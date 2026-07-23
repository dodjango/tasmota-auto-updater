"""API endpoints for the Tasmota updater web application"""

import os
from flask import request, jsonify, current_app
from flask_restful import Api, Resource
from marshmallow import Schema, fields, validate
from flasgger import swag_from
from app.tasmota.updater import (
    get_device_firmware_version,
    fetch_latest_tasmota_release,
    update_device_firmware,
    is_valid_ip_address,
)
from app.tasmota.utils import load_devices_from_file, resolve_dns_name, is_fake_device


# Schema definitions for request/response validation
class DeviceSchema(Schema):
    """Schema for device information"""
    ip = fields.String()
    username = fields.String()
    password = fields.String()

    class Meta:
        fields = ("ip", "username", "password")


class DeviceUpdateSchema(Schema):
    """Schema for device update request"""
    ip = fields.String(required=True)
    username = fields.String()
    password = fields.String()
    check_only = fields.Boolean()
    timeout = fields.Integer(validate=validate.Range(min=60, max=600))

    class Meta:
        fields = ("ip", "username", "password", "check_only", "timeout")


# API Resources
class DeviceListResource(Resource):
    """Resource for listing all devices"""
    
    def get(self):
        """
        Get all configured devices
        ---
        tags:
          - devices
        responses:
          200:
            description: List of devices
            schema:
              type: object
              properties:
                devices:
                  type: array
                  items:
                    type: object
                    properties:
                      ip:
                        type: string
                        description: Device IP address
                      fake:
                        type: boolean
                        description: Whether this is a fake device
                      dns_name:
                        type: string
                        description: Resolved DNS name for the device
        """
        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)
        
        # Remove passwords from response for security and add DNS names
        for device in devices:
            if 'password' in device:
                device['password'] = '********' if device['password'] else None
            
            # Try to resolve DNS name for the device
            if 'ip' in device:
                dns_name = resolve_dns_name(device['ip'], device)
                if dns_name:
                    device['dns_name'] = dns_name
                else:
                    device['dns_name'] = device['ip']
        
        return jsonify({'devices': devices})


class DeviceStatusResource(Resource):
    """Resource for getting device status"""
    
    def get(self, device_ip):
        """
        Get status of a specific device
        ---
        tags:
          - devices
        parameters:
          - name: device_ip
            in: path
            type: string
            required: true
            description: Device IP address
        responses:
          200:
            description: Device status
            schema:
              type: object
              properties:
                ip:
                  type: string
                  description: Device IP address
                version:
                  type: string
                  description: Current firmware version
                core_version:
                  type: string
                  description: Core version
                sdk_version:
                  type: string
                  description: SDK version
                is_minimal:
                  type: boolean
                  description: Whether this is a minimal version
          404:
            description: Device not found
          500:
            description: Error getting device status
        """
        # Reject malformed IPs early (prevents echoing unsanitised
        # path input back in the response body).
        if not is_valid_ip_address(device_ip):
            return {'error': 'Invalid device IP address'}, 400

        # Find device in configuration
        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)
        
        device = next((d for d in devices if d['ip'] == device_ip), None)
        if not device:
            return {'error': 'Device not found'}, 404
        
        # Get device firmware version
        firmware_info = get_device_firmware_version(device)
        
        if not firmware_info:
            return {'error': 'Failed to get device status'}, 500
        
        # Add IP to the response
        firmware_info['ip'] = device_ip
        
        return jsonify(firmware_info)


class LatestReleaseResource(Resource):
    """Resource for getting latest Tasmota release information"""
    
    def get(self):
        """
        Get latest Tasmota release information
        ---
        tags:
          - releases
        responses:
          200:
            description: Latest release information
            schema:
              type: object
              properties:
                version:
                  type: string
                  description: Latest version
                release_date:
                  type: string
                  description: Release date
                release_notes:
                  type: string
                  description: Release notes
                download_url:
                  type: string
                  description: Download URL for firmware binary
                release_url:
                  type: string
                  description: URL to the GitHub release page with release notes
          500:
            description: Error fetching release information
        """
        latest_release = fetch_latest_tasmota_release()
        
        if not latest_release:
            return {'error': 'Failed to fetch latest release information'}, 500
        
        return jsonify(latest_release)


class DeviceUpdateResource(Resource):
    """Resource for updating device firmware"""
    
    def post(self):
        """
        Update device firmware
        ---
        tags:
          - updates
        parameters:
          - in: body
            name: body
            schema:
              type: object
              required:
                - ip
              properties:
                ip:
                  type: string
                  description: Device IP address
                check_only:
                  type: boolean
                  description: Only check if update is needed
                  default: false
                timeout:
                  type: integer
                  description: Total timeout for update operation in seconds (60-600)
                  minimum: 60
                  maximum: 600
                  default: 180
        responses:
          200:
            description: Update result
            schema:
              type: object
              properties:
                ip:
                  type: string
                  description: Device IP address
                success:
                  type: boolean
                  description: Whether the operation was successful
                message:
                  type: string
                  description: Result message
                current_version:
                  type: string
                  description: Current firmware version
                latest_version:
                  type: string
                  description: Latest available version
                needs_update:
                  type: boolean
                  description: Whether an update is needed
                timeout_config:
                  type: object
                  description: Timeout configuration used for the operation
                  properties:
                    total_timeout:
                      type: integer
                      description: Total timeout in seconds
                    initial_wait:
                      type: integer
                      description: Initial wait before checking device
                    min_check_interval:
                      type: number
                      description: Minimum interval between checks
                    max_check_interval:
                      type: number
                      description: Maximum interval between checks
                timeout_report:
                  type: object
                  description: Detailed timeout information if applicable
                  properties:
                    total_timeout:
                      type: integer
                      description: Total timeout configured
                    elapsed_time:
                      type: number
                      description: Time elapsed during operation
                    phase:
                      type: string
                      description: Phase where timeout occurred
                    attempts:
                      type: integer
                      description: Number of attempts made
                    timed_out:
                      type: boolean
                      description: Whether operation timed out
                    error_type:
                      type: string
                      description: Type of error encountered
          400:
            description: Invalid request
          500:
            description: Error updating device
        """
        # Validate request data
        schema = DeviceUpdateSchema()
        if not request.is_json:
            return {'error': 'Invalid request',
                    'details': 'Content-Type must be application/json'}, 415
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {'error': 'Invalid request',
                    'details': 'Request body must be a JSON object'}, 400
        errors = schema.validate(payload)
        if errors:
            return {'error': 'Invalid request', 'details': errors}, 400
        
        # Extract parameters
        device_ip = payload['ip']
        check_only = payload.get('check_only', False) if payload.get('check_only') is not None else False
        timeout = payload.get('timeout')  # Optional timeout override

        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)

        # Find the device by IP
        device = next((d for d in devices if d.get('ip') == device_ip), None)

        # If we found the device in the config file, merge with any additional settings
        if device:
            # Create a copy of device config to avoid modifying the original
            device_config = device.copy()

            # Override timeout if provided in request
            if timeout is not None:
                device_config['timeout'] = timeout
                current_app.logger.info(f"Using timeout override: {timeout}s for device {device_ip}")

            # Update device firmware with enhanced timeout handling
            current_app.logger.info(
                f"Firmware update requested for {device_ip} "
                f"(check_only={check_only}) from {request.remote_addr}"
            )
            result = update_device_firmware(device_config, check_only)
        else:
            return {'error': 'Device not found'}, 404
        
        return jsonify(result)


class AllDevicesUpdateResource(Resource):
    """Resource for updating all devices"""
    
    def post(self):
        """
        Update all devices
        ---
        tags:
          - updates
        parameters:
          - in: body
            name: body
            schema:
              type: object
              properties:
                check_only:
                  type: boolean
                  description: Only check if updates are needed
                  default: false
                update_only_needed:
                  type: boolean
                  description: Only update devices that need updates
                  default: true
                timeout:
                  type: integer
                  description: Global timeout override for all devices (60-600 seconds)
                  minimum: 60
                  maximum: 600
        responses:
          200:
            description: Update results
            schema:
              type: object
              properties:
                results:
                  type: array
                  items:
                    type: object
                    properties:
                      ip:
                        type: string
                        description: Device IP address
                      success:
                        type: boolean
                        description: Whether the operation was successful
                      message:
                        type: string
                        description: Result message
                      current_version:
                        type: string
                        description: Current firmware version
                      latest_version:
                        type: string
                        description: Latest available version
                      needs_update:
                        type: boolean
                        description: Whether an update is needed
                      update_started:
                        type: boolean
                        description: Whether the update was initiated
                      update_completed:
                        type: boolean
                        description: Whether the update completed
                summary:
                  type: object
                  properties:
                    total:
                      type: integer
                      description: Total number of devices
                    success:
                      type: integer
                      description: Number of successful operations
                    needs_update:
                      type: integer
                      description: Number of devices that need updates
                    updated:
                      type: integer
                      description: Number of devices actually updated
          500:
            description: Error updating devices
        """
        
        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)
        
        # Extract parameters
        if not request.is_json:
            return {'error': 'Invalid request',
                    'details': 'Content-Type must be application/json'}, 415
        payload = request.get_json(silent=True) or {}
        check_only = payload.get('check_only', False)
        update_only_needed = payload.get('update_only_needed', True)
        global_timeout = payload.get('timeout')

        current_app.logger.info(
            f"Batch firmware update requested (check_only={check_only}, "
            f"update_only_needed={update_only_needed}) from {request.remote_addr}"
        )

        if global_timeout is not None:
            if global_timeout < 60 or global_timeout > 600:
                return {'error': 'Global timeout must be between 60 and 600 seconds'}, 400
            current_app.logger.info(f"Using global timeout override: {global_timeout}s for all devices")
        
        # First check which devices need updates
        if update_only_needed and not check_only:
            check_results = []
            for device in devices:
                # Create a copy of the device config
                device_config = device.copy()
                result = update_device_firmware(device_config, check_only=True)
                check_results.append(result)
            
            # Filter devices that need updates
            devices_to_update = []
            for i, result in enumerate(check_results):
                if result.get('needs_update', False):
                    devices_to_update.append(devices[i])
        else:
            devices_to_update = devices
        
        # Update devices that need updates
        results = []
        updated_count = 0
        
        for device in devices_to_update:
            # Create a copy of the device config
            device_config = device.copy()

            # Apply global timeout override if provided
            if global_timeout is not None:
                device_config['timeout'] = global_timeout

            result = update_device_firmware(device_config, check_only)
            
            # Add additional status fields
            result['update_started'] = not check_only and (result.get('needs_update', False) or not update_only_needed)
            result['update_completed'] = result['success'] and result['update_started']
            
            if result['update_completed']:
                updated_count += 1
                
            results.append(result)
        
        # Generate summary
        summary = {
            'total': len(devices),
            'success': sum(1 for r in results if r['success']),
            'needs_update': sum(1 for r in results if r.get('needs_update', False)),
            'updated': updated_count
        }
        
        return jsonify({
            'results': results,
            'summary': summary
        })


def init_api(app):
    """Initialize API routes"""
    api = Api(app)
    
    # Register resources
    api.add_resource(DeviceListResource, '/api/devices')
    api.add_resource(DeviceStatusResource, '/api/devices/<string:device_ip>')
    api.add_resource(LatestReleaseResource, '/api/releases/latest')
    api.add_resource(DeviceUpdateResource, '/api/update')
    api.add_resource(AllDevicesUpdateResource, '/api/update/all')
    
    return api

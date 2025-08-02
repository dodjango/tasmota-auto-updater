"""API endpoints for the Tasmota updater web application"""

import os
from flask import request, jsonify, current_app
from flask_restful import Api, Resource
from marshmallow import Schema, fields, validate
from flasgger import swag_from
from app.tasmota.updater import (
    get_device_firmware_version,
    fetch_latest_tasmota_release,
    update_device_firmware
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
        required = ("ip",)


class DeviceUpdateSchema(Schema):
    """Schema for device update request"""
    ip = fields.String()
    username = fields.String()
    password = fields.String()
    check_only = fields.Boolean()
    
    class Meta:
        fields = ("ip", "username", "password", "check_only")
        required = ("ip",)


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
                      username:
                        type: string
                        description: Authentication username
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
          400:
            description: Invalid request
          500:
            description: Error updating device
        """
        # Validate request data
        schema = DeviceUpdateSchema()
        errors = schema.validate(request.json)
        if errors:
            return {'error': 'Invalid request', 'details': errors}, 400
        
        # Extract parameters
        device_ip = request.json['ip']
        check_only = request.json.get('check_only', False) if request.json.get('check_only') is not None else False
        
        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)
        
        # Find the device by IP
        device = next((d for d in devices if d.get('ip') == device_ip), None)
        
        # If we found the device in the config file, merge with any additional settings
        if device:
            # Update device firmware
            result = update_device_firmware(device, check_only)
        else:
            result = {'error': 'Device not found'}, 404
        
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
        check_only = request.json.get('check_only', False) if request.json else False
        update_only_needed = request.json.get('update_only_needed', True) if request.json else True
        
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

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
from app.tasmota.utils import load_devices_from_file, resolve_dns_name


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
                dns_name = resolve_dns_name(device['ip'])
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
        username = device.get('username')
        password = device.get('password')
        firmware_info = get_device_firmware_version(device_ip, username, password)
        
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
                username:
                  type: string
                  description: Authentication username
                password:
                  type: string
                  description: Authentication password
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
        username = request.json.get('username')
        password = request.json.get('password')
        check_only = request.json.get('check_only', False) if request.json.get('check_only') is not None else False
        
        # Update device firmware
        result = update_device_firmware(device_ip, username, password, check_only)
        
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
          500:
            description: Error updating devices
        """
        # Load devices from configuration
        devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
        devices = load_devices_from_file(devices_file)
        
        if not devices:
            return {'error': 'No devices found in configuration'}, 404
        
        # Extract parameters
        check_only = request.json.get('check_only', False) if request.json else False
        
        # Update all devices
        results = []
        for device in devices:
            result = update_device_firmware(
                device['ip'],
                device.get('username'),
                device.get('password'),
                check_only
            )
            results.append(result)
        
        # Generate summary
        summary = {
            'total': len(results),
            'success': sum(1 for r in results if r['success']),
            'needs_update': sum(1 for r in results if r['needs_update'])
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

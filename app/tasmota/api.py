"""API endpoints for the Tasmota updater web application"""

import ipaddress
import os
import socket
from pathlib import Path
from typing import Any
from flask import request, jsonify, current_app
from flask_restful import Api, Resource
from marshmallow import Schema, ValidationError, fields, validate
from flasgger import swag_from
from app.tasmota.updater import (
    get_device_firmware_version,
    fetch_latest_tasmota_release,
    update_device_firmware,
    is_valid_ip_address,
)
from app.tasmota.utils import load_devices_from_file, resolve_dns_name, is_fake_device
from app.tasmota import device_config
from app.tasmota import discovery
from app.tasmota import jobs


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


def _validate_device_ip(value: str) -> None:
    """Reject anything is_valid_ip_address() rejects.

    That function deliberately blocks loopback, link-local and the cloud
    metadata address — the same block that keeps the update endpoints from
    being turned into an SSRF primitive. The editor must not be a way around it.
    """
    if not is_valid_ip_address(value):
        raise ValidationError(f"Not a usable device address: {value!r}")


class DeviceConfigSchema(Schema):
    """One device as the editor may submit it.

    ``unknown = "raise"`` is a security property, not a convenience: it is
    what keeps ``fake`` and ``firmware_info`` unsettable through the editor.
    """

    ip = fields.String(required=True, validate=_validate_device_ip)
    username = fields.String()
    password = fields.String()
    dns_name = fields.String()
    timeout = fields.Integer(validate=validate.Range(min=60, max=600))
    remove_password = fields.Boolean()

    class Meta:
        unknown = "raise"


def validate_device_list(devices: list[dict[str, Any]]) -> list[str]:
    """List-level checks that a per-device schema cannot express."""
    errors: list[str] = []
    seen: set[Any] = set()
    for device in devices:
        ip = device.get("ip")
        if ip in seen:
            errors.append(f"Duplicate device address: {ip}")
        seen.add(ip)
    return errors


class DeviceConfigResource(Resource):
    """The device list as configuration — raw fields, editable.

    Separate from DeviceListResource on purpose: that one is the operational
    view and enriches its answer (masked password, resolved dns_name falling
    back to the IP), which must never be written back to the file.
    """

    def get(self):
        """
        Get the raw device configuration
        ---
        tags:
          - configuration
        responses:
          200:
            description: Configured devices, passwords replaced by has_password
        """
        devices_file = Path(current_app.config.get('DEVICES_FILE', 'devices.yaml'))
        devices = load_devices_from_file(str(devices_file))

        exposed = []
        for device in devices:
            entry: dict[str, Any] = {
                field: device[field]
                for field in ("ip", "username", "dns_name", "timeout")
                if field in device
            }
            entry["has_password"] = bool(device.get("password"))
            exposed.append(entry)

        return jsonify({
            "devices": exposed,
            "writable": device_config.is_writable(devices_file),
            "devices_file": str(devices_file),
        })

    def put(self):
        """
        Replace the device configuration
        ---
        tags:
          - configuration
        responses:
          200:
            description: The stored configuration after the write
          400:
            description: Validation failed
          409:
            description: The configuration file is not writable
          415:
            description: Body was not JSON
        """
        if not request.is_json:
            return {'error': 'Unsupported Media Type',
                    'details': 'Content-Type must be application/json'}, 415

        body = request.get_json(silent=True) or {}
        submitted = body.get('devices')
        if not isinstance(submitted, list):
            return {'error': 'Bad Request', 'details': "'devices' must be a list"}, 400

        schema = DeviceConfigSchema()
        cleaned = []
        for index, entry in enumerate(submitted):
            try:
                cleaned.append(schema.load(entry))
            except ValidationError as exc:
                return {'error': 'Bad Request',
                        'details': f"Device #{index + 1}: {exc.messages}"}, 400

        list_errors = validate_device_list(cleaned)
        if list_errors:
            return {'error': 'Bad Request', 'details': '; '.join(list_errors)}, 400

        devices_file = Path(current_app.config.get('DEVICES_FILE', 'devices.yaml'))
        try:
            merged = device_config.replace_devices(devices_file, cleaned)
        except (device_config.ConfigReadError, device_config.ConfigWriteError) as exc:
            return {'error': 'Conflict', 'details': str(exc)}, 409

        current_app.logger.info("Device configuration updated: %d device(s)", len(merged))
        return self.get()


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
                version_verification:
                  type: object
                  description: >
                    Result of verifying that the device actually runs a new firmware
                    version after the update. Reachability alone is not proof of a
                    completed update, so success is only reported once the reported
                    version changed. error_type is "version_unchanged" when the device
                    came back online but kept reporting the previous version.
                  properties:
                    elapsed_time:
                      type: number
                      description: Time spent waiting for the version to change
                    attempts:
                      type: integer
                      description: Number of version reads performed
                    timed_out:
                      type: boolean
                      description: Whether the version never changed in time
                    error_type:
                      type: string
                      description: '"none" or "version_unchanged"'
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
        
        # Run the (potentially minutes-long) batch on a background thread and
        # return immediately; the client polls GET /api/jobs/<id> for progress.
        # This frees the worker and avoids the Gunicorn request timeout.
        job_id = jobs.create_batch_job(
            devices, check_only, update_only_needed, global_timeout
        )
        if job_id is None:
            return {'error': 'A batch update is already in progress'}, 409
        return {'job_id': job_id, 'status_url': f'/api/jobs/{job_id}'}, 202


class JobResource(Resource):
    """Resource for polling the status/results of a background job."""

    def get(self, job_id):
        """
        Get the status and (partial) results of a background job
        ---
        tags:
          - updates
        parameters:
          - in: path
            name: job_id
            type: string
            required: true
        responses:
          200:
            description: Job status, progress and results
          404:
            description: Job not found
        """
        job = jobs.get_job(job_id)
        if job is None:
            return {'error': 'Job not found'}, 404

        if job.get('kind') == 'discovery' and job.get('results'):
            devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
            known = {
                device.get('ip')
                for device in load_devices_from_file(str(devices_file))
            }
            # load_devices_from_file() answers every failure with an empty list.
            # For a display flag that is harmless — a known device would show up
            # as new. It must never be a write baseline, and it is not one here:
            # discovery has no write path at all.
            job['results'] = [
                {**entry, 'already_configured': entry.get('ip') in known}
                for entry in job['results']
            ]

        return job


# A /22 is 1024 addresses — about 25 seconds at 64 workers. Wide enough for any
# home network, narrow enough that the endpoint cannot be turned into a sweep.
MAX_SCAN_PREFIX = 22
MAX_SCAN_HOSTS = 1024


def validate_scan_target(value: str) -> ipaddress.IPv4Network:
    """Decide whether a network may be scanned at all.

    Deliberately stricter than ``is_valid_ip_address()``, which allows public
    addresses because a device may legitimately sit on one. A *scan* is a
    different matter: an endpoint that sweeps arbitrary public ranges is a port
    scanner behind someone's session cookie. Private IPv4 only, and bounded.
    """
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"Not a usable network: {value!r}") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValidationError("Only IPv4 networks can be scanned.")
    if network.is_loopback or network.is_link_local or network.is_multicast:
        raise ValidationError("Loopback, link-local and multicast ranges cannot be scanned.")
    if not network.is_private:
        raise ValidationError(
            "Only private networks can be scanned, so the scanner cannot be "
            "pointed at the public internet."
        )
    if network.prefixlen < MAX_SCAN_PREFIX:
        raise ValidationError(
            f"Network is too large: /{network.prefixlen} exceeds the "
            f"/{MAX_SCAN_PREFIX} limit of {MAX_SCAN_HOSTS} addresses."
        )
    return network


def suggest_local_networks() -> list[str]:
    """Guess the local network, to prefill the scan field.

    A UDP socket 'connected' to an arbitrary address reveals which interface
    would carry the traffic, without sending a packet. It reveals the address,
    not its prefix length — /24 is an assumption, which is exactly why the API
    calls this a suggestion and the UI keeps the field editable.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, guaranteed unrouted
        local_ip = probe.getsockname()[0]
    except OSError:
        return []
    finally:
        probe.close()

    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return []
    return [str(network)] if network.is_private else []


def _validation_message(exc: ValidationError) -> str:
    """Flatten a ValidationError into one readable sentence for the client."""
    messages = exc.messages
    if isinstance(messages, list):
        return "; ".join(str(message) for message in messages)
    return str(messages)


class DiscoveryResource(Resource):
    """Find Tasmota devices on the network. Never writes anything.

    Findings are suggestions: they leave through the job endpoint and the user
    adopts them in the editor, which saves through PUT /api/config/devices.
    Keeping the write path out of here is what leaves device_config with a
    single caller.
    """

    def get(self):
        """
        Get scan suggestions and limits
        ---
        tags:
          - discovery
        responses:
          200:
            description: A suggested network to scan and the enforced limits
            examples:
              application/json:
                suggested_networks: ["192.168.1.0/24"]
                limits: {max_prefix: 22, max_hosts: 1024}
        """
        return {
            "suggested_networks": suggest_local_networks(),
            "limits": {"max_prefix": MAX_SCAN_PREFIX, "max_hosts": MAX_SCAN_HOSTS},
        }

    def post(self):
        """
        Start a discovery job
        ---
        tags:
          - discovery
        parameters:
          - in: body
            name: body
            required: true
            schema:
              properties:
                method:
                  type: string
                  enum: [mdns, scan]
                network:
                  type: string
                  description: Required for method=scan. Private IPv4, prefix >= 22.
            examples:
              scan: {method: scan, network: "192.168.1.0/24"}
              mdns: {method: mdns}
        responses:
          202:
            description: Job accepted; poll GET /api/jobs/{job_id}
            examples:
              application/json: {job_id: "3f2a", status_url: "/api/jobs/3f2a"}
          400:
            description: Unknown method, or a network outside the allowed range
          409:
            description: A discovery job is already running
          415:
            description: Body was not JSON
        """
        if not request.is_json:
            return {'error': 'Unsupported Media Type',
                    'details': 'Content-Type must be application/json'}, 415

        body = request.get_json(silent=True) or {}
        method = body.get('method')
        if method not in ('mdns', 'scan'):
            return {'error': 'Bad Request',
                    'details': "'method' must be 'mdns' or 'scan'"}, 400

        hosts = None
        if method == 'scan':
            try:
                network = validate_scan_target(body.get('network') or '')
            except ValidationError as exc:
                return {'error': 'Bad Request', 'details': _validation_message(exc)}, 400
            hosts = discovery.hosts_in_network(network)
            current_app.logger.info(
                "Discovery scan requested for %s (%d hosts)", network, len(hosts)
            )
        else:
            current_app.logger.info("Discovery via mDNS requested")

        job_id = jobs.create_discovery_job(method, hosts)
        if job_id is None:
            return {'error': 'A discovery job is already in progress'}, 409
        return {'job_id': job_id, 'status_url': f'/api/jobs/{job_id}'}, 202


def init_api(app):
    """Initialize API routes"""
    api = Api(app)

    # Register resources
    api.add_resource(DeviceConfigResource, '/api/config/devices')
    api.add_resource(DeviceListResource, '/api/devices')
    api.add_resource(DeviceStatusResource, '/api/devices/<string:device_ip>')
    api.add_resource(LatestReleaseResource, '/api/releases/latest')
    api.add_resource(DeviceUpdateResource, '/api/update')
    api.add_resource(AllDevicesUpdateResource, '/api/update/all')
    api.add_resource(JobResource, '/api/jobs/<string:job_id>')
    api.add_resource(DiscoveryResource, '/api/discovery')

    return api

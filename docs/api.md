# API Documentation

The Tasmota Remote Updater provides a comprehensive REST API that allows you to integrate its functionality into your own applications or automation systems.

> **Note:** This API follows [Semantic Versioning 2.0.0](https://semver.org/). Breaking changes will only be introduced in new major versions.

## API Overview

The API is built using Flask-RESTful and is documented using Swagger/OpenAPI. You can access the interactive API documentation at http://localhost:5001/apidocs/ when the web application is running.

## Base URL

All API endpoints are relative to the base URL of your Tasmota Remote Updater installation:

```
http://localhost:5001/api/v1
```

## Version Information

You can retrieve the current version of the API using the version endpoint:

```
GET /version
```

Example response:

```json
{
  "version": "0.1.0",
  "name": "Tasmota Updater"
}
```

## Authentication

Currently, the API does not require authentication. If you're exposing the API to untrusted networks, consider implementing appropriate network-level security measures.

## Endpoints

### Device Management

#### List All Devices

```
GET /api/v1/devices
```

Returns a list of all configured devices.

**Response Example:**

```json
{
  "devices": [
    {
      "ip": "192.168.1.100",
      "username": "admin"
    },
    {
      "ip": "192.168.1.101"
    }
  ]
}
```

#### Get Device Status

```
GET /api/v1/devices/{device_ip}/status
```

Returns the status of a specific device, including its current firmware version.

**Response Example:**

```json
{
  "ip": "192.168.1.100",
  "version": "9.5.0",
  "core_version": "2.7.4.9",
  "sdk_version": "2.2.2-dev",
  "is_minimal": false
}
```

### Firmware Management

#### Get Latest Release Information

```
GET /api/v1/releases/latest
```

Returns information about the latest Tasmota firmware release.

**Response Example:**

```json
{
  "version": "12.4.0",
  "release_date": "2023-09-15",
  "release_notes": "# Tasmota v12.4.0\n\n- Fixed various bugs\n- Added new features",
  "download_url": "https://github.com/arendst/Tasmota/releases/download/v12.4.0/tasmota.bin"
}
```

### Update Operations

#### Update Device

```
POST /api/v1/updates/device
```

Initiates a firmware update for a specific device.

**Request Body:**

```json
{
  "ip": "192.168.1.100",
  "username": "admin",
  "password": "secret",
  "check_only": false
}
```

**Response Example:**

```json
{
  "ip": "192.168.1.100",
  "success": true,
  "message": "Update successful",
  "current_version": "12.4.0",
  "latest_version": "12.4.0",
  "needs_update": false
}
```

#### Update All Devices

```
POST /api/v1/updates/all
```

Initiates firmware updates for all configured devices.

**Request Body:**

```json
{
  "check_only": false
}
```

**Response Example:**

```json
{
  "results": [
    {
      "ip": "192.168.1.100",
      "success": true,
      "message": "Update successful",
      "current_version": "12.4.0",
      "latest_version": "12.4.0",
      "needs_update": false
    },
    {
      "ip": "192.168.1.101",
      "success": false,
      "message": "Device is not reachable",
      "current_version": "Unknown",
      "latest_version": "12.4.0",
      "needs_update": true
    }
  ],
  "summary": {
    "total": 2,
    "success": 1,
    "needs_update": 1
  }
}
```

### Device Discovery

Discovery finds Tasmota devices on the network. It **never writes** the
configuration: the result is a list of suggestions, and adopting them into
`devices.yaml` goes through the regular editor endpoint.

Both searches run as background jobs, because a full range scan takes about
25 seconds and would otherwise block the single worker.

#### Get Scan Suggestions and Limits

```
GET /api/discovery
```

**Response Example:**

```json
{
  "suggested_networks": ["192.168.1.0/24"],
  "limits": {"max_prefix": 22, "max_hosts": 1024}
}
```

`suggested_networks` is a *guess*: the app can determine which interface would
carry the traffic, but not that interface's prefix length, so `/24` is assumed.
Treat it as a prefill, not as a fact — correct it if your network is larger.

#### Start a Discovery Job

```
POST /api/discovery
```

**Request Body:**

```json
{"method": "scan", "network": "192.168.1.0/24"}
```

or

```json
{"method": "mdns"}
```

**Response Example (202 Accepted):**

```json
{"job_id": "3f2a9c1e...", "status_url": "/api/jobs/3f2a9c1e..."}
```

The scan target is validated server-side and cannot be widened by the client:
private IPv4 only, prefix `>= 22`, no loopback, link-local or multicast. A host
address with a prefix (`192.168.1.55/24`) is normalised to its network. A
rejected target returns `400` with the reason in `details`.

**Status codes:** `202` accepted · `400` unknown method or disallowed network ·
`409` a discovery job is already running · `415` body was not JSON.

#### Poll a Discovery Job

```
GET /api/jobs/{job_id}
```

**Response Example:**

```json
{
  "job_id": "3f2a9c1e...",
  "kind": "discovery",
  "method": "scan",
  "status": "completed",
  "completed": 254,
  "total": 254,
  "results": [
    {
      "ip": "192.168.1.42",
      "hostname": "tasmota-1234",
      "friendly_name": "Hallway Light",
      "module": "ESP8266EX",
      "firmware_version": "14.2.0(release-tasmota)",
      "mac": "AA:BB:CC:DD:EE:FF",
      "requires_auth": false,
      "already_configured": false
    }
  ],
  "notice": null,
  "error": null
}
```

Notes on the fields:

- `total` is `null` for `mdns`: that search listens rather than working through
  a list, so there is no total to report and none is invented.
- `requires_auth` marks a device that answered with HTTP 401. Discovery never
  sends credentials — not even ones already stored — so this is a result, not a
  reason for a second attempt. Add the credentials in the editor after adopting
  the device.
- `already_configured` marks an address that is already in `devices.yaml`.
- `notice` carries an explanation when an empty result would otherwise mislead.
  An mDNS run that finds nothing in a bridge-network container says so, rather
  than implying that no devices exist.

## Error Handling

The API uses standard HTTP status codes to indicate the success or failure of requests:

- **200 OK**: The request was successful
- **400 Bad Request**: The request was invalid or cannot be served
- **404 Not Found**: The requested resource does not exist
- **500 Internal Server Error**: An error occurred on the server

Error responses include a JSON object with an error message:

```json
{
  "error": "Device not found"
}
```

## Integration Examples

### cURL

```bash
# Get all devices
curl -X GET http://localhost:5001/api/v1/devices

# Update a device
curl -X POST http://localhost:5001/api/v1/updates/device \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}'
```

### Python

```python
import requests

# Get all devices
response = requests.get("http://localhost:5001/api/v1/devices")
devices = response.json()["devices"]

# Update a device
response = requests.post(
    "http://localhost:5001/api/v1/updates/device",
    json={"ip": "192.168.1.100"}
)
result = response.json()
```

## Next Steps

- [Configuration Options](configuration.md)
- [Troubleshooting](troubleshooting.md)
- [Contributing Guide](contributing.md)

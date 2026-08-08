# API Documentation

The Tasmota Remote Updater provides a REST API that allows you to integrate its functionality into your own applications or automation systems.

## API Overview

The API is built using Flask-RESTful and is documented using Swagger/OpenAPI. You can access the interactive API documentation at http://localhost:5001/apidocs/ when the web application is running. That page is generated from the code and is therefore the authoritative reference if it ever disagrees with this document.

## Base URL

All API endpoints are relative to the base URL of your Tasmota Remote Updater installation:

```
http://localhost:5001
```

There is **no `/api/v1` prefix.** Endpoints live directly under `/api/`, and the application version is not part of the URL — query `/version` for it.

## Version Information

You can retrieve the current version of the application using the version endpoint. It needs no authentication:

```
GET /version
```

Example response:

```json
{
  "name": "Tasmota Updater",
  "version": "0.5.4"
}
```

## Health Check

For container orchestration. Needs no authentication:

```
GET /health
```

```json
{"status": "healthy"}
```

## Authentication

**Every `/api/*` endpoint requires authentication.** The gate is fail-closed: a request that presents neither credential is rejected with `401`, no exceptions.

There are two ways in:

1. **Session cookie (the bundled web UI).** Loading `GET /` sets a signed, HttpOnly, `SameSite=Strict` session cookie. The UI's own requests carry it automatically. Because the cookie is `SameSite=Strict`, a cross-site request cannot send it, which is what makes the API CSRF-safe.
2. **`X-API-Key` header (programmatic clients).** Set the `API_KEY` environment variable to a strong value, then send it as `X-API-Key`. If `API_KEY` is unset, this route is disabled entirely and only the UI session works.

```bash
curl -H "X-API-Key: your-key-here" http://localhost:5001/api/devices
```

Two further rules apply to every state-changing request:

- **The body must be JSON.** A `POST` or `PUT` without `Content-Type: application/json` is rejected with `415`.
- **CORS defaults to same-origin.** Set `CORS_ORIGINS` to allow cross-origin clients.

> **Note:** `SESSION_COOKIE_SECURE` defaults to `false` so the UI works over plain HTTP on a LAN. Set it to `true` when you serve the app behind HTTPS.

## Endpoints

### Device Management

#### List All Devices

```
GET /api/devices
```

Returns all configured devices — the *operational* view, enriched for display.

**Response Example:**

```json
{
  "devices": [
    {
      "ip": "192.168.1.100",
      "username": "admin",
      "password": "********",
      "dns_name": "hallway.local"
    }
  ]
}
```

> **Do not write this response back as configuration.** The password is masked to `********`, and `dns_name` is the *resolved* name, falling back to the IP itself when nothing resolves. Round-tripping it would destroy stored passwords and write `dns_name: 192.168.1.100` into every device that has no name. Use `/api/config/devices` for editing.

#### Get Device Status

```
GET /api/devices/{device_ip}
```

Returns the status of a specific device, including its current firmware version.

**Response Example:**

```json
{
  "ip": "192.168.1.100",
  "version": "12.0.2",
  "core_version": "2.7.4.9",
  "sdk_version": "3.0.2",
  "is_minimal": false
}
```

### Device Configuration

The editing counterpart to `/api/devices`: raw configured fields, no enrichment. This is what the web UI's device editor uses, and it is the only path that writes `devices.yaml`.

#### Read the Configuration

```
GET /api/config/devices
```

**Response Example:**

```json
{
  "devices": [
    {
      "ip": "192.168.1.100",
      "username": "admin",
      "has_password": true,
      "dns_name": "hallway",
      "timeout": 240
    }
  ],
  "writable": true,
  "devices_file": "/app/config/devices.yaml"
}
```

Passwords are never sent back — `has_password` reports only whether one is stored. `writable` is `false` when the file cannot be replaced atomically (see [Container Setup](container-setup.md) on directory mounts).

#### Replace the Configuration

```
PUT /api/config/devices
```

**Request Body:**

```json
{
  "devices": [
    {"ip": "192.168.1.100", "username": "admin", "dns_name": "hallway", "timeout": 240}
  ]
}
```

The submitted list decides membership: a device missing from it is deleted. Fields the editor does not manage (`fake`, cached `firmware_info`) are preserved from the existing entry, matched by IP.

Password handling is deliberate:

- **omit `password`** → the stored one is kept
- **send `password`** → it replaces the stored one
- **send `remove_password: true`** → the stored one is deleted

Each write is atomic and keeps one backup generation as `devices.yaml.bak`.

**Status codes:** `200` written (returns the stored configuration) · `400` validation failed · `409` the file is not writable or not readable · `415` body was not JSON.

### Firmware Management

#### Get Latest Release Information

```
GET /api/releases/latest
```

Returns information about the latest Tasmota firmware release.

**Response Example:**

```json
{
  "version": "15.5.0",
  "release_date": "2026-06-22",
  "release_notes": "# RELEASE NOTES\n\n## Migration Information …",
  "download_url": "https://github.com/arendst/Tasmota/releases/download/v15.5.0/tasmota.bin",
  "release_url": "https://github.com/arendst/Tasmota/releases/"
}
```

`release_notes` carries the full upstream release notes and is long — expect tens of kilobytes.

### Update Operations

#### Update Device

```
POST /api/update
```

Initiates a firmware update for a specific device. This one is **synchronous** — it returns when the update has been verified or has failed.

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
  "current_version": "15.5.0",
  "latest_version": "15.5.0",
  "needs_update": false
}
```

> **Set your client timeout above the server's.** A Tasmota device answers `Upgrade 1` with HTTP 200 *immediately* while still running the old firmware, and reboots seconds to minutes later. The server therefore polls until the reported version actually changes before calling the update a success. Its total budget defaults to 240 s — your client must wait longer than that, or you will time out on an update that is still succeeding.

#### Update All Devices

```
POST /api/update/all
```

Starts firmware updates for all configured devices. **Asynchronous:** a batch can take many minutes, which would block the single worker and trip the request timeout, so this returns immediately and you poll for progress.

**Request Body:**

```json
{
  "check_only": false,
  "update_only_needed": true,
  "timeout": 240
}
```

**Response Example (202 Accepted):**

```json
{"job_id": "3f2a9c1e...", "status_url": "/api/jobs/3f2a9c1e..."}
```

**Status codes:** `202` accepted · `409` a batch update is already running · `415` body was not JSON.

Only one batch update runs at a time. A running *discovery* job does not block it, and vice versa — the two are tracked separately.

#### Poll a Job

```
GET /api/jobs/{job_id}
```

Works for both batch updates (`kind: "batch"`) and discovery (`kind: "discovery"`).

**Response Example:**

```json
{
  "job_id": "3f2a9c1e...",
  "kind": "batch",
  "status": "running",
  "total": 4,
  "completed": 2,
  "failed": 0,
  "results": [
    {
      "ip": "192.168.1.100",
      "success": true,
      "message": "Update successful",
      "current_version": "15.5.0",
      "latest_version": "15.5.0",
      "needs_update": false,
      "update_started": true,
      "update_completed": true
    }
  ],
  "summary": null,
  "error": null
}
```

`status` is one of `pending`, `running`, `completed`, `error`. `results` fills in as devices finish, so you can show progress. `summary` stays `null` until the job completes.

> **`needs_update: false` does not always mean "up to date".** It also means "could not compare" — a failed release lookup reports `latest_version: "Unknown"`. Decide on `latest_version`, not on `success`: a failed *update* still carries a known latest version.

Jobs are kept in memory (at most 50, oldest finished ones pruned) and do not survive a restart.

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

Same endpoint and same mechanics as a batch job — see [Poll a Job](#poll-a-job) above. A discovery job carries `kind: "discovery"` plus `method` and `notice`:

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
- **202 Accepted**: A background job was started; poll `status_url` for progress
- **400 Bad Request**: The request was invalid or cannot be served
- **401 Unauthorized**: Neither a UI session cookie nor a valid `X-API-Key` was presented
- **404 Not Found**: The requested resource does not exist
- **409 Conflict**: A job of that kind is already running, or the configuration file is not writable
- **415 Unsupported Media Type**: The body was not `Content-Type: application/json`
- **500 Internal Server Error**: An error occurred on the server

Error responses include a JSON object with an error message, and usually a `details` field with the specific reason:

```json
{
  "error": "Bad Request",
  "details": "Only private networks can be scanned, so the scanner cannot be pointed at the public internet."
}
```

## Integration Examples

Both examples assume `API_KEY` is set in the application's environment.

### cURL

```bash
KEY="your-api-key"

# Get all devices
curl -H "X-API-Key: $KEY" http://localhost:5001/api/devices

# Update a single device (synchronous — allow more than the server's 240s budget)
curl -X POST http://localhost:5001/api/update \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.1.100"}' \
  --max-time 300

# Update all devices (asynchronous)
JOB=$(curl -s -X POST http://localhost:5001/api/update/all \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"update_only_needed": true}' | jq -r .job_id)

curl -H "X-API-Key: $KEY" "http://localhost:5001/api/jobs/$JOB"
```

### Python

```python
import time
import requests

BASE = "http://localhost:5001"
HEADERS = {"X-API-Key": "your-api-key"}

# Get all devices
devices = requests.get(f"{BASE}/api/devices", headers=HEADERS).json()["devices"]

# Update a single device. The device answers the flash command immediately and
# reboots later, so the server keeps polling until the version really changed —
# the client timeout has to sit above the server's own budget.
result = requests.post(
    f"{BASE}/api/update",
    headers=HEADERS,
    json={"ip": "192.168.1.100"},
    timeout=300,
).json()

# Update all devices, then poll until the job finishes
job_id = requests.post(
    f"{BASE}/api/update/all",
    headers=HEADERS,
    json={"update_only_needed": True},
).json()["job_id"]

while True:
    job = requests.get(f"{BASE}/api/jobs/{job_id}", headers=HEADERS).json()
    if job["status"] in ("completed", "error"):
        break
    print(f"{job['completed']}/{job['total']}")
    time.sleep(2)
```

> For scheduled checks and updates you usually do not need the API at all — the bundled CLI (`python -m app.cli`) drives the same code and reports its outcome through exit codes. See [Command-Line Usage](cli-usage.md).

## Next Steps

- [Configuration Options](configuration.md)
- [Troubleshooting](troubleshooting.md)
- [Contributing Guide](contributing.md)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tasmota Remote Updater is a Python Flask application that allows remote updating of multiple Tasmota devices via CLI, web interface, and REST API. The application follows a modular architecture with separate components for core functionality, web interface, and API endpoints.

## Core Architecture

### Application Structure
- **Entry Points**:
  - `server.py`: Flask web application with Swagger API documentation
  - `tasmota_updater.py`: Command-line interface — **DEPRECATED** (stub only; use web UI / REST API)
  - `wsgi.py`: WSGI entry point for production deployment

- **Core Module** (`app/tasmota/`):
  - `updater.py`: Core Tasmota device update functionality
  - `api.py`: Flask-RESTful API endpoints
  - `utils.py`: Shared utility functions
  - `cache/`: GitHub API response caching

- **Configuration**: YAML-based device configuration with support for authentication and fake devices for testing

### Key Design Patterns
- **Modular separation**: CLI logic extracted from web application into reusable modules
- **Security-first**: Credential sanitization in logs, no sensitive data exposure
- **Fake device support**: Development mode with simulated devices for testing
- **Environment-based configuration**: `.env` files for different deployment scenarios

## Development Commands

### Running the Application
```bash
# Development server (default port 5001)
python server.py

# With fake devices for development
ENV_FILE=.env.dev python server.py

# CLI interface
python tasmota_updater.py -f devices.yaml

# CLI dry run mode
python tasmota_updater.py --dry-run

# Check firmware versions only
python tasmota_updater.py --check-only
```

### Environment Setup
```bash
# Using uv (recommended)
uv venv
uv pip install -r requirements.txt

# Traditional venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### Documentation
```bash
# Build documentation (MkDocs)
mkdocs serve   # Development server
mkdocs build   # Static build
```

### Testing and Development
```bash
# Development with fake devices
ENV_FILE=.env.dev python server.py

# Test CLI with dry run
python tasmota_updater.py --dry-run

# Example configuration generation
python tasmota_updater.py --example
```

## Configuration Files

### Device Configuration
- `devices.yaml`: Production device list
- `devices-dev.yaml`: Development devices with `fake: true` flag
- Environment files (`.env`, `.env.dev`) control which device file is loaded

### Fake Device Structure
```yaml
devices:
  - ip: 192.168.100.101
    username: admin
    password: password
    fake: true
    dns_name: fake-tasmota-light1.local
    firmware_info:
      version: "12.0.2"
      core_version: "2.7.4.9"
      sdk_version: "3.0.2"
      is_minimal: false
```

## Important Implementation Details

### Version Management
- `app/version.py` `__version__` is canonical (served at `/version`), managed by **release-please** — do not hand-edit (it also bumps `pyproject.toml` + `app/__init__.py`)
- Releases are automated: merge conventional commits → release-please opens a `chore(main): release x.y.z` PR → merging it tags + publishes the container image

### Security Considerations
- All password/credential logging is sanitized via `sanitize_log_data()`
- Authentication credentials never appear in logs
- URL passwords masked in log output
- Follows OWASP security logging guidelines

### API Structure
- Flask-RESTful with Swagger documentation at `/apidocs/`
- Access control is **fail-closed**: `/api/*` needs a UI session cookie (set on `GET /`) or `X-API-Key`; CORS defaults to same-origin; state-changing POSTs require JSON
- Health check endpoint at `/health` for container orchestration
- Marshmallow schemas for request/response validation

### Container Deployment
- Multi-stage Containerfile for production builds
- Gunicorn WSGI server in production
- Docker Compose support with volume mounts for configuration
- Published to both Docker Hub and GitHub Container Registry

## Development Workflow

When making changes:
1. Use fake devices for testing (`ENV_FILE=.env.dev python server.py`)
2. Run the green test core (see below) + the Playwright e2e job
3. Verify API endpoints via Swagger UI
4. Use conventional commit messages (release-please derives the version)
5. Update documentation in `docs/` directory as needed

## CI, Testing & Gotchas

- **Tests:** `pyproject.toml` is the single pytest config (don't add a second). Green core: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`. `stale` = outdated-vs-code tests (excluded; backlog #63).
- **E2E:** `tests/e2e/` = pytest-playwright against a subprocess app with fake devices (`DEVICES_FILE=devices-dev.yaml`); separate CI job (chromium cached at `~/.cache/ms-playwright`).
- **Required checks on `main`:** CodeQL + `pytest (3.10/3.11/3.12)` (e2e not yet required).
- **release-please:** squash-merge PR titles MUST be valid conventional commits or no release is cut. Release PRs are bot-authored → approve their `action_required` Tests run (`gh api -X POST repos/<r>/actions/runs/<id>/approve`) before required checks report; if a bot-PR's later pushes don't trigger CI, `gh pr close` + `gh pr reopen` re-triggers it.
- **CI flakiness:** a runner job occasionally sticks in `in_progress` while its run shows `completed` → re-run just that job with `gh run rerun --job <id>`.
- **Runtime:** single gthread Gunicorn worker (`gunicorn.conf.py`) required — the batch-job store (`app/tasmota/jobs.py`) is in-memory. Batch updates async: `POST /api/update/all` → `202 {job_id}`, poll `GET /api/jobs/<id>`; single `POST /api/update` still sync. `SESSION_COOKIE_SECURE=false` for plain-HTTP LAN.
- **Frontend/UI:** after a device-changing action, refresh `device.status` via `fetchDeviceStatus()`/`refreshDevices()` — updating only `device.update_status` leaves the card's version/tag stale (fix #84). The batch path already re-fetches via `refreshDevices()`.
- **Env:** corporate TLS proxy blocks external npm/CDN fetches (no release-please dry-run, no SRI/`playwright install` from scratch); pip/uv work.

The application supports development without physical Tasmota devices through the fake device system, allowing full feature testing in isolation.
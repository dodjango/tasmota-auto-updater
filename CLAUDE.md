# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tasmota Remote Updater is a Python Flask application that allows remote updating of multiple Tasmota devices via a web interface and a REST API. The application follows a modular architecture with separate components for core functionality, web interface, and API endpoints. (A CLI existed but is deprecated — see below.)

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
- **Modular separation**: the update logic lives in `app/tasmota` and is shared by the web UI and the API (no duplicated copies — that duplication is exactly what killed the CLI)
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
```

There is **no working CLI**. `tasmota_updater.py` is a deprecation stub that
prints a notice to stderr and exits 1 — `-f/--file`, `--dry-run`,
`--check-only`, `--update-all` and `--example` are all gone. For scripting, use
the REST API (`POST /api/update`, `POST /api/update/all`, `GET /api/jobs/<id>`).
Re-introducing a thin CLI over `app/tasmota` is a backlog item.

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

# Green test core (see "CI, Testing & Gotchas" below)
pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"

# Playwright e2e suite (needs a GITHUB_TOKEN to avoid GitHub API rate limits)
pytest tests/e2e -m e2e -o addopts=""
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
- Device credentials go in the request's `auth` (`build_device_auth()`), never in the URL — `build_device_url()` deliberately returns a credential-free URL. Re-embedding `user:pass@host` breaks passwords containing `:`/`@` and makes CodeQL taint every device response, so any logged firmware version reports as clear-text password logging. `sanitize_log_data()`'s URL masking is the second line of defence, not the first.
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
6. **Check `README.md` before opening any PR** — including Dependabot/Renovate PRs, where it should be reviewed together with the maintainer. It drifts unnoticed because nothing in a normal diff touches it: a dependency bump can silently invalidate a badge or a minimum version, and broken markdown never fails a test. Verify code fences are balanced (`grep -c '^```' README.md` must be even), plus badges, the clone URL, ports, commands, and that deprecated paths aren't presented as current. Careful when "correcting" names: the container images really are `dodjango/tasmota-updater` (both registries, see `publish-container.yml`) while the *git* repo is `dodjango/tasmota-auto-updater`.

## CI, Testing & Gotchas

- **Tests:** `pyproject.toml` is the single pytest config (don't add a second). Green core: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`. `stale` = outdated-vs-code tests (excluded; backlog #63).
- **E2E:** `tests/e2e/` = pytest-playwright against a subprocess app with fake devices (`DEVICES_FILE=devices-dev.yaml`); separate CI job (chromium cached at `~/.cache/ms-playwright`). Needs `GITHUB_TOKEN`: the app resolves the latest Tasmota release live on every start (its cache is gitignored, so CI is always cold) and unauthenticated it hits 60 req/h per IP — on a 403 no device "needs" an update and the update-flow tests fail with a misleading timeout. The suite also assumes the real latest version is newer than the fake devices'; prefer stubbing the check via `page.route` (#76).
- **Required checks on `main`:** CodeQL + `pytest (3.10/3.11/3.12)` (e2e not yet required).
- **Tasmota OTA:** `Upgrade 1` returns HTTP 200 *immediately* and flashes in the background while still serving the OLD firmware; the reboot follows seconds-to-minutes later. Reachability is NOT completion — `verify_firmware_version_changed()` polls until the reported version actually changes before success is reported (#87). The client timeout for `POST /api/update` must stay above the server's `total_timeout` (default 240s).
- **release-please:** squash-merge PR titles MUST be valid conventional commits or no release is cut. Release PRs are authored by the `tasmota-updater-release-bot` GitHub App (`vars.RELEASE_APP_CLIENT_ID` + `secrets.RELEASE_APP_PRIVATE_KEY`), so their checks run normally — see `docs/releasing.md`. Without it the PR is `GITHUB_TOKEN`-authored and its Tests run parks as `action_required`: the required checks are then **missing, not failing**, and `gh pr checks` looks all-green because it only lists checks that exist. If a bot-PR's later pushes don't trigger CI, `gh pr close` + `gh pr reopen` re-triggers it.
- **CI flakiness:** a runner job occasionally sticks in `in_progress` while its run shows `completed` → re-run just that job with `gh run rerun --job <id>`.
- **Runtime:** single gthread Gunicorn worker (`gunicorn.conf.py`) required — the batch-job store (`app/tasmota/jobs.py`) is in-memory. Batch updates async: `POST /api/update/all` → `202 {job_id}`, poll `GET /api/jobs/<id>`; single `POST /api/update` still sync. `SESSION_COOKIE_SECURE=false` for plain-HTTP LAN.
- **Frontend/UI:** after a device-changing action, refresh `device.status` via `fetchDeviceStatus()`/`refreshDevices()` — updating only `device.update_status` leaves the card's version/tag stale (fix #84). The batch path already re-fetches via `refreshDevices()`.
- **UI honesty:** `needs_update: false` also means "could not compare" (failed release lookup → `latest_version: "Unknown"`). Gate "Up to Date"/"Update Available" on `isVersionComparisonKnown(device)` — keyed on `latest_version`, NOT on `success`, because a failed *update* still carries a known latest version (#91).
- **Alpine + Playwright:** `x-show` only toggles `display`; elements stay in the DOM. Assert `to_be_visible()`/`to_be_hidden()`, never `to_have_count(0)`.
- **Misc:** a branch named `docs` exists, so `docs/…` branch names are rejected ("directory file conflict") → use `chore/…`. Verify doc links with `mkdocs build --strict`. For a CodeQL finding, pull the real dataflow path from the SARIF (`gh api …/code-scanning/analyses/<id> -H "Accept: application/sarif+json"` → `codeFlows`) instead of guessing at the taint source.
- **Env:** corporate TLS proxy blocks external npm/CDN fetches (no release-please dry-run, no SRI/`playwright install` from scratch); pip/uv work.

The application supports development without physical Tasmota devices through the fake device system, allowing full feature testing in isolation.
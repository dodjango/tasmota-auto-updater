# Devices Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manage the device list from the web UI — add, edit, delete — with `devices.yaml` remaining the source of truth.

**Architecture:** A new module `app/tasmota/device_config.py` owns reading, merging and atomically writing the device configuration. A new API resource `/api/config/devices` (GET/PUT) exposes it, deliberately separate from the operational `/api/devices`. A separate Alpine component in its own file drives the UI.

**Tech Stack:** Python 3.10+, Flask-RESTful, Marshmallow, PyYAML, Alpine.js 3, pytest, Playwright.

## Global Constraints

- Design document: [`2026-08-07-devices-editor-design.md`](2026-08-07-devices-editor-design.md). Read it before starting.
- **The password never leaves the server.** `GET` returns `has_password: true|false`, never the value.
- **The server does not write what the client sends.** It reads the file, merges the managed fields (`ip`, `username`, `password`, `dns_name`, `timeout`) over the existing entry matched by IP, and writes the result. Unmanaged fields (`fake`, `firmware_info`, anything a later version adds) survive untouched.
- A device absent from the payload is deleted. That is the only way to delete.
- `fake` and `firmware_info` are **not settable** through the API — `unknown = RAISE`.
- IP validation goes through the existing `is_valid_ip_address()`, which blocks loopback, link-local and 169.254.169.254. That block stays.
- Duplicate IPs are rejected.
- Writability check is `os.access(parent, W_OK) and not target.is_mount()` — the directory alone is not enough, because with a single-file bind mount the directory is writable while `os.replace()` fails with `EBUSY` at save time.
- Atomic write: temp file **in the same directory**, `fsync`, copy the previous version to `<name>.bak` (one generation only), then `os.replace()`.
- Style from `pyproject.toml`: line length 100, ruff with `PTH` (use `pathlib`), mypy `disallow_untyped_defs = true` — annotate every function.
- Every interactive element gets a tooltip starting with a verb; destructive actions get a warning and a confirmation (project frontend convention).
- No new runtime dependencies.

---

## File Structure

| File | Responsibility |
|---|---|
| Create `app/tasmota/device_config.py` | Read, merge and atomically write the device configuration file. ~120 lines. |
| Create `app/static/js/devices-editor.js` | The editor's Alpine component. Kept out of `app/static/js/app.js`, which is already 499 lines. |
| Modify `app/tasmota/api.py` | Add `DeviceConfigSchema` and the `DeviceConfigResource` (GET/PUT), register the route. |
| Modify `app/templates/index.html` | Editor section plus the new script tag. |
| Modify `compose.example.yml` | Directory mount instead of the single-file mount. |
| Create `tests/test_device_config.py` | Unit tests for writer and merge. |
| Create `tests/test_config_api.py` | Flask-test-client integration tests. |
| Create `tests/e2e/test_devices_editor.py` | Playwright flow, against its own app instance on a copy of the fixture. |
| Modify `docs/configuration.md`, `docs/container-setup.md`, `README.md` | Document the editor and the mount migration. |

---

### Task 1: Writability detection and the atomic write

**Files:**
- Create: `app/tasmota/device_config.py`
- Test: `tests/test_device_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_writable(target: Path) -> bool`, `write_devices(target: Path, devices: list[dict[str, Any]]) -> None`, `ConfigWriteError(Exception)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_device_config.py
"""Unit tests for reading, merging and writing the device configuration."""
from pathlib import Path

import pytest
import yaml

from app.tasmota import device_config


def test_is_writable_accepts_a_normal_file(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    assert device_config.is_writable(target) is True


def test_is_writable_accepts_a_missing_file_in_a_writable_directory(tmp_path):
    assert device_config.is_writable(tmp_path / "devices.yaml") is True


def test_is_writable_rejects_an_unwritable_directory(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    tmp_path.chmod(0o500)
    try:
        assert device_config.is_writable(target) is False
    finally:
        tmp_path.chmod(0o700)


def test_write_devices_replaces_the_file(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 1.1.1.1\n", encoding="utf-8")

    device_config.write_devices(target, [{"ip": "2.2.2.2"}])

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"devices": [{"ip": "2.2.2.2"}]}


def test_write_devices_keeps_one_backup_generation(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 1.1.1.1\n", encoding="utf-8")

    device_config.write_devices(target, [{"ip": "2.2.2.2"}])
    device_config.write_devices(target, [{"ip": "3.3.3.3"}])

    backup = yaml.safe_load((tmp_path / "devices.yaml.bak").read_text(encoding="utf-8"))
    assert backup == {"devices": [{"ip": "2.2.2.2"}]}, "the backup holds the previous version"


def test_write_devices_leaves_no_temp_file_behind(tmp_path):
    target = tmp_path / "devices.yaml"
    device_config.write_devices(target, [{"ip": "2.2.2.2"}])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.yaml"]


def test_write_devices_refuses_an_unwritable_target(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(device_config.ConfigWriteError):
            device_config.write_devices(target, [{"ip": "2.2.2.2"}])
    finally:
        tmp_path.chmod(0o700)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_device_config.py -v -o addopts=""`
Expected: FAIL — `ImportError: cannot import name 'device_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/tasmota/device_config.py
"""Read, merge and atomically write the device configuration file.

`devices.yaml` is the source of truth. This module is the only place that
writes it. It deliberately holds no HTTP or update logic.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigWriteError(Exception):
    """The device configuration could not be written."""


def is_writable(target: Path) -> bool:
    """Can we replace ``target`` atomically?

    Checking the directory alone is not enough. With a single-file bind mount
    the directory is writable while the file itself is a mount point, and
    ``os.replace()`` onto a mount point fails with EBUSY — at save time, long
    after the UI told the user everything was fine.
    """
    if not os.access(target.parent, os.W_OK):
        return False
    try:
        return not target.is_mount()
    except OSError:  # pragma: no cover - unreadable path, treat as not writable
        return False


def write_devices(target: Path, devices: list[dict[str, Any]]) -> None:
    """Replace the device file atomically, keeping one backup generation."""
    if not is_writable(target):
        raise ConfigWriteError(
            f"{target} is not writable. If the file is bind-mounted individually, "
            "mount its directory instead."
        )

    payload = yaml.safe_dump({"devices": devices}, sort_keys=False, allow_unicode=True)

    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".devices-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        os.replace(temp_path, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise ConfigWriteError(f"Could not write {target}: {exc}") from exc
```

Note `target.with_suffix(target.suffix + ".bak")` yields `devices.yaml.bak`, not
`devices.bak` — `with_suffix` replaces the last suffix, so the current one is
concatenated deliberately.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_device_config.py -v -o addopts=""`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/device_config.py tests/test_device_config.py
git commit -m "feat(config): add atomic device-config writer with writability detection"
```

---

### Task 2: The merge rule

**Files:**
- Modify: `app/tasmota/device_config.py`
- Test: `tests/test_device_config.py`

**Interfaces:**
- Consumes: nothing from Task 1 beyond the module.
- Produces: `MANAGED_FIELDS: tuple[str, ...]`, `merge_devices(existing: list[dict[str, Any]], submitted: list[dict[str, Any]]) -> list[dict[str, Any]]`.

This is the heart of the feature. The submitted list wins on order and
membership; the existing entries contribute everything the editor does not
manage.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_device_config.py


def test_merge_keeps_the_existing_password_when_none_is_submitted():
    existing = [{"ip": "1.1.1.1", "password": "secret", "username": "admin"}]
    submitted = [{"ip": "1.1.1.1", "username": "admin"}]
    assert device_config.merge_devices(existing, submitted) == [
        {"ip": "1.1.1.1", "username": "admin", "password": "secret"}
    ]


def test_merge_replaces_a_submitted_password():
    existing = [{"ip": "1.1.1.1", "password": "old"}]
    submitted = [{"ip": "1.1.1.1", "password": "new"}]
    assert device_config.merge_devices(existing, submitted) == [
        {"ip": "1.1.1.1", "password": "new"}
    ]


def test_merge_removes_the_password_on_request():
    existing = [{"ip": "1.1.1.1", "password": "old"}]
    submitted = [{"ip": "1.1.1.1", "remove_password": True}]
    assert device_config.merge_devices(existing, submitted) == [{"ip": "1.1.1.1"}]


def test_merge_never_writes_the_control_field():
    existing = [{"ip": "1.1.1.1"}]
    submitted = [{"ip": "1.1.1.1", "remove_password": False}]
    assert "remove_password" not in device_config.merge_devices(existing, submitted)[0]


def test_merge_preserves_unmanaged_fields():
    existing = [
        {"ip": "1.1.1.1", "fake": True, "firmware_info": {"version": "12.0.2"}, "future": 1}
    ]
    submitted = [{"ip": "1.1.1.1", "dns_name": "flur"}]
    assert device_config.merge_devices(existing, submitted) == [
        {
            "ip": "1.1.1.1",
            "fake": True,
            "firmware_info": {"version": "12.0.2"},
            "future": 1,
            "dns_name": "flur",
        }
    ]


def test_merge_deletes_a_device_absent_from_the_payload():
    existing = [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}]
    submitted = [{"ip": "1.1.1.1"}]
    assert device_config.merge_devices(existing, submitted) == [{"ip": "1.1.1.1"}]


def test_merge_treats_a_changed_ip_as_a_new_device():
    """The password cannot follow an IP change — there is nothing to match on."""
    existing = [{"ip": "1.1.1.1", "password": "secret", "fake": True}]
    submitted = [{"ip": "9.9.9.9"}]
    assert device_config.merge_devices(existing, submitted) == [{"ip": "9.9.9.9"}]


def test_merge_adds_a_new_device():
    existing = [{"ip": "1.1.1.1"}]
    submitted = [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2", "username": "admin"}]
    assert device_config.merge_devices(existing, submitted) == [
        {"ip": "1.1.1.1"},
        {"ip": "2.2.2.2", "username": "admin"},
    ]


def test_merge_drops_a_managed_field_the_client_cleared():
    existing = [{"ip": "1.1.1.1", "dns_name": "old", "timeout": 240}]
    submitted = [{"ip": "1.1.1.1"}]
    result = device_config.merge_devices(existing, submitted)
    assert "dns_name" not in result[0], "a cleared managed field is removed"
    assert "timeout" not in result[0]


def test_merge_follows_the_submitted_order():
    existing = [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}]
    submitted = [{"ip": "2.2.2.2"}, {"ip": "1.1.1.1"}]
    assert [d["ip"] for d in device_config.merge_devices(existing, submitted)] == [
        "2.2.2.2",
        "1.1.1.1",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_device_config.py -v -o addopts=""`
Expected: FAIL — `AttributeError: module 'app.tasmota.device_config' has no attribute 'merge_devices'`

- [ ] **Step 3: Write minimal implementation**

```python
MANAGED_FIELDS = ("ip", "username", "password", "dns_name", "timeout")


def merge_devices(
    existing: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge the editor's view over the configuration on disk.

    The submitted list decides membership and order; a device missing from it is
    deleted. Everything this module does not manage — ``fake``,
    ``firmware_info``, fields a later version introduces — is carried over from
    the existing entry, matched by IP. A password is only replaced when one is
    submitted, and only removed on explicit request.
    """
    by_ip = {device.get("ip"): device for device in existing}
    merged: list[dict[str, Any]] = []

    for entry in submitted:
        current = dict(by_ip.get(entry.get("ip"), {}))
        remove_password = bool(entry.get("remove_password"))

        for field in MANAGED_FIELDS:
            if field == "password":
                continue
            if entry.get(field) not in (None, ""):
                current[field] = entry[field]
            else:
                current.pop(field, None)

        if entry.get("password"):
            current["password"] = entry["password"]
        elif remove_password:
            current.pop("password", None)

        current.pop("remove_password", None)
        merged.append(current)

    return merged
```

Note the `ip` field is in `MANAGED_FIELDS` and always present after validation,
so the loop sets it from the submitted entry — which is what makes a changed IP
produce a fresh device.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_device_config.py -v -o addopts=""`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/device_config.py tests/test_device_config.py
git commit -m "feat(config): merge submitted devices over the existing configuration"
```

---

### Task 3: Validation schema

**Files:**
- Modify: `app/tasmota/api.py`
- Test: `tests/test_config_api.py`

**Interfaces:**
- Consumes: `is_valid_ip_address` from `app.tasmota.updater` (already imported in `api.py`; check the existing import block and add it there if missing).
- Produces: `DeviceConfigSchema` (Marshmallow, `unknown = RAISE`), `validate_device_list(devices: list[dict]) -> list[str]` returning human-readable errors (empty when valid).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_api.py
"""Validation and API behaviour for the device-configuration editor."""
import pytest

from app.tasmota import api


def test_schema_accepts_a_minimal_device():
    assert api.DeviceConfigSchema().load({"ip": "192.168.8.191"}) == {"ip": "192.168.8.191"}


def test_schema_accepts_every_managed_field():
    payload = {
        "ip": "192.168.8.191",
        "username": "admin",
        "password": "secret",
        "dns_name": "flur",
        "timeout": 240,
        "remove_password": False,
    }
    assert api.DeviceConfigSchema().load(payload) == payload


@pytest.mark.parametrize("field", ["fake", "firmware_info"])
def test_schema_rejects_unsettable_fields(field):
    from marshmallow import ValidationError

    with pytest.raises(ValidationError):
        api.DeviceConfigSchema().load({"ip": "192.168.8.191", field: True})


@pytest.mark.parametrize("ip", ["not-an-ip", "127.0.0.1", "169.254.169.254", ""])
def test_schema_rejects_bad_or_blocked_addresses(ip):
    from marshmallow import ValidationError

    with pytest.raises(ValidationError):
        api.DeviceConfigSchema().load({"ip": ip})


@pytest.mark.parametrize("timeout", [59, 601])
def test_schema_rejects_out_of_range_timeouts(timeout):
    from marshmallow import ValidationError

    with pytest.raises(ValidationError):
        api.DeviceConfigSchema().load({"ip": "192.168.8.191", "timeout": timeout})


def test_validate_device_list_reports_duplicate_ips():
    errors = api.validate_device_list([{"ip": "192.168.8.191"}, {"ip": "192.168.8.191"}])
    assert any("192.168.8.191" in message for message in errors)


def test_validate_device_list_accepts_distinct_devices():
    assert api.validate_device_list([{"ip": "192.168.8.191"}, {"ip": "192.168.8.192"}]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: FAIL — `AttributeError: module 'app.tasmota.api' has no attribute 'DeviceConfigSchema'`

- [ ] **Step 3: Write minimal implementation**

Add to the imports in `app/tasmota/api.py` (check what is already imported from
`app.tasmota.updater` and extend that line rather than adding a second import):

```python
from marshmallow import Schema, ValidationError, fields, validate, validates_schema
from app.tasmota.updater import is_valid_ip_address
```

Then, next to the existing schemas:

```python
def _validate_device_ip(value: str) -> None:
    """Reject anything is_valid_ip_address() rejects.

    That function deliberately blocks loopback, link-local and the cloud
    metadata address — the same block that keeps the update endpoints from
    being turned into an SSRF primitive. The editor must not be a way around it.
    """
    if not is_valid_ip_address(value):
        raise ValidationError(f"Not a usable device address: {value!r}")


class DeviceConfigSchema(Schema):
    """One device as the editor may submit it."""

    ip = fields.String(required=True, validate=_validate_device_ip)
    username = fields.String()
    password = fields.String()
    dns_name = fields.String()
    timeout = fields.Integer(validate=validate.Range(min=60, max=600))
    remove_password = fields.Boolean()

    class Meta:
        unknown = "raise"


def validate_device_list(devices: list) -> list:
    """List-level checks that a per-device schema cannot express."""
    errors = []
    seen = set()
    for device in devices:
        ip = device.get("ip")
        if ip in seen:
            errors.append(f"Duplicate device address: {ip}")
        seen.add(ip)
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: PASS (13 tests)

If `Meta.unknown = "raise"` does not reject unknown fields on your Marshmallow
version, use `from marshmallow import RAISE` and `unknown = RAISE` — the string
form is accepted from Marshmallow 3.0 onward, and this project pins
`marshmallow>=4.0.1`, so it should work. Report which form you used.

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/api.py tests/test_config_api.py
git commit -m "feat(api): validate device-configuration payloads"
```

---

### Task 4: `GET /api/config/devices`

**Files:**
- Modify: `app/tasmota/api.py`
- Test: `tests/test_config_api.py`

**Interfaces:**
- Consumes: `device_config.is_writable`, `load_devices_from_file`.
- Produces: `DeviceConfigResource` with a `get()` method, registered at `/api/config/devices`.

The response must carry the **raw configured** fields. Do not resolve DNS names
and do not reuse `DeviceListResource`'s enrichment — it overwrites `dns_name`
with the IP when nothing resolves, which round-tripped would pollute the file.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config_api.py
from pathlib import Path


@pytest.fixture
def config_app(tmp_path, monkeypatch):
    """A Flask test client whose devices file lives in a writable tmp dir."""
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text(
        "devices:\n"
        "- ip: 192.168.8.191\n"
        "  username: admin\n"
        "  password: secret\n"
        "  fake: true\n"
        "- ip: 192.168.8.192\n",
        encoding="utf-8",
    )
    from server import create_app

    # create_app() takes no arguments — the project's pattern is to construct it
    # and then override config, exactly as tests/conftest.py's `app` fixture does.
    application = create_app()
    application.config.update({"TESTING": True, "DEVICES_FILE": str(devices_file)})
    with application.test_client() as client:
        with client.session_transaction() as session:
            session["ui"] = True
        yield client, devices_file


def test_get_config_masks_the_password(config_app):
    client, _ = config_app
    payload = client.get("/api/config/devices").get_json()
    first = payload["devices"][0]
    assert first["has_password"] is True
    assert "password" not in first
    assert payload["devices"][1]["has_password"] is False


def test_get_config_returns_raw_fields_without_dns_resolution(config_app):
    client, _ = config_app
    payload = client.get("/api/config/devices").get_json()
    assert "dns_name" not in payload["devices"][1], (
        "a device without a configured dns_name must not get one invented"
    )


def test_get_config_reports_writability_and_path(config_app):
    client, devices_file = config_app
    payload = client.get("/api/config/devices").get_json()
    assert payload["writable"] is True
    assert payload["devices_file"] == str(devices_file)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: FAIL — 404, the route does not exist yet.

If the session-cookie trick in the fixture does not authenticate, read
`server.py`'s `_require_api_auth` and use whatever it accepts (an `X-API-Key`
header with `API_KEY` set in the app config is the alternative). Report what you
used.

- [ ] **Step 3: Write minimal implementation**

```python
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
            entry = {
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
```

Add `from pathlib import Path` and `from app.tasmota import device_config` to the
imports, and register the route in `init_api`:

```python
    api.add_resource(DeviceConfigResource, '/api/config/devices')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/api.py tests/test_config_api.py
git commit -m "feat(api): expose the raw device configuration for editing"
```

---

### Task 5: `PUT /api/config/devices`

**Files:**
- Modify: `app/tasmota/api.py`
- Test: `tests/test_config_api.py`

**Interfaces:**
- Consumes: `DeviceConfigSchema`, `validate_device_list`, `device_config.merge_devices`, `device_config.write_devices`, `device_config.ConfigWriteError`.
- Produces: a `put()` method on `DeviceConfigResource`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config_api.py
import yaml


def test_put_writes_the_merged_list(config_app):
    client, devices_file = config_app
    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191", "username": "admin", "dns_name": "flur"},
    ]})
    assert response.status_code == 200

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert written == [{
        "ip": "192.168.8.191", "username": "admin", "dns_name": "flur",
        "password": "secret", "fake": True,
    }], "password and fake survive; the second device was deleted"


def test_put_rejects_a_non_json_body(config_app):
    client, _ = config_app
    assert client.put("/api/config/devices", data="devices: []").status_code == 415


def test_put_rejects_an_invalid_device(config_app):
    client, devices_file = config_app
    before = devices_file.read_text(encoding="utf-8")
    response = client.put("/api/config/devices", json={"devices": [{"ip": "127.0.0.1"}]})
    assert response.status_code == 400
    assert devices_file.read_text(encoding="utf-8") == before, "nothing is written on error"


def test_put_rejects_duplicate_ips(config_app):
    client, _ = config_app
    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191"}, {"ip": "192.168.8.191"},
    ]})
    assert response.status_code == 400


def test_put_rejects_unknown_fields(config_app):
    client, _ = config_app
    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191", "fake": True},
    ]})
    assert response.status_code == 400


def test_put_reports_an_unwritable_target(config_app, monkeypatch):
    client, _ = config_app
    monkeypatch.setattr(api.device_config, "is_writable", lambda target: False)
    response = client.put("/api/config/devices", json={"devices": [{"ip": "192.168.8.191"}]})
    assert response.status_code == 409
    assert "mount" in response.get_json()["details"].lower()


def test_put_never_echoes_a_password(config_app):
    client, _ = config_app
    payload = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191", "password": "brandnew"},
    ]}).get_json()
    assert "brandnew" not in str(payload)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: FAIL — 405, `put` is not defined on the resource.

- [ ] **Step 3: Write minimal implementation**

```python
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
        existing = load_devices_from_file(str(devices_file))
        merged = device_config.merge_devices(existing, cleaned)

        try:
            device_config.write_devices(devices_file, merged)
        except device_config.ConfigWriteError as exc:
            return {'error': 'Conflict', 'details': str(exc)}, 409

        current_app.logger.info("Device configuration updated: %d device(s)", len(merged))
        return self.get()
```

`api.py` defines no module-level `logger`, so this uses Flask's
`current_app.logger` rather than introducing one. Do not add a module logger for
a single line.

Returning `self.get()` means the response is the freshly read configuration with
passwords masked — the client never sees a password echoed back, and it gets the
authoritative state rather than its own submission.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_api.py -v -o addopts=""`
Expected: PASS (23 tests)

- [ ] **Step 5: Run the whole green core**

Run: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`
Expected: PASS, with no pre-existing test broken.

- [ ] **Step 6: Commit**

```bash
git add app/tasmota/api.py tests/test_config_api.py
git commit -m "feat(api): write the device configuration from the editor"
```

---

### Task 6: The editor UI

**Files:**
- Create: `app/static/js/devices-editor.js`
- Modify: `app/templates/index.html`

**Interfaces:**
- Consumes: `GET`/`PUT /api/config/devices`.
- Produces: an Alpine component `devicesEditor()`.

Kept in its own file: `app/static/js/app.js` is already 499 lines and owns the
operational view. The editor is a separate concern with its own state.

- [ ] **Step 1: Write the component**

```javascript
// app/static/js/devices-editor.js
/**
 * Devices editor — edits the configuration behind /api/config/devices.
 *
 * The password is write-only: the server never sends it, an empty field means
 * "keep", and removal is explicit. Changing a device's IP makes it a new device,
 * so its password cannot follow.
 */
function devicesEditor() {
    return {
        devices: [],
        writable: true,
        devicesFile: '',
        loading: false,
        saving: false,
        error: '',
        saved: false,

        async init() {
            await this.load();
        },

        async load() {
            this.loading = true;
            this.error = '';
            try {
                const response = await fetch('/api/config/devices');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                this.devices = payload.devices.map(device => ({
                    ...device,
                    password: '',
                    remove_password: false,
                }));
                this.writable = payload.writable;
                this.devicesFile = payload.devices_file;
            } catch (err) {
                this.error = `Konfiguration konnte nicht geladen werden: ${err.message}`;
            } finally {
                this.loading = false;
            }
        },

        addDevice() {
            this.devices.push({
                ip: '', username: '', dns_name: '', timeout: null,
                password: '', has_password: false, remove_password: false,
            });
        },

        removeDevice(index) {
            const device = this.devices[index];
            const label = device.dns_name || device.ip || 'dieses Gerät';
            if (!confirm(`${label} aus der Konfiguration entfernen?`)) return;
            this.devices.splice(index, 1);
        },

        clearPassword(device) {
            device.remove_password = true;
            device.password = '';
            device.has_password = false;
        },

        _payload() {
            return this.devices.map(device => {
                const entry = { ip: (device.ip || '').trim() };
                if (device.username) entry.username = device.username;
                if (device.dns_name) entry.dns_name = device.dns_name;
                if (device.timeout) entry.timeout = Number(device.timeout);
                if (device.password) entry.password = device.password;
                if (device.remove_password) entry.remove_password = true;
                return entry;
            });
        },

        async save() {
            this.saving = true;
            this.error = '';
            this.saved = false;
            try {
                const response = await fetch('/api/config/devices', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: this._payload() }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.details || `HTTP ${response.status}`);
                }
                this.devices = payload.devices.map(device => ({
                    ...device, password: '', remove_password: false,
                }));
                this.saved = true;
                setTimeout(() => { this.saved = false; }, 4000);
            } catch (err) {
                this.error = `Speichern fehlgeschlagen: ${err.message}`;
            } finally {
                this.saving = false;
            }
        },
    };
}
```

- [ ] **Step 2: Add the section to the template**

In `app/templates/index.html`, add the script tag next to the existing one at the
bottom:

```html
    <script src="{{ url_for('static', filename='js/devices-editor.js') }}"></script>
```

And add the editor section after the device list section (find the closing tag of
the block containing `<template x-for="device in devices"` around line 117 and
place this after that section):

```html
    <section class="section" x-data="devicesEditor()" x-init="init()">
      <h2 class="title is-4">Geräte verwalten</h2>

      <div class="notification is-warning" x-show="!writable" x-cloak>
        Die Konfigurationsdatei <span x-text="devicesFile"></span> ist nicht
        schreibbar. Wird sie als einzelne Datei ins Image gemountet, muss
        stattdessen ihr Verzeichnis gemountet werden — siehe
        <code>compose.example.yml</code>.
      </div>

      <div class="notification is-danger" x-show="error" x-cloak x-text="error"></div>
      <div class="notification is-success" x-show="saved" x-cloak>Gespeichert.</div>

      <table class="table is-fullwidth">
        <thead>
          <tr>
            <th>IP</th><th>Name</th><th>Benutzer</th><th>Passwort</th>
            <th>Timeout</th><th></th>
          </tr>
        </thead>
        <tbody>
          <template x-for="(device, index) in devices" :key="index">
            <tr>
              <td><input class="input" type="text" x-model="device.ip"
                         :disabled="!writable" placeholder="192.168.8.191"
                         title="IP-Adresse des Geräts eintragen"></td>
              <td><input class="input" type="text" x-model="device.dns_name"
                         :disabled="!writable"
                         title="Anzeigenamen für das Gerät eintragen"></td>
              <td><input class="input" type="text" x-model="device.username"
                         :disabled="!writable"
                         title="Benutzernamen für die Geräte-Anmeldung eintragen"></td>
              <td>
                <input class="input" type="password" x-model="device.password"
                       :disabled="!writable"
                       :placeholder="device.has_password ? '•••••••• (gesetzt)' : 'kein Passwort'"
                       title="Neues Passwort eintragen — leer lassen behält das gespeicherte">
                <button class="button is-small is-text" type="button"
                        x-show="device.has_password" :disabled="!writable"
                        @click="clearPassword(device)"
                        title="Gespeichertes Passwort entfernen — das Gerät wird danach ohne Anmeldung angesprochen">
                  Passwort entfernen
                </button>
              </td>
              <td><input class="input" type="number" x-model="device.timeout"
                         :disabled="!writable" min="60" max="600" placeholder="240"
                         title="Timeout in Sekunden für dieses Gerät setzen (60–600)"></td>
              <td>
                <button class="button is-danger is-small" type="button"
                        :disabled="!writable" @click="removeDevice(index)"
                        title="Gerät aus der Konfiguration entfernen — wird erst beim Speichern wirksam">
                  Entfernen
                </button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <div class="buttons">
        <button class="button" type="button" :disabled="!writable" @click="addDevice()"
                title="Neues Gerät zur Liste hinzufügen">Gerät hinzufügen</button>
        <button class="button is-primary" type="button"
                :disabled="!writable || saving" :class="{'is-loading': saving}"
                @click="save()"
                title="Geänderte Geräteliste in die Konfigurationsdatei schreiben">
          Speichern
        </button>
      </div>
    </section>
```

- [ ] **Step 3: Verify by hand against fake devices**

Run: `ENV_FILE=.env.dev python server.py` and open `http://localhost:5001`.

Check, and put the result in your report: the table lists the four fake devices;
the password field shows the `•••••••• (gesetzt)` placeholder and not a value;
adding a device, saving, and reloading the page keeps the change; and
`devices-dev.yaml` still contains `fake: true` and the `firmware_info` blocks
afterwards.

Restore `devices-dev.yaml` with `git checkout devices-dev.yaml` when you are
done, and say in the report that you did.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/devices-editor.js app/templates/index.html
git commit -m "feat(ui): add the devices editor"
```

---

### Task 7: End-to-end test

**Files:**
- Create: `tests/e2e/test_devices_editor.py`

**Interfaces:**
- Consumes: the finished editor.

**The trap this task exists to avoid:** `tests/e2e/conftest.py`'s `app_server`
fixture is **session-scoped** and runs against the repository's real
`devices-dev.yaml`. An editor test using it would rewrite that file and corrupt
every other e2e test in the same session. This test therefore starts its own app
instance against a **copy** in a tmp directory.

- [ ] **Step 1: Write the test**

```python
# tests/e2e/test_devices_editor.py
"""The devices editor, against its own app instance on a copy of the fixture.

Deliberately not using the shared `app_server` fixture: it is session-scoped and
points at the repository's devices-dev.yaml, which this test would rewrite.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def editable_app(tmp_path):
    devices_file = tmp_path / "devices.yaml"
    shutil.copy(REPO_ROOT / "devices-dev.yaml", devices_file)

    port = _free_port()
    env = {**os.environ, "DEVICES_FILE": str(devices_file), "PORT": str(port),
           "HOST": "127.0.0.1"}
    proc = subprocess.Popen(
        [sys.executable, "server.py"], cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 25
    try:
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("app did not become healthy")
        yield base_url, devices_file
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_editor_persists_a_new_device(page, editable_app):
    base_url, devices_file = editable_app
    page.goto(base_url)

    page.get_by_title("Neues Gerät zur Liste hinzufügen").click()
    page.get_by_title("IP-Adresse des Geräts eintragen").last.fill("192.168.100.199")
    page.get_by_title("Geänderte Geräteliste in die Konfigurationsdatei schreiben").click()

    page.get_by_text("Gespeichert.").wait_for(state="visible", timeout=10000)

    import yaml
    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert any(device["ip"] == "192.168.100.199" for device in written)
    assert any(device.get("fake") for device in written), "fake devices survived the write"
```

- [ ] **Step 2: Run it**

Run: `pytest tests/e2e/test_devices_editor.py -m e2e -o addopts=""`
Expected: PASS. If the selectors do not match what Task 6 produced, fix the
selectors — not the UI — unless the UI is genuinely missing a tooltip the plan
requires.

- [ ] **Step 3: Confirm the repository fixture is untouched**

Run: `git status --short devices-dev.yaml`
Expected: no output. If the file changed, the test used the wrong app instance.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_devices_editor.py
git commit -m "test(e2e): cover the devices editor round trip"
```

---

### Task 8: Deployment change and documentation

**Files:**
- Modify: `compose.example.yml`
- Modify: `docs/configuration.md`, `docs/container-setup.md`, `README.md`

- [ ] **Step 1: Switch the mount**

In `compose.example.yml`, replace the single-file mount (line 18,
`- ./devices.yaml:/app/devices.yaml`) with a directory mount, and point
`DEVICES_FILE` at it:

```yaml
      # The directory is mounted, not the file: replacing a bind-mounted file
      # fails with EBUSY, so the editor could not write it.
      - ./config:/app/config
```

and in the environment block:

```yaml
      - DEVICES_FILE=${DEVICES_FILE:-/app/config/devices.yaml}
```

- [ ] **Step 2: Document the editor and the migration**

In `docs/configuration.md`, add a section on editing devices in the UI covering:
what the editor manages, that the password is write-only and an empty field
keeps the stored one, that changing a device's IP means the password must be
entered again, that comments in the YAML are lost when the UI saves, and that
one backup generation is kept as `devices.yaml.bak`.

In `docs/container-setup.md` and `README.md`, update every place showing the
old `-v ./devices.yaml:/app/devices.yaml` form, and add a short migration note:
existing deployments must move the file into a directory and mount that,
otherwise the editor stays read-only and says so.

Run `grep -rn "devices.yaml:/app" README.md docs/ compose.example.yml` and fix
every hit.

- [ ] **Step 3: Verify**

Run: `grep -c '^```' README.md` — must be even (project rule).
Run: `uv run --with mkdocs-material mkdocs build --strict`, then delete `site/`
and any `uv.lock`.
Run: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`

- [ ] **Step 4: Commit**

```bash
git add compose.example.yml docs README.md
git commit -m "docs(editor): document the devices editor and the mount migration"
```

---

## Opening the pull request

PR title: `feat(editor): manage devices from the web UI`. The `feat` type gives a
minor bump, which a new interface warrants.

The PR body must state the breaking deployment change prominently — existing
deployments that bind-mount `devices.yaml` directly keep working read-only, and
the editor tells them why — and name the two accepted risks: last writer wins
with no conflict detection, and device passwords remain in plain text in the
file, now reachable through an HTTP write path on a LAN without TLS (#74).

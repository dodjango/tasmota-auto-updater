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
            # server.py's _require_api_auth() checks the `ui_authenticated` key,
            # not `ui` — matching that name here.
            session["ui_authenticated"] = True
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

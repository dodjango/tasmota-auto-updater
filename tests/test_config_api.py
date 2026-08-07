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

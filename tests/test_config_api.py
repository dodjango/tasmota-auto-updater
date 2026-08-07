"""Validation and API behaviour for the device-configuration editor."""
import pytest
import yaml

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


@pytest.fixture
def config_app(tmp_path):
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


def test_put_refuses_to_merge_over_unparsable_yaml(config_app):
    client, devices_file = config_app
    devices_file.write_text("devices:\n  - ip: [unterminated\n", encoding="utf-8")
    before = devices_file.read_text(encoding="utf-8")

    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191"},
    ]})

    assert response.status_code == 409
    assert devices_file.read_text(encoding="utf-8") == before, "nothing is written on error"


def test_put_accepts_an_empty_device_list_on_disk(config_app):
    client, devices_file = config_app
    devices_file.write_text("devices: []\n", encoding="utf-8")

    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191"},
    ]})

    assert response.status_code == 200
    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert written == [{"ip": "192.168.8.191"}]


def test_put_accepts_a_missing_devices_file(config_app):
    client, devices_file = config_app
    devices_file.unlink()

    response = client.put("/api/config/devices", json={"devices": [
        {"ip": "192.168.8.191"},
    ]})

    assert response.status_code == 200
    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert written == [{"ip": "192.168.8.191"}]

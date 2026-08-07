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


def test_write_devices_cleans_up_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "devices.yaml"
    original_content = "devices:\n- ip: 1.1.1.1\n"
    target.write_text(original_content, encoding="utf-8")

    def failing_replace(src, dst):
        raise OSError("Mock replace failure")

    monkeypatch.setattr(device_config.os, "replace", failing_replace)

    with pytest.raises(device_config.ConfigWriteError):
        device_config.write_devices(target, [{"ip": "2.2.2.2"}])

    assert target.read_text(encoding="utf-8") == original_content
    # Backup is created before replace fails, so it exists
    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.yaml", "devices.yaml.bak"]


def test_write_devices_cleans_up_on_backup_failure(tmp_path, monkeypatch):
    target = tmp_path / "devices.yaml"
    original_content = "devices:\n- ip: 1.1.1.1\n"
    target.write_text(original_content, encoding="utf-8")

    def failing_copy2(src, dst):
        raise OSError("Mock copy2 failure")

    monkeypatch.setattr(device_config.shutil, "copy2", failing_copy2)

    with pytest.raises(device_config.ConfigWriteError):
        device_config.write_devices(target, [{"ip": "2.2.2.2"}])

    assert target.read_text(encoding="utf-8") == original_content
    assert sorted(p.name for p in tmp_path.iterdir()) == ["devices.yaml"]


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
    """A stray control field in the file on disk must not survive the merge."""
    existing = [{"ip": "1.1.1.1", "remove_password": True}]
    submitted = [{"ip": "1.1.1.1"}]
    assert device_config.merge_devices(existing, submitted) == [{"ip": "1.1.1.1"}]


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


def test_merge_skips_entries_without_an_ip_on_either_side():
    """An ip-less entry cannot be matched and must not leak another device's data."""
    existing = [{"fake": True, "firmware_info": {"version": "12.0.2"}}, {"ip": "1.1.1.1"}]
    submitted = [{}, {"ip": "1.1.1.1"}]
    assert device_config.merge_devices(existing, submitted) == [{"ip": "1.1.1.1"}]

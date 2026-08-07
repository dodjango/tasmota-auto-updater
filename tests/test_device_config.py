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

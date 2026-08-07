"""Unit tests for reading, merging and writing the device configuration."""
import os
import stat
import threading
import time
from pathlib import Path

import pytest
import yaml

from app.tasmota import device_config

# Root ignores the permission bits these tests exercise, which is exactly the
# situation in a devcontainer — skip rather than fail there.
skip_as_root = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")


def test_is_writable_accepts_a_normal_file(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    assert device_config.is_writable(target) is True


def test_is_writable_accepts_a_missing_file_in_a_writable_directory(tmp_path):
    assert device_config.is_writable(tmp_path / "devices.yaml") is True


@skip_as_root
def test_is_writable_rejects_an_unwritable_directory(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    tmp_path.chmod(0o500)
    try:
        assert device_config.is_writable(target) is False
    finally:
        tmp_path.chmod(0o700)


def test_read_devices_returns_empty_for_a_missing_file(tmp_path):
    assert device_config.read_devices(tmp_path / "devices.yaml") == []


def test_read_devices_returns_empty_for_an_empty_file(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("", encoding="utf-8")
    assert device_config.read_devices(target) == []


def test_read_devices_returns_empty_for_an_empty_device_list(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    assert device_config.read_devices(target) == []


def test_read_devices_returns_the_configured_devices(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 192.168.8.191\n", encoding="utf-8")
    assert device_config.read_devices(target) == [{"ip": "192.168.8.191"}]


def test_read_devices_raises_on_invalid_yaml(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n  - ip: [unterminated\n", encoding="utf-8")
    with pytest.raises(device_config.ConfigReadError):
        device_config.read_devices(target)


def test_read_devices_raises_when_devices_is_not_a_list(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices: not-a-list\n", encoding="utf-8")
    with pytest.raises(device_config.ConfigReadError):
        device_config.read_devices(target)


def test_read_devices_raises_when_the_document_is_not_a_mapping(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(device_config.ConfigReadError):
        device_config.read_devices(target)


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


@skip_as_root
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

    def failing_replace(self, target):
        raise OSError("Mock replace failure")

    monkeypatch.setattr(Path, "replace", failing_replace)

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


def test_read_document_returns_the_full_mapping(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 1.1.1.1\nother_key: keep-me\n", encoding="utf-8")
    assert device_config.read_document(target) == {
        "devices": [{"ip": "1.1.1.1"}],
        "other_key": "keep-me",
    }


def test_read_document_returns_an_empty_mapping_for_a_missing_file(tmp_path):
    assert device_config.read_document(tmp_path / "devices.yaml") == {}


def test_write_devices_preserves_an_unmanaged_top_level_key(tmp_path):
    """The document level must not lose a key it was never asked to touch —
    matching the lengths merge_devices() already goes to for per-device fields.
    """
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 1.1.1.1\nother_key: keep-me\n", encoding="utf-8")

    document = device_config.read_document(target)
    device_config.write_devices(target, [{"ip": "2.2.2.2"}], document=document)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "devices": [{"ip": "2.2.2.2"}],
        "other_key": "keep-me",
    }


def test_write_devices_matches_the_target_permissions(tmp_path):
    """mkstemp() creates the temp file 0600; Path.replace() would otherwise carry
    that onto the target, silently tightening it and locking out the SSH editing
    path the design promises stays open.
    """
    target = tmp_path / "devices.yaml"
    target.write_text("devices: []\n", encoding="utf-8")
    target.chmod(0o664)

    device_config.write_devices(target, [{"ip": "2.2.2.2"}])

    assert stat.S_IMODE(target.stat().st_mode) == 0o664


def test_replace_devices_reads_merges_and_writes_under_lock(tmp_path):
    target = tmp_path / "devices.yaml"
    target.write_text(
        "devices:\n- ip: 1.1.1.1\n  password: secret\nother_key: keep-me\n", encoding="utf-8"
    )

    merged = device_config.replace_devices(target, [{"ip": "1.1.1.1"}, {"ip": "2.2.2.2"}])

    assert merged == [{"ip": "1.1.1.1", "password": "secret"}, {"ip": "2.2.2.2"}]
    on_disk = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert on_disk["devices"] == merged
    assert on_disk["other_key"] == "keep-me"


def test_replace_devices_serialises_overlapping_writers(tmp_path):
    """Two overlapping writers must not both read the same pre-edit state and
    each write a `.bak` that clobbers the other's backup — the lock makes
    read-merge-write one unit, so the second writer's backup is the first
    writer's real result, and the original pre-edit state is never lost.

    Verified here by forcing write_devices() to take a moment and recording
    the [start, end) interval each call ran in: with the lock in place the two
    intervals cannot overlap, no matter how the OS schedules the threads.
    """
    target = tmp_path / "devices.yaml"
    target.write_text("devices:\n- ip: 0.0.0.0\n", encoding="utf-8")

    intervals: list[tuple[float, float]] = []
    intervals_lock = threading.Lock()
    original_write_devices = device_config.write_devices

    def slow_write_devices(path, devices, document=None):
        start = time.monotonic()
        time.sleep(0.05)
        original_write_devices(path, devices, document=document)
        end = time.monotonic()
        with intervals_lock:
            intervals.append((start, end))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(device_config, "write_devices", slow_write_devices)
        first = threading.Thread(
            target=device_config.replace_devices, args=(target, [{"ip": "1.1.1.1"}])
        )
        second = threading.Thread(
            target=device_config.replace_devices, args=(target, [{"ip": "2.2.2.2"}])
        )
        first.start()
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)

    assert len(intervals) == 2, "both writers must have completed"
    (start_a, end_a), (start_b, end_b) = intervals
    assert end_a <= start_b or end_b <= start_a, "writes overlapped despite the lock"

    on_disk = yaml.safe_load(target.read_text(encoding="utf-8"))
    backup = yaml.safe_load((tmp_path / "devices.yaml.bak").read_text(encoding="utf-8"))
    assert on_disk["devices"] in ([{"ip": "1.1.1.1"}], [{"ip": "2.2.2.2"}])
    assert backup["devices"] in ([{"ip": "1.1.1.1"}], [{"ip": "2.2.2.2"}])
    assert on_disk["devices"] != backup["devices"]

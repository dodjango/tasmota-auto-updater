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
import yaml
from playwright.sync_api import expect

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

    page.get_by_title("Add a new device to the list").click()
    page.get_by_title(
        "Enter the device's IP address — changing it makes this a new device, "
        "so its stored password is not carried over"
    ).last.fill("192.168.100.199")
    page.get_by_title("Write the changed device list to the configuration file").click()

    page.get_by_text("Saved.").wait_for(state="visible", timeout=10000)
    expect(page.get_by_test_id("editor-error")).not_to_be_visible()

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert any(device["ip"] == "192.168.100.199" for device in written)
    assert any(device.get("fake") for device in written), "fake devices survived the write"


def _row_for_ip(page, ip_field_title, ip):
    """The table has no stable per-row id — find the <tr> by its IP input's
    current value instead of relying on row order, which changing state can
    shuffle.
    """
    inputs = page.get_by_title(ip_field_title)
    for index in range(inputs.count()):
        candidate = inputs.nth(index)
        if candidate.input_value() == ip:
            return candidate.locator("xpath=ancestor::tr[1]")
    raise AssertionError(f"no row found for ip {ip!r}")


def test_editor_round_trip_add_edit_reload_delete(page, editable_app):
    """Add a device, save, reload, confirm it survived, edit its name, save,
    delete it, save, reload, confirm it is gone — the round trip the design
    asked for, beyond the single add-and-save the other test covers.
    """
    base_url, devices_file = editable_app
    ip_field_title = (
        "Enter the device's IP address — changing it makes this a new device, "
        "so its stored password is not carried over"
    )
    name_field_title = "Enter a display name for the device"
    save_title = "Write the changed device list to the configuration file"

    page.goto(base_url)
    page.get_by_title("Add a new device to the list").click()
    page.get_by_title(ip_field_title).last.fill("192.168.100.222")
    page.get_by_title(save_title).click()
    page.get_by_text("Saved.").wait_for(state="visible", timeout=10000)

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert any(device["ip"] == "192.168.100.222" for device in written)

    page.reload()
    page.get_by_title(save_title).wait_for(state="visible", timeout=10000)
    row = _row_for_ip(page, ip_field_title, "192.168.100.222")
    row.get_by_title(name_field_title).fill("Round Trip Device")
    page.get_by_title(save_title).click()
    page.get_by_text("Saved.").wait_for(state="visible", timeout=10000)

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    edited = next(device for device in written if device["ip"] == "192.168.100.222")
    assert edited["dns_name"] == "Round Trip Device"

    page.reload()
    page.get_by_title(save_title).wait_for(state="visible", timeout=10000)
    row = _row_for_ip(page, ip_field_title, "192.168.100.222")
    page.once("dialog", lambda dialog: dialog.accept())  # removeDevice()'s confirm()
    row.get_by_title(
        "Remove the device from the configuration — applied when you save"
    ).click()
    page.get_by_title(save_title).click()
    page.get_by_text("Saved.").wait_for(state="visible", timeout=10000)

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert not any(device["ip"] == "192.168.100.222" for device in written)

    page.reload()
    page.get_by_title(save_title).wait_for(state="visible", timeout=10000)
    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert not any(device["ip"] == "192.168.100.222" for device in written)
    assert any(device.get("fake") for device in written), "fake devices survived the round trip"

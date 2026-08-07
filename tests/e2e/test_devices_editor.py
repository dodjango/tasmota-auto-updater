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

    written = yaml.safe_load(devices_file.read_text(encoding="utf-8"))["devices"]
    assert any(device["ip"] == "192.168.100.199" for device in written)
    assert any(device.get("fake") for device in written), "fake devices survived the write"

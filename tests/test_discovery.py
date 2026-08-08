"""Unit tests for the discovery core."""
import pytest

from app.tasmota import discovery

TASMOTA_STATUS = {
    "Status": {"Module": 1, "DeviceName": "Hallway", "FriendlyName": ["Hallway Light"]},
    "StatusFWR": {"Version": "14.2.0(release-tasmota)", "Hardware": "ESP8266EX"},
    "StatusNET": {"Hostname": "tasmota-1234", "IPAddress": "192.168.1.42",
                  "Mac": "AA:BB:CC:DD:EE:FF"},
}


def test_parse_status_extracts_the_fields_the_ui_shows():
    result = discovery.parse_status(TASMOTA_STATUS, "192.168.1.42")
    assert result == {
        "ip": "192.168.1.42",
        "hostname": "tasmota-1234",
        "friendly_name": "Hallway Light",
        "module": "ESP8266EX",
        "firmware_version": "14.2.0(release-tasmota)",
        "mac": "AA:BB:CC:DD:EE:FF",
        "requires_auth": False,
    }


def test_parse_status_survives_a_sparse_payload():
    """A minimal device still answers Status 0 — it must not crash the scan."""
    result = discovery.parse_status({"Status": {}}, "192.168.1.7")
    assert result is not None
    assert result["ip"] == "192.168.1.7"
    assert result["firmware_version"] is None
    assert result["friendly_name"] is None


def test_parse_status_rejects_a_foreign_json_device():
    """A printer answering JSON is not a Tasmota. No Status block, no entry."""
    assert discovery.parse_status({"printer": {"model": "X"}}, "192.168.1.9") is None


def test_parse_status_rejects_a_non_mapping():
    assert discovery.parse_status([1, 2, 3], "192.168.1.9") is None

"""Unit tests for the discovery core."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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


class _StubHandler(BaseHTTPRequestHandler):
    """Answers like the device its `mode` says. Set by the factory below."""

    mode = "tasmota"

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
        if self.mode == "tasmota":
            body = json.dumps(TASMOTA_STATUS).encode()
            self.send_response(200)
        elif self.mode == "auth":
            body = json.dumps({"WARNING": "Need user&password"}).encode()
            self.send_response(401)
        else:
            body = json.dumps({"printer": {"model": "X"}}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output readable
        pass


def _start_stub(mode):
    handler = type("Handler", (_StubHandler,), {"mode": mode})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def stub_servers():
    servers = {mode: _start_stub(mode) for mode in ("tasmota", "auth", "foreign")}
    yield {mode: s.server_address[1] for mode, s in servers.items()}
    for server in servers.values():
        server.shutdown()


def test_scan_finds_real_devices_without_mocking_the_probe(stub_servers):
    """The one test that drives the real probe over a real socket.

    Mocking probe_host here would only prove that a thread pool calls a
    function — exactly the blind spot that let #126 ship.
    """
    found = []
    for mode, port in stub_servers.items():
        results = discovery.scan_network(
            ["127.0.0.1"],
            probe=lambda ip, port=port: discovery.probe_host(ip, port=port, timeout=2.0),
        )
        found.extend(results)

    by_auth = {entry["requires_auth"]: entry for entry in found}
    assert len(found) == 2, "the foreign JSON device must not be reported"
    assert by_auth[False]["firmware_version"] == "14.2.0(release-tasmota)"
    assert by_auth[True]["ip"] == "127.0.0.1"


def test_scan_reports_progress_for_every_host():
    seen = []
    discovery.scan_network(
        [f"192.0.2.{n}" for n in range(1, 6)],
        probe=lambda ip: None,
        on_progress=lambda completed, total: seen.append((completed, total)),
    )
    assert [c for c, _ in seen] == [1, 2, 3, 4, 5]
    assert {t for _, t in seen} == {5}


def test_scan_survives_a_probe_that_raises():
    """One broken host must not abort the whole range."""
    def flaky(ip):
        if ip.endswith(".2"):
            raise RuntimeError("boom")
        return {"ip": ip, "requires_auth": False}

    results = discovery.scan_network(["192.0.2.1", "192.0.2.2", "192.0.2.3"], probe=flaky)
    assert sorted(r["ip"] for r in results) == ["192.0.2.1", "192.0.2.3"]


def test_scan_of_an_empty_range_does_nothing():
    assert discovery.scan_network([]) == []


def test_hosts_in_network_leaves_out_network_and_broadcast():
    import ipaddress

    hosts = discovery.hosts_in_network(ipaddress.ip_network("192.168.1.0/29"))
    assert hosts == [f"192.168.1.{n}" for n in range(1, 7)]

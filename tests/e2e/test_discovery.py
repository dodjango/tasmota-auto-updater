"""End-to-end coverage for the discovery modal.

The job is stubbed through `page.route` rather than scanned for real: the e2e
run must not depend on what happens to be on the CI runner's network, and a
real scan would cost 25 seconds per test.

The shared session-scoped `app_server` is fine here because nothing in this
file saves — adoption only produces unsaved rows, so the repository's
devices-dev.yaml is never rewritten.
"""
import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

FINDINGS = [
    {"ip": "192.168.100.150", "hostname": "tasmota-new", "friendly_name": "Attic",
     "module": "ESP8266EX", "firmware_version": "14.2.0", "mac": "AA:BB:CC:DD:EE:01",
     "requires_auth": False, "already_configured": False},
    {"ip": "192.168.100.101", "hostname": "known", "friendly_name": "Known one",
     "module": "ESP8266EX", "firmware_version": "13.0.0", "mac": "AA:BB:CC:DD:EE:02",
     "requires_auth": False, "already_configured": True},
    {"ip": "192.168.100.151", "hostname": None, "friendly_name": None,
     "module": None, "firmware_version": None, "mac": None,
     "requires_auth": True, "already_configured": False},
]


def _stub_discovery(page, results, notice=None, method="scan"):
    """Answer both discovery endpoints and the job poll with canned data."""

    def handle_discovery(route):
        if route.request.method == "POST":
            route.fulfill(
                status=202, content_type="application/json",
                body=json.dumps({"job_id": "stub", "status_url": "/api/jobs/stub"}),
            )
        else:
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"suggested_networks": ["192.168.100.0/24"],
                                 "limits": {"max_prefix": 22, "max_hosts": 1024}}),
            )

    page.route("**/api/discovery", handle_discovery)
    page.route("**/api/jobs/stub", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"job_id": "stub", "kind": "discovery", "method": method,
                         "status": "completed", "completed": 254, "total": 254,
                         "results": results, "notice": notice, "error": None}),
    ))


def _open_and_scan(page, app_server):
    page.goto(app_server)
    page.get_by_test_id("open-discovery").click()
    page.get_by_test_id("start-scan").click()


def test_scan_lists_findings_and_marks_known_devices(page, app_server):
    _stub_discovery(page, FINDINGS)
    _open_and_scan(page, app_server)

    results = page.get_by_test_id("discovery-results")
    expect(results).to_be_visible()
    expect(results.locator("tbody tr")).to_have_count(3)

    known_row = results.locator("tbody tr", has_text="192.168.100.101")
    expect(known_row.locator("input[type=checkbox]")).to_be_disabled()
    expect(known_row).to_contain_text("Already in list")


def test_a_password_protected_find_is_tagged_not_retried(page, app_server):
    _stub_discovery(page, FINDINGS)
    _open_and_scan(page, app_server)

    row = page.get_by_test_id("discovery-results").locator(
        "tbody tr", has_text="192.168.100.151")
    expect(row).to_contain_text("Credentials needed")
    # Still adoptable — the user supplies credentials in the editor afterwards.
    expect(row.locator("input[type=checkbox]")).to_be_enabled()


def test_adopting_a_finding_adds_an_unsaved_row(page, app_server):
    _stub_discovery(page, FINDINGS)
    _open_and_scan(page, app_server)
    expect(page.get_by_test_id("discovery-results")).to_be_visible()

    page.locator('input[type=checkbox][value="192.168.100.150"]').check()
    page.get_by_test_id("adopt-selected").click()

    # x-show only toggles display, so assert visibility — never count == 0.
    expect(page.get_by_test_id("discovery-modal")).to_be_hidden()

    ip_fields = page.get_by_label("Device IP address")
    values = [ip_fields.nth(i).input_value() for i in range(ip_fields.count())]
    assert "192.168.100.150" in values, "the adopted device must appear in the editor"


def test_an_already_configured_device_cannot_be_adopted_twice(page, app_server):
    _stub_discovery(page, FINDINGS)
    _open_and_scan(page, app_server)
    expect(page.get_by_test_id("discovery-results")).to_be_visible()

    ip_fields = page.get_by_label("Device IP address")
    before = [ip_fields.nth(i).input_value() for i in range(ip_fields.count())]
    assert before.count("192.168.100.101") == 1

    # The checkbox is disabled, so the device can never reach the selection.
    expect(page.get_by_test_id("adopt-selected")).to_be_disabled()


def test_an_empty_mdns_run_explains_itself(page, app_server):
    _stub_discovery(
        page, [], method="mdns",
        notice="No device announced itself. In a bridge-network container mDNS "
               "cannot work at all, because multicast does not cross the bridge.",
    )
    page.goto(app_server)
    page.get_by_test_id("open-discovery").click()
    page.get_by_test_id("start-mdns").click()

    notice = page.get_by_test_id("discovery-notice")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("bridge-network")
    # The honest message replaces the blunt one, it does not accompany it.
    expect(page.get_by_test_id("discovery-empty")).to_be_hidden()


def test_a_rejected_network_is_reported_with_its_reason(page, app_server):
    """The server's fence must be visible to the user, not swallowed."""
    def handle_discovery(route):
        if route.request.method == "POST":
            route.fulfill(
                status=400, content_type="application/json",
                body=json.dumps({"error": "Bad Request",
                                 "details": "Only private networks can be scanned."}),
            )
        else:
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"suggested_networks": [],
                                 "limits": {"max_prefix": 22, "max_hosts": 1024}}),
            )

    page.route("**/api/discovery", handle_discovery)
    page.goto(app_server)
    page.get_by_test_id("open-discovery").click()
    page.get_by_test_id("scan-network").fill("8.8.8.0/24")
    page.get_by_test_id("start-scan").click()

    error = page.get_by_test_id("discovery-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("private")

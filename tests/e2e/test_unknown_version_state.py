"""Regression E2E: when the latest firmware version cannot be determined, the
card must not claim "Up to Date".

The API returns `needs_update: false` both for an up-to-date device and for a
failed release lookup (e.g. a GitHub API rate limit), so keying the green tag on
`needs_update` alone reported a failure as a healthy state. The check response is
stubbed here because the real failure depends on an external service.
"""
import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _stub_check(page: Page, payload_extra):
    """Answer the UI's check call (POST /api/update with check_only) with a stub."""

    def handler(route):
        request = route.request
        if request.method != "POST":
            return route.fallback()
        body = request.post_data_json or {}
        if not body.get("check_only"):
            return route.fallback()

        payload = {
            "ip": body.get("ip"),
            "current_version": "12.0.2",
            "needs_update": False,
            **payload_extra,
        }
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    page.route("**/api/update", handler)


def test_failed_release_lookup_is_not_shown_as_up_to_date(page: Page, app_server: str):
    _stub_check(page, {
        "success": False,
        "message": "Failed to get latest release information",
        "latest_version": "Unknown",
    })

    page.goto(app_server + "/")
    card = page.locator(".card").first
    expect(card).to_be_visible()

    # The honest state is surfaced ...
    expect(card.get_by_text("Version unknown")).to_be_visible(timeout=30000)
    # ... and the misleading ones stay hidden. (x-show keeps the elements in the
    # DOM and only toggles display, so assert visibility, not element count.)
    expect(card.get_by_text("Up to Date")).to_be_hidden()
    expect(card.get_by_text("Update Available")).to_be_hidden()


def test_a_real_comparison_still_shows_up_to_date(page: Page, app_server: str):
    """Contrast case: a concrete latest_version keeps the green tag working."""
    _stub_check(page, {
        "success": True,
        "message": "Device is already running the latest version",
        "latest_version": "12.0.2",
    })

    page.goto(app_server + "/")
    card = page.locator(".card").first
    expect(card).to_be_visible()

    expect(card.get_by_text("Up to Date")).to_be_visible(timeout=30000)
    expect(card.get_by_text("Version unknown")).to_be_hidden()

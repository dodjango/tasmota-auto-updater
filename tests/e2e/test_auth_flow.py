"""E2E: the UI session-cookie flow reaches the (gated) API end-to-end.

After Phase 1, /api/* is fail-closed. This verifies the browser obtains the
session cookie from GET / and then successfully calls the API with it — the
device list AND a per-device status fetch both succeed.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_ui_session_reaches_api(page: Page, app_server: str):
    page.goto(app_server + "/")

    # Device cards render → GET /api/devices succeeded with the session cookie.
    expect(page.locator(".card").first).to_be_visible()

    # A fake device's firmware version shows → GET /api/devices/<ip> also
    # succeeded end-to-end through the cookie-gated API.
    expect(page.get_by_text("Current Version:").first).to_be_visible(timeout=15000)

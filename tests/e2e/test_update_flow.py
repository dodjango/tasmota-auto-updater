"""E2E: the async batch flow (Phase 2) works end-to-end from the browser.

Clicking "Check All" starts a background job (202), the UI polls it, and the
per-device results land — exercising POST /api/update/all → GET /api/jobs/<id>
through the cookie-gated API with fake devices.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_check_all_async_flow(page: Page, app_server: str):
    page.goto(app_server + "/")
    expect(page.locator(".card").first).to_be_visible()

    page.get_by_role("button", name="Check All").click()

    # The polled job completes and per-device "Last:" checked timestamps appear
    # (proves 202 → poll → results end-to-end). Generous timeout: the check may
    # fetch the latest release upstream.
    expect(page.get_by_text("Last:").first).to_be_visible(timeout=30000)

    # No error notification surfaced during the async flow.
    expect(page.locator(".notification.is-danger")).not_to_be_visible()

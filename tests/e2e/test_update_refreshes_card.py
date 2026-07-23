"""Regression E2E: after a single-device update the card must re-fetch the
device status (GET /api/devices/<ip>), so the shown firmware version updates
and the "Update Available" tag clears — not just a re-check.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_single_update_refetches_device_status(page: Page, app_server: str):
    page.goto(app_server + "/")
    card = page.locator(".card").first
    expect(card).to_be_visible()

    # Wait until the first device has been checked and needs an update
    # (this enables its "Update" action).
    expect(card.get_by_text("Update Available")).to_be_visible(timeout=30000)

    # The post-update status refetch (GET /api/devices/<ip>) is what refreshes the
    # shown version; on fake devices it lags the success indicator, so wait for it.
    with page.expect_request(
        lambda r: r.method == "GET" and "/api/devices/" in r.url,
        timeout=20000,
    ):
        card.locator(".card-footer-item").filter(has_text="Update").click()
        page.get_by_role("button", name="Update", exact=True).click()  # confirm modal

    expect(page.get_by_text("Update completed successfully").first).to_be_visible(timeout=10000)

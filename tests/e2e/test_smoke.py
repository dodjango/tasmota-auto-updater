"""Smoke end-to-end test: the UI loads and renders the (fake) device list.

This establishes the Playwright harness. Feature-specific E2E (auth/cookie flow,
update flow, error/timeout states) is added by the respective phases.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_ui_loads_and_lists_fake_devices(page: Page, app_server: str):
    page.goto(app_server + "/")

    # Main heading renders (Alpine app initialised).
    expect(page.get_by_text("Tasmota Device Manager")).to_be_visible()

    # Fake devices from devices-dev.yaml are fetched and rendered as cards.
    expect(page.locator(".card").first).to_be_visible()

    # Phase 0 fix: the mobile navbar burger exists.
    expect(page.locator(".navbar-burger")).to_have_count(1)

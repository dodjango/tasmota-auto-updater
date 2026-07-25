"""Tests for the "latest version unknown" case.

When the latest release cannot be determined, the API returns
`needs_update: false` — the same value it returns for an up-to-date device. The
UI therefore must not key "Up to Date" on `needs_update` alone; it distinguishes
the cases via `latest_version`. These tests pin that contract down so the two
situations stay tellable apart.
"""

import pytest
from unittest.mock import patch

from app.tasmota.updater import update_device_firmware

DEVICE = {"ip": "192.168.8.191", "timeout": 60}


def firmware(version="15.2.0"):
    return {
        "version": version,
        "core_version": "2.7.8",
        "sdk_version": "2.2.2-dev",
        "is_minimal": False,
    }


class TestFailedReleaseLookup:
    """A failed GitHub release lookup must stay distinguishable from "up to date"."""

    def _check(self):
        with patch("app.tasmota.updater.get_device_firmware_version") as mock_version, \
             patch("app.tasmota.updater.fetch_latest_tasmota_release") as mock_latest:
            mock_version.return_value = firmware()
            mock_latest.return_value = None  # e.g. GitHub API rate limit
            return update_device_firmware(DEVICE, check_only=True)

    def test_reports_failure_rather_than_success(self):
        result = self._check()

        assert result["success"] is False
        assert "latest release" in result["message"].lower()

    def test_latest_version_stays_unknown(self):
        """This is the field the UI uses to tell "unknown" from "up to date"."""
        result = self._check()

        assert result["latest_version"] == "Unknown"
        assert result["needs_update"] is False

    def test_current_version_is_still_reported(self):
        result = self._check()

        assert result["current_version"] == "15.2.0"


class TestFailedDeviceVersionRead:
    """An unreachable device must not look up to date either."""

    def test_latest_version_stays_unknown(self):
        with patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_version.return_value = None
            result = update_device_firmware(DEVICE, check_only=True)

        assert result["success"] is False
        assert result["latest_version"] == "Unknown"
        assert result["needs_update"] is False


class TestSuccessfulComparison:
    """Contrast: a real comparison always carries a concrete latest_version."""

    @pytest.mark.parametrize("needs_update", [True, False])
    def test_latest_version_is_concrete(self, needs_update):
        with patch("app.tasmota.updater.get_device_firmware_version") as mock_version, \
             patch("app.tasmota.updater.fetch_latest_tasmota_release") as mock_latest, \
             patch("app.tasmota.updater.compare_versions") as mock_compare:
            mock_version.return_value = firmware()
            mock_latest.return_value = {"version": "15.5.0"}
            mock_compare.return_value = needs_update
            result = update_device_firmware(DEVICE, check_only=True)

        assert result["success"] is True
        assert result["latest_version"] == "15.5.0"
        assert result["latest_version"] != "Unknown"
        assert result["needs_update"] is needs_update

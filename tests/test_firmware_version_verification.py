"""Tests for post-OTA firmware version verification.

Tasmota acknowledges `Upgrade 1` with HTTP 200 and then downloads and flashes
the new firmware *in the background* while still serving requests on the OLD
firmware. Reachability is therefore not proof of a completed update: the device
only runs the new version after it reboots, which happens seconds to minutes
after the command was accepted.

These tests pin down that `update_device_firmware()` must not report success
until the device actually reports a different firmware version.
"""

import pytest
from unittest.mock import patch

from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    log_safe_address,
    update_device_firmware,
    verify_firmware_version_changed,
)

OLD_VERSION = "15.2.0(release-tasmota-4M)"
NEW_VERSION = "15.5.0(release-tasmota-4M)"


class FakeClock:
    """Deterministic clock so backoff loops don't burn real wall-clock time."""

    def __init__(self, start=1000.0):
        self.now = start

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def firmware(version):
    return {
        "version": version,
        "core_version": "2.7.8",
        "sdk_version": "2.2.2-dev(38a443e)",
        "is_minimal": False,
    }


def restart_verified_report(total_timeout=240):
    """Report as produced when the device answers HTTP 200 again."""
    return TimeoutReport(
        total_timeout=total_timeout,
        elapsed_time=10.0,
        phase=TimeoutPhase.RESTART_VERIFICATION,
        attempts=1,
        last_check_interval=1.0,
        timed_out=False,
        error_type="none",
        details={"success": True, "final_status_code": 200},
    )


@pytest.fixture
def clock():
    return FakeClock()


class TestLogSafeAddress:
    """The address used in log messages is normalized, never taken verbatim."""

    def test_normalizes_a_valid_address(self):
        assert log_safe_address(" 192.168.8.191 ") == "192.168.8.191"

    def test_normalizes_ipv6(self):
        assert log_safe_address("FE80::1") == "fe80::1"

    @pytest.mark.parametrize("value", [
        "192.168.8.191\nfake log line",  # would forge an extra log record
        "not-an-ip",
        "",
        None,
    ])
    def test_replaces_anything_that_is_not_an_ip(self, value):
        assert log_safe_address(value) == "<invalid-address>"


class TestVerifyFirmwareVersionChanged:
    """Unit tests for the version-based verification helper."""

    def test_returns_new_firmware_once_version_changes(self, clock):
        config = TimeoutConfig(total_timeout=240)

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            # Still flashing on the old firmware, then rebooted onto the new one
            mock_version.side_effect = [
                firmware(OLD_VERSION),
                firmware(OLD_VERSION),
                firmware(NEW_VERSION),
            ]

            info, report = verify_firmware_version_changed(
                {"ip": "192.168.8.191"}, OLD_VERSION, config
            )

        assert info["version"] == NEW_VERSION
        assert report.timed_out is False
        assert report.attempts == 3

    def test_tolerates_device_being_offline_while_rebooting(self, clock):
        config = TimeoutConfig(total_timeout=240)

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            # Unreachable mid-reboot (None), then back with the new firmware
            mock_version.side_effect = [None, None, firmware(NEW_VERSION)]

            info, report = verify_firmware_version_changed(
                {"ip": "192.168.8.191"}, OLD_VERSION, config
            )

        assert info["version"] == NEW_VERSION
        assert report.timed_out is False

    def test_ignores_unknown_version_readings(self, clock):
        config = TimeoutConfig(total_timeout=240)

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            mock_version.side_effect = [
                firmware("Unknown"),
                firmware(NEW_VERSION),
            ]

            info, report = verify_firmware_version_changed(
                {"ip": "192.168.8.191"}, OLD_VERSION, config
            )

        assert info["version"] == NEW_VERSION

    def test_times_out_when_version_never_changes(self, clock):
        config = TimeoutConfig(total_timeout=120)

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            mock_version.return_value = firmware(OLD_VERSION)

            info, report = verify_firmware_version_changed(
                {"ip": "192.168.8.191"}, OLD_VERSION, config
            )

        assert info is None
        assert report.timed_out is True
        assert report.error_type == "version_unchanged"
        assert report.phase == TimeoutPhase.FIRMWARE_FLASH

    def test_respects_an_externally_supplied_deadline(self, clock):
        config = TimeoutConfig(total_timeout=600)

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            mock_version.return_value = firmware(OLD_VERSION)

            info, report = verify_firmware_version_changed(
                {"ip": "192.168.8.191"},
                OLD_VERSION,
                config,
                deadline=clock.now + 30,
            )

        assert info is None
        assert report.timed_out is True
        # The deadline, not total_timeout, bounds the loop
        assert report.elapsed_time <= 30 + config.max_check_interval


class TestUpdateDeviceFirmwareVersionVerification:
    """update_device_firmware() must verify the running firmware, not just reachability."""

    def _patched_update(self, clock, version_readings, compare_results=None):
        """Run update_device_firmware with the network boundary mocked out."""
        patches = {
            "get_device_firmware_version": None,
            "fetch_latest_tasmota_release": None,
            "compare_versions": None,
            "is_fake_device": None,
            "build_device_url": None,
        }

        with patch("app.tasmota.updater.time") as mock_time, \
             patch("app.tasmota.updater.get_device_firmware_version") as mock_version, \
             patch("app.tasmota.updater.fetch_latest_tasmota_release") as mock_latest, \
             patch("app.tasmota.updater.compare_versions") as mock_compare, \
             patch("app.tasmota.updater.is_fake_device") as mock_fake, \
             patch("app.tasmota.updater.build_device_url") as mock_url, \
             patch("app.tasmota.updater.requests.get") as mock_get, \
             patch("app.tasmota.updater.verify_device_restart_with_backoff") as mock_restart:
            mock_time.time.side_effect = clock.time
            mock_time.sleep.side_effect = clock.sleep
            mock_version.side_effect = version_readings
            mock_latest.return_value = {"version": "15.5.0"}
            if compare_results is None:
                mock_compare.return_value = True
            else:
                mock_compare.side_effect = compare_results
            mock_fake.return_value = False
            mock_url.return_value = "http://192.168.8.191/cm"

            mock_get.return_value.status_code = 200
            # The device answers again right away — it never actually rebooted yet
            mock_restart.return_value = (True, restart_verified_report())

            return update_device_firmware(
                {"ip": "192.168.8.191", "timeout": 240}, check_only=False
            )

    def test_does_not_claim_success_while_old_firmware_still_running(self, clock):
        """Regression: reachable + old version was reported as a successful update."""
        result = self._patched_update(
            clock,
            # Pre-update read, then the device keeps reporting the old version
            version_readings=[firmware(OLD_VERSION)] + [firmware(OLD_VERSION)] * 60,
        )

        assert result["success"] is False
        assert result["current_version"] == OLD_VERSION
        # The card must keep offering the update instead of showing "Up to Date"
        assert result["needs_update"] is True
        assert "still running" in result["message"].lower()

    def test_reports_success_with_the_new_version_after_the_flash_window(self, clock):
        result = self._patched_update(
            clock,
            version_readings=[
                firmware(OLD_VERSION),  # pre-update check
                firmware(OLD_VERSION),  # still flashing, old firmware serving
                firmware(OLD_VERSION),
                firmware(NEW_VERSION),  # rebooted onto the new firmware
            ],
            # needs_update before the update, then re-evaluated afterwards
            compare_results=[True, False],
        )

        assert result["success"] is True
        assert result["current_version"] == NEW_VERSION
        assert result["needs_update"] is False
        assert "completed successfully" in result["message"].lower()

    def test_exposes_the_version_verification_report(self, clock):
        result = self._patched_update(
            clock,
            version_readings=[
                firmware(OLD_VERSION),
                firmware(NEW_VERSION),
            ],
            compare_results=[True, False],
        )

        assert result["version_verification"]["timed_out"] is False
        assert result["version_verification"]["phase"] == TimeoutPhase.FIRMWARE_FLASH.value
        # The reachability report stays intact alongside it
        assert result["timeout_report"]["phase"] == TimeoutPhase.RESTART_VERIFICATION.value

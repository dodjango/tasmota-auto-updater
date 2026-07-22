"""Comprehensive test suite for timeout handling in Tasmota Updater

This module tests the enhanced timeout handling functionality including:
- Exponential backoff for device restart verification
- Configurable timeout values up to 600 seconds
- Structured timeout reporting
- Error differentiation between network and update timeouts
"""

import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import ConnectionError, Timeout, RequestException

from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    create_timeout_config,
    verify_device_restart_with_backoff,
    update_device_firmware
)


class TestTimeoutConfig:
    """Test timeout configuration validation and creation"""

    def test_default_timeout_config(self):
        """Test default timeout configuration values"""
        config = TimeoutConfig()
        assert config.total_timeout == 240
        assert config.initial_wait == 10
        assert config.min_check_interval == 1.0
        assert config.max_check_interval == 30.0
        assert config.backoff_multiplier == 1.5
        assert config.request_timeout == 5

    def test_timeout_config_validation(self):
        """Test timeout configuration validation"""
        # Test minimum timeout validation
        with pytest.raises(ValueError, match="Total timeout must be at least 30 seconds"):
            TimeoutConfig(total_timeout=20)

        # Test maximum timeout validation
        with pytest.raises(ValueError, match="Total timeout cannot exceed 600 seconds"):
            TimeoutConfig(total_timeout=700)

        # Test initial wait validation
        with pytest.raises(ValueError, match="Initial wait must be less than total timeout"):
            TimeoutConfig(total_timeout=60, initial_wait=70)

        # Test check interval validation
        with pytest.raises(ValueError, match="Min check interval must be less than max check interval"):
            TimeoutConfig(min_check_interval=10.0, max_check_interval=5.0)

    def test_valid_timeout_config(self):
        """Test valid timeout configuration creation"""
        config = TimeoutConfig(
            total_timeout=300,
            initial_wait=15,
            min_check_interval=2.0,
            max_check_interval=20.0,
            backoff_multiplier=2.0,
            request_timeout=10
        )
        assert config.total_timeout == 300
        assert config.initial_wait == 15
        assert config.min_check_interval == 2.0
        assert config.max_check_interval == 20.0
        assert config.backoff_multiplier == 2.0
        assert config.request_timeout == 10


class TestCreateTimeoutConfig:
    """Test timeout configuration creation from device config"""

    def test_default_device_config(self):
        """Test timeout config creation with default values"""
        device_config = {"ip": "192.168.1.100"}
        config = create_timeout_config(device_config)

        assert config.total_timeout == 240  # Default
        assert config.initial_wait == 10     # min(10, 180 // 12)
        assert config.min_check_interval == 2.0  # For timeout > 120
        assert config.max_check_interval == 30.0  # 180 // 6

    def test_custom_timeout_in_range(self):
        """Test timeout config creation with custom timeout in valid range"""
        device_config = {"ip": "192.168.1.100", "timeout": 240}
        config = create_timeout_config(device_config)

        assert config.total_timeout == 240
        assert config.initial_wait == 10  # min(10, 240 // 12)
        assert config.min_check_interval == 2.0
        assert config.max_check_interval == 30.0  # min(30, 240 // 6)

    def test_timeout_too_low_adjusted(self):
        """Test timeout config creation with too low timeout (adjusted)"""
        device_config = {"ip": "192.168.1.100", "timeout": 30}
        config = create_timeout_config(device_config)

        assert config.total_timeout == 60  # Adjusted to minimum
        assert config.initial_wait == 5   # 60 // 12

    def test_timeout_too_high_capped(self):
        """Test timeout config creation with too high timeout (capped)"""
        device_config = {"ip": "192.168.1.100", "timeout": 800}
        config = create_timeout_config(device_config)

        assert config.total_timeout == 600  # Capped to maximum
        assert config.initial_wait == 10   # min(10, 600 // 12)
        assert config.max_check_interval == 30.0  # min(30, 600 // 6)

    def test_short_timeout_intervals(self):
        """Test timeout config creation with short timeout"""
        device_config = {"ip": "192.168.1.100", "timeout": 90}
        config = create_timeout_config(device_config)

        assert config.total_timeout == 90
        assert config.min_check_interval == 1.0  # For timeout <= 120
        assert config.max_check_interval == 15.0  # 90 // 6


class TestTimeoutReport:
    """Test timeout report functionality"""

    def test_timeout_report_creation(self):
        """Test timeout report creation and serialization"""
        report = TimeoutReport(
            total_timeout=180,
            elapsed_time=45.67,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=5,
            last_check_interval=8.5,
            timed_out=False,
            error_type="none",
            details={"success": True}
        )

        assert report.total_timeout == 180
        assert report.elapsed_time == 45.67
        assert report.phase == TimeoutPhase.RESTART_VERIFICATION
        assert report.attempts == 5
        assert report.last_check_interval == 8.5
        assert not report.timed_out
        assert report.error_type == "none"
        assert report.details == {"success": True}

    def test_timeout_report_to_dict(self):
        """Test timeout report conversion to dictionary"""
        report = TimeoutReport(
            total_timeout=180,
            elapsed_time=45.678,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=5,
            last_check_interval=8.567,
            timed_out=True,
            error_type="restart_timeout",
            details={"message": "Device did not respond"}
        )

        result_dict = report.to_dict()

        expected = {
            'total_timeout': 180,
            'elapsed_time': 45.68,  # Rounded to 2 decimal places
            'phase': 'restart_verification',
            'attempts': 5,
            'last_check_interval': 8.57,  # Rounded to 2 decimal places
            'timed_out': True,
            'error_type': 'restart_timeout',
            'details': {"message": "Device did not respond"}
        }

        assert result_dict == expected

    def test_timeout_report_json_serializable(self):
        """Test that timeout report dict is JSON serializable"""
        report = TimeoutReport(
            total_timeout=180,
            elapsed_time=45.67,
            phase=TimeoutPhase.DEVICE_REBOOT,
            attempts=3,
            last_check_interval=5.0,
            timed_out=False,
            error_type="none",
            details={"test": "data"}
        )

        result_dict = report.to_dict()
        # Should not raise an exception
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)


class TestVerifyDeviceRestartWithBackoff:
    """Test device restart verification with exponential backoff"""

    def test_successful_device_restart_immediate(self):
        """Test successful device restart on first attempt"""
        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(total_timeout=60, initial_wait=1)

        with patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('time.sleep') as mock_sleep:

            mock_build_url.return_value = "http://192.168.1.100/cm"
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            assert success is True
            assert not report.timed_out
            assert report.error_type == "none"
            assert report.attempts == 1
            assert "success" in report.details
            mock_sleep.assert_called_once_with(1)  # Initial wait

    def test_successful_device_restart_after_retries(self):
        """Test successful device restart after several attempts"""
        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(
            total_timeout=60,
            initial_wait=1,
            min_check_interval=1.0,
            max_check_interval=5.0,
            backoff_multiplier=2.0
        )

        with patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('time.sleep') as mock_sleep:

            mock_build_url.return_value = "http://192.168.1.100/cm"

            # First two attempts fail, third succeeds
            mock_responses = [
                ConnectionError("Connection refused"),
                ConnectionError("Connection refused"),
                Mock(status_code=200)
            ]
            mock_get.side_effect = mock_responses

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            assert success is True
            assert not report.timed_out
            assert report.error_type == "none"
            assert report.attempts == 3
            assert mock_get.call_count == 3

            # Check that exponential backoff was applied
            sleep_calls = mock_sleep.call_args_list
            assert len(sleep_calls) >= 3  # Initial wait + 2 backoff sleeps
            # Initial wait
            assert sleep_calls[0][0][0] == 1
            # First backoff (1.0 seconds)
            assert sleep_calls[1][0][0] == 1.0
            # Second backoff (2.0 seconds)
            assert sleep_calls[2][0][0] == 2.0

    def test_device_restart_timeout(self):
        """Test device restart verification timeout"""
        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(
            total_timeout=30,  # Minimum valid timeout for testing
            initial_wait=1,
            min_check_interval=1.0,
            max_check_interval=2.0
        )

        with patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('time.sleep') as mock_sleep, \
             patch('time.time') as mock_time:

            mock_build_url.return_value = "http://192.168.1.100/cm"
            mock_get.side_effect = ConnectionError("Connection refused")

            # Mock time progression - need more values for multiple time.time() calls
            start_time = 1000.0
            time_progression = []
            for i in range(20):  # Enough values for all time.time() calls
                time_progression.append(start_time + (i * 5))  # Progress in 5-second increments
            mock_time.side_effect = time_progression

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            assert success is False
            assert report.timed_out is True
            assert report.error_type == "restart_timeout"
            assert report.attempts >= 1
            assert "did not come back online" in report.details["message"]

    def test_invalid_device_url(self):
        """Test device restart verification with invalid URL"""
        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(total_timeout=60)

        with patch('app.tasmota.updater.build_device_url') as mock_build_url:
            mock_build_url.return_value = None

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            assert success is False
            assert report.timed_out is True
            assert report.error_type == "invalid_url"
            assert report.attempts == 0
            assert "Failed to build valid device URL" in report.details["message"]

    def test_exponential_backoff_capping(self):
        """Test that exponential backoff is properly capped"""
        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(
            total_timeout=30,
            initial_wait=1,
            min_check_interval=1.0,
            max_check_interval=8.0,
            backoff_multiplier=3.0  # Aggressive multiplier
        )

        with patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('time.sleep') as mock_sleep, \
             patch('time.time') as mock_time:

            mock_build_url.return_value = "http://192.168.1.100/cm"
            mock_get.side_effect = ConnectionError("Connection refused")

            # Mock time to allow several attempts
            start_time = 1000.0
            mock_time.side_effect = [start_time + i for i in range(0, 50, 2)]

            verify_device_restart_with_backoff(device_config, timeout_config)

            # Check that sleep intervals are capped at max_check_interval
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list[1:]]  # Skip initial wait
            for interval in sleep_calls:
                assert interval <= timeout_config.max_check_interval


class TestUpdateDeviceFirmwareTimeout:
    """Test firmware update function with enhanced timeout handling"""

    def test_successful_firmware_update_with_timeout_report(self):
        """Test successful firmware update with timeout reporting"""
        device_config = {"ip": "192.168.1.100", "timeout": 120}

        with patch('app.tasmota.updater.get_device_firmware_version') as mock_get_version, \
             patch('app.tasmota.updater.fetch_latest_tasmota_release') as mock_latest, \
             patch('app.tasmota.updater.compare_versions') as mock_compare, \
             patch('app.tasmota.updater.is_fake_device') as mock_fake, \
             patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('app.tasmota.updater.verify_device_restart_with_backoff') as mock_verify:

            # Setup mocks
            mock_get_version.side_effect = [
                {"version": "12.0.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False},
                {"version": "12.1.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False}
            ]
            mock_latest.return_value = {"version": "12.1.0"}
            mock_compare.return_value = True  # Update needed
            mock_fake.return_value = False
            mock_build_url.return_value = "http://192.168.1.100/cm"

            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            # Mock successful restart verification
            timeout_report = TimeoutReport(
                total_timeout=120,
                elapsed_time=45.0,
                phase=TimeoutPhase.RESTART_VERIFICATION,
                attempts=3,
                last_check_interval=4.0,
                timed_out=False,
                error_type="none",
                details={"success": True}
            )
            mock_verify.return_value = (True, timeout_report)

            result = update_device_firmware(device_config, check_only=False)

            assert result["success"] is True
            assert result["message"] == "Firmware update completed successfully"
            assert result["current_version"] == "12.1.0"
            assert "timeout_config" in result
            assert result["timeout_config"]["total_timeout"] == 120
            assert "timeout_report" in result
            assert result["timeout_report"]["timed_out"] is False
            assert result["timeout_report"]["attempts"] == 3

    def test_firmware_update_timeout_during_restart(self):
        """Test firmware update with timeout during device restart"""
        device_config = {"ip": "192.168.1.100", "timeout": 60}

        with patch('app.tasmota.updater.get_device_firmware_version') as mock_get_version, \
             patch('app.tasmota.updater.fetch_latest_tasmota_release') as mock_latest, \
             patch('app.tasmota.updater.compare_versions') as mock_compare, \
             patch('app.tasmota.updater.is_fake_device') as mock_fake, \
             patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get, \
             patch('app.tasmota.updater.verify_device_restart_with_backoff') as mock_verify:

            # Setup mocks
            mock_get_version.return_value = {"version": "12.0.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False}
            mock_latest.return_value = {"version": "12.1.0"}
            mock_compare.return_value = True  # Update needed
            mock_fake.return_value = False
            mock_build_url.return_value = "http://192.168.1.100/cm"

            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            # Mock timeout during restart verification
            timeout_report = TimeoutReport(
                total_timeout=60,
                elapsed_time=60.0,
                phase=TimeoutPhase.RESTART_VERIFICATION,
                attempts=8,
                last_check_interval=15.0,
                timed_out=True,
                error_type="restart_timeout",
                details={"message": "Device did not come back online within 60 seconds"}
            )
            mock_verify.return_value = (False, timeout_report)

            result = update_device_firmware(device_config, check_only=False)

            assert result["success"] is False
            assert "did not come back online within 60 seconds" in result["message"]
            assert "timeout_report" in result
            assert result["timeout_report"]["timed_out"] is True
            assert result["timeout_report"]["error_type"] == "restart_timeout"

    def test_firmware_update_command_timeout(self):
        """Test firmware update with timeout sending upgrade command"""
        device_config = {"ip": "192.168.1.100", "timeout": 120}

        with patch('app.tasmota.updater.get_device_firmware_version') as mock_get_version, \
             patch('app.tasmota.updater.fetch_latest_tasmota_release') as mock_latest, \
             patch('app.tasmota.updater.compare_versions') as mock_compare, \
             patch('app.tasmota.updater.is_fake_device') as mock_fake, \
             patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get:

            # Setup mocks
            mock_get_version.return_value = {"version": "12.0.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False}
            mock_latest.return_value = {"version": "12.1.0"}
            mock_compare.return_value = True  # Update needed
            mock_fake.return_value = False
            mock_build_url.return_value = "http://192.168.1.100/cm"

            # Simulate timeout when sending upgrade command
            mock_get.side_effect = Timeout("Request timed out")

            result = update_device_firmware(device_config, check_only=False)

            assert result["success"] is False
            assert "Timeout sending upgrade command" in result["message"]
            assert "timeout_report" in result
            assert result["timeout_report"]["error_type"] == "command_timeout"

    def test_invalid_device_url_timeout_report(self):
        """Test firmware update with invalid device URL and timeout reporting"""
        device_config = {"ip": "invalid-ip", "timeout": 120}

        with patch('app.tasmota.updater.get_device_firmware_version') as mock_get_version, \
             patch('app.tasmota.updater.fetch_latest_tasmota_release') as mock_latest, \
             patch('app.tasmota.updater.compare_versions') as mock_compare, \
             patch('app.tasmota.updater.is_fake_device') as mock_fake, \
             patch('app.tasmota.updater.build_device_url') as mock_build_url:

            # Setup mocks
            mock_get_version.return_value = {"version": "12.0.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False}
            mock_latest.return_value = {"version": "12.1.0"}
            mock_compare.return_value = True  # Update needed
            mock_fake.return_value = False
            mock_build_url.return_value = None  # Invalid URL

            result = update_device_firmware(device_config, check_only=False)

            assert result["success"] is False
            assert "Invalid device IP address" in result["message"]
            assert "timeout_report" in result
            assert result["timeout_report"]["error_type"] == "invalid_url"

    def test_network_error_timeout_report(self):
        """Test firmware update with network error and timeout reporting"""
        device_config = {"ip": "192.168.1.100", "timeout": 120}

        with patch('app.tasmota.updater.get_device_firmware_version') as mock_get_version, \
             patch('app.tasmota.updater.fetch_latest_tasmota_release') as mock_latest, \
             patch('app.tasmota.updater.compare_versions') as mock_compare, \
             patch('app.tasmota.updater.is_fake_device') as mock_fake, \
             patch('app.tasmota.updater.build_device_url') as mock_build_url, \
             patch('app.tasmota.updater.requests.get') as mock_get:

            # Setup mocks
            mock_get_version.return_value = {"version": "12.0.0", "core_version": "2.7.4", "sdk_version": "3.0.2", "is_minimal": False}
            mock_latest.return_value = {"version": "12.1.0"}
            mock_compare.return_value = True  # Update needed
            mock_fake.return_value = False
            mock_build_url.return_value = "http://192.168.1.100/cm"

            # Simulate network error
            mock_get.side_effect = RequestException("Network unreachable")

            result = update_device_firmware(device_config, check_only=False)

            assert result["success"] is False
            assert "Network error during firmware update" in result["message"]
            assert "timeout_report" in result
            assert result["timeout_report"]["error_type"] == "network_error"


if __name__ == "__main__":
    pytest.main([__file__])
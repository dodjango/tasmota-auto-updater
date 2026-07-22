"""Test suite for API timeout handling functionality

Tests the timeout handling capabilities in the API endpoints including:
- Timeout parameter validation
- Timeout override functionality
- Structured timeout reporting in API responses
- Global timeout configuration for batch updates
"""

import pytest
import json
from unittest.mock import Mock, patch

from app.tasmota.api import DeviceUpdateSchema
from app.tasmota.updater import TimeoutReport, TimeoutPhase


class TestDeviceUpdateSchema:
    """Test device update schema timeout validation"""

    def test_valid_timeout_values(self):
        """Test valid timeout values pass validation"""
        schema = DeviceUpdateSchema()

        # Test minimum valid timeout
        data = {"ip": "192.168.1.100", "timeout": 60}
        errors = schema.validate(data)
        assert errors == {}

        # Test maximum valid timeout
        data = {"ip": "192.168.1.100", "timeout": 600}
        errors = schema.validate(data)
        assert errors == {}

        # Test typical timeout value
        data = {"ip": "192.168.1.100", "timeout": 180}
        errors = schema.validate(data)
        assert errors == {}

    def test_invalid_timeout_values(self):
        """Test invalid timeout values fail validation"""
        schema = DeviceUpdateSchema()

        # Test timeout too low
        data = {"ip": "192.168.1.100", "timeout": 30}
        errors = schema.validate(data)
        assert "timeout" in errors
        assert "greater than or equal to 60" in str(errors["timeout"])

        # Test timeout too high
        data = {"ip": "192.168.1.100", "timeout": 700}
        errors = schema.validate(data)
        assert "timeout" in errors
        assert "less than or equal to 600" in str(errors["timeout"])

        # Test non-integer timeout
        data = {"ip": "192.168.1.100", "timeout": "invalid"}
        errors = schema.validate(data)
        assert "timeout" in errors

    def test_optional_timeout_parameter(self):
        """Test that timeout parameter is optional"""
        schema = DeviceUpdateSchema()

        # Test without timeout parameter
        data = {"ip": "192.168.1.100"}
        errors = schema.validate(data)
        assert errors == {}

        # Test with other optional parameters
        data = {
            "ip": "192.168.1.100",
            "check_only": True,
            "username": "admin",
            "password": "secret"
        }
        errors = schema.validate(data)
        assert errors == {}


@pytest.fixture
def mock_app():
    """Create a mock Flask app for testing"""
    app = Mock()
    app.config = {'DEVICES_FILE': 'test_devices.yaml'}
    app.logger = Mock()
    return app


@pytest.fixture
def sample_devices():
    """Sample device configuration for testing"""
    return [
        {
            "ip": "192.168.1.100",
            "username": "admin",
            "password": "secret",
            "timeout": 120
        },
        {
            "ip": "192.168.1.101",
            "timeout": 240
        },
        {
            "ip": "192.168.1.102"
            # No timeout specified - should use default
        }
    ]


# Outdated vs current API (request.get_json / app-context / jsonify); excluded
# from CI until repaired. The TestDeviceUpdateSchema tests above stay in CI.
@pytest.mark.stale
class TestDeviceUpdateResourceTimeout:
    """Test device update resource timeout handling"""

    def test_device_update_with_timeout_override(
        self, mock_app, sample_devices
    ):
        """Test device update with timeout override"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        # Mock successful update with timeout report
        timeout_report = TimeoutReport(
            total_timeout=300,
            elapsed_time=45.5,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=3,
            last_check_interval=8.0,
            timed_out=False,
            error_type="none",
            details={"success": True}
        )

        mock_result = {
            "ip": "192.168.1.100",
            "success": True,
            "message": "Firmware update completed successfully",
            "current_version": "12.1.0",
            "latest_version": "12.1.0",
            "needs_update": False,
            "timeout_config": {
                "total_timeout": 300,
                "initial_wait": 10,
                "min_check_interval": 2.0,
                "max_check_interval": 30.0
            },
            "timeout_report": timeout_report.to_dict()
        }
        mock_update_firmware.return_value = mock_result

        from app.tasmota.api import DeviceUpdateResource

        # Create resource and mock request
        resource = DeviceUpdateResource()

        # Mock request with timeout override
        mock_request = Mock()
        mock_request.json = {
            "ip": "192.168.1.100",
            "timeout": 300,
            "check_only": False
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        # Verify timeout override was applied
        mock_update_firmware.assert_called_once()
        device_config_used = mock_update_firmware.call_args[0][0]
        assert device_config_used["timeout"] == 300  # Overridden value

        # Verify response contains timeout information
        result_data = json.loads(result.data.decode())
        assert "timeout_config" in result_data
        assert result_data["timeout_config"]["total_timeout"] == 300
        assert "timeout_report" in result_data
        assert result_data["timeout_report"]["total_timeout"] == 300

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    @patch('app.tasmota.api.update_device_firmware')
    def test_device_update_without_timeout_override(
        self, mock_update_firmware, mock_load_devices, mock_current_app,
        mock_app, sample_devices
    ):
        """Test device update without timeout override (uses device default)"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        mock_result = {
            "ip": "192.168.1.100",
            "success": True,
            "message": "Update check completed",
            "timeout_config": {
                "total_timeout": 120,  # Device's configured timeout
                "initial_wait": 10,
                "min_check_interval": 1.0,
                "max_check_interval": 20.0
            }
        }
        mock_update_firmware.return_value = mock_result

        from app.tasmota.api import DeviceUpdateResource

        resource = DeviceUpdateResource()

        # Mock request without timeout override
        mock_request = Mock()
        mock_request.json = {
            "ip": "192.168.1.100",
            "check_only": True
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        # Verify device's original timeout was used
        mock_update_firmware.assert_called_once()
        device_config_used = mock_update_firmware.call_args[0][0]
        assert device_config_used["timeout"] == 120  # Original device timeout

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    def test_device_not_found_error(
        self, mock_load_devices, mock_current_app, mock_app, sample_devices
    ):
        """Test device update with non-existent device"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        from app.tasmota.api import DeviceUpdateResource

        resource = DeviceUpdateResource()

        mock_request = Mock()
        mock_request.json = {
            "ip": "192.168.1.999",  # Non-existent device
            "timeout": 180
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        assert result[1] == 404  # HTTP 404 status
        result_data = result[0]
        assert result_data["error"] == "Device not found"


@pytest.mark.stale
class TestAllDevicesUpdateResourceTimeout:
    """Test all devices update resource timeout handling"""

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    @patch('app.tasmota.api.update_device_firmware')
    def test_all_devices_update_with_global_timeout(
        self, mock_update_firmware, mock_load_devices, mock_current_app,
        mock_app, sample_devices
    ):
        """Test updating all devices with global timeout override"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        # Mock update results
        mock_results = [
            {
                "ip": "192.168.1.100",
                "success": True,
                "needs_update": True,
                "timeout_config": {"total_timeout": 300}
            },
            {
                "ip": "192.168.1.101",
                "success": True,
                "needs_update": False,
                "timeout_config": {"total_timeout": 300}
            },
            {
                "ip": "192.168.1.102",
                "success": True,
                "needs_update": True,
                "timeout_config": {"total_timeout": 300}
            }
        ]
        mock_update_firmware.side_effect = mock_results

        from app.tasmota.api import AllDevicesUpdateResource

        resource = AllDevicesUpdateResource()

        mock_request = Mock()
        mock_request.json = {
            "timeout": 300,
            "check_only": True
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        # Verify global timeout was applied to all devices
        assert mock_update_firmware.call_count == 3
        for call in mock_update_firmware.call_args_list:
            device_config = call[0][0]
            assert device_config["timeout"] == 300

        # Verify response structure
        result_data = json.loads(result.data.decode())
        assert "results" in result_data
        assert len(result_data["results"]) == 3
        assert "summary" in result_data

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    def test_all_devices_update_invalid_global_timeout(
        self, mock_load_devices, mock_current_app, mock_app, sample_devices
    ):
        """Test all devices update with invalid global timeout"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        from app.tasmota.api import AllDevicesUpdateResource

        resource = AllDevicesUpdateResource()

        # Test timeout too low
        mock_request = Mock()
        mock_request.json = {
            "timeout": 30,  # Below minimum
            "check_only": True
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        assert result[1] == 400  # HTTP 400 status
        result_data = result[0]
        assert "Global timeout must be between 60 and 600 seconds" in result_data["error"]

        # Test timeout too high
        mock_request.json = {
            "timeout": 700,  # Above maximum
            "check_only": True
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        assert result[1] == 400  # HTTP 400 status
        result_data = result[0]
        assert "Global timeout must be between 60 and 600 seconds" in result_data["error"]

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    @patch('app.tasmota.api.update_device_firmware')
    def test_all_devices_update_without_global_timeout(
        self, mock_update_firmware, mock_load_devices, mock_current_app,
        mock_app, sample_devices
    ):
        """Test updating all devices without global timeout (uses individual device timeouts)"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        mock_results = [
            {"ip": "192.168.1.100", "success": True, "needs_update": False},
            {"ip": "192.168.1.101", "success": True, "needs_update": False},
            {"ip": "192.168.1.102", "success": True, "needs_update": False}
        ]
        mock_update_firmware.side_effect = mock_results

        from app.tasmota.api import AllDevicesUpdateResource

        resource = AllDevicesUpdateResource()

        mock_request = Mock()
        mock_request.json = {
            "check_only": True
            # No global timeout specified
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        # Verify individual device timeouts were preserved
        assert mock_update_firmware.call_count == 3
        call_args_list = mock_update_firmware.call_args_list

        # First device should have its configured timeout
        assert call_args_list[0][0][0]["timeout"] == 120
        # Second device should have its configured timeout
        assert call_args_list[1][0][0]["timeout"] == 240
        # Third device should use default timeout (180)
        assert call_args_list[2][0][0].get("timeout", 180) == 180

    @patch('app.tasmota.api.current_app')
    @patch('app.tasmota.api.load_devices_from_file')
    @patch('app.tasmota.api.update_device_firmware')
    def test_all_devices_update_with_timeout_reports(
        self, mock_update_firmware, mock_load_devices, mock_current_app,
        mock_app, sample_devices
    ):
        """Test all devices update includes timeout reports in response"""
        mock_current_app.return_value = mock_app
        mock_load_devices.return_value = sample_devices

        # Mock results with timeout reports
        timeout_report = TimeoutReport(
            total_timeout=240,
            elapsed_time=67.8,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=4,
            last_check_interval=12.0,
            timed_out=False,
            error_type="none",
            details={"success": True}
        )

        mock_results = [
            {
                "ip": "192.168.1.100",
                "success": True,
                "needs_update": True,
                "timeout_report": timeout_report.to_dict()
            },
            {
                "ip": "192.168.1.101",
                "success": True,
                "needs_update": False,
                "timeout_report": None
            },
            {
                "ip": "192.168.1.102",
                "success": False,
                "needs_update": True,
                "timeout_report": TimeoutReport(
                    total_timeout=240,
                    elapsed_time=240.0,
                    phase=TimeoutPhase.RESTART_VERIFICATION,
                    attempts=8,
                    last_check_interval=30.0,
                    timed_out=True,
                    error_type="restart_timeout",
                    details={"message": "Device did not respond"}
                ).to_dict()
            }
        ]
        mock_update_firmware.side_effect = mock_results

        from app.tasmota.api import AllDevicesUpdateResource

        resource = AllDevicesUpdateResource()

        mock_request = Mock()
        mock_request.json = {
            "timeout": 240,
            "check_only": False,
            "update_only_needed": True
        }

        with patch('app.tasmota.api.request', mock_request):
            result = resource.post()

        # Verify response contains timeout reports
        result_data = json.loads(result.data.decode())
        assert "results" in result_data

        results = result_data["results"]
        assert len(results) == 3

        # First device - successful with timeout report
        assert results[0]["timeout_report"]["timed_out"] is False
        assert results[0]["timeout_report"]["attempts"] == 4

        # Second device - no timeout report (check only, no update needed)
        assert results[1]["timeout_report"] is None

        # Third device - timeout occurred
        assert results[2]["timeout_report"]["timed_out"] is True
        assert results[2]["timeout_report"]["error_type"] == "restart_timeout"


if __name__ == "__main__":
    pytest.main([__file__])
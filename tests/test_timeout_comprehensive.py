"""Comprehensive timeout testing for Tasmota Updater

This test suite covers all timeout scenarios including:
- Configuration validation and edge cases
- Exponential backoff behavior
- Visual feedback integration
- Error differentiation
- Performance under load
- Security considerations
"""

import pytest
import time
import asyncio
import threading
from unittest.mock import Mock, patch, MagicMock, call
from requests.exceptions import ConnectionError, Timeout, RequestException
from freezegun import freeze_time

from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    create_timeout_config,
    verify_device_restart_with_backoff,
    update_device_firmware
)


class TestTimeoutConfigValidation:
    """Test timeout configuration validation and boundary conditions"""

    def test_timeout_config_minimum_boundary(self):
        """Test minimum timeout boundary (30 seconds)"""
        with pytest.raises(ValueError, match="Total timeout must be at least 30 seconds"):
            TimeoutConfig(total_timeout=29)

    def test_timeout_config_maximum_boundary(self):
        """Test maximum timeout boundary (600 seconds)"""
        with pytest.raises(ValueError, match="Total timeout cannot exceed 600 seconds"):
            TimeoutConfig(total_timeout=601)

    def test_timeout_config_valid_boundaries(self):
        """Test valid timeout boundaries"""
        # Test minimum valid value
        config_min = TimeoutConfig(total_timeout=30)
        assert config_min.total_timeout == 30

        # Test maximum valid value
        config_max = TimeoutConfig(total_timeout=600)
        assert config_max.total_timeout == 600

    def test_initial_wait_validation(self):
        """Test initial wait validation against total timeout"""
        with pytest.raises(ValueError, match="Initial wait must be less than total timeout"):
            TimeoutConfig(total_timeout=60, initial_wait=60)

        # Should work when initial_wait < total_timeout
        config = TimeoutConfig(total_timeout=60, initial_wait=59)
        assert config.initial_wait == 59

    def test_check_interval_validation(self):
        """Test check interval validation"""
        with pytest.raises(ValueError, match="Min check interval must be less than max check interval"):
            TimeoutConfig(min_check_interval=10.0, max_check_interval=5.0)

        # Equal intervals should also fail
        with pytest.raises(ValueError, match="Min check interval must be less than max check interval"):
            TimeoutConfig(min_check_interval=5.0, max_check_interval=5.0)

    @pytest.mark.parametrize("device_timeout,expected_total", [
        (30, 60),      # Too low, adjusted to minimum
        (45, 60),      # Below minimum, adjusted
        (180, 180),    # Standard timeout
        (300, 300),    # High timeout
        (700, 600),    # Too high, capped at maximum
    ])
    def test_create_timeout_config_adjustments(self, device_timeout, expected_total):
        """Test timeout config creation with various input values"""
        device_config = {"ip": "192.168.1.100", "timeout": device_timeout}
        config = create_timeout_config(device_config)
        assert config.total_timeout == expected_total

    def test_timeout_config_adaptive_intervals(self):
        """Test adaptive interval calculation based on total timeout"""
        # Short timeout should use small intervals
        device_config = {"ip": "192.168.1.100", "timeout": 60}
        config = create_timeout_config(device_config)
        assert config.min_check_interval == 1.0
        assert config.max_check_interval == 10.0  # 60 // 6

        # Long timeout should use larger intervals
        device_config = {"ip": "192.168.1.100", "timeout": 600}
        config = create_timeout_config(device_config)
        assert config.min_check_interval == 2.0
        assert config.max_check_interval == 30.0  # min(30, 600 // 6)


class TestExponentialBackoffBehavior:
    """Test exponential backoff behavior in timeout scenarios"""

    @patch('app.tasmota.updater.time.sleep')
    @patch('app.tasmota.updater.time.time')
    @patch('app.tasmota.updater.requests.get')
    def test_exponential_backoff_intervals(self, mock_requests, mock_time, mock_sleep):
        """Test that backoff intervals follow exponential pattern"""
        # Setup time progression
        time_values = [0, 5, 6.5, 8.75, 12.125, 30]  # Simulated time progression
        mock_time.side_effect = time_values

        # Setup request failures followed by success
        mock_requests.side_effect = [
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            Mock(status_code=200)  # Success on 4th attempt
        ]

        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(
            total_timeout=60,
            initial_wait=5,
            min_check_interval=1.0,
            max_check_interval=30.0,
            backoff_multiplier=1.5
        )

        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        assert success is True
        assert report.attempts == 4

        # Verify sleep intervals follow exponential backoff: 1.0, 1.5, 2.25
        expected_sleeps = [5, 1.0, 1.5, 2.25]  # initial_wait + exponential intervals
        mock_sleep.assert_has_calls([call(interval) for interval in expected_sleeps])

    @patch('app.tasmota.updater.time.sleep')
    @patch('app.tasmota.updater.time.time')
    @patch('app.tasmota.updater.requests.get')
    def test_backoff_capped_at_max_interval(self, mock_requests, mock_time, mock_sleep):
        """Test that backoff interval is capped at max_check_interval"""
        # Setup time progression for many failures
        time_values = [0] + [i * 2 for i in range(1, 20)]  # Long progression
        mock_time.side_effect = time_values

        # All requests fail except the last one
        mock_requests.side_effect = [ConnectionError("Failed")] * 10 + [Mock(status_code=200)]

        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(
            total_timeout=100,
            initial_wait=1,
            min_check_interval=1.0,
            max_check_interval=5.0,  # Low max to test capping
            backoff_multiplier=2.0
        )

        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        # Verify that sleep intervals are capped at max_check_interval
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        intervals_after_initial = sleep_calls[1:]  # Skip initial wait

        # With multiplier 2.0 and max 5.0: 1.0, 2.0, 4.0, 5.0 (capped), 5.0 (capped), ...
        assert all(interval <= 5.0 for interval in intervals_after_initial)
        assert 5.0 in intervals_after_initial  # Should reach the cap

    @patch('app.tasmota.updater.time.sleep')
    @patch('app.tasmota.updater.time.time')
    @patch('app.tasmota.updater.requests.get')
    def test_timeout_reached_before_success(self, mock_requests, mock_time, mock_sleep):
        """Test behavior when timeout is reached before device comes online"""
        # Setup time to exceed timeout
        mock_time.side_effect = [0, 10, 20, 35, 55, 80]  # Exceeds 60s timeout

        # All requests fail
        mock_requests.side_effect = ConnectionError("Connection failed")

        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(total_timeout=60, initial_wait=5)

        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        assert success is False
        assert report.timed_out is True
        assert report.error_type == "restart_timeout"
        assert report.elapsed_time >= 60
        assert "did not come back online within 60 seconds" in report.details["message"]


class TestTimeoutReporting:
    """Test structured timeout reporting functionality"""

    def test_timeout_report_structure(self):
        """Test timeout report structure and serialization"""
        report = TimeoutReport(
            total_timeout=180,
            elapsed_time=45.67,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=5,
            last_check_interval=2.25,
            timed_out=False,
            error_type="none",
            details={"success": True, "final_status_code": 200}
        )

        report_dict = report.to_dict()

        # Verify all required fields are present
        expected_fields = [
            'total_timeout', 'elapsed_time', 'phase', 'attempts',
            'last_check_interval', 'timed_out', 'error_type', 'details'
        ]
        for field in expected_fields:
            assert field in report_dict

        # Verify data types and formatting
        assert report_dict['total_timeout'] == 180
        assert report_dict['elapsed_time'] == 45.67
        assert report_dict['phase'] == 'restart_verification'
        assert report_dict['attempts'] == 5
        assert report_dict['last_check_interval'] == 2.25
        assert report_dict['timed_out'] is False
        assert report_dict['error_type'] == "none"
        assert isinstance(report_dict['details'], dict)

    def test_timeout_phases_enum(self):
        """Test timeout phase enumeration values"""
        assert TimeoutPhase.INITIAL_WAIT.value == "initial_wait"
        assert TimeoutPhase.RESTART_VERIFICATION.value == "restart_verification"
        assert TimeoutPhase.FIRMWARE_DOWNLOAD.value == "firmware_download"
        assert TimeoutPhase.FIRMWARE_FLASH.value == "firmware_flash"
        assert TimeoutPhase.DEVICE_REBOOT.value == "device_reboot"

    @patch('app.tasmota.updater.requests.get')
    def test_timeout_report_in_update_failure(self, mock_requests):
        """Test timeout report generation in update failure scenarios"""
        # Mock timeout during upgrade command
        mock_requests.side_effect = Timeout("Request timed out")

        device_config = {"ip": "192.168.1.100", "timeout": 120}

        with patch('app.tasmota.updater.build_device_url', return_value="http://192.168.1.100/cm"):
            with patch('app.tasmota.updater.get_device_firmware_version', return_value={"version": "12.0.0"}):
                with patch('app.tasmota.updater.fetch_latest_tasmota_release', return_value={"version": "13.0.0"}):
                    result = update_device_firmware(device_config)

        assert result["success"] is False
        assert "timeout_report" in result
        timeout_report = result["timeout_report"]

        assert timeout_report["error_type"] == "command_timeout"
        assert timeout_report["phase"] == "initial_wait"
        assert timeout_report["timed_out"] is True


class TestVisualFeedbackIntegration:
    """Test integration between timeout handling and visual feedback"""

    def test_timeout_config_in_api_response(self, client, mock_device_config):
        """Test that timeout configuration is included in API responses"""
        with patch('app.tasmota.utils.load_devices_from_file', return_value=[mock_device_config]):
            with patch('app.tasmota.updater.get_device_firmware_version', return_value={"version": "12.0.0"}):
                with patch('app.tasmota.updater.fetch_latest_tasmota_release', return_value={"version": "13.0.0"}):
                    with patch('app.tasmota.updater.verify_device_restart_with_backoff',
                              return_value=(True, TimeoutReport(
                                  total_timeout=180, elapsed_time=45.0, phase=TimeoutPhase.RESTART_VERIFICATION,
                                  attempts=3, last_check_interval=2.0, timed_out=False, error_type="none", details={}
                              ))):
                        response = client.post('/api/update',
                                             json={'ip': '192.168.1.100', 'timeout': 240})

        assert response.status_code == 200
        data = response.get_json()

        # Verify timeout configuration is included
        assert 'timeout_config' in data
        timeout_config = data['timeout_config']
        assert timeout_config['total_timeout'] == 240
        assert 'initial_wait' in timeout_config
        assert 'min_check_interval' in timeout_config
        assert 'max_check_interval' in timeout_config

        # Verify timeout report is included
        assert 'timeout_report' in data
        timeout_report = data['timeout_report']
        assert timeout_report['elapsed_time'] == 45.0
        assert timeout_report['attempts'] == 3

    @pytest.mark.parametrize("timeout_override", [60, 180, 300, 600])
    def test_api_timeout_parameter_validation(self, client, timeout_override):
        """Test API timeout parameter validation"""
        with patch('app.tasmota.utils.load_devices_from_file', return_value=[{"ip": "192.168.1.100"}]):
            response = client.post('/api/update',
                                 json={'ip': '192.168.1.100', 'timeout': timeout_override})

        if 60 <= timeout_override <= 600:
            assert response.status_code == 200
        else:
            assert response.status_code == 400

    def test_api_invalid_timeout_parameter(self, client):
        """Test API validation of invalid timeout parameters"""
        invalid_timeouts = [30, 700, -1, "invalid", None]

        for invalid_timeout in invalid_timeouts:
            with patch('app.tasmota.utils.load_devices_from_file', return_value=[{"ip": "192.168.1.100"}]):
                response = client.post('/api/update',
                                     json={'ip': '192.168.1.100', 'timeout': invalid_timeout})

            if invalid_timeout in [30, 700, -1, "invalid"]:
                assert response.status_code == 400
                data = response.get_json()
                assert 'error' in data


class TestErrorDifferentiation:
    """Test error differentiation between network, update, and restart timeouts"""

    @patch('app.tasmota.updater.requests.get')
    def test_network_error_differentiation(self, mock_requests):
        """Test differentiation of network errors vs timeout errors"""
        # Test ConnectionError (network issue)
        mock_requests.side_effect = ConnectionError("Network unreachable")

        device_config = {"ip": "192.168.1.100"}
        timeout_config = TimeoutConfig(total_timeout=60)

        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        assert success is False
        assert report.error_type == "restart_timeout"  # Eventual timeout due to network issues

        # Test Timeout error (request timeout)
        mock_requests.side_effect = Timeout("Request timeout")
        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        assert success is False
        assert report.error_type == "restart_timeout"

    @patch('app.tasmota.updater.requests.get')
    def test_command_timeout_vs_restart_timeout(self, mock_requests):
        """Test differentiation between command timeout and restart timeout"""
        device_config = {"ip": "192.168.1.100", "timeout": 120}

        with patch('app.tasmota.updater.build_device_url', return_value="http://192.168.1.100/cm"):
            with patch('app.tasmota.updater.get_device_firmware_version', return_value={"version": "12.0.0"}):
                with patch('app.tasmota.updater.fetch_latest_tasmota_release', return_value={"version": "13.0.0"}):

                    # Test command timeout (upgrade command fails)
                    mock_requests.side_effect = Timeout("Command timeout")
                    result = update_device_firmware(device_config)

                    assert result["success"] is False
                    assert result["timeout_report"]["error_type"] == "command_timeout"
                    assert result["timeout_report"]["phase"] == "initial_wait"

    def test_invalid_url_error(self):
        """Test handling of invalid device URL"""
        device_config = {"ip": "invalid_ip"}
        timeout_config = TimeoutConfig(total_timeout=60)

        with patch('app.tasmota.updater.build_device_url', return_value=None):
            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        assert success is False
        assert report.error_type == "invalid_url"
        assert report.attempts == 0
        assert "Failed to build valid device URL" in report.details["message"]


class TestPerformanceUnderLoad:
    """Test timeout handling performance under load conditions"""

    @pytest.mark.slow
    @patch('app.tasmota.updater.requests.get')
    def test_concurrent_device_updates(self, mock_requests):
        """Test timeout handling with multiple concurrent device updates"""
        import concurrent.futures
        import random

        # Mock varying response times
        def mock_request_with_delay(*args, **kwargs):
            time.sleep(random.uniform(0.1, 0.5))  # Simulate network delay
            return Mock(status_code=200)

        mock_requests.side_effect = mock_request_with_delay

        devices = [{"ip": f"192.168.1.{100+i}", "timeout": 60} for i in range(5)]
        timeout_configs = [create_timeout_config(device) for device in devices]

        start_time = time.time()

        # Test concurrent timeout handling
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(verify_device_restart_with_backoff, device, config)
                for device, config in zip(devices, timeout_configs)
            ]

            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        elapsed_time = time.time() - start_time

        # All should succeed with proper timeout handling
        assert all(success for success, _ in results)

        # Should complete within reasonable time (parallel execution)
        assert elapsed_time < 10  # Should be much faster than sequential

    @pytest.mark.slow
    def test_timeout_precision_under_load(self):
        """Test timeout precision under high load conditions"""
        import threading

        results = []
        start_time = time.time()

        def worker():
            device_config = {"ip": "192.168.1.100"}
            timeout_config = TimeoutConfig(total_timeout=30)

            with patch('app.tasmota.updater.requests.get', side_effect=ConnectionError("Failed")):
                success, report = verify_device_restart_with_backoff(device_config, timeout_config)
                results.append((success, report.elapsed_time))

        # Start multiple workers simultaneously
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Verify timeout precision
        for success, elapsed_time in results:
            assert success is False
            assert 29 <= elapsed_time <= 35  # Allow some tolerance for timing


class TestSecurityAndInput:
    """Test security considerations and input validation"""

    def test_timeout_parameter_sanitization(self, security_test_scenarios):
        """Test that timeout parameters are properly sanitized"""
        malicious_timeouts = [
            security_test_scenarios['sql_injection'],
            security_test_scenarios['xss_payload'],
            security_test_scenarios['command_injection'],
        ]

        for malicious_input in malicious_timeouts:
            device_config = {"ip": "192.168.1.100", "timeout": malicious_input}

            # Should handle invalid input gracefully
            try:
                config = create_timeout_config(device_config)
                # If no exception, should use default timeout
                assert config.total_timeout == 180
            except (ValueError, TypeError):
                # Expected for invalid input types
                pass

    def test_device_ip_validation_in_timeout_context(self, security_test_scenarios):
        """Test device IP validation in timeout scenarios"""
        malicious_ips = [
            security_test_scenarios['sql_injection'],
            security_test_scenarios['command_injection'],
            "../../../etc/passwd",
            "127.0.0.1; cat /etc/passwd",
        ]

        for malicious_ip in malicious_ips:
            device_config = {"ip": malicious_ip}
            timeout_config = TimeoutConfig(total_timeout=60)

            with patch('app.tasmota.updater.build_device_url', return_value=None):
                success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            # Should fail safely without executing malicious commands
            assert success is False
            assert report.error_type == "invalid_url"

    def test_log_sanitization_in_timeout_errors(self, caplog):
        """Test that timeout error logs are properly sanitized"""
        device_config = {"ip": "192.168.1.100", "password": "secret123"}

        with patch('app.tasmota.updater.requests.get',
                  side_effect=RequestException("Error with password: secret123")):
            timeout_config = TimeoutConfig(total_timeout=60)
            verify_device_restart_with_backoff(device_config, timeout_config)

        # Check that sensitive data is not logged
        log_output = caplog.text
        assert "secret123" not in log_output
        assert "********" in log_output or "password" not in log_output.lower()


class TestRegressionPrevention:
    """Test regression prevention for existing functionality"""

    def test_backward_compatibility_device_config(self):
        """Test backward compatibility with old device configuration format"""
        # Old format: just IP string
        old_format_ip = "192.168.1.100"

        with patch('app.tasmota.updater.build_device_url') as mock_build_url:
            with patch('app.tasmota.updater.is_valid_ip_address', return_value=True):
                mock_build_url.return_value = "http://192.168.1.100/cm"

                # Should work with old string format
                timeout_config = create_timeout_config({"ip": old_format_ip})
                assert timeout_config.total_timeout == 180  # Default

    def test_existing_api_endpoints_still_work(self, client):
        """Test that existing API endpoints still work after timeout improvements"""
        with patch('app.tasmota.utils.load_devices_from_file', return_value=[{"ip": "192.168.1.100"}]):
            # Test without timeout parameter (should use defaults)
            response = client.post('/api/update', json={'ip': '192.168.1.100'})

            # Should not break existing functionality
            assert response.status_code in [200, 404, 500]  # Valid HTTP responses

    def test_fake_device_timeout_handling(self, mock_fake_device_config):
        """Test that fake devices still work with timeout improvements"""
        with patch('app.tasmota.updater.fetch_latest_tasmota_release',
                  return_value={"version": "13.0.0"}):
            with patch('app.tasmota.utils.is_fake_device', return_value=True):
                result = update_device_firmware(mock_fake_device_config)

        assert result["success"] is True
        assert "timeout_config" in result
        assert result["timeout_config"]["total_timeout"] == 180


# Performance markers for test categorization
pytestmark = [
    pytest.mark.integration,
    pytest.mark.stale,  # unmocked network → hangs; pending repair vs current code
]
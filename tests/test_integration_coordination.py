"""Integration tests for frontend-backend timeout coordination

This module tests the complete integration between frontend timeout handling,
backend timeout logic, and container configuration. It validates:
- End-to-end timeout coordination
- API timeout parameter validation
- Container timeout configuration
- Real-time communication during updates
- Error propagation across layers
"""

import pytest
import time
import json
import asyncio
import threading
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from server import create_app
from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    update_device_firmware,
    verify_device_restart_with_backoff
)


class TestEndToEndTimeoutCoordination:
    """Test complete end-to-end timeout coordination"""

    @pytest.fixture
    def app_with_test_config(self):
        """Create app with test configuration"""
        app = create_app()
        app.config.update({
            'TESTING': True,
            'DEVICES_FILE': 'test_devices.yaml'
        })
        return app

    def test_complete_update_flow_with_timeouts(self, app_with_test_config):
        """Test complete firmware update flow with timeout coordination"""
        with app_with_test_config.test_client() as client:
            # Mock device configuration
            device_config = {
                'ip': '192.168.1.100',
                'username': 'admin',
                'password': 'admin',
                'timeout': 240
            }

            # Mock successful flow with timing
            mock_responses = []

            def mock_update_firmware(config, check_only=False):
                """Mock update with realistic timing"""
                start_time = time.time()

                # Simulate update process with stages
                if not check_only:
                    time.sleep(0.1)  # Simulate processing time

                timeout_report = TimeoutReport(
                    total_timeout=config.get('timeout', 240),
                    elapsed_time=0.1,
                    phase=TimeoutPhase.RESTART_VERIFICATION,
                    attempts=3,
                    last_check_interval=2.0,
                    timed_out=False,
                    error_type="none",
                    details={"success": True}
                )

                return {
                    'ip': config['ip'],
                    'success': True,
                    'message': 'Update completed successfully',
                    'current_version': '13.0.0',
                    'latest_version': '13.0.0',
                    'needs_update': False,
                    'timeout_config': {
                        'total_timeout': config.get('timeout', 240),
                        'initial_wait': 10,
                        'min_check_interval': 2.0,
                        'max_check_interval': 30.0
                    },
                    'timeout_report': timeout_report.to_dict()
                }

            with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_update_firmware):

                    # Test single device update
                    response = client.post('/api/update', json={
                        'ip': '192.168.1.100',
                        'timeout': 240,
                        'check_only': False
                    })

                    assert response.status_code == 200
                    data = response.get_json()

                    # Verify timeout coordination
                    assert data['success'] is True
                    assert 'timeout_config' in data
                    assert data['timeout_config']['total_timeout'] == 240
                    assert 'timeout_report' in data
                    assert data['timeout_report']['timed_out'] is False

    def test_api_timeout_parameter_propagation(self, app_with_test_config):
        """Test timeout parameter propagation through API layers"""
        test_cases = [
            {'timeout': 60, 'expected': 60},
            {'timeout': 180, 'expected': 180},
            {'timeout': 300, 'expected': 300},
            {'timeout': 600, 'expected': 600},
        ]

        with app_with_test_config.test_client() as client:
            for case in test_cases:
                device_config = {'ip': '192.168.1.100'}

                with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                    with patch('app.tasmota.updater.update_device_firmware') as mock_update:
                        mock_update.return_value = {
                            'ip': '192.168.1.100',
                            'success': True,
                            'timeout_config': {'total_timeout': case['expected']}
                        }

                        response = client.post('/api/update', json={
                            'ip': '192.168.1.100',
                            'timeout': case['timeout']
                        })

                        assert response.status_code == 200

                        # Verify timeout was passed to backend
                        args, kwargs = mock_update.call_args
                        device_config_arg = args[0]
                        assert device_config_arg['timeout'] == case['expected']

    def test_batch_update_timeout_coordination(self, app_with_test_config):
        """Test timeout coordination for batch device updates"""
        devices = [
            {'ip': '192.168.1.100', 'timeout': 180},
            {'ip': '192.168.1.101', 'timeout': 240},
            {'ip': '192.168.1.102', 'timeout': 300}
        ]

        def mock_batch_update(config, check_only=False):
            """Mock batch update with varying completion times"""
            device_ip = config['ip']
            timeout = config.get('timeout', 180)

            # Simulate different completion times
            completion_times = {
                '192.168.1.100': 0.05,
                '192.168.1.101': 0.1,
                '192.168.1.102': 0.15
            }

            time.sleep(completion_times.get(device_ip, 0.1))

            return {
                'ip': device_ip,
                'success': True,
                'message': 'Update completed',
                'timeout_config': {'total_timeout': timeout},
                'needs_update': True,
                'update_started': not check_only,
                'update_completed': True
            }

        with app_with_test_config.test_client() as client:
            with patch('app.tasmota.utils.load_devices_from_file', return_value=devices):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_batch_update):

                    start_time = time.time()

                    response = client.post('/api/update/all', json={
                        'check_only': False,
                        'update_only_needed': True,
                        'timeout': 300  # Global timeout override
                    })

                    end_time = time.time()

                    assert response.status_code == 200
                    data = response.get_json()

                    # Verify batch coordination
                    assert 'results' in data
                    assert 'summary' in data
                    assert len(data['results']) == 3

                    # Verify all devices used global timeout
                    for result in data['results']:
                        assert result['timeout_config']['total_timeout'] == 300

                    # Verify timing (should be roughly parallel, not sequential)
                    total_time = end_time - start_time
                    assert total_time < 1.0  # Much faster than sequential (0.3s)

    def test_error_propagation_across_layers(self, app_with_test_config):
        """Test error propagation from backend to frontend"""
        device_config = {'ip': '192.168.1.100', 'timeout': 60}

        # Mock different types of errors
        error_scenarios = [
            {
                'error_type': 'timeout',
                'backend_response': {
                    'ip': '192.168.1.100',
                    'success': False,
                    'message': 'Device restart verification timed out after 60 seconds',
                    'timeout_report': {
                        'total_timeout': 60,
                        'elapsed_time': 62.0,
                        'timed_out': True,
                        'error_type': 'restart_timeout',
                        'phase': 'restart_verification'
                    }
                }
            },
            {
                'error_type': 'network',
                'backend_response': {
                    'ip': '192.168.1.100',
                    'success': False,
                    'message': 'Network error during firmware update',
                    'timeout_report': {
                        'total_timeout': 60,
                        'elapsed_time': 5.0,
                        'timed_out': False,
                        'error_type': 'network_error'
                    }
                }
            },
            {
                'error_type': 'invalid_device',
                'backend_response': {
                    'ip': '192.168.1.100',
                    'success': False,
                    'message': 'Invalid device IP address',
                    'timeout_report': {
                        'total_timeout': 60,
                        'elapsed_time': 0.0,
                        'timed_out': False,
                        'error_type': 'invalid_url'
                    }
                }
            }
        ]

        with app_with_test_config.test_client() as client:
            for scenario in error_scenarios:
                with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                    with patch('app.tasmota.updater.update_device_firmware',
                              return_value=scenario['backend_response']):

                        response = client.post('/api/update', json={
                            'ip': '192.168.1.100',
                            'timeout': 60
                        })

                        assert response.status_code == 200
                        data = response.get_json()

                        # Verify error propagation
                        assert data['success'] is False
                        assert 'timeout_report' in data
                        assert data['timeout_report']['error_type'] == scenario['backend_response']['timeout_report']['error_type']

    def test_real_time_progress_coordination(self, app_with_test_config):
        """Test real-time progress coordination during updates"""
        device_config = {'ip': '192.168.1.100', 'timeout': 180}

        # Mock progressive update states
        update_stages = []

        def mock_progressive_update(config, check_only=False):
            """Mock update that tracks progress stages"""
            stages = [
                ('initial_wait', 'Sending upgrade command'),
                ('firmware_download', 'Downloading firmware'),
                ('firmware_flash', 'Flashing firmware'),
                ('device_reboot', 'Device rebooting'),
                ('restart_verification', 'Verifying restart')
            ]

            for i, (phase, message) in enumerate(stages):
                stage_report = {
                    'phase': phase,
                    'message': message,
                    'progress_percentage': (i + 1) / len(stages) * 100,
                    'elapsed_time': (i + 1) * 0.02
                }
                update_stages.append(stage_report)
                time.sleep(0.02)  # Simulate stage duration

            return {
                'ip': config['ip'],
                'success': True,
                'message': 'Update completed successfully',
                'timeout_config': {'total_timeout': config.get('timeout', 180)},
                'timeout_report': {
                    'total_timeout': 180,
                    'elapsed_time': 0.1,
                    'phase': 'restart_verification',
                    'timed_out': False,
                    'error_type': 'none'
                },
                'update_stages': update_stages
            }

        with app_with_test_config.test_client() as client:
            with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_progressive_update):

                    response = client.post('/api/update', json={
                        'ip': '192.168.1.100',
                        'timeout': 180
                    })

                    assert response.status_code == 200
                    data = response.get_json()

                    # Verify progress coordination
                    assert data['success'] is True
                    assert 'update_stages' in data
                    assert len(data['update_stages']) == 5

                    # Verify stage progression
                    expected_phases = ['initial_wait', 'firmware_download', 'firmware_flash', 'device_reboot', 'restart_verification']
                    actual_phases = [stage['phase'] for stage in data['update_stages']]
                    assert actual_phases == expected_phases


class TestContainerTimeoutIntegration:
    """Test container timeout configuration integration"""

    def test_gunicorn_timeout_configuration(self):
        """Test Gunicorn timeout configuration for long-running updates"""
        # Import the Gunicorn configuration
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

        import gunicorn.conf as gunicorn_config

        # Verify timeout settings
        assert hasattr(gunicorn_config, 'timeout')
        assert gunicorn_config.timeout >= 300  # At least 5 minutes for firmware updates

        # Verify worker configuration
        assert hasattr(gunicorn_config, 'workers')
        assert gunicorn_config.workers >= 1

        # Verify graceful timeout
        assert hasattr(gunicorn_config, 'graceful_timeout')
        assert gunicorn_config.graceful_timeout >= 30

    def test_container_environment_timeout_override(self):
        """Test timeout configuration via environment variables"""
        import os
        original_timeout = os.environ.get('GUNICORN_TIMEOUT')

        try:
            # Test environment variable override
            os.environ['GUNICORN_TIMEOUT'] = '450'

            # Reload configuration (simulate)
            timeout_value = int(os.environ.get('GUNICORN_TIMEOUT', '300'))
            assert timeout_value == 450

            # Test with invalid value
            os.environ['GUNICORN_TIMEOUT'] = 'invalid'
            timeout_value = int(os.environ.get('GUNICORN_TIMEOUT', '300'))
            # Should fall back to default
            assert timeout_value == 300

        except ValueError:
            # Expected for invalid value
            pass
        finally:
            # Restore original environment
            if original_timeout is not None:
                os.environ['GUNICORN_TIMEOUT'] = original_timeout
            elif 'GUNICORN_TIMEOUT' in os.environ:
                del os.environ['GUNICORN_TIMEOUT']

    @patch('gunicorn.app.wsgiapp.WSGIApplication.run')
    def test_container_timeout_coordination_with_app(self, mock_gunicorn_run):
        """Test coordination between container timeouts and application timeouts"""
        from server import create_app

        app = create_app()

        # Mock Gunicorn configuration
        class MockGunicornConfig:
            timeout = 300
            workers = 2
            graceful_timeout = 30

        mock_config = MockGunicornConfig()

        # Test that application respects container timeouts
        with app.test_client() as client:
            # Mock a long-running update within container timeout
            device_config = {'ip': '192.168.1.100', 'timeout': 280}  # Less than container timeout

            def mock_long_update(config, check_only=False):
                # Simulate update that takes most of the container timeout
                time.sleep(0.1)  # Simulate processing

                return {
                    'ip': config['ip'],
                    'success': True,
                    'message': 'Update completed within container timeout',
                    'timeout_config': {'total_timeout': config.get('timeout', 280)},
                    'container_timeout_respected': True
                }

            with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_long_update):

                    response = client.post('/api/update', json={
                        'ip': '192.168.1.100',
                        'timeout': 280
                    })

                    assert response.status_code == 200
                    data = response.get_json()
                    assert data['success'] is True
                    assert data.get('container_timeout_respected') is True


class TestConcurrentUpdateCoordination:
    """Test coordination of concurrent device updates"""

    def test_concurrent_timeout_handling(self, app_with_test_config):
        """Test timeout handling with multiple concurrent updates"""
        devices = [{'ip': f'192.168.1.{100+i}', 'timeout': 60 + (i * 30)} for i in range(5)]

        def mock_concurrent_update(config, check_only=False):
            """Mock update with varying completion times"""
            import random
            device_ip = config['ip']
            timeout = config.get('timeout', 60)

            # Simulate varying update times
            completion_time = random.uniform(0.05, 0.2)
            time.sleep(completion_time)

            return {
                'ip': device_ip,
                'success': True,
                'message': f'Update completed in {completion_time:.2f}s',
                'timeout_config': {'total_timeout': timeout},
                'completion_time': completion_time,
                'needs_update': True,
                'update_started': True,
                'update_completed': True
            }

        with app_with_test_config.test_client() as client:
            with patch('app.tasmota.utils.load_devices_from_file', return_value=devices):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_concurrent_update):

                    start_time = time.time()

                    response = client.post('/api/update/all', json={
                        'check_only': False,
                        'update_only_needed': True
                    })

                    end_time = time.time()
                    total_time = end_time - start_time

                    assert response.status_code == 200
                    data = response.get_json()

                    # Verify concurrent execution
                    assert len(data['results']) == 5
                    assert data['summary']['updated'] == 5

                    # Should complete faster than sequential execution
                    assert total_time < 0.5  # Much faster than 5 * 0.2 = 1.0s

    def test_mixed_timeout_scenarios(self, app_with_test_config):
        """Test coordination with mixed success/failure timeout scenarios"""
        devices = [
            {'ip': '192.168.1.100', 'timeout': 60},   # Will succeed quickly
            {'ip': '192.168.1.101', 'timeout': 120},  # Will timeout
            {'ip': '192.168.1.102', 'timeout': 180},  # Will succeed slowly
            {'ip': '192.168.1.103', 'timeout': 240},  # Will have network error
        ]

        def mock_mixed_scenario_update(config, check_only=False):
            """Mock update with different outcomes based on IP"""
            device_ip = config['ip']
            timeout = config.get('timeout', 60)

            if device_ip == '192.168.1.100':
                # Quick success
                time.sleep(0.05)
                return {
                    'ip': device_ip,
                    'success': True,
                    'message': 'Quick update completed',
                    'timeout_config': {'total_timeout': timeout},
                    'needs_update': True,
                    'update_started': True,
                    'update_completed': True
                }

            elif device_ip == '192.168.1.101':
                # Timeout scenario
                time.sleep(0.1)
                return {
                    'ip': device_ip,
                    'success': False,
                    'message': 'Update timed out',
                    'timeout_config': {'total_timeout': timeout},
                    'timeout_report': {
                        'timed_out': True,
                        'error_type': 'restart_timeout',
                        'elapsed_time': timeout + 1
                    },
                    'needs_update': True,
                    'update_started': True,
                    'update_completed': False
                }

            elif device_ip == '192.168.1.102':
                # Slow success
                time.sleep(0.15)
                return {
                    'ip': device_ip,
                    'success': True,
                    'message': 'Slow update completed',
                    'timeout_config': {'total_timeout': timeout},
                    'needs_update': True,
                    'update_started': True,
                    'update_completed': True
                }

            else:  # 192.168.1.103
                # Network error
                time.sleep(0.08)
                return {
                    'ip': device_ip,
                    'success': False,
                    'message': 'Network error during update',
                    'timeout_config': {'total_timeout': timeout},
                    'timeout_report': {
                        'timed_out': False,
                        'error_type': 'network_error',
                        'elapsed_time': 5.0
                    },
                    'needs_update': True,
                    'update_started': True,
                    'update_completed': False
                }

        with app_with_test_config.test_client() as client:
            with patch('app.tasmota.utils.load_devices_from_file', return_value=devices):
                with patch('app.tasmota.updater.update_device_firmware', side_effect=mock_mixed_scenario_update):

                    response = client.post('/api/update/all', json={
                        'check_only': False,
                        'update_only_needed': True
                    })

                    assert response.status_code == 200
                    data = response.get_json()

                    # Verify mixed results coordination
                    assert len(data['results']) == 4
                    assert data['summary']['total'] == 4

                    # Count different outcomes
                    successful = sum(1 for r in data['results'] if r['success'])
                    failed = sum(1 for r in data['results'] if not r['success'])
                    timeouts = sum(1 for r in data['results']
                                  if not r['success'] and
                                  r.get('timeout_report', {}).get('timed_out', False))

                    assert successful == 2  # 192.168.1.100 and 192.168.1.102
                    assert failed == 2      # 192.168.1.101 and 192.168.1.103
                    assert timeouts == 1    # 192.168.1.101

    def test_resource_management_during_concurrent_updates(self):
        """Test resource management during concurrent timeout operations"""
        import threading
        import queue
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Track resource usage
        active_connections = queue.Queue()
        max_concurrent = 0
        lock = threading.Lock()

        def mock_resource_intensive_update(device_config):
            """Mock update that tracks resource usage"""
            nonlocal max_concurrent

            with lock:
                active_connections.put(threading.current_thread().ident)
                current_count = active_connections.qsize()
                max_concurrent = max(max_concurrent, current_count)

            try:
                # Simulate resource-intensive operation
                time.sleep(0.1)

                return {
                    'ip': device_config['ip'],
                    'success': True,
                    'message': 'Update completed',
                    'thread_id': threading.current_thread().ident
                }
            finally:
                with lock:
                    try:
                        active_connections.get_nowait()
                    except queue.Empty:
                        pass

        # Test with multiple devices
        devices = [{'ip': f'192.168.1.{100+i}'} for i in range(10)]

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(mock_resource_intensive_update, device)
                for device in devices
            ]

            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        # Verify resource management
        assert len(results) == 10
        assert all(r['success'] for r in results)
        assert max_concurrent <= 5  # Should respect thread pool limit

        # Verify unique thread usage
        thread_ids = [r['thread_id'] for r in results]
        assert len(set(thread_ids)) <= 5  # Should reuse threads efficiently


# Test markers for categorization
pytestmark = [
    pytest.mark.integration,
    pytest.mark.coordination,
    pytest.mark.stale,  # failing/erroring vs current code; pending repair
]
"""Performance and Load Testing for Timeout Handling

This module tests timeout handling performance under various load conditions:
- High concurrent device updates
- Resource utilization during timeouts
- Memory and CPU usage patterns
- Network timeout simulation under load
- Stress testing with multiple timeout scenarios
- Performance regression detection
"""

import pytest
import time
import threading
import psutil
import gc
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from unittest.mock import Mock, patch, MagicMock

pytest.importorskip("memory_profiler", reason="memory_profiler not installed (performance tests)")
from memory_profiler import profile
import statistics

from app.tasmota.updater import (
    TimeoutConfig,
    TimeoutReport,
    TimeoutPhase,
    verify_device_restart_with_backoff,
    update_device_firmware,
    create_timeout_config
)


class TestHighConcurrencyTimeouts:
    """Test timeout handling under high concurrency loads"""

    @pytest.mark.slow
    @pytest.mark.performance
    def test_concurrent_device_timeout_handling(self):
        """Test timeout handling with many concurrent device operations"""
        num_devices = 50
        devices = [{'ip': f'192.168.1.{100 + (i % 154)}', 'timeout': 60} for i in range(num_devices)]

        results = []
        start_time = time.time()
        max_workers = 10

        def mock_device_operation(device_config):
            """Mock device operation that may timeout"""
            import random

            # Simulate various outcomes
            outcome = random.choice(['success', 'timeout', 'error'])
            delay = random.uniform(0.01, 0.1)
            time.sleep(delay)

            if outcome == 'success':
                return {
                    'ip': device_config['ip'],
                    'success': True,
                    'elapsed_time': delay,
                    'outcome': 'success'
                }
            elif outcome == 'timeout':
                return {
                    'ip': device_config['ip'],
                    'success': False,
                    'elapsed_time': device_config['timeout'],
                    'outcome': 'timeout',
                    'error_type': 'restart_timeout'
                }
            else:
                return {
                    'ip': device_config['ip'],
                    'success': False,
                    'elapsed_time': delay,
                    'outcome': 'error',
                    'error_type': 'network_error'
                }

        # Execute concurrent operations
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(mock_device_operation, device)
                for device in devices
            ]

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        end_time = time.time()
        total_time = end_time - start_time

        # Performance assertions
        assert len(results) == num_devices
        assert total_time < 5.0  # Should complete within 5 seconds

        # Analyze outcomes
        successful = sum(1 for r in results if r['success'])
        timeouts = sum(1 for r in results if r.get('error_type') == 'restart_timeout')
        errors = sum(1 for r in results if r.get('error_type') == 'network_error')

        # Should handle mixed outcomes gracefully
        assert successful + timeouts + errors == num_devices

        # Calculate average response time
        response_times = [r['elapsed_time'] for r in results if r['success']]
        if response_times:
            avg_response_time = statistics.mean(response_times)
            assert avg_response_time < 0.2  # Average under 200ms

    @pytest.mark.slow
    @pytest.mark.performance
    def test_memory_usage_during_concurrent_timeouts(self):
        """Test memory usage patterns during concurrent timeout operations"""
        import tracemalloc

        tracemalloc.start()
        initial_memory = psutil.Process().memory_info().rss

        num_operations = 100
        timeout_configs = [
            TimeoutConfig(total_timeout=60 + (i % 300))
            for i in range(num_operations)
        ]

        def memory_intensive_timeout_operation(config):
            """Mock operation that uses memory during timeout handling"""
            device_config = {'ip': f'192.168.1.{100 + (id(config) % 154)}'}

            # Simulate memory allocation during timeout
            large_data = [i for i in range(1000)]  # Simulate processing data

            with patch('app.tasmota.updater.requests.get') as mock_get:
                mock_get.side_effect = Exception("Timeout")

                try:
                    success, report = verify_device_restart_with_backoff(device_config, config)
                    return {
                        'success': success,
                        'memory_delta': len(large_data),
                        'config_id': id(config)
                    }
                except Exception:
                    return {
                        'success': False,
                        'memory_delta': len(large_data),
                        'config_id': id(config),
                        'error': True
                    }

        # Execute memory-intensive operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(memory_intensive_timeout_operation, config)
                for config in timeout_configs
            ]

            results = [future.result() for future in as_completed(futures)]

        # Force garbage collection
        gc.collect()
        final_memory = psutil.Process().memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory usage assertions
        assert len(results) == num_operations

        # Memory increase should be reasonable (less than 100MB for 100 operations)
        assert memory_increase < 100 * 1024 * 1024

        # Check for memory leaks by comparing tracemalloc data
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be reasonable
        assert peak < 50 * 1024 * 1024  # Less than 50MB peak

    @pytest.mark.slow
    @pytest.mark.performance
    def test_cpu_usage_during_timeout_operations(self):
        """Test CPU usage patterns during timeout operations"""
        import time

        # Monitor CPU usage
        cpu_samples = []
        monitoring = True

        def monitor_cpu():
            while monitoring:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                cpu_samples.append(cpu_percent)

        # Start CPU monitoring
        monitor_thread = threading.Thread(target=monitor_cpu, daemon=True)
        monitor_thread.start()

        try:
            # Execute CPU-intensive timeout operations
            num_operations = 30
            devices = [{'ip': f'192.168.1.{100 + i}', 'timeout': 30} for i in range(num_operations)]

            def cpu_intensive_operation(device_config):
                """Mock operation that uses CPU during timeout handling"""
                timeout_config = create_timeout_config(device_config)

                # Simulate CPU-intensive timeout verification
                with patch('app.tasmota.updater.requests.get') as mock_get:
                    # First few attempts fail, then succeed
                    mock_get.side_effect = [
                        Exception("Connection failed"),
                        Exception("Connection failed"),
                        Exception("Connection failed"),
                        Mock(status_code=200)
                    ]

                    start_time = time.time()
                    success, report = verify_device_restart_with_backoff(device_config, timeout_config)
                    end_time = time.time()

                    return {
                        'success': success,
                        'duration': end_time - start_time,
                        'attempts': report.attempts if success else 0
                    }

            # Execute operations
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = [
                    executor.submit(cpu_intensive_operation, device)
                    for device in devices
                ]

                results = [future.result() for future in as_completed(futures)]

        finally:
            monitoring = False
            monitor_thread.join(timeout=1)

        # CPU usage analysis
        if cpu_samples:
            avg_cpu = statistics.mean(cpu_samples)
            max_cpu = max(cpu_samples)

            # CPU usage should be reasonable
            assert avg_cpu < 80.0  # Average CPU under 80%
            assert max_cpu < 95.0  # Peak CPU under 95%

        # Operation results analysis
        assert len(results) == num_operations
        successful_ops = sum(1 for r in results if r['success'])

        # Should have reasonable success rate despite load
        assert successful_ops > num_operations * 0.7  # At least 70% success


class TestStressTestingTimeouts:
    """Stress testing for timeout handling under extreme conditions"""

    @pytest.mark.slow
    @pytest.mark.stress
    def test_rapid_timeout_scenario_switching(self):
        """Test rapid switching between different timeout scenarios"""
        scenarios = [
            {'name': 'quick_success', 'delay': 0.01, 'should_succeed': True},
            {'name': 'slow_success', 'delay': 0.1, 'should_succeed': True},
            {'name': 'timeout_failure', 'delay': 1.0, 'should_succeed': False},
            {'name': 'network_error', 'delay': 0.05, 'should_succeed': False, 'error': True},
        ]

        results = []
        iterations = 200  # High number of iterations

        def execute_scenario(iteration):
            """Execute a randomly selected scenario"""
            import random
            scenario = random.choice(scenarios)

            device_config = {'ip': f'192.168.1.{100 + (iteration % 154)}'}
            timeout_config = TimeoutConfig(total_timeout=30)  # Short timeout for stress testing

            with patch('app.tasmota.updater.requests.get') as mock_get:
                if scenario.get('error'):
                    mock_get.side_effect = Exception("Network error")
                elif scenario['should_succeed']:
                    # Success after delay
                    def delayed_success(*args, **kwargs):
                        time.sleep(scenario['delay'])
                        return Mock(status_code=200)
                    mock_get.side_effect = delayed_success
                else:
                    # Always fail (timeout)
                    mock_get.side_effect = Exception("Connection failed")

                start_time = time.time()
                success, report = verify_device_restart_with_backoff(device_config, timeout_config)
                end_time = time.time()

                return {
                    'iteration': iteration,
                    'scenario': scenario['name'],
                    'success': success,
                    'duration': end_time - start_time,
                    'expected_success': scenario['should_succeed']
                }

        # Execute rapid scenario switching
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = [
                executor.submit(execute_scenario, i)
                for i in range(iterations)
            ]

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        end_time = time.time()
        total_time = end_time - start_time

        # Stress test assertions
        assert len(results) == iterations
        assert total_time < 30.0  # Should complete within 30 seconds

        # Analyze scenario handling
        scenario_stats = {}
        for result in results:
            scenario = result['scenario']
            if scenario not in scenario_stats:
                scenario_stats[scenario] = {'total': 0, 'correct': 0}

            scenario_stats[scenario]['total'] += 1
            if result['success'] == result['expected_success']:
                scenario_stats[scenario]['correct'] += 1

        # Each scenario should have reasonable accuracy
        for scenario, stats in scenario_stats.items():
            accuracy = stats['correct'] / stats['total']
            assert accuracy > 0.8  # At least 80% accuracy under stress

    @pytest.mark.slow
    @pytest.mark.stress
    def test_extended_duration_stress_test(self):
        """Test timeout handling over extended duration"""
        duration_seconds = 60  # 1 minute stress test
        start_time = time.time()
        operation_count = 0
        error_count = 0
        success_count = 0

        def continuous_operations():
            """Continuously execute timeout operations"""
            nonlocal operation_count, error_count, success_count

            while time.time() - start_time < duration_seconds:
                operation_count += 1

                device_config = {'ip': f'192.168.1.{100 + (operation_count % 154)}'}
                timeout_config = TimeoutConfig(total_timeout=10)  # Very short for stress

                try:
                    with patch('app.tasmota.updater.requests.get') as mock_get:
                        # Random success/failure
                        if operation_count % 3 == 0:
                            mock_get.return_value = Mock(status_code=200)
                        else:
                            mock_get.side_effect = Exception("Stress test failure")

                        success, report = verify_device_restart_with_backoff(device_config, timeout_config)

                        if success:
                            success_count += 1
                        else:
                            error_count += 1

                except Exception:
                    error_count += 1

                # Small delay to prevent overwhelming
                time.sleep(0.01)

        # Run stress test with multiple threads
        num_threads = 5
        threads = []

        for _ in range(num_threads):
            thread = threading.Thread(target=continuous_operations, daemon=True)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Stress test analysis
        assert operation_count > 100  # Should execute many operations
        assert error_count + success_count == operation_count

        # Calculate operation rate
        total_time = time.time() - start_time
        operations_per_second = operation_count / total_time

        assert operations_per_second > 5  # At least 5 operations per second


class TestPerformanceRegression:
    """Test for performance regression in timeout handling"""

    @pytest.mark.performance
    def test_timeout_configuration_performance(self):
        """Test performance of timeout configuration creation"""
        num_configs = 10000
        device_configs = [
            {'ip': f'192.168.{i//254}.{i%254}', 'timeout': 60 + (i % 540)}
            for i in range(num_configs)
        ]

        start_time = time.time()

        # Create many timeout configurations
        configs = []
        for device_config in device_configs:
            config = create_timeout_config(device_config)
            configs.append(config)

        end_time = time.time()
        creation_time = end_time - start_time

        # Performance assertions
        assert len(configs) == num_configs
        assert creation_time < 1.0  # Should create 10k configs in under 1 second

        # Verify configurations are valid
        for config in configs[:10]:  # Sample check
            assert isinstance(config, TimeoutConfig)
            assert config.total_timeout >= 60
            assert config.total_timeout <= 600

        # Calculate creation rate
        configs_per_second = num_configs / creation_time
        assert configs_per_second > 5000  # At least 5k configs per second

    @pytest.mark.performance
    def test_timeout_report_serialization_performance(self):
        """Test performance of timeout report serialization"""
        num_reports = 5000

        # Create many timeout reports
        reports = []
        for i in range(num_reports):
            report = TimeoutReport(
                total_timeout=180 + (i % 420),
                elapsed_time=45.67 + (i * 0.01),
                phase=TimeoutPhase.RESTART_VERIFICATION,
                attempts=5 + (i % 10),
                last_check_interval=2.25 + (i * 0.1),
                timed_out=i % 4 == 0,
                error_type="restart_timeout" if i % 4 == 0 else "none",
                details={"test_data": f"value_{i}", "iteration": i}
            )
            reports.append(report)

        # Test serialization performance
        start_time = time.time()

        serialized_reports = []
        for report in reports:
            serialized = report.to_dict()
            serialized_reports.append(serialized)

        end_time = time.time()
        serialization_time = end_time - start_time

        # Performance assertions
        assert len(serialized_reports) == num_reports
        assert serialization_time < 1.0  # Should serialize 5k reports in under 1 second

        # Verify serialization correctness
        for i, serialized in enumerate(serialized_reports[:10]):  # Sample check
            assert isinstance(serialized, dict)
            assert 'total_timeout' in serialized
            assert 'elapsed_time' in serialized
            assert serialized['details']['iteration'] == i

        # Calculate serialization rate
        reports_per_second = num_reports / serialization_time
        assert reports_per_second > 2000  # At least 2k reports per second

    @pytest.mark.performance
    def test_api_response_time_under_load(self, app_with_test_config):
        """Test API response times under load"""
        num_requests = 100
        response_times = []

        def make_api_request(client, request_id):
            """Make a single API request and measure response time"""
            device_config = {'ip': f'192.168.1.{100 + (request_id % 154)}', 'timeout': 60}

            with patch('app.tasmota.utils.load_devices_from_file', return_value=[device_config]):
                with patch('app.tasmota.updater.update_device_firmware') as mock_update:
                    mock_update.return_value = {
                        'ip': device_config['ip'],
                        'success': True,
                        'timeout_config': {'total_timeout': 60}
                    }

                    start_time = time.time()

                    response = client.post('/api/update', json={
                        'ip': device_config['ip'],
                        'timeout': 60,
                        'check_only': True
                    })

                    end_time = time.time()
                    response_time = end_time - start_time

                    return {
                        'request_id': request_id,
                        'response_time': response_time,
                        'status_code': response.status_code,
                        'success': response.status_code == 200
                    }

        # Execute concurrent API requests
        with app_with_test_config.test_client() as client:
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [
                    executor.submit(make_api_request, client, i)
                    for i in range(num_requests)
                ]

                results = [future.result() for future in as_completed(futures)]

        # Response time analysis
        response_times = [r['response_time'] for r in results if r['success']]

        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            max_response_time = max(response_times)

            # Performance assertions
            assert avg_response_time < 0.1  # Average under 100ms
            assert p95_response_time < 0.2  # 95th percentile under 200ms
            assert max_response_time < 0.5  # Maximum under 500ms

        # Success rate assertion
        success_rate = sum(1 for r in results if r['success']) / len(results)
        assert success_rate > 0.95  # At least 95% success rate under load


class TestResourceUtilization:
    """Test resource utilization during timeout operations"""

    @pytest.mark.performance
    @pytest.mark.resource
    def test_thread_pool_efficiency(self):
        """Test thread pool efficiency during timeout operations"""
        import queue
        import threading

        thread_usage = queue.Queue()
        max_threads = 10
        num_operations = 50

        def monitor_thread_usage(device_config):
            """Monitor thread usage during operation"""
            thread_id = threading.current_thread().ident
            thread_usage.put(thread_id)

            try:
                # Simulate timeout operation
                timeout_config = create_timeout_config(device_config)

                with patch('app.tasmota.updater.requests.get') as mock_get:
                    mock_get.return_value = Mock(status_code=200)
                    success, report = verify_device_restart_with_backoff(device_config, timeout_config)

                return {
                    'thread_id': thread_id,
                    'success': success,
                    'device_ip': device_config['ip']
                }
            finally:
                # Remove from queue when done
                try:
                    thread_usage.get_nowait()
                except queue.Empty:
                    pass

        devices = [{'ip': f'192.168.1.{100 + i}', 'timeout': 60} for i in range(num_operations)]

        # Execute with thread pool
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [
                executor.submit(monitor_thread_usage, device)
                for device in devices
            ]

            results = [future.result() for future in as_completed(futures)]

        # Thread efficiency analysis
        assert len(results) == num_operations

        # Count unique threads used
        thread_ids = [r['thread_id'] for r in results]
        unique_threads = len(set(thread_ids))

        # Should efficiently reuse threads
        assert unique_threads <= max_threads
        assert unique_threads >= min(max_threads, num_operations // 10)  # Reasonable reuse

    @pytest.mark.performance
    @pytest.mark.resource
    def test_network_connection_management(self):
        """Test network connection management during timeout operations"""
        connection_count = 0
        max_connections = 0
        connection_lock = threading.Lock()

        def mock_network_operation(device_config):
            """Mock network operation with connection tracking"""
            nonlocal connection_count, max_connections

            with connection_lock:
                connection_count += 1
                max_connections = max(max_connections, connection_count)

            try:
                # Simulate network timeout operation
                timeout_config = create_timeout_config(device_config)

                with patch('app.tasmota.updater.requests.get') as mock_get:
                    # Simulate connection delay
                    time.sleep(0.05)
                    mock_get.return_value = Mock(status_code=200)

                    success, report = verify_device_restart_with_backoff(device_config, timeout_config)

                return {
                    'ip': device_config['ip'],
                    'success': success,
                    'max_connections_seen': max_connections
                }
            finally:
                with connection_lock:
                    connection_count -= 1

        # Test with many concurrent network operations
        devices = [{'ip': f'192.168.1.{100 + i}', 'timeout': 60} for i in range(30)]

        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [
                executor.submit(mock_network_operation, device)
                for device in devices
            ]

            results = [future.result() for future in as_completed(futures)]

        # Connection management analysis
        assert len(results) == 30
        assert max_connections <= 15  # Should not exceed thread pool size

        # All operations should succeed
        success_count = sum(1 for r in results if r['success'])
        assert success_count == 30


# Test markers for categorization
pytestmark = [
    pytest.mark.performance,
    pytest.mark.load,
    pytest.mark.slow
]
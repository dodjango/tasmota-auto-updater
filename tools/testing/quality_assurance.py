"""Quality Assurance and Anti-Flakiness Framework for Timeout Testing

This module provides comprehensive quality assurance measures including:
- Test determinism and anti-flakiness patterns
- Security validation and sanitization testing
- Quality gates and metrics collection
- Test stability analysis and improvement recommendations
- Regression detection and prevention
"""

import os
import time
import threading
import hashlib
import random
from unittest.mock import patch, Mock
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path


@dataclass
class QualityMetrics:
    """Quality metrics for test execution"""
    test_name: str
    execution_count: int
    success_count: int
    failure_count: int
    avg_execution_time: float
    min_execution_time: float
    max_execution_time: float
    std_deviation: float
    flakiness_score: float
    determinism_score: float


class DeterministicTestRunner:
    """Ensures deterministic test execution"""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.time_patches = {}
        self.random_patches = {}

    def make_deterministic(self, test_func: Callable) -> Callable:
        """Make a test function deterministic"""

        def deterministic_wrapper(*args, **kwargs):
            # Set deterministic seed
            random.seed(self.seed)

            # Freeze time if needed
            with patch('time.time', return_value=1642691200.0):  # Fixed timestamp
                with patch('time.sleep') as mock_sleep:
                    # Track sleep calls but don't actually sleep
                    mock_sleep.side_effect = lambda duration: None

                    # Execute test
                    return test_func(*args, **kwargs)

        return deterministic_wrapper

    def with_controlled_timing(self, test_func: Callable, time_sequence: List[float]) -> Callable:
        """Execute test with controlled timing sequence"""

        def timing_controlled_wrapper(*args, **kwargs):
            time_iter = iter(time_sequence)

            def mock_time():
                try:
                    return next(time_iter)
                except StopIteration:
                    return time_sequence[-1] + 1.0

            with patch('time.time', side_effect=mock_time):
                return test_func(*args, **kwargs)

        return timing_controlled_wrapper


class SecurityTestValidator:
    """Validates security aspects of timeout testing"""

    def __init__(self):
        self.security_patterns = {
            'sql_injection': [
                r"'; DROP TABLE",
                r"UNION SELECT",
                r"OR '1'='1",
                r"INSERT INTO",
                r"DELETE FROM"
            ],
            'xss': [
                r"<script>",
                r"javascript:",
                r"onload=",
                r"onerror=",
                r"alert\("
            ],
            'command_injection': [
                r";\s*rm\s+-rf",
                r"&&\s*cat\s+/etc/passwd",
                r"\|\s*nc\s+",
                r"`.*`",
                r"\$\(.*\)"
            ],
            'path_traversal': [
                r"\.\./",
                r"\.\.\\",
                r"/etc/passwd",
                r"/etc/shadow",
                r"C:\\Windows\\System32"
            ]
        }

    def validate_input_sanitization(self, input_handler: Callable, test_inputs: List[str]) -> Dict[str, Any]:
        """Validate that input handler properly sanitizes malicious inputs"""

        results = {
            'total_inputs_tested': len(test_inputs),
            'properly_sanitized': 0,
            'failed_sanitization': [],
            'security_score': 0
        }

        for test_input in test_inputs:
            try:
                # Test the input handler
                result = input_handler(test_input)

                # Check if malicious patterns are still present
                is_sanitized = True
                for category, patterns in self.security_patterns.items():
                    for pattern in patterns:
                        if re.search(pattern, str(result), re.IGNORECASE):
                            is_sanitized = False
                            results['failed_sanitization'].append({
                                'input': test_input[:100],  # Limit length for logging
                                'category': category,
                                'pattern': pattern,
                                'output': str(result)[:100]
                            })
                            break

                if is_sanitized:
                    results['properly_sanitized'] += 1

            except Exception as e:
                # If input causes exception, that's acceptable for malicious input
                results['properly_sanitized'] += 1

        # Calculate security score
        results['security_score'] = (results['properly_sanitized'] / results['total_inputs_tested']) * 100

        return results

    def validate_log_sanitization(self, log_content: str) -> Dict[str, Any]:
        """Validate that logs don't contain sensitive information"""

        sensitive_patterns = [
            r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
            r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
            r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
            r'api_key["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
            r'http[s]?://[^:]+:([^@]+)@',  # URLs with passwords
        ]

        findings = []
        for pattern in sensitive_patterns:
            matches = re.finditer(pattern, log_content, re.IGNORECASE)
            for match in matches:
                findings.append({
                    'pattern': pattern,
                    'match': match.group(0),
                    'line_number': log_content[:match.start()].count('\n') + 1
                })

        return {
            'sensitive_data_found': len(findings) > 0,
            'findings': findings,
            'log_length': len(log_content),
            'security_score': 0 if findings else 100
        }


class FlakinessPrevention:
    """Prevents and detects test flakiness"""

    def __init__(self):
        self.execution_history = {}
        self.timing_analyzer = TimingAnalyzer()

    def analyze_test_stability(self, test_func: Callable, iterations: int = 10) -> QualityMetrics:
        """Analyze test stability over multiple executions"""

        execution_times = []
        results = []

        for i in range(iterations):
            start_time = time.time()

            try:
                # Run test with clean environment
                with self._clean_test_environment():
                    result = test_func()
                    success = True
            except Exception as e:
                result = str(e)
                success = False

            end_time = time.time()
            execution_time = end_time - start_time

            execution_times.append(execution_time)
            results.append(success)

        # Calculate metrics
        success_count = sum(results)
        failure_count = len(results) - success_count
        avg_time = sum(execution_times) / len(execution_times)
        min_time = min(execution_times)
        max_time = max(execution_times)

        # Calculate standard deviation
        variance = sum((t - avg_time) ** 2 for t in execution_times) / len(execution_times)
        std_dev = variance ** 0.5

        # Calculate flakiness score (lower is better)
        flakiness_score = (failure_count / len(results)) * 100

        # Calculate determinism score based on timing consistency
        time_variance = (std_dev / avg_time) * 100 if avg_time > 0 else 100
        determinism_score = max(0, 100 - time_variance)

        return QualityMetrics(
            test_name=test_func.__name__,
            execution_count=iterations,
            success_count=success_count,
            failure_count=failure_count,
            avg_execution_time=avg_time,
            min_execution_time=min_time,
            max_execution_time=max_time,
            std_deviation=std_dev,
            flakiness_score=flakiness_score,
            determinism_score=determinism_score
        )

    def _clean_test_environment(self):
        """Context manager for clean test environment"""
        class CleanEnvironment:
            def __enter__(self):
                # Clear any cached data
                self.original_cwd = os.getcwd()
                # Reset any global state if needed
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                # Restore original state
                os.chdir(self.original_cwd)
                # Clean up any test artifacts

        return CleanEnvironment()

    def detect_timing_dependencies(self, test_func: Callable) -> Dict[str, Any]:
        """Detect if test has timing dependencies that could cause flakiness"""

        # Run test with different timing scenarios
        scenarios = [
            {'name': 'fast_execution', 'sleep_multiplier': 0.1},
            {'name': 'normal_execution', 'sleep_multiplier': 1.0},
            {'name': 'slow_execution', 'sleep_multiplier': 2.0},
        ]

        results = {}

        for scenario in scenarios:
            with patch('time.sleep') as mock_sleep:
                def controlled_sleep(duration):
                    time.sleep(duration * scenario['sleep_multiplier'])

                mock_sleep.side_effect = controlled_sleep

                try:
                    result = test_func()
                    results[scenario['name']] = {'success': True, 'result': result}
                except Exception as e:
                    results[scenario['name']] = {'success': False, 'error': str(e)}

        # Analyze consistency across scenarios
        success_states = [r['success'] for r in results.values()]
        is_timing_dependent = not all(s == success_states[0] for s in success_states)

        return {
            'is_timing_dependent': is_timing_dependent,
            'scenario_results': results,
            'consistency_score': (sum(success_states) / len(success_states)) * 100
        }


class TimingAnalyzer:
    """Analyzes timing patterns in tests"""

    def __init__(self):
        self.timing_data = []

    def record_timing(self, operation: str, duration: float, context: Dict[str, Any] = None):
        """Record timing data for analysis"""
        self.timing_data.append({
            'operation': operation,
            'duration': duration,
            'timestamp': time.time(),
            'context': context or {}
        })

    def analyze_patterns(self) -> Dict[str, Any]:
        """Analyze timing patterns for anomalies"""
        if not self.timing_data:
            return {'status': 'No timing data available'}

        # Group by operation
        operations = {}
        for record in self.timing_data:
            op = record['operation']
            if op not in operations:
                operations[op] = []
            operations[op].append(record['duration'])

        analysis = {}
        for operation, durations in operations.items():
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)

            # Detect outliers (values > 2 standard deviations from mean)
            variance = sum((d - avg_duration) ** 2 for d in durations) / len(durations)
            std_dev = variance ** 0.5
            outliers = [d for d in durations if abs(d - avg_duration) > 2 * std_dev]

            analysis[operation] = {
                'avg_duration': avg_duration,
                'min_duration': min_duration,
                'max_duration': max_duration,
                'std_deviation': std_dev,
                'outliers': outliers,
                'outlier_percentage': (len(outliers) / len(durations)) * 100,
                'consistency_score': max(0, 100 - (std_dev / avg_duration * 100)) if avg_duration > 0 else 0
            }

        return analysis


class QualityGateValidator:
    """Validates quality gates for timeout testing"""

    def __init__(self):
        self.quality_gates = {
            'minimum_coverage': 85.0,
            'maximum_flakiness': 5.0,
            'minimum_determinism': 90.0,
            'maximum_test_duration': 300.0,
            'minimum_security_score': 95.0,
            'maximum_performance_regression': 10.0
        }

    def validate_quality_gates(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Validate all quality gates"""

        gate_results = {}

        # Coverage gate
        coverage = metrics.get('coverage_percentage', 0)
        gate_results['coverage'] = {
            'value': coverage,
            'threshold': self.quality_gates['minimum_coverage'],
            'passed': coverage >= self.quality_gates['minimum_coverage'],
            'message': f"Coverage: {coverage}% (target: {self.quality_gates['minimum_coverage']}%)"
        }

        # Flakiness gate
        flakiness = metrics.get('average_flakiness_score', 0)
        gate_results['flakiness'] = {
            'value': flakiness,
            'threshold': self.quality_gates['maximum_flakiness'],
            'passed': flakiness <= self.quality_gates['maximum_flakiness'],
            'message': f"Flakiness: {flakiness}% (max: {self.quality_gates['maximum_flakiness']}%)"
        }

        # Determinism gate
        determinism = metrics.get('average_determinism_score', 100)
        gate_results['determinism'] = {
            'value': determinism,
            'threshold': self.quality_gates['minimum_determinism'],
            'passed': determinism >= self.quality_gates['minimum_determinism'],
            'message': f"Determinism: {determinism}% (min: {self.quality_gates['minimum_determinism']}%)"
        }

        # Test duration gate
        duration = metrics.get('max_test_duration', 0)
        gate_results['duration'] = {
            'value': duration,
            'threshold': self.quality_gates['maximum_test_duration'],
            'passed': duration <= self.quality_gates['maximum_test_duration'],
            'message': f"Max duration: {duration}s (max: {self.quality_gates['maximum_test_duration']}s)"
        }

        # Security score gate
        security_score = metrics.get('security_score', 0)
        gate_results['security'] = {
            'value': security_score,
            'threshold': self.quality_gates['minimum_security_score'],
            'passed': security_score >= self.quality_gates['minimum_security_score'],
            'message': f"Security: {security_score}% (min: {self.quality_gates['minimum_security_score']}%)"
        }

        # Overall pass/fail
        all_passed = all(gate['passed'] for gate in gate_results.values())

        return {
            'overall_passed': all_passed,
            'gates': gate_results,
            'summary': f"Quality Gates: {sum(g['passed'] for g in gate_results.values())}/{len(gate_results)} passed"
        }


class RegressionDetector:
    """Detects performance and quality regressions"""

    def __init__(self, baseline_file: str = "baseline_metrics.json"):
        self.baseline_file = Path(baseline_file)
        self.baseline_metrics = self._load_baseline()

    def _load_baseline(self) -> Dict[str, Any]:
        """Load baseline metrics from file"""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Error loading baseline metrics: {e}")

        return {}

    def save_baseline(self, metrics: Dict[str, Any]):
        """Save current metrics as baseline"""
        baseline_data = {
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        }

        with open(self.baseline_file, 'w') as f:
            json.dump(baseline_data, f, indent=2)

    def detect_regressions(self, current_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Detect regressions compared to baseline"""

        if not self.baseline_metrics:
            return {'status': 'No baseline available for comparison'}

        baseline = self.baseline_metrics.get('metrics', {})
        regressions = []

        # Performance regression detection
        performance_metrics = [
            'average_test_duration',
            'timeout_operation_latency',
            'memory_usage_peak',
            'cpu_usage_average'
        ]

        for metric in performance_metrics:
            baseline_value = baseline.get(metric)
            current_value = current_metrics.get(metric)

            if baseline_value is not None and current_value is not None:
                # Calculate percentage change
                change_pct = ((current_value - baseline_value) / baseline_value) * 100

                # Consider regression if performance degrades by more than 10%
                if change_pct > 10:
                    regressions.append({
                        'metric': metric,
                        'baseline_value': baseline_value,
                        'current_value': current_value,
                        'change_percentage': change_pct,
                        'type': 'performance_degradation'
                    })

        # Quality regression detection
        quality_metrics = [
            'coverage_percentage',
            'security_score',
            'determinism_score'
        ]

        for metric in quality_metrics:
            baseline_value = baseline.get(metric)
            current_value = current_metrics.get(metric)

            if baseline_value is not None and current_value is not None:
                # Calculate absolute change
                change = current_value - baseline_value

                # Consider regression if quality drops by more than 5%
                if change < -5:
                    regressions.append({
                        'metric': metric,
                        'baseline_value': baseline_value,
                        'current_value': current_value,
                        'change_percentage': change,
                        'type': 'quality_degradation'
                    })

        return {
            'regressions_detected': len(regressions) > 0,
            'regression_count': len(regressions),
            'regressions': regressions,
            'baseline_timestamp': self.baseline_metrics.get('timestamp'),
            'comparison_summary': f"{len(regressions)} regressions detected"
        }


# Utility functions for quality assurance
def run_quality_analysis(test_results: Dict[str, Any], reports_dir: str = "reports") -> Dict[str, Any]:
    """Run comprehensive quality analysis on test results"""

    qa_results = {
        'timestamp': datetime.now().isoformat(),
        'quality_gates': {},
        'security_validation': {},
        'flakiness_analysis': {},
        'regression_detection': {},
        'recommendations': []
    }

    # Initialize components
    gate_validator = QualityGateValidator()
    security_validator = SecurityTestValidator()
    regression_detector = RegressionDetector(f"{reports_dir}/baseline_metrics.json")

    # Validate quality gates
    qa_results['quality_gates'] = gate_validator.validate_quality_gates(test_results)

    # Detect regressions
    qa_results['regression_detection'] = regression_detector.detect_regressions(test_results)

    # Generate recommendations
    recommendations = []

    # Coverage recommendations
    if test_results.get('coverage_percentage', 0) < 90:
        recommendations.append({
            'type': 'coverage',
            'priority': 'high',
            'message': 'Increase test coverage to above 90% for critical timeout functionality'
        })

    # Flakiness recommendations
    if test_results.get('average_flakiness_score', 0) > 2:
        recommendations.append({
            'type': 'flakiness',
            'priority': 'high',
            'message': 'Address test flakiness by implementing deterministic time control'
        })

    # Performance recommendations
    if qa_results['regression_detection'].get('regressions_detected'):
        recommendations.append({
            'type': 'performance',
            'priority': 'medium',
            'message': 'Performance regressions detected - review timeout algorithms'
        })

    qa_results['recommendations'] = recommendations

    # Save QA results
    qa_file = Path(reports_dir) / "quality_analysis.json"
    with open(qa_file, 'w') as f:
        json.dump(qa_results, f, indent=2)

    return qa_results


# Decorators for quality assurance
def deterministic_test(seed: int = 42):
    """Decorator to make tests deterministic"""
    def decorator(test_func):
        runner = DeterministicTestRunner(seed)
        return runner.make_deterministic(test_func)
    return decorator


def stability_test(iterations: int = 5):
    """Decorator to test function stability"""
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            prevention = FlakinessPrevention()
            metrics = prevention.analyze_test_stability(lambda: test_func(*args, **kwargs), iterations)

            if metrics.flakiness_score > 10:  # More than 10% failure rate
                raise AssertionError(f"Test {test_func.__name__} is flaky (flakiness: {metrics.flakiness_score}%)")

            return test_func(*args, **kwargs)
        return wrapper
    return decorator


def timing_controlled(time_sequence: List[float]):
    """Decorator for controlled timing tests"""
    def decorator(test_func):
        runner = DeterministicTestRunner()
        return runner.with_controlled_timing(test_func, time_sequence)
    return decorator


# Export key classes and functions
__all__ = [
    'QualityMetrics',
    'DeterministicTestRunner',
    'SecurityTestValidator',
    'FlakinessPrevention',
    'TimingAnalyzer',
    'QualityGateValidator',
    'RegressionDetector',
    'run_quality_analysis',
    'deterministic_test',
    'stability_test',
    'timing_controlled'
]
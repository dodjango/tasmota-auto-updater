#!/usr/bin/env python3
"""
Test execution framework for Tasmota Updater timeout testing

This script provides a comprehensive test execution framework with:
- Multiple test execution modes (fast, comprehensive, smoke, etc.)
- Parallel execution support
- Test result reporting and analysis
- Performance metrics collection
- CI/CD integration support
- Test failure analysis and retry logic
"""

import os
import sys
import subprocess
import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta


class TestExecutor:
    """Main test executor for timeout testing"""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or os.path.dirname(os.path.dirname(__file__)))
        self.test_dir = self.project_root / "tests"
        self.reports_dir = self.project_root / "reports"
        self.reports_dir.mkdir(exist_ok=True)

        # Test execution modes
        self.test_modes = {
            'smoke': {
                'description': 'Quick smoke tests for basic functionality',
                'markers': 'smoke',
                'timeout': 60,
                'workers': 2
            },
            'fast': {
                'description': 'Fast unit and integration tests',
                'markers': 'not slow and not stress and not performance',
                'timeout': 300,
                'workers': 4
            },
            'comprehensive': {
                'description': 'Complete test suite including performance tests',
                'markers': '',
                'timeout': 1800,  # 30 minutes
                'workers': 'auto'
            },
            'timeout': {
                'description': 'Timeout-specific functionality tests',
                'markers': 'timeout',
                'timeout': 600,
                'workers': 4
            },
            'performance': {
                'description': 'Performance and load testing',
                'markers': 'performance or load',
                'timeout': 900,  # 15 minutes
                'workers': 2
            },
            'integration': {
                'description': 'Integration and coordination tests',
                'markers': 'integration',
                'timeout': 600,
                'workers': 2
            },
            'security': {
                'description': 'Security and edge case tests',
                'markers': 'security or edge_cases',
                'timeout': 300,
                'workers': 4
            },
            'regression': {
                'description': 'Regression prevention tests',
                'markers': 'regression',
                'timeout': 300,
                'workers': 4
            }
        }

    def execute_tests(
        self,
        mode: str = 'fast',
        parallel: bool = True,
        coverage: bool = True,
        retry_failed: bool = False,
        custom_markers: str = None,
        verbose: bool = False
    ) -> Dict[str, any]:
        """Execute tests with specified configuration"""

        if mode not in self.test_modes:
            raise ValueError(f"Unknown test mode: {mode}. Available modes: {list(self.test_modes.keys())}")

        mode_config = self.test_modes[mode]
        start_time = time.time()

        print(f"\n🧪 Starting {mode} tests: {mode_config['description']}")
        print(f"📁 Test directory: {self.test_dir}")
        print(f"📊 Reports directory: {self.reports_dir}")

        # Build pytest command
        cmd = self._build_pytest_command(
            mode_config=mode_config,
            parallel=parallel,
            coverage=coverage,
            custom_markers=custom_markers,
            verbose=verbose
        )

        print(f"🚀 Executing: {' '.join(cmd)}")

        # Execute tests
        result = self._execute_command(cmd, mode_config['timeout'])

        # Analyze results
        execution_time = time.time() - start_time
        test_results = self._analyze_results(result, execution_time)

        # Handle failed test retry
        if retry_failed and not test_results['success'] and test_results['failed_count'] > 0:
            print(f"\n🔄 Retrying {test_results['failed_count']} failed tests...")
            retry_results = self._retry_failed_tests(mode_config, coverage, verbose)
            test_results['retry_results'] = retry_results

        # Generate summary report
        self._generate_summary_report(test_results, mode)

        return test_results

    def _build_pytest_command(
        self,
        mode_config: Dict,
        parallel: bool,
        coverage: bool,
        custom_markers: str,
        verbose: bool
    ) -> List[str]:
        """Build pytest command with appropriate arguments"""

        cmd = ['python', '-m', 'pytest']

        # Add test directory
        cmd.append(str(self.test_dir))

        # Add markers
        markers = custom_markers or mode_config['markers']
        if markers:
            cmd.extend(['-m', markers])

        # Add parallel execution
        if parallel and mode_config['workers']:
            try:
                import pytest_xdist
                if mode_config['workers'] == 'auto':
                    cmd.extend(['-n', 'auto'])
                else:
                    cmd.extend(['-n', str(mode_config['workers'])])
            except ImportError:
                print("⚠️  pytest-xdist not available, running sequentially")

        # Add coverage
        if coverage:
            cmd.extend([
                '--cov=app',
                '--cov-report=html:htmlcov',
                '--cov-report=term-missing',
                '--cov-report=xml:reports/coverage.xml',
                '--cov-branch'
            ])

        # Add reporting
        cmd.extend([
            '--junitxml=reports/junit.xml',
            '--html=reports/report.html',
            '--self-contained-html'
        ])

        # Add verbosity
        if verbose:
            cmd.append('-v')
        else:
            cmd.append('-q')

        # Add other options
        cmd.extend([
            '--tb=short',
            '--durations=10',
            '--maxfail=10'
        ])

        return cmd

    def _execute_command(self, cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
        """Execute command with timeout"""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            print(f"⏰ Test execution timed out after {timeout} seconds")
            raise

    def _analyze_results(self, result: subprocess.CompletedProcess, execution_time: float) -> Dict[str, any]:
        """Analyze test execution results"""

        test_results = {
            'success': result.returncode == 0,
            'execution_time': execution_time,
            'return_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'total_count': 0,
            'passed_count': 0,
            'failed_count': 0,
            'skipped_count': 0,
            'error_count': 0,
            'coverage_percentage': None,
            'failed_tests': [],
            'junit_file': self.reports_dir / 'junit.xml'
        }

        # Parse JUnit XML if available
        junit_file = self.reports_dir / 'junit.xml'
        if junit_file.exists():
            try:
                tree = ET.parse(junit_file)
                root = tree.getroot()

                test_results['total_count'] = int(root.attrib.get('tests', 0))
                test_results['failed_count'] = int(root.attrib.get('failures', 0)) + int(root.attrib.get('errors', 0))
                test_results['skipped_count'] = int(root.attrib.get('skipped', 0))
                test_results['passed_count'] = test_results['total_count'] - test_results['failed_count'] - test_results['skipped_count']

                # Extract failed test details
                for testcase in root.findall('.//testcase'):
                    failure = testcase.find('failure')
                    error = testcase.find('error')
                    if failure is not None or error is not None:
                        test_results['failed_tests'].append({
                            'name': testcase.attrib.get('name'),
                            'classname': testcase.attrib.get('classname'),
                            'file': testcase.attrib.get('file'),
                            'line': testcase.attrib.get('line'),
                            'message': (failure or error).attrib.get('message', ''),
                        })

            except Exception as e:
                print(f"⚠️  Error parsing JUnit XML: {e}")

        # Parse coverage information
        coverage_file = self.reports_dir / 'coverage.xml'
        if coverage_file.exists():
            try:
                tree = ET.parse(coverage_file)
                root = tree.getroot()
                coverage_elem = root.find('.//coverage')
                if coverage_elem is not None:
                    line_rate = float(coverage_elem.attrib.get('line-rate', 0))
                    test_results['coverage_percentage'] = round(line_rate * 100, 2)
            except Exception as e:
                print(f"⚠️  Error parsing coverage XML: {e}")

        return test_results

    def _retry_failed_tests(self, mode_config: Dict, coverage: bool, verbose: bool) -> Dict[str, any]:
        """Retry failed tests"""

        junit_file = self.reports_dir / 'junit.xml'
        if not junit_file.exists():
            return {'error': 'No JUnit file found for retry'}

        try:
            tree = ET.parse(junit_file)
            root = tree.getroot()

            failed_tests = []
            for testcase in root.findall('.//testcase'):
                failure = testcase.find('failure')
                error = testcase.find('error')
                if failure is not None or error is not None:
                    test_path = f"{testcase.attrib.get('file')}::{testcase.attrib.get('classname')}::{testcase.attrib.get('name')}"
                    failed_tests.append(test_path)

            if not failed_tests:
                return {'error': 'No failed tests found'}

            # Build retry command
            cmd = ['python', '-m', 'pytest']
            cmd.extend(failed_tests)

            if coverage:
                cmd.extend(['--cov=app', '--cov-report=term-missing'])

            cmd.extend([
                '--junitxml=reports/junit_retry.xml',
                '--html=reports/report_retry.html',
                '--self-contained-html'
            ])

            if verbose:
                cmd.append('-v')

            print(f"🔄 Retrying {len(failed_tests)} failed tests...")

            # Execute retry
            start_time = time.time()
            result = self._execute_command(cmd, mode_config['timeout'] // 2)
            execution_time = time.time() - start_time

            return self._analyze_results(result, execution_time)

        except Exception as e:
            return {'error': f'Error during retry: {e}'}

    def _generate_summary_report(self, test_results: Dict, mode: str):
        """Generate summary report"""

        print(f"\n📋 Test Results Summary ({mode} mode)")
        print("=" * 50)

        # Basic metrics
        print(f"✅ Total tests: {test_results['total_count']}")
        print(f"✅ Passed: {test_results['passed_count']}")
        print(f"❌ Failed: {test_results['failed_count']}")
        print(f"⏭️  Skipped: {test_results['skipped_count']}")

        # Execution metrics
        print(f"⏱️  Execution time: {test_results['execution_time']:.2f} seconds")
        print(f"📊 Return code: {test_results['return_code']}")

        # Coverage metrics
        if test_results['coverage_percentage'] is not None:
            print(f"📈 Coverage: {test_results['coverage_percentage']}%")

        # Success rate
        if test_results['total_count'] > 0:
            success_rate = (test_results['passed_count'] / test_results['total_count']) * 100
            print(f"🎯 Success rate: {success_rate:.1f}%")

        # Failed tests summary
        if test_results['failed_tests']:
            print(f"\n❌ Failed Tests ({len(test_results['failed_tests'])}):")
            for i, test in enumerate(test_results['failed_tests'][:10]):  # Show first 10
                print(f"  {i+1}. {test['classname']}::{test['name']}")
                if test['message']:
                    print(f"     {test['message'][:100]}...")

            if len(test_results['failed_tests']) > 10:
                print(f"     ... and {len(test_results['failed_tests']) - 10} more")

        # Retry results
        if 'retry_results' in test_results:
            retry = test_results['retry_results']
            if 'error' not in retry:
                print(f"\n🔄 Retry Results:")
                print(f"  ✅ Passed on retry: {retry['passed_count']}")
                print(f"  ❌ Still failing: {retry['failed_count']}")

        # Report files
        print(f"\n📁 Report files:")
        print(f"  📊 HTML report: {self.reports_dir}/report.html")
        print(f"  📋 JUnit XML: {self.reports_dir}/junit.xml")
        if test_results['coverage_percentage'] is not None:
            print(f"  📈 Coverage HTML: htmlcov/index.html")
            print(f"  📈 Coverage XML: {self.reports_dir}/coverage.xml")

        # Overall status
        if test_results['success']:
            print(f"\n🎉 All tests passed!")
        else:
            print(f"\n💥 Some tests failed. Check reports for details.")

        # Save JSON summary
        summary_file = self.reports_dir / f'summary_{mode}_{int(time.time())}.json'
        with open(summary_file, 'w') as f:
            # Remove non-serializable fields
            serializable_results = {k: v for k, v in test_results.items()
                                  if k not in ['stdout', 'stderr', 'junit_file']}
            json.dump(serializable_results, f, indent=2)

        print(f"💾 Summary saved to: {summary_file}")

    def list_tests(self, pattern: str = None) -> List[str]:
        """List available tests"""
        cmd = ['python', '-m', 'pytest', '--collect-only', '-q', str(self.test_dir)]

        if pattern:
            cmd.extend(['-k', pattern])

        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            return result.stdout.split('\n')
        except Exception as e:
            print(f"Error listing tests: {e}")
            return []

    def validate_environment(self) -> Dict[str, bool]:
        """Validate test environment"""
        checks = {}

        # Check Python version
        checks['python_version'] = sys.version_info >= (3, 8)

        # Check required packages
        required_packages = [
            'pytest', 'pytest-cov', 'pytest-html', 'pytest-timeout',
            'requests', 'flask', 'pyyaml'
        ]

        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                checks[f'package_{package}'] = True
            except ImportError:
                checks[f'package_{package}'] = False

        # Check optional packages
        optional_packages = ['pytest-xdist', 'pytest-benchmark', 'memory-profiler']
        for package in optional_packages:
            try:
                __import__(package.replace('-', '_'))
                checks[f'optional_{package}'] = True
            except ImportError:
                checks[f'optional_{package}'] = False

        # Check directories
        checks['test_directory'] = self.test_dir.exists()
        checks['app_directory'] = (self.project_root / 'app').exists()

        return checks


def main():
    """Main entry point for test execution"""
    parser = argparse.ArgumentParser(description='Tasmota Updater Test Execution Framework')

    parser.add_argument('mode', nargs='?', default='fast',
                       help='Test execution mode (smoke, fast, comprehensive, timeout, performance, integration, security, regression)')

    parser.add_argument('--no-parallel', action='store_true',
                       help='Disable parallel execution')

    parser.add_argument('--no-coverage', action='store_true',
                       help='Disable coverage reporting')

    parser.add_argument('--retry-failed', action='store_true',
                       help='Retry failed tests')

    parser.add_argument('--markers', type=str,
                       help='Custom pytest markers')

    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    parser.add_argument('--list-tests', action='store_true',
                       help='List available tests')

    parser.add_argument('--validate-env', action='store_true',
                       help='Validate test environment')

    parser.add_argument('--project-root', type=str,
                       help='Project root directory')

    args = parser.parse_args()

    # Initialize executor
    executor = TestExecutor(args.project_root)

    # Validate environment if requested
    if args.validate_env:
        print("🔍 Validating test environment...")
        checks = executor.validate_environment()

        print("\nEnvironment Check Results:")
        for check, status in checks.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {check}")

        if all(checks.values()):
            print("\n🎉 Environment validation passed!")
        else:
            print("\n⚠️  Some environment checks failed. Tests may not run properly.")

        return

    # List tests if requested
    if args.list_tests:
        print("📋 Available tests:")
        tests = executor.list_tests()
        for test in tests[:50]:  # Show first 50
            if test.strip():
                print(f"  {test}")
        return

    # Execute tests
    try:
        results = executor.execute_tests(
            mode=args.mode,
            parallel=not args.no_parallel,
            coverage=not args.no_coverage,
            retry_failed=args.retry_failed,
            custom_markers=args.markers,
            verbose=args.verbose
        )

        # Exit with appropriate code
        sys.exit(0 if results['success'] else 1)

    except KeyboardInterrupt:
        print("\n⏹️  Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
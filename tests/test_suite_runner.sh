#!/bin/bash
"""
Comprehensive test suite runner for Tasmota Updater timeout testing

This script provides multiple execution modes and comprehensive reporting
for the timeout/visual feedback testing strategy.
"""

set -euo pipefail

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="${PROJECT_ROOT}/tests"
REPORTS_DIR="${PROJECT_ROOT}/reports"
VENV_DIR="${PROJECT_ROOT}/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="${REPORTS_DIR}/test_execution.log"

# Create necessary directories
mkdir -p "${REPORTS_DIR}"

# Logging function
log() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log_info() {
    log "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    log "${GREEN}✅ $1${NC}"
}

log_warning() {
    log "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    log "${RED}❌ $1${NC}"
}

# Function to check if running in CI
is_ci() {
    [[ "${CI:-false}" == "true" || "${GITHUB_ACTIONS:-false}" == "true" || "${GITLAB_CI:-false}" == "true" ]]
}

# Function to setup virtual environment
setup_venv() {
    log_info "Setting up virtual environment..."

    if [[ ! -d "${VENV_DIR}" ]]; then
        log_info "Creating virtual environment..."
        python3 -m venv "${VENV_DIR}"
    fi

    # Activate virtual environment
    source "${VENV_DIR}/bin/activate"

    # Upgrade pip
    pip install --upgrade pip setuptools wheel

    # Install dependencies
    log_info "Installing dependencies..."
    if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
        pip install -r "${PROJECT_ROOT}/requirements.txt"
    fi

    if [[ -f "${PROJECT_ROOT}/requirements-test.txt" ]]; then
        pip install -r "${PROJECT_ROOT}/requirements-test.txt"
    fi

    log_success "Virtual environment setup complete"
}

# Function to validate environment
validate_environment() {
    log_info "Validating test environment..."

    # Check Python version
    python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_info "Python version: $python_version"

    # Check required commands
    required_commands=("python3" "pip")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done

    # Activate virtual environment if it exists
    if [[ -d "${VENV_DIR}" ]]; then
        source "${VENV_DIR}/bin/activate"
    fi

    # Check required Python packages
    required_packages=("pytest" "requests" "flask")
    for package in "${required_packages[@]}"; do
        if ! python3 -c "import $package" &> /dev/null; then
            log_warning "Required package not found: $package"
        fi
    done

    # Check optional packages
    optional_packages=("pytest_xdist" "selenium" "psutil")
    for package in "${optional_packages[@]}"; do
        if python3 -c "import $package" &> /dev/null; then
            log_info "Optional package available: $package"
        else
            log_warning "Optional package not available: $package"
        fi
    done

    log_success "Environment validation complete"
}

# Function to run smoke tests
run_smoke_tests() {
    log_info "Running smoke tests..."

    cd "${PROJECT_ROOT}"

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "smoke" \
        --tb=short \
        --durations=5 \
        --maxfail=3 \
        -v \
        --junitxml="${REPORTS_DIR}/junit_smoke.xml" \
        --html="${REPORTS_DIR}/report_smoke.html" \
        --self-contained-html \
        || return 1

    log_success "Smoke tests completed"
}

# Function to run fast tests
run_fast_tests() {
    log_info "Running fast tests..."

    cd "${PROJECT_ROOT}"

    # Determine parallel execution
    workers="auto"
    if is_ci; then
        workers="2"  # Limit workers in CI
    fi

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "not slow and not stress and not performance" \
        -n "${workers}" \
        --tb=short \
        --durations=10 \
        --maxfail=5 \
        --cov=app \
        --cov-report=html:htmlcov \
        --cov-report=term-missing \
        --cov-report=xml:"${REPORTS_DIR}/coverage.xml" \
        --cov-branch \
        --junitxml="${REPORTS_DIR}/junit_fast.xml" \
        --html="${REPORTS_DIR}/report_fast.html" \
        --self-contained-html \
        || return 1

    log_success "Fast tests completed"
}

# Function to run comprehensive tests
run_comprehensive_tests() {
    log_info "Running comprehensive test suite..."

    cd "${PROJECT_ROOT}"

    # Determine parallel execution
    workers="auto"
    if is_ci; then
        workers="4"  # Limit workers in CI
    fi

    python3 -m pytest \
        "${TEST_DIR}" \
        -n "${workers}" \
        --tb=short \
        --durations=20 \
        --maxfail=10 \
        --cov=app \
        --cov-report=html:htmlcov \
        --cov-report=term-missing \
        --cov-report=xml:"${REPORTS_DIR}/coverage.xml" \
        --cov-branch \
        --cov-fail-under=85 \
        --junitxml="${REPORTS_DIR}/junit_comprehensive.xml" \
        --html="${REPORTS_DIR}/report_comprehensive.html" \
        --self-contained-html \
        --timeout=300 \
        || return 1

    log_success "Comprehensive tests completed"
}

# Function to run timeout-specific tests
run_timeout_tests() {
    log_info "Running timeout-specific tests..."

    cd "${PROJECT_ROOT}"

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "timeout" \
        -n "4" \
        --tb=short \
        --durations=15 \
        --maxfail=5 \
        --cov=app.tasmota.updater \
        --cov-report=term-missing \
        --cov-report=html:htmlcov_timeout \
        --junitxml="${REPORTS_DIR}/junit_timeout.xml" \
        --html="${REPORTS_DIR}/report_timeout.html" \
        --self-contained-html \
        --timeout=600 \
        || return 1

    log_success "Timeout tests completed"
}

# Function to run performance tests
run_performance_tests() {
    log_info "Running performance tests..."

    cd "${PROJECT_ROOT}"

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "performance or load" \
        -n "2" \
        --tb=short \
        --durations=10 \
        --maxfail=3 \
        --junitxml="${REPORTS_DIR}/junit_performance.xml" \
        --html="${REPORTS_DIR}/report_performance.html" \
        --self-contained-html \
        --timeout=900 \
        --benchmark-only \
        --benchmark-json="${REPORTS_DIR}/benchmark.json" \
        || return 1

    log_success "Performance tests completed"
}

# Function to run security tests
run_security_tests() {
    log_info "Running security tests..."

    cd "${PROJECT_ROOT}"

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "security or edge_cases" \
        -n "4" \
        --tb=short \
        --durations=10 \
        --maxfail=5 \
        --junitxml="${REPORTS_DIR}/junit_security.xml" \
        --html="${REPORTS_DIR}/report_security.html" \
        --self-contained-html \
        || return 1

    # Run additional security tools if available
    if command -v bandit &> /dev/null; then
        log_info "Running Bandit security analysis..."
        bandit -r app/ -f json -o "${REPORTS_DIR}/bandit.json" || log_warning "Bandit analysis failed"
    fi

    if command -v safety &> /dev/null; then
        log_info "Running Safety vulnerability check..."
        safety check --json --output "${REPORTS_DIR}/safety.json" || log_warning "Safety check failed"
    fi

    log_success "Security tests completed"
}

# Function to run mutation tests
run_mutation_tests() {
    log_info "Running mutation tests..."

    cd "${PROJECT_ROOT}"

    if command -v mutmut &> /dev/null; then
        # Run mutation testing on core timeout functionality
        mutmut run \
            --paths-to-mutate app/tasmota/updater.py \
            --tests-dir "${TEST_DIR}" \
            --runner "python -m pytest" \
            || log_warning "Mutation testing failed"

        # Generate mutation report
        mutmut junitxml > "${REPORTS_DIR}/mutation.xml" || true
        mutmut html --directory "${REPORTS_DIR}/mutation_html" || true

        log_success "Mutation tests completed"
    else
        log_warning "mutmut not available, skipping mutation tests"
    fi
}

# Function to run integration tests
run_integration_tests() {
    log_info "Running integration tests..."

    cd "${PROJECT_ROOT}"

    python3 -m pytest \
        "${TEST_DIR}" \
        -m "integration" \
        -n "2" \
        --tb=short \
        --durations=15 \
        --maxfail=5 \
        --junitxml="${REPORTS_DIR}/junit_integration.xml" \
        --html="${REPORTS_DIR}/report_integration.html" \
        --self-contained-html \
        --timeout=600 \
        || return 1

    log_success "Integration tests completed"
}

# Function to generate comprehensive report
generate_report() {
    log_info "Generating comprehensive test report..."

    cd "${PROJECT_ROOT}"

    # Create report summary
    cat > "${REPORTS_DIR}/README.md" << EOF
# Tasmota Updater Timeout Testing Report

Generated on: $(date)

## Test Execution Summary

This directory contains comprehensive test results for the Tasmota Updater timeout/visual feedback improvements.

## Report Files

### Core Test Reports
- \`report_*.html\` - HTML test reports with detailed results
- \`junit_*.xml\` - JUnit XML reports for CI/CD integration
- \`coverage.xml\` - Code coverage report (XML format)
- \`htmlcov/\` - HTML coverage report

### Security Reports
- \`bandit.json\` - Bandit security analysis results
- \`safety.json\` - Safety vulnerability check results

### Performance Reports
- \`benchmark.json\` - Performance benchmark results

### Mutation Testing
- \`mutation.xml\` - Mutation testing results
- \`mutation_html/\` - HTML mutation testing report

## Key Metrics

### Test Categories Covered
- ✅ Timeout Configuration Validation
- ✅ Exponential Backoff Behavior
- ✅ Visual Feedback Integration
- ✅ Frontend-Backend Coordination
- ✅ Performance Under Load
- ✅ Edge Cases and Boundary Conditions
- ✅ Container Timeout Configuration
- ✅ Security and Input Validation

### Test Quality Gates
- Minimum 85% code coverage
- All critical timeout paths tested
- Performance regression detection
- Security vulnerability scanning
- Edge case validation

## Usage

Open the HTML reports in your browser to view detailed test results:

\`\`\`bash
# View main test report
open reports/report_comprehensive.html

# View coverage report
open htmlcov/index.html

# View mutation testing report
open reports/mutation_html/index.html
\`\`\`

EOF

    # Generate test statistics
    python3 << 'EOF'
import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path

reports_dir = Path("reports")
stats = {
    "total_tests": 0,
    "passed_tests": 0,
    "failed_tests": 0,
    "skipped_tests": 0,
    "coverage_percentage": None,
    "execution_time": 0
}

# Parse JUnit XML files
for junit_file in reports_dir.glob("junit_*.xml"):
    try:
        tree = ET.parse(junit_file)
        root = tree.getroot()

        stats["total_tests"] += int(root.attrib.get("tests", 0))
        stats["failed_tests"] += int(root.attrib.get("failures", 0)) + int(root.attrib.get("errors", 0))
        stats["skipped_tests"] += int(root.attrib.get("skipped", 0))
        stats["execution_time"] += float(root.attrib.get("time", 0))

    except Exception as e:
        print(f"Error parsing {junit_file}: {e}")

stats["passed_tests"] = stats["total_tests"] - stats["failed_tests"] - stats["skipped_tests"]

# Parse coverage
coverage_file = reports_dir / "coverage.xml"
if coverage_file.exists():
    try:
        tree = ET.parse(coverage_file)
        root = tree.getroot()
        coverage_elem = root.find(".//coverage")
        if coverage_elem is not None:
            line_rate = float(coverage_elem.attrib.get("line-rate", 0))
            stats["coverage_percentage"] = round(line_rate * 100, 2)
    except Exception as e:
        print(f"Error parsing coverage: {e}")

# Save statistics
with open(reports_dir / "test_statistics.json", "w") as f:
    json.dump(stats, f, indent=2)

print("Test Statistics:")
print(f"  Total tests: {stats['total_tests']}")
print(f"  Passed: {stats['passed_tests']}")
print(f"  Failed: {stats['failed_tests']}")
print(f"  Skipped: {stats['skipped_tests']}")
print(f"  Coverage: {stats['coverage_percentage']}%")
print(f"  Execution time: {stats['execution_time']:.2f}s")
EOF

    log_success "Comprehensive report generated in ${REPORTS_DIR}/"
}

# Function to cleanup
cleanup() {
    log_info "Cleaning up temporary files..."

    # Remove temporary files
    find "${PROJECT_ROOT}" -name "*.pyc" -delete
    find "${PROJECT_ROOT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "${PROJECT_ROOT}" -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

    log_success "Cleanup completed"
}

# Main function
main() {
    local mode="${1:-fast}"
    local setup_env="${2:-true}"

    log_info "Starting Tasmota Updater timeout testing..."
    log_info "Mode: $mode"
    log_info "Project root: $PROJECT_ROOT"

    # Setup environment if requested
    if [[ "$setup_env" == "true" ]]; then
        setup_venv
    fi

    # Validate environment
    validate_environment

    # Change to project directory
    cd "${PROJECT_ROOT}"

    # Execute based on mode
    case "$mode" in
        "smoke")
            run_smoke_tests
            ;;
        "fast")
            run_fast_tests
            ;;
        "comprehensive")
            run_comprehensive_tests
            ;;
        "timeout")
            run_timeout_tests
            ;;
        "performance")
            run_performance_tests
            ;;
        "security")
            run_security_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "mutation")
            run_mutation_tests
            ;;
        "all")
            run_smoke_tests
            run_fast_tests
            run_timeout_tests
            run_integration_tests
            run_security_tests
            run_performance_tests
            ;;
        "ci")
            run_smoke_tests
            run_fast_tests
            run_security_tests
            ;;
        *)
            log_error "Unknown mode: $mode"
            echo "Available modes: smoke, fast, comprehensive, timeout, performance, security, integration, mutation, all, ci"
            exit 1
            ;;
    esac

    # Generate comprehensive report
    generate_report

    # Cleanup
    cleanup

    log_success "Test execution completed successfully!"
}

# Help function
show_help() {
    cat << EOF
Tasmota Updater Test Suite Runner

Usage: $0 [MODE] [SETUP_ENV]

MODES:
  smoke         - Quick smoke tests for basic functionality
  fast          - Fast unit and integration tests (default)
  comprehensive - Complete test suite including performance tests
  timeout       - Timeout-specific functionality tests
  performance   - Performance and load testing
  security      - Security and edge case tests
  integration   - Integration and coordination tests
  mutation      - Mutation testing for code quality
  all           - Run all test categories
  ci            - CI/CD optimized test suite

SETUP_ENV:
  true          - Setup virtual environment (default)
  false         - Skip environment setup

Examples:
  $0                    # Run fast tests with environment setup
  $0 comprehensive      # Run comprehensive test suite
  $0 timeout false      # Run timeout tests without environment setup
  $0 ci                 # Run CI-optimized test suite

Environment Variables:
  CI=true               # Enable CI mode (limits parallelization)
  PYTEST_WORKERS=4      # Override number of test workers

EOF
}

# Script entry point
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    show_help
    exit 0
fi

# Set trap for cleanup on exit
trap cleanup EXIT

# Run main function
main "${@}"
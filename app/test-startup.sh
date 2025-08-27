#!/bin/bash
set -e

# Startup Validation Test Script
# This script runs comprehensive tests for the orchestrator startup sequence
# Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4

echo "=============================================================================="
echo "ORCHESTRATOR STARTUP VALIDATION TEST SUITE"
echo "=============================================================================="
echo "Started at: $(date)"
echo ""

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_TIMEOUT=${TEST_TIMEOUT:-300}  # 5 minutes default timeout
VERBOSE=${VERBOSE:-1}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Test result tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Function to run a test with timeout and error handling
run_test() {
    local test_name="$1"
    local test_command="$2"
    local test_timeout="${3:-60}"
    
    log_step "Running test: $test_name"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    local start_time=$(date +%s)
    
    if timeout "$test_timeout" bash -c "$test_command" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_success "$test_name completed successfully (${duration}s)"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        local exit_code=$?
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        if [ $exit_code -eq 124 ]; then
            log_error "$test_name timed out after ${test_timeout}s"
        else
            log_error "$test_name failed with exit code $exit_code (${duration}s)"
        fi
        
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return $exit_code
    fi
}

# Function to check if a service is running
check_service_running() {
    local service_name="$1"
    local process_pattern="$2"
    
    if pgrep -f "$process_pattern" > /dev/null 2>&1; then
        log_success "$service_name is running"
        return 0
    else
        log_warning "$service_name is not running"
        return 1
    fi
}

# Function to test PostgreSQL startup sequence
test_postgres_startup_sequence() {
    log_step "Testing PostgreSQL startup sequence"
    
    # Test 1: Check if PostgreSQL process is running
    run_test "PostgreSQL Process Check" "pgrep -f postgres > /dev/null" 10
    
    # Test 2: Check PostgreSQL port accessibility
    run_test "PostgreSQL Port Check" "nc -z ${DB_HOST:-localhost} ${DB_PORT:-5432}" 10
    
    # Test 3: Test PostgreSQL connection with pg_isready
    if command -v pg_isready >/dev/null 2>&1; then
        run_test "PostgreSQL Ready Check" "pg_isready -h ${DB_HOST:-localhost} -p ${DB_PORT:-5432}" 15
    else
        log_warning "pg_isready not available, skipping ready check"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    fi
    
    # Test 4: Test database connection with credentials
    run_test "PostgreSQL Connection Test" "python3 -c \"
import psycopg2
import os
config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'orchestrator'),
    'user': os.getenv('DB_USER', 'orchestrator_user'),
    'password': os.getenv('DB_PASSWORD', 'orchestrator_pass')
}
conn = psycopg2.connect(**config)
cursor = conn.cursor()
cursor.execute('SELECT version()')
version = cursor.fetchone()[0]
print(f'PostgreSQL version: {version[:50]}...')
cursor.close()
conn.close()
print('PostgreSQL connection test successful')
\"" 20
}

# Function to test Redis startup sequence
test_redis_startup_sequence() {
    log_step "Testing Redis startup sequence"
    
    # Test 1: Check if Redis process is running
    run_test "Redis Process Check" "pgrep -f redis-server > /dev/null" 10
    
    # Test 2: Check Redis port accessibility
    run_test "Redis Port Check" "nc -z ${REDIS_HOST:-localhost} ${REDIS_PORT:-6379}" 10
    
    # Test 3: Test Redis ping
    if command -v redis-cli >/dev/null 2>&1; then
        run_test "Redis Ping Test" "redis-cli -h ${REDIS_HOST:-localhost} -p ${REDIS_PORT:-6379} ping" 10
    else
        log_warning "redis-cli not available, skipping ping test"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    fi
    
    # Test 4: Test Redis functionality
    run_test "Redis Functionality Test" "python3 -c \"
import redis
import os
import time
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    socket_connect_timeout=5
)
# Test ping
ping_result = redis_client.ping()
print(f'Redis ping result: {ping_result}')
# Test set/get
test_key = f'startup_test_{int(time.time())}'
test_value = 'test_value'
redis_client.set(test_key, test_value, ex=60)
retrieved = redis_client.get(test_key)
redis_client.delete(test_key)
redis_client.close()
assert retrieved.decode() == test_value
print('Redis functionality test successful')
\"" 15
}

# Function to test complete container startup integration
test_container_startup_integration() {
    log_step "Testing container startup integration"
    
    # Test 1: Environment variables validation
    run_test "Environment Variables Check" "python3 -c \"
import os
required_vars = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'REDIS_HOST', 'REDIS_PORT']
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    raise Exception(f'Missing environment variables: {missing}')
print('All required environment variables are set')
\"" 10
    
    # Test 2: Test startup script syntax
    if [ -f "$SCRIPT_DIR/start-orchestrator.sh" ]; then
        run_test "Startup Script Syntax Check" "bash -n $SCRIPT_DIR/start-orchestrator.sh" 10
    else
        log_warning "Startup script not found, skipping syntax check"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    fi
    
    # Test 3: Test orchestrator module imports
    run_test "Orchestrator Module Import Test" "python3 -c \"
import sys
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from orchestrator import wait_for_postgres, wait_for_redis, setup_database, verify_services
    print('All orchestrator functions imported successfully')
except ImportError as e:
    raise Exception(f'Failed to import orchestrator functions: {e}')
\"" 15
    
    # Test 4: Test database setup function
    run_test "Database Setup Function Test" "python3 -c \"
import sys
import os
sys.path.insert(0, '$SCRIPT_DIR')
from orchestrator import setup_database
config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'orchestrator'),
    'user': os.getenv('DB_USER', 'orchestrator_user'),
    'password': os.getenv('DB_PASSWORD', 'orchestrator_pass')
}
result = setup_database(config)
if not result:
    raise Exception('Database setup function returned False')
print('Database setup function test successful')
\"" 30
    
    # Test 5: Test service verification function
    run_test "Service Verification Function Test" "python3 -c \"
import sys
import os
sys.path.insert(0, '$SCRIPT_DIR')
from orchestrator import verify_services
config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'orchestrator'),
    'user': os.getenv('DB_USER', 'orchestrator_user'),
    'password': os.getenv('DB_PASSWORD', 'orchestrator_pass')
}
result = verify_services(config, os.getenv('REDIS_HOST', 'localhost'), int(os.getenv('REDIS_PORT', 6379)))
if result.get('overall_status') != 'ready':
    raise Exception(f'Service verification failed: {result}')
print('Service verification function test successful')
\"" 30
}

# Function to test health endpoint validation
test_health_endpoint_validation() {
    log_step "Testing health endpoint validation"
    
    local app_host="${APP_HOST:-localhost}"
    local app_port="${APP_PORT:-8000}"
    local health_url="http://${app_host}:${app_port}/health"
    
    # Test 1: Check if application is running
    run_test "Application Process Check" "pgrep -f 'uvicorn.*orchestrator' > /dev/null || pgrep -f 'python.*orchestrator' > /dev/null" 10
    
    # Test 2: Check application port accessibility
    run_test "Application Port Check" "nc -z $app_host $app_port" 10
    
    # Test 3: Test health endpoint accessibility
    if command -v curl >/dev/null 2>&1; then
        run_test "Health Endpoint Accessibility" "curl -f -s --connect-timeout 10 --max-time 15 $health_url > /dev/null" 20
    elif command -v wget >/dev/null 2>&1; then
        run_test "Health Endpoint Accessibility" "wget -q --timeout=15 --tries=1 -O /dev/null $health_url" 20
    else
        log_warning "Neither curl nor wget available, skipping health endpoint accessibility test"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    fi
    
    # Test 4: Test health endpoint response format
    if command -v curl >/dev/null 2>&1; then
        run_test "Health Endpoint Response Format" "python3 -c \"
import json
import subprocess
import sys
try:
    result = subprocess.run(['curl', '-s', '--connect-timeout', '10', '--max-time', '15', '$health_url'], 
                          capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise Exception(f'curl failed with code {result.returncode}')
    
    data = json.loads(result.stdout)
    required_fields = ['status', 'timestamp', 'services']
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise Exception(f'Missing required fields: {missing}')
    
    print(f'Health endpoint response valid - Status: {data.get(\"status\")}, Services: {len(data.get(\"services\", {}))}')
except Exception as e:
    print(f'Health endpoint test failed: {e}', file=sys.stderr)
    sys.exit(1)
\"" 25
    else
        log_warning "curl not available, skipping health endpoint response format test"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    fi
}

# Function to run comprehensive Python test suite
run_python_test_suite() {
    log_step "Running comprehensive Python test suite"
    
    if [ -f "$SCRIPT_DIR/test_startup_validation.py" ]; then
        run_test "Python Startup Validation Test Suite" "cd '$SCRIPT_DIR' && python3 test_startup_validation.py" 120
    else
        log_error "Python test suite not found at $SCRIPT_DIR/test_startup_validation.py"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# Main execution
main() {
    local start_time=$(date +%s)
    
    # Print configuration
    log_info "Test Configuration:"
    log_info "  Script Directory: $SCRIPT_DIR"
    log_info "  Test Timeout: ${TEST_TIMEOUT}s"
    log_info "  Database: ${DB_USER:-orchestrator_user}@${DB_HOST:-localhost}:${DB_PORT:-5432}/${DB_NAME:-orchestrator}"
    log_info "  Redis: ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
    log_info "  Application: ${APP_HOST:-localhost}:${APP_PORT:-8000}"
    echo ""
    
    # Check prerequisites
    log_step "Checking prerequisites"
    
    local missing_tools=()
    for tool in python3 nc; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_tools+=("$tool")
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install missing tools before running tests"
        exit 1
    fi
    
    log_success "All required tools are available"
    echo ""
    
    # Run test suites
    echo "=============================================================================="
    echo "POSTGRESQL STARTUP TESTS"
    echo "=============================================================================="
    test_postgres_startup_sequence
    echo ""
    
    echo "=============================================================================="
    echo "REDIS STARTUP TESTS"
    echo "=============================================================================="
    test_redis_startup_sequence
    echo ""
    
    echo "=============================================================================="
    echo "CONTAINER STARTUP INTEGRATION TESTS"
    echo "=============================================================================="
    test_container_startup_integration
    echo ""
    
    echo "=============================================================================="
    echo "HEALTH ENDPOINT VALIDATION TESTS"
    echo "=============================================================================="
    test_health_endpoint_validation
    echo ""
    
    echo "=============================================================================="
    echo "COMPREHENSIVE PYTHON TEST SUITE"
    echo "=============================================================================="
    run_python_test_suite
    echo ""
    
    # Generate final report
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    
    echo "=============================================================================="
    echo "STARTUP VALIDATION TEST RESULTS"
    echo "=============================================================================="
    echo "Completed at: $(date)"
    echo "Total Duration: ${total_duration}s"
    echo ""
    echo "Test Summary:"
    echo "  Total Tests: $TOTAL_TESTS"
    echo "  Passed: $PASSED_TESTS"
    echo "  Failed: $FAILED_TESTS"
    echo "  Skipped: $SKIPPED_TESTS"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        log_success "ALL TESTS PASSED! Orchestrator startup validation successful."
        echo ""
        echo "The orchestrator startup sequence is working correctly:"
        echo "  ✓ PostgreSQL startup and connectivity"
        echo "  ✓ Redis startup and functionality"
        echo "  ✓ Container startup integration"
        echo "  ✓ Health endpoint validation"
        echo ""
        return 0
    else
        log_error "SOME TESTS FAILED! ($FAILED_TESTS out of $TOTAL_TESTS)"
        echo ""
        echo "Please review the test output above to identify and fix issues."
        echo "Common solutions:"
        echo "  - Ensure all services are running (PostgreSQL, Redis)"
        echo "  - Check environment variables are properly set"
        echo "  - Verify network connectivity and port accessibility"
        echo "  - Review service logs for detailed error information"
        echo ""
        return 1
    fi
}

# Handle script termination
cleanup() {
    log_warning "Test execution interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function with timeout
if timeout "$TEST_TIMEOUT" bash -c "$(declare -f main); main"; then
    exit 0
else
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
        log_error "Test suite timed out after ${TEST_TIMEOUT}s"
    else
        log_error "Test suite failed with exit code $exit_code"
    fi
    exit $exit_code
fi
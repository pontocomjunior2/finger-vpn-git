# Startup Validation Tests

This document describes the comprehensive startup validation test suite for the orchestrator system. These tests validate the complete startup sequence including PostgreSQL initialization, Redis connectivity, service integration, and health endpoint functionality.

## Overview

The startup validation tests ensure that all components of the orchestrator startup sequence work correctly and handle errors gracefully. The test suite covers:

- **PostgreSQL Startup Tests**: Validate database service startup, connectivity, and error handling
- **Redis Startup Tests**: Verify Redis service initialization, ping functionality, and connection pooling
- **Integration Tests**: Test complete container startup sequence and service dependencies
- **Health Endpoint Tests**: Validate health check endpoints and diagnostic information

## Requirements Coverage

The test suite addresses the following requirements:

- **1.1, 1.2**: PostgreSQL startup sequence validation with timeout and retry logic
- **3.1, 3.2**: Redis startup validation with ping verification and functionality tests
- **3.3, 3.4**: Health endpoint validation with detailed service status checks

## Test Files

### Core Test Files

1. **`test_startup_validation.py`** - Main test suite with comprehensive test cases
2. **`test_startup_comprehensive.py`** - Enhanced test runner with detailed reporting
3. **`validate_startup_simple.py`** - Lightweight validation script for quick checks
4. **`test-startup.sh`** - Shell script for Unix/Linux environments
5. **`run-startup-tests.bat`** - Windows batch script for test execution

### Test Categories

#### PostgreSQL Startup Tests (`PostgreSQLStartupTests`)

- **Service Startup Detection**: Verify PostgreSQL process is running
- **Port Accessibility**: Test TCP/IP connectivity to PostgreSQL port
- **Wait Function Testing**: Validate `wait_for_postgres()` function with timeouts
- **Connection with Credentials**: Test database connection with authentication
- **Timeout Handling**: Verify graceful timeout behavior with different timeout values
- **Retry Logic**: Test connection retry mechanisms and error recovery

#### Redis Startup Tests (`RedisStartupTests`)

- **Service Startup Detection**: Verify Redis server process is running
- **Port Accessibility**: Test TCP/IP connectivity to Redis port
- **Wait Function Testing**: Validate `wait_for_redis()` function
- **Ping Functionality**: Test Redis ping and basic operations (SET/GET)
- **Timeout Handling**: Verify graceful timeout behavior
- **Connection Pool Behavior**: Test multiple Redis connections and pool management

#### Integration Startup Tests (`IntegrationStartupTests`)

- **Database Setup Function**: Test `setup_database()` function execution
- **Service Verification**: Validate `verify_services()` comprehensive checks
- **Environment Variables**: Verify all required environment variables are set
- **Startup Script Execution**: Test startup script syntax and execution
- **Service Dependency Order**: Verify correct service startup sequence
- **Error Handling**: Test graceful degradation and error recovery

#### Health Endpoint Tests (`HealthEndpointTests`)

- **Endpoint Accessibility**: Test health endpoint HTTP connectivity
- **Response Format**: Validate JSON response structure and required fields
- **Service Status Reporting**: Verify individual service status reporting
- **Response Time Performance**: Test endpoint response time consistency
- **Detailed Diagnostics**: Validate comprehensive diagnostic information

## Usage

### Quick Validation

For a quick startup validation check:

```bash
# Simple validation (lightweight)
python validate_startup_simple.py

# Shell script (Unix/Linux)
./test-startup.sh

# Windows batch script
run-startup-tests.bat
```

### Comprehensive Testing

For detailed testing with full reporting:

```bash
# Run comprehensive test suite
python test_startup_comprehensive.py

# Run individual test categories
python -m unittest test_startup_validation.PostgreSQLStartupTests
python -m unittest test_startup_validation.RedisStartupTests
python -m unittest test_startup_validation.IntegrationStartupTests
python -m unittest test_startup_validation.HealthEndpointTests
```

### Environment Configuration

Set the following environment variables before running tests:

```bash
# Database configuration
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=orchestrator
export DB_USER=orchestrator_user
export DB_PASSWORD=orchestrator_pass

# Redis configuration
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Application configuration
export APP_HOST=localhost
export APP_PORT=8000
```

## Test Reports

### JSON Reports

The comprehensive test runner generates detailed JSON reports:

```json
{
  "session_info": {
    "start_time": "2025-08-26T21:30:00",
    "end_time": "2025-08-26T21:32:15",
    "total_duration": 135.42
  },
  "environment": {
    "python_version": "3.9.0",
    "platform": "win32",
    "environment_variables": {...}
  },
  "test_suites": {
    "PostgreSQL Startup Tests": {
      "tests_run": 6,
      "failures": 0,
      "errors": 0,
      "success_rate": 1.0,
      "duration": 45.2
    }
  },
  "summary": {
    "total_tests": 24,
    "total_passed": 22,
    "total_failures": 1,
    "total_errors": 1,
    "overall_success_rate": 0.92
  }
}
```

### Console Output

Tests provide real-time console output with clear status indicators:

```
✓ PostgreSQL service is running (detected in 0.12s)
✓ PostgreSQL port 5432 is accessible on localhost (verified in 0.08s)
✓ wait_for_postgres succeeded (in 2.34s)
✗ Redis connection failed: Error 10061 connecting to localhost:6379
⚠ Health endpoint not accessible (application may not be running)
```

## Error Handling

The test suite includes comprehensive error handling:

- **Service Unavailable**: Tests gracefully handle services that are not running
- **Network Issues**: Timeout handling for network connectivity problems
- **Authentication Failures**: Proper handling of invalid credentials
- **Missing Dependencies**: Clear error messages for missing Python packages
- **Configuration Issues**: Validation of environment variables and settings

## Integration with CI/CD

The test suite is designed for integration with continuous integration systems:

```bash
# Exit codes
# 0: All tests passed
# 1: Some tests failed or errors occurred

# Example CI integration
python test_startup_comprehensive.py
if [ $? -eq 0 ]; then
    echo "Startup validation passed - proceeding with deployment"
else
    echo "Startup validation failed - blocking deployment"
    exit 1
fi
```

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   ```bash
   pip install psycopg2-binary redis requests
   ```

2. **Service Not Running**
   - Ensure PostgreSQL and Redis services are started
   - Check service logs for startup errors
   - Verify port accessibility with `netcat` or `telnet`

3. **Environment Variables**
   - Verify all required environment variables are set
   - Check variable values match your service configuration
   - Use `.env` files for local development

4. **Network Connectivity**
   - Test port accessibility: `nc -z localhost 5432`
   - Check firewall settings
   - Verify service binding addresses

### Debug Mode

Enable verbose output for debugging:

```bash
# Set debug environment variables
export VERBOSE=1
export LOG_LEVEL=DEBUG

# Run tests with detailed output
python test_startup_comprehensive.py
```

## Performance Benchmarks

Expected performance benchmarks for healthy systems:

- **PostgreSQL Connection**: < 2 seconds
- **Redis Connection**: < 1 second  
- **Health Endpoint Response**: < 5 seconds
- **Complete Test Suite**: < 5 minutes

## Maintenance

### Adding New Tests

To add new startup validation tests:

1. Create test methods in appropriate test class
2. Follow naming convention: `test_<component>_<functionality>`
3. Use `record_test_result()` for consistent reporting
4. Include proper error handling and timeouts
5. Add documentation to this README

### Updating Test Configuration

Update test configuration in:
- Environment variable definitions
- Timeout values in test classes
- Expected service endpoints and ports
- Performance benchmark thresholds
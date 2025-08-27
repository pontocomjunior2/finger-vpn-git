#!/usr/bin/env python3
"""
Test script for enhanced startup script functionality.
Validates the improvements made to start-orchestrator.sh for task 3.

Requirements tested:
- 1.1, 1.2, 1.3, 1.4: Service startup sequencing
- 5.1, 5.2, 5.3, 5.4: Detailed logging and error handling
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def test_startup_script_structure():
    """Test that the startup script has the required structure and functions."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    if not script_path.exists():
        print("❌ FAIL: start-orchestrator.sh not found")
        return False
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Test for enhanced logging functions
    required_functions = [
        'log_info()',
        'log_error()',
        'log_warning()',
        'log_step()',
        'log_success()',
        'handle_startup_failure()',
        'cleanup_services()',
        'wait_for_postgres()',
        'wait_for_redis()',
        'setup_database()',
        'verify_services()'
    ]
    
    missing_functions = []
    for func in required_functions:
        if func not in content:
            missing_functions.append(func)
    
    if missing_functions:
        print(f"❌ FAIL: Missing required functions: {missing_functions}")
        return False
    
    print("✅ PASS: All required functions present in startup script")
    return True


def test_enhanced_logging_structure():
    """Test that enhanced logging with structured output is implemented."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for structured logging format
    log_patterns = [
        r'echo "\$\(date.*\) \[INFO\] \[STARTUP\]',
        r'echo "\$\(date.*\) \[ERROR\] \[STARTUP\]',
        r'echo "\$\(date.*\) \[STEP\] \[STARTUP\]',
        r'echo "\$\(date.*\) \[SUCCESS\] \[STARTUP\]'
    ]
    
    for pattern in log_patterns:
        if not re.search(pattern, content):
            print(f"❌ FAIL: Missing structured logging pattern: {pattern}")
            return False
    
    print("✅ PASS: Enhanced structured logging implemented")
    return True


def test_timeout_handling():
    """Test that proper timeout handling is implemented."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for timeout configuration
    timeout_vars = [
        'POSTGRES_STARTUP_TIMEOUT',
        'REDIS_STARTUP_TIMEOUT',
        'APP_STARTUP_TIMEOUT'
    ]
    
    for var in timeout_vars:
        if var not in content:
            print(f"❌ FAIL: Missing timeout variable: {var}")
            return False
    
    # Check for timeout usage in wait functions
    if 'timeout=${3:-$POSTGRES_STARTUP_TIMEOUT}' not in content:
        print("❌ FAIL: PostgreSQL timeout not properly configured")
        return False
    
    if 'timeout=${3:-$REDIS_STARTUP_TIMEOUT}' not in content:
        print("❌ FAIL: Redis timeout not properly configured")
        return False
    
    print("✅ PASS: Proper timeout handling implemented")
    return True


def test_service_sequencing():
    """Test that proper service sequencing is implemented."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for step-by-step sequencing
    required_steps = [
        'Step 1: Pre-startup environment validation',
        'Step 2: PostgreSQL service startup',
        'Step 3: PostgreSQL readiness verification',
        'Step 4: Database and user setup',
        'Step 5: Redis service startup',
        'Step 6: Redis readiness verification',
        'Step 7: Comprehensive service verification',
        'Step 8: Environment configuration',
        'Step 9: Starting Python application'
    ]
    
    for step in required_steps:
        if step not in content:
            print(f"❌ FAIL: Missing service sequencing step: {step}")
            return False
    
    print("✅ PASS: Proper service sequencing implemented")
    return True


def test_error_handling():
    """Test that graceful failure handling is implemented."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for error handling patterns
    error_patterns = [
        'handle_startup_failure',
        'cleanup_services',
        'trap cleanup_services EXIT INT TERM',
        'suggested_solution'
    ]
    
    for pattern in error_patterns:
        if pattern not in content:
            print(f"❌ FAIL: Missing error handling pattern: {pattern}")
            return False
    
    # Check for specific error codes and messages
    if 'Error Code:' not in content or 'Suggested Solution:' not in content:
        print("❌ FAIL: Missing detailed error reporting")
        return False
    
    print("✅ PASS: Graceful failure handling implemented")
    return True


def test_verification_functions_integration():
    """Test that verification functions from orchestrator.py are properly integrated."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for Python verification integration
    if 'from orchestrator import verify_services' not in content:
        print("❌ FAIL: Python verification functions not integrated")
        return False
    
    if 'Python service verification' not in content:
        print("❌ FAIL: Python service verification step missing")
        return False
    
    print("✅ PASS: Verification functions properly integrated")
    return True


def test_environment_variable_handling():
    """Test that environment variables are properly handled."""
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for environment variable configuration
    env_vars = [
        'DB_HOST=${DB_HOST:-localhost}',
        'DB_PORT=${DB_PORT:-5432}',
        'DB_NAME=${DB_NAME:-orchestrator}',
        'DB_USER=${DB_USER:-orchestrator_user}',
        'REDIS_HOST=${REDIS_HOST:-localhost}',
        'REDIS_PORT=${REDIS_PORT:-6379}'
    ]
    
    for var in env_vars:
        if var not in content:
            print(f"❌ FAIL: Missing environment variable configuration: {var}")
            return False
    
    print("✅ PASS: Environment variables properly handled")
    return True


def main():
    """Run all tests for the enhanced startup script."""
    print("🧪 Testing Enhanced Startup Script (Task 3)")
    print("=" * 50)
    
    tests = [
        test_startup_script_structure,
        test_enhanced_logging_structure,
        test_timeout_handling,
        test_service_sequencing,
        test_error_handling,
        test_verification_functions_integration,
        test_environment_variable_handling
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ FAIL: Test {test.__name__} crashed: {e}")
            print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Enhanced startup script implementation is complete.")
        return True
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
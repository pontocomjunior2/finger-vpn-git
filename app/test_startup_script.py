#!/usr/bin/env python3
"""
Test script to validate the startup script functions work correctly.

This script tests the bash functions in the startup script by simulating
their behavior in Python.
"""

import subprocess
import sys
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_startup_script_syntax():
    """Test that the startup script has valid bash syntax."""
    logger.info("Testing startup script syntax...")
    
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    if not script_path.exists():
        logger.error(f"Startup script not found: {script_path}")
        return False
    
    try:
        # Test bash syntax
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info("Startup script syntax is valid")
            return True
        else:
            logger.error(f"Startup script syntax error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Startup script syntax check timed out")
        return False
    except Exception as e:
        logger.error(f"Error checking startup script syntax: {e}")
        return False

def test_startup_script_functions():
    """Test that the startup script functions are defined correctly."""
    logger.info("Testing startup script function definitions...")
    
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    try:
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Check for required functions
        required_functions = [
            "wait_for_postgres",
            "wait_for_redis", 
            "setup_database",
            "verify_services",
            "log_info",
            "log_error",
            "log_warning"
        ]
        
        missing_functions = []
        for func in required_functions:
            if f"{func}()" not in script_content:
                missing_functions.append(func)
        
        if missing_functions:
            logger.error(f"Missing functions in startup script: {missing_functions}")
            return False
        else:
            logger.info("All required functions found in startup script")
            return True
            
    except Exception as e:
        logger.error(f"Error reading startup script: {e}")
        return False

def test_startup_script_permissions():
    """Test that the startup script has executable permissions."""
    logger.info("Testing startup script permissions...")
    
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    try:
        # Check if file is executable (on Unix-like systems)
        if script_path.stat().st_mode & 0o111:
            logger.info("Startup script has executable permissions")
            return True
        else:
            logger.warning("Startup script may not have executable permissions")
            return False
            
    except Exception as e:
        logger.error(f"Error checking startup script permissions: {e}")
        return False

def test_environment_variables():
    """Test that required environment variables are handled correctly."""
    logger.info("Testing environment variable handling...")
    
    script_path = Path(__file__).parent / "start-orchestrator.sh"
    
    try:
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Check for environment variable usage
        required_env_vars = [
            "POSTGRES_STARTUP_TIMEOUT",
            "REDIS_STARTUP_TIMEOUT",
            "APP_STARTUP_TIMEOUT",
            "DB_PASSWORD",
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER"
        ]
        
        missing_env_vars = []
        for var in required_env_vars:
            if var not in script_content:
                missing_env_vars.append(var)
        
        if missing_env_vars:
            logger.warning(f"Environment variables not referenced in script: {missing_env_vars}")
        else:
            logger.info("All required environment variables are referenced")
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking environment variables: {e}")
        return False

def main():
    """Run all startup script validation tests."""
    logger.info("Starting startup script validation tests...")
    
    tests = [
        ("Script Syntax", test_startup_script_syntax),
        ("Function Definitions", test_startup_script_functions),
        ("File Permissions", test_startup_script_permissions),
        ("Environment Variables", test_environment_variables),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            start_time = time.time()
            result = test_func()
            end_time = time.time()
            
            results[test_name] = {
                "success": result,
                "duration": end_time - start_time,
                "error": None
            }
            
            logger.info(f"{test_name} completed in {end_time - start_time:.2f}s")
            
        except Exception as e:
            logger.error(f"{test_name} failed with error: {e}")
            results[test_name] = {
                "success": False,
                "duration": 0,
                "error": str(e)
            }
    
    # Print summary
    logger.info(f"\n{'='*50}")
    logger.info("VALIDATION SUMMARY")
    logger.info(f"{'='*50}")
    
    total_tests = len(tests)
    passed_tests = sum(1 for r in results.values() if r["success"])
    
    for test_name, result in results.items():
        status = "PASS" if result["success"] else "FAIL"
        duration = result["duration"]
        logger.info(f"{test_name}: {status} ({duration:.2f}s)")
        
        if result["error"]:
            logger.info(f"  Error: {result['error']}")
    
    logger.info(f"\nResults: {passed_tests}/{total_tests} validation tests passed")
    
    if passed_tests == total_tests:
        logger.info("All startup script validation tests passed!")
        return 0
    else:
        logger.error("Some startup script validation tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
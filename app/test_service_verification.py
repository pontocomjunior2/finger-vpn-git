#!/usr/bin/env python3
"""
Test script for service startup verification functions.

This script tests the robust service verification functions implemented
for the orchestrator Docker startup fix.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the service verification functions
from orchestrator import wait_for_postgres, wait_for_redis, setup_database, verify_services

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_postgres_verification():
    """Test PostgreSQL verification function."""
    logger.info("Testing PostgreSQL verification...")
    
    # Test with default parameters
    result = wait_for_postgres(timeout=10)
    logger.info(f"PostgreSQL verification result: {result}")
    
    return result

def test_redis_verification():
    """Test Redis verification function."""
    logger.info("Testing Redis verification...")
    
    # Test with default parameters
    result = wait_for_redis(timeout=10)
    logger.info(f"Redis verification result: {result}")
    
    return result

def test_database_setup():
    """Test database setup function."""
    logger.info("Testing database setup...")
    
    # Use configuration from environment or defaults
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "orchestrator"),
        "user": os.getenv("DB_USER", "orchestrator_user"),
        "password": os.getenv("DB_PASSWORD", "orchestrator_pass"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }
    
    result = setup_database(db_config)
    logger.info(f"Database setup result: {result}")
    
    return result

def test_comprehensive_verification():
    """Test comprehensive service verification."""
    logger.info("Testing comprehensive service verification...")
    
    # Use configuration from environment or defaults
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "orchestrator"),
        "user": os.getenv("DB_USER", "orchestrator_user"),
        "password": os.getenv("DB_PASSWORD", "orchestrator_pass"),
        "port": int(os.getenv("DB_PORT", 5432)),
    }
    
    result = verify_services(db_config)
    logger.info(f"Comprehensive verification result: {result}")
    
    return result

def main():
    """Run all service verification tests."""
    logger.info("Starting service verification tests...")
    
    tests = [
        ("PostgreSQL Verification", test_postgres_verification),
        ("Redis Verification", test_redis_verification),
        ("Database Setup", test_database_setup),
        ("Comprehensive Verification", test_comprehensive_verification),
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
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    total_tests = len(tests)
    passed_tests = sum(1 for r in results.values() if r["success"])
    
    for test_name, result in results.items():
        status = "PASS" if result["success"] else "FAIL"
        duration = result["duration"]
        logger.info(f"{test_name}: {status} ({duration:.2f}s)")
        
        if result["error"]:
            logger.info(f"  Error: {result['error']}")
    
    logger.info(f"\nResults: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        logger.info("All service verification tests passed!")
        return 0
    else:
        logger.error("Some service verification tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
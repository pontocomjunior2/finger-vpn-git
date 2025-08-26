#!/usr/bin/env python3
"""
Simple Test Runner for Quick Testing

A simplified test runner that can execute the comprehensive test suite
without complex dependencies. Useful for quick validation.
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_test_file(test_file: str, timeout: int = 300) -> bool:
    """Run a single test file and return success status"""
    logger.info(f"Running {test_file}...")
    
    try:
        cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]
        
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        if result.returncode == 0:
            logger.info(f"✓ {test_file} passed in {execution_time:.2f}s")
            return True
        else:
            logger.error(f"✗ {test_file} failed in {execution_time:.2f}s")
            if result.stderr:
                logger.error(f"Error output: {result.stderr[:500]}...")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"✗ {test_file} timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"✗ {test_file} failed with exception: {e}")
        return False


def main():
    """Main test execution"""
    logger.info("Starting simple test runner...")
    
    # Test files to run (in order of importance)
    test_files = [
        "test_suite_comprehensive.py",
        "test_integration_orchestrator_worker.py", 
        "test_load_balancing_framework.py"
    ]
    
    # Check if test files exist
    existing_files = []
    for test_file in test_files:
        if Path(test_file).exists():
            existing_files.append(test_file)
        else:
            logger.warning(f"Test file not found: {test_file}")
    
    if not existing_files:
        logger.error("No test files found!")
        sys.exit(1)
    
    # Run tests
    passed = 0
    failed = 0
    start_time = time.time()
    
    for test_file in existing_files:
        if run_test_file(test_file):
            passed += 1
        else:
            failed += 1
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Summary
    total_tests = passed + failed
    success_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total execution time: {total_time:.2f}s")
    logger.info(f"Test files run: {total_tests}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Success rate: {success_rate:.1f}%")
    
    if success_rate >= 75:
        logger.info("🎉 Test suite passed!")
        sys.exit(0)
    else:
        logger.error("❌ Test suite failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
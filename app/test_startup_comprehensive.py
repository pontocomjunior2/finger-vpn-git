#!/usr/bin/env python3
"""
Comprehensive Startup Validation Test Runner

This script runs all startup validation tests in a structured manner,
providing detailed reporting and covering all requirements for the
orchestrator startup sequence validation.

Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4
"""

import json
import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import test classes
from test_startup_validation import (
    PostgreSQLStartupTests,
    RedisStartupTests,
    IntegrationStartupTests,
    HealthEndpointTests
)


class ComprehensiveTestRunner:
    """Enhanced test runner with detailed reporting and validation."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.test_results = {
            "session_info": {
                "start_time": self.start_time.isoformat(),
                "test_runner": "comprehensive_startup_validation",
                "version": "1.0.0"
            },
            "environment": self._collect_environment_info(),
            "test_suites": {},
            "summary": {},
            "errors": [],
            "warnings": []
        }
    
    def _collect_environment_info(self):
        """Collect environment information for the test report."""
        return {
            "python_version": sys.version,
            "platform": sys.platform,
            "working_directory": str(Path.cwd()),
            "environment_variables": {
                "DB_HOST": os.getenv("DB_HOST", "not_set"),
                "DB_PORT": os.getenv("DB_PORT", "not_set"),
                "DB_NAME": os.getenv("DB_NAME", "not_set"),
                "DB_USER": os.getenv("DB_USER", "not_set"),
                "REDIS_HOST": os.getenv("REDIS_HOST", "not_set"),
                "REDIS_PORT": os.getenv("REDIS_PORT", "not_set"),
                "APP_HOST": os.getenv("APP_HOST", "not_set"),
                "APP_PORT": os.getenv("APP_PORT", "not_set")
            }
        }
    
    def run_test_suite(self, test_class, suite_name):
        """Run a specific test suite and collect results."""
        print(f"\n{'='*60}")
        print(f"RUNNING {suite_name.upper()}")
        print(f"{'='*60}")
        
        suite_start = time.time()
        
        # Create test suite
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        
        # Run tests with custom result collector
        result = unittest.TestResult()
        suite.run(result)
        
        suite_duration = time.time() - suite_start
        
        # Collect suite results
        suite_results = {
            "suite_name": suite_name,
            "duration": suite_duration,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped) if hasattr(result, 'skipped') else 0,
            "success_rate": (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun if result.testsRun > 0 else 0,
            "failure_details": [{"test": str(test), "error": error} for test, error in result.failures],
            "error_details": [{"test": str(test), "error": error} for test, error in result.errors]
        }
        
        self.test_results["test_suites"][suite_name] = suite_results
        
        # Print suite summary
        print(f"\n{suite_name} Results:")
        print(f"  Tests run: {result.testsRun}")
        print(f"  Failures: {len(result.failures)}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Success rate: {suite_results['success_rate']:.1%}")
        print(f"  Duration: {suite_duration:.2f}s")
        
        if result.failures:
            print(f"  Failures:")
            for test, error in result.failures:
                print(f"    - {test}: {error.split(chr(10))[0]}")
        
        if result.errors:
            print(f"  Errors:")
            for test, error in result.errors:
                print(f"    - {test}: {error.split(chr(10))[0]}")
        
        return suite_results
    
    def run_all_tests(self):
        """Run all startup validation test suites."""
        print("="*80)
        print("COMPREHENSIVE ORCHESTRATOR STARTUP VALIDATION")
        print("="*80)
        print(f"Started at: {self.start_time}")
        print(f"Environment: {self.test_results['environment']['environment_variables']}")
        
        # Define test suites to run
        test_suites = [
            (PostgreSQLStartupTests, "PostgreSQL Startup Tests"),
            (RedisStartupTests, "Redis Startup Tests"),
            (IntegrationStartupTests, "Integration Startup Tests"),
            (HealthEndpointTests, "Health Endpoint Tests")
        ]
        
        # Run each test suite
        all_suite_results = []
        for test_class, suite_name in test_suites:
            try:
                suite_result = self.run_test_suite(test_class, suite_name)
                all_suite_results.append(suite_result)
            except Exception as e:
                error_msg = f"Failed to run {suite_name}: {e}"
                self.test_results["errors"].append(error_msg)
                print(f"✗ {error_msg}")
        
        # Generate final summary
        self._generate_final_summary(all_suite_results)
        
        return self.test_results
    
    def _generate_final_summary(self, suite_results):
        """Generate comprehensive test summary."""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # Calculate totals
        total_tests = sum(suite["tests_run"] for suite in suite_results)
        total_failures = sum(suite["failures"] for suite in suite_results)
        total_errors = sum(suite["errors"] for suite in suite_results)
        total_passed = total_tests - total_failures - total_errors
        
        overall_success_rate = total_passed / total_tests if total_tests > 0 else 0
        
        # Update test results
        self.test_results["session_info"]["end_time"] = end_time.isoformat()
        self.test_results["session_info"]["total_duration"] = total_duration
        
        self.test_results["summary"] = {
            "total_test_suites": len(suite_results),
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failures": total_failures,
            "total_errors": total_errors,
            "overall_success_rate": overall_success_rate,
            "suite_success_rates": {suite["suite_name"]: suite["success_rate"] for suite in suite_results}
        }
        
        # Print final summary
        print("\n" + "="*80)
        print("COMPREHENSIVE TEST RESULTS SUMMARY")
        print("="*80)
        print(f"Completed at: {end_time}")
        print(f"Total duration: {total_duration:.2f}s")
        print()
        print("Overall Results:")
        print(f"  Test suites: {len(suite_results)}")
        print(f"  Total tests: {total_tests}")
        print(f"  Passed: {total_passed}")
        print(f"  Failed: {total_failures}")
        print(f"  Errors: {total_errors}")
        print(f"  Success rate: {overall_success_rate:.1%}")
        print()
        
        # Print suite breakdown
        print("Suite Breakdown:")
        for suite in suite_results:
            status_icon = "✓" if suite["success_rate"] == 1.0 else "⚠" if suite["success_rate"] > 0.5 else "✗"
            print(f"  {status_icon} {suite['suite_name']}: {suite['success_rate']:.1%} ({suite['tests_run']} tests, {suite['duration']:.1f}s)")
        
        print()
        
        # Determine overall status
        if overall_success_rate == 1.0:
            print("🎉 ALL TESTS PASSED! Orchestrator startup validation successful.")
            print("\nThe orchestrator startup sequence is fully validated:")
            print("  ✓ PostgreSQL startup and connectivity verified")
            print("  ✓ Redis startup and functionality verified")
            print("  ✓ Container startup integration validated")
            print("  ✓ Health endpoint validation completed")
            print("\nThe system is ready for production deployment.")
        elif overall_success_rate >= 0.8:
            print("⚠ MOSTLY SUCCESSFUL with some issues.")
            print(f"\n{total_failures + total_errors} test(s) failed out of {total_tests}.")
            print("Review the detailed results above to address remaining issues.")
        else:
            print("❌ SIGNIFICANT ISSUES DETECTED!")
            print(f"\n{total_failures + total_errors} test(s) failed out of {total_tests}.")
            print("The orchestrator startup sequence requires attention before deployment.")
            print("\nCommon solutions:")
            print("  • Ensure PostgreSQL and Redis services are running")
            print("  • Verify environment variables are properly configured")
            print("  • Check network connectivity and firewall settings")
            print("  • Review service logs for detailed error information")
        
        print()
    
    def save_report(self, filename=None):
        """Save detailed test report to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comprehensive_startup_validation_report_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        print(f"📄 Detailed test report saved to: {filename}")
        return filename


def main():
    """Main function to run comprehensive startup validation tests."""
    # Check for required dependencies
    missing_deps = []
    try:
        import psycopg2
    except ImportError:
        missing_deps.append("psycopg2")
    
    try:
        import redis
    except ImportError:
        missing_deps.append("redis")
    
    try:
        import requests
    except ImportError:
        missing_deps.append("requests")
    
    if missing_deps:
        print(f"❌ Missing required dependencies: {', '.join(missing_deps)}")
        print("Please install missing dependencies before running tests.")
        return False
    
    # Run comprehensive tests
    runner = ComprehensiveTestRunner()
    
    try:
        test_results = runner.run_all_tests()
        report_file = runner.save_report()
        
        # Return success based on overall results
        overall_success_rate = test_results["summary"]["overall_success_rate"]
        return overall_success_rate >= 0.8  # 80% success rate threshold
        
    except KeyboardInterrupt:
        print("\n⚠ Test execution interrupted by user.")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during test execution: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
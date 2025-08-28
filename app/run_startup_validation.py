#!/usr/bin/env python3
"""
Startup Validation Test Runner

Simple script to run all startup validation tests with proper error handling
and reporting. This script can be used in development, testing, and CI/CD
environments.

Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def check_dependencies():
    """Check if required dependencies are available."""
    print("Checking dependencies...")

    missing_deps = []
    required_packages = ["psycopg2", "redis", "requests"]

    for package in required_packages:
        try:
            __import__(package)
            print(f"  + {package}")
        except ImportError:
            missing_deps.append(package)
            print(f"  X {package} (missing)")

    if missing_deps:
        print(f"\nMissing dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        return False

    print("All dependencies available.\n")
    return True


def check_environment():
    """Check environment variables."""
    print("Checking environment variables...")

    required_vars = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "REDIS_HOST",
        "REDIS_PORT",
    ]

    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Don't print password values
            display_value = "***" if "PASSWORD" in var else value
            print(f"  + {var}={display_value}")
        else:
            missing_vars.append(var)
            print(f"  X {var} (not set)")

    if missing_vars:
        print(f"\nMissing environment variables: {', '.join(missing_vars)}")
        print("Set them before running tests or use default values for testing.")
        return False

    print("All environment variables set.\n")
    return True


def run_simple_validation():
    """Run simple startup validation."""
    print("Running simple startup validation...")

    try:
        result = subprocess.run(
            [sys.executable, "validate_startup_simple.py"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=120,
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("X Simple validation timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"X Error running simple validation: {e}")
        return False


def run_comprehensive_tests():
    """Run comprehensive startup validation tests."""
    print("Running comprehensive startup validation tests...")

    try:
        result = subprocess.run(
            [sys.executable, "test_startup_comprehensive.py"],
            cwd=Path(__file__).parent,
            timeout=300,  # 5 minutes timeout
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("X Comprehensive tests timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"X Error running comprehensive tests: {e}")
        return False


def run_individual_test_suite(suite_name):
    """Run individual test suite."""
    print(f"Running {suite_name} test suite...")

    suite_map = {
        "postgres": "test_startup_validation.PostgreSQLStartupTests",
        "redis": "test_startup_validation.RedisStartupTests",
        "integration": "test_startup_validation.IntegrationStartupTests",
        "health": "test_startup_validation.HealthEndpointTests",
    }

    if suite_name not in suite_map:
        print(f"X Unknown test suite: {suite_name}")
        print(f"Available suites: {', '.join(suite_map.keys())}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", suite_map[suite_name]],
            cwd=Path(__file__).parent,
            timeout=120,
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"X {suite_name} tests timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"X Error running {suite_name} tests: {e}")
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Run orchestrator startup validation tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_startup_validation.py                    # Run all tests
  python run_startup_validation.py --simple           # Run simple validation only
  python run_startup_validation.py --suite postgres   # Run PostgreSQL tests only
  python run_startup_validation.py --no-env-check     # Skip environment check
        """,
    )

    parser.add_argument(
        "--simple", action="store_true", help="Run only simple validation tests"
    )

    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run only comprehensive tests (skip simple)",
    )

    parser.add_argument(
        "--suite",
        choices=["postgres", "redis", "integration", "health"],
        help="Run specific test suite only",
    )

    parser.add_argument(
        "--no-deps-check", action="store_true", help="Skip dependency check"
    )

    parser.add_argument(
        "--no-env-check", action="store_true", help="Skip environment variable check"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("ORCHESTRATOR STARTUP VALIDATION TEST RUNNER")
    print("=" * 70)
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Check dependencies
    if not args.no_deps_check:
        if not check_dependencies():
            print("X Dependency check failed. Use --no-deps-check to skip.")
            return False

    # Check environment
    if not args.no_env_check:
        env_ok = check_environment()
        if not env_ok:
            print("! Environment check failed. Tests may fail or use defaults.")
            print("Use --no-env-check to skip this check.")
            print()

    # Run tests based on arguments
    success = True

    if args.suite:
        # Run specific test suite
        success = run_individual_test_suite(args.suite)

    elif args.simple:
        # Run simple validation only
        success = run_simple_validation()

    elif args.comprehensive:
        # Run comprehensive tests only
        success = run_comprehensive_tests()

    else:
        # Run all tests (default)
        print("Running all startup validation tests...\n")

        # First run simple validation
        simple_success = run_simple_validation()
        print()

        # Then run comprehensive tests
        comprehensive_success = run_comprehensive_tests()

        success = simple_success and comprehensive_success

    # Print final result
    print("\n" + "=" * 70)
    print("STARTUP VALIDATION RESULTS")
    print("=" * 70)

    if success:
        print("+ ALL STARTUP VALIDATION TESTS PASSED!")
        print("\nThe orchestrator startup sequence is validated and ready.")
        print("You can proceed with deployment or further testing.")
    else:
        print("X STARTUP VALIDATION TESTS FAILED!")
        print("\nSome tests failed. Please review the output above.")
        print("Common solutions:")
        print("  - Ensure PostgreSQL and Redis services are running")
        print("  - Check environment variables are properly set")
        print("  - Verify network connectivity and credentials")
        print("  - Review service logs for detailed error information")

    print(f"\nCompleted at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

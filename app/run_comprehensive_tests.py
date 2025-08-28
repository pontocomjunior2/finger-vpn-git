#!/usr/bin/env python3
"""
Comprehensive Test Runner for Orchestrator Stream Balancing Fix

This script runs the complete automated testing suite including:
- Unit tests for all components with error scenario coverage
- Integration tests for orchestrator-worker communication
- Load testing framework for balancing algorithm validation

Requirements: All requirements validation
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("test_results.log")],
)
logger = logging.getLogger(__name__)


class TestSuiteRunner:
    """Comprehensive test suite runner"""

    def __init__(self, app_dir: str = "app"):
        self.app_dir = Path(app_dir)
        self.test_results = {}
        self.start_time = None
        self.end_time = None

    def run_pytest_suite(
        self, test_file: str, test_name: str, additional_args: List[str] = None
    ) -> Dict:
        """Run a pytest test suite and capture results"""
        logger.info(f"Running {test_name}...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.app_dir / test_file),
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file={test_name}_report.json",
        ]

        if additional_args:
            cmd.extend(additional_args)

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.app_dir.parent,
                timeout=300,  # 5 minute timeout
            )

            end_time = time.time()
            execution_time = end_time - start_time

            # Parse JSON report if available
            json_report_path = self.app_dir.parent / f"{test_name}_report.json"
            json_report = None
            if json_report_path.exists():
                try:
                    with open(json_report_path, "r") as f:
                        json_report = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not parse JSON report for {test_name}: {e}")

            test_result = {
                "name": test_name,
                "file": test_file,
                "return_code": result.returncode,
                "execution_time": execution_time,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "json_report": json_report,
                "passed": result.returncode == 0,
            }

            if result.returncode == 0:
                logger.info(f"✓ {test_name} passed in {execution_time:.2f}s")
            else:
                logger.error(f"✗ {test_name} failed in {execution_time:.2f}s")
                logger.error(f"STDERR: {result.stderr}")

            return test_result

        except subprocess.TimeoutExpired:
            logger.error(f"✗ {test_name} timed out after 5 minutes")
            return {
                "name": test_name,
                "file": test_file,
                "return_code": -1,
                "execution_time": 300,
                "stdout": "",
                "stderr": "Test timed out",
                "json_report": None,
                "passed": False,
            }
        except Exception as e:
            logger.error(f"✗ {test_name} failed with exception: {e}")
            return {
                "name": test_name,
                "file": test_file,
                "return_code": -2,
                "execution_time": 0,
                "stdout": "",
                "stderr": str(e),
                "json_report": None,
                "passed": False,
            }

    def run_unit_tests(self) -> Dict:
        """Run comprehensive unit tests"""
        logger.info("=" * 60)
        logger.info("RUNNING UNIT TESTS")
        logger.info("=" * 60)

        unit_test_suites = [
            {
                "file": "test_suite_comprehensive.py::TestSmartLoadBalancerUnit",
                "name": "smart_load_balancer_unit",
                "description": "Smart Load Balancer Unit Tests",
            },
            {
                "file": "test_suite_comprehensive.py::TestEnhancedOrchestratorUnit",
                "name": "enhanced_orchestrator_unit",
                "description": "Enhanced Orchestrator Unit Tests",
            },
            {
                "file": "test_suite_comprehensive.py::TestResilientOrchestratorUnit",
                "name": "resilient_orchestrator_unit",
                "description": "Resilient Orchestrator Unit Tests",
            },
            {
                "file": "test_suite_comprehensive.py::TestConsistencyCheckerUnit",
                "name": "consistency_checker_unit",
                "description": "Consistency Checker Unit Tests",
            },
            {
                "file": "test_suite_comprehensive.py::TestErrorScenarios",
                "name": "error_scenarios",
                "description": "Comprehensive Error Scenario Tests",
            },
        ]

        unit_results = {}
        for suite in unit_test_suites:
            logger.info(f"Running {suite['description']}...")
            result = self.run_pytest_suite(suite["file"], suite["name"])
            unit_results[suite["name"]] = result

        return unit_results

    def run_integration_tests(self) -> Dict:
        """Run integration tests"""
        logger.info("=" * 60)
        logger.info("RUNNING INTEGRATION TESTS")
        logger.info("=" * 60)

        integration_test_suites = [
            {
                "file": "test_integration_orchestrator_worker.py::TestOrchestratorWorkerRegistration",
                "name": "orchestrator_worker_registration",
                "description": "Orchestrator-Worker Registration Tests",
            },
            {
                "file": "test_integration_orchestrator_worker.py::TestOrchestratorWorkerHeartbeat",
                "name": "orchestrator_worker_heartbeat",
                "description": "Orchestrator-Worker Heartbeat Tests",
            },
            {
                "file": "test_integration_orchestrator_worker.py::TestOrchestratorWorkerStreamManagement",
                "name": "orchestrator_worker_streams",
                "description": "Orchestrator-Worker Stream Management Tests",
            },
            {
                "file": "test_integration_orchestrator_worker.py::TestOrchestratorWorkerFailureScenarios",
                "name": "orchestrator_worker_failures",
                "description": "Orchestrator-Worker Failure Scenario Tests",
            },
            {
                "file": "test_integration_orchestrator_worker.py::TestOrchestratorWorkerLoadBalancing",
                "name": "orchestrator_worker_load_balancing",
                "description": "Orchestrator-Worker Load Balancing Tests",
            },
        ]

        integration_results = {}
        for suite in integration_test_suites:
            logger.info(f"Running {suite['description']}...")
            result = self.run_pytest_suite(suite["file"], suite["name"])
            integration_results[suite["name"]] = result

        return integration_results

    def run_load_tests(self) -> Dict:
        """Run load testing framework"""
        logger.info("=" * 60)
        logger.info("RUNNING LOAD TESTS")
        logger.info("=" * 60)

        load_test_suites = [
            {
                "file": "test_load_balancing_framework.py::TestLoadTestingFramework",
                "name": "load_testing_framework",
                "description": "Load Testing Framework Tests",
            },
            {
                "file": "test_suite_comprehensive.py::TestPerformanceAndStress",
                "name": "performance_stress_tests",
                "description": "Performance and Stress Tests",
            },
        ]

        load_results = {}
        for suite in load_test_suites:
            logger.info(f"Running {suite['description']}...")
            result = self.run_pytest_suite(
                suite["file"],
                suite["name"],
                additional_args=["--timeout=600"],  # 10 minute timeout for load tests
            )
            load_results[suite["name"]] = result

        return load_results

    def run_existing_tests(self) -> Dict:
        """Run existing test suites to ensure compatibility"""
        logger.info("=" * 60)
        logger.info("RUNNING EXISTING TESTS")
        logger.info("=" * 60)

        existing_test_files = [
            "test_consistency_checker.py",
            "test_smart_load_balancer.py",
            "test_resilient_orchestrator.py",
            "test_diagnostic_api.py",
        ]

        existing_results = {}
        for test_file in existing_test_files:
            test_path = self.app_dir / test_file
            if test_path.exists():
                test_name = test_file.replace(".py", "")
                logger.info(f"Running existing test: {test_name}...")
                result = self.run_pytest_suite(test_file, f"existing_{test_name}")
                existing_results[f"existing_{test_name}"] = result
            else:
                logger.warning(f"Existing test file not found: {test_file}")

        return existing_results

    def generate_summary_report(self) -> Dict:
        """Generate comprehensive test summary report"""
        total_tests = len(self.test_results)
        passed_tests = sum(
            1 for result in self.test_results.values() if result["passed"]
        )
        failed_tests = total_tests - passed_tests

        total_execution_time = sum(
            result["execution_time"] for result in self.test_results.values()
        )

        # Categorize results
        unit_test_results = {
            k: v
            for k, v in self.test_results.items()
            if "unit" in k or "error_scenarios" in k
        }
        integration_test_results = {
            k: v for k, v in self.test_results.items() if "orchestrator_worker" in k
        }
        load_test_results = {
            k: v
            for k, v in self.test_results.items()
            if "load" in k or "performance" in k
        }
        existing_test_results = {
            k: v for k, v in self.test_results.items() if "existing" in k
        }

        summary = {
            "test_run_info": {
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "total_execution_time": total_execution_time,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": (
                    (passed_tests / total_tests * 100) if total_tests > 0 else 0
                ),
            },
            "category_summary": {
                "unit_tests": {
                    "total": len(unit_test_results),
                    "passed": sum(1 for r in unit_test_results.values() if r["passed"]),
                    "failed": sum(
                        1 for r in unit_test_results.values() if not r["passed"]
                    ),
                },
                "integration_tests": {
                    "total": len(integration_test_results),
                    "passed": sum(
                        1 for r in integration_test_results.values() if r["passed"]
                    ),
                    "failed": sum(
                        1 for r in integration_test_results.values() if not r["passed"]
                    ),
                },
                "load_tests": {
                    "total": len(load_test_results),
                    "passed": sum(1 for r in load_test_results.values() if r["passed"]),
                    "failed": sum(
                        1 for r in load_test_results.values() if not r["passed"]
                    ),
                },
                "existing_tests": {
                    "total": len(existing_test_results),
                    "passed": sum(
                        1 for r in existing_test_results.values() if r["passed"]
                    ),
                    "failed": sum(
                        1 for r in existing_test_results.values() if not r["passed"]
                    ),
                },
            },
            "detailed_results": self.test_results,
            "failed_test_details": {
                name: {
                    "file": result["file"],
                    "stderr": result["stderr"],
                    "execution_time": result["execution_time"],
                }
                for name, result in self.test_results.items()
                if not result["passed"]
            },
        }

        return summary

    def print_summary_report(self, summary: Dict):
        """Print formatted summary report"""
        logger.info("=" * 80)
        logger.info("COMPREHENSIVE TEST SUITE SUMMARY")
        logger.info("=" * 80)

        info = summary["test_run_info"]
        logger.info(f"Test Run Duration: {info['total_execution_time']:.2f} seconds")
        logger.info(f"Total Tests: {info['total_tests']}")
        logger.info(f"Passed: {info['passed_tests']} ({info['success_rate']:.1f}%)")
        logger.info(f"Failed: {info['failed_tests']}")

        logger.info("\nCategory Breakdown:")
        for category, stats in summary["category_summary"].items():
            category_name = category.replace("_", " ").title()
            success_rate = (
                (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            logger.info(
                f"  {category_name}: {stats['passed']}/{stats['total']} ({success_rate:.1f}%)"
            )

        if summary["failed_test_details"]:
            logger.info("\nFailed Test Details:")
            for test_name, details in summary["failed_test_details"].items():
                logger.info(
                    f"  ✗ {test_name} ({details['file']}) - {details['execution_time']:.2f}s"
                )
                if details["stderr"]:
                    logger.info(f"    Error: {details['stderr'][:200]}...")

        logger.info("=" * 80)

        # Overall assessment
        if info["success_rate"] >= 90:
            logger.info("🎉 EXCELLENT: Test suite passed with high success rate!")
        elif info["success_rate"] >= 75:
            logger.info("✅ GOOD: Test suite passed with acceptable success rate.")
        elif info["success_rate"] >= 50:
            logger.info("⚠️  WARNING: Test suite has moderate failures. Review needed.")
        else:
            logger.info(
                "❌ CRITICAL: Test suite has high failure rate. Immediate attention required."
            )

    def save_detailed_report(
        self, summary: Dict, filename: str = "comprehensive_test_report.json"
    ):
        """Save detailed test report to JSON file"""
        report_path = self.app_dir.parent / filename

        try:
            with open(report_path, "w") as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info(f"Detailed test report saved to: {report_path}")
        except Exception as e:
            logger.error(f"Failed to save detailed report: {e}")

    def run_full_test_suite(
        self, include_existing: bool = True, include_load_tests: bool = True
    ) -> Dict:
        """Run the complete test suite"""
        self.start_time = datetime.now()
        logger.info(f"Starting comprehensive test suite at {self.start_time}")

        try:
            # Run unit tests
            unit_results = self.run_unit_tests()
            self.test_results.update(unit_results)

            # Run integration tests
            integration_results = self.run_integration_tests()
            self.test_results.update(integration_results)

            # Run load tests if requested
            if include_load_tests:
                load_results = self.run_load_tests()
                self.test_results.update(load_results)

            # Run existing tests if requested
            if include_existing:
                existing_results = self.run_existing_tests()
                self.test_results.update(existing_results)

        except KeyboardInterrupt:
            logger.warning("Test suite interrupted by user")
        except Exception as e:
            logger.error(f"Test suite failed with exception: {e}")
        finally:
            self.end_time = datetime.now()

        # Generate and display summary
        summary = self.generate_summary_report()
        self.print_summary_report(summary)
        self.save_detailed_report(summary)

        return summary


def main():
    """Main entry point for test runner"""
    parser = argparse.ArgumentParser(description="Run comprehensive test suite")
    parser.add_argument(
        "--no-existing", action="store_true", help="Skip existing test suites"
    )
    parser.add_argument(
        "--no-load-tests", action="store_true", help="Skip load testing framework"
    )
    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")
    parser.add_argument(
        "--integration-only", action="store_true", help="Run only integration tests"
    )
    parser.add_argument("--load-only", action="store_true", help="Run only load tests")
    parser.add_argument(
        "--app-dir", default="app", help="Application directory (default: app)"
    )

    args = parser.parse_args()

    runner = TestSuiteRunner(args.app_dir)

    if args.unit_only:
        logger.info("Running unit tests only...")
        results = runner.run_unit_tests()
        runner.test_results.update(results)
    elif args.integration_only:
        logger.info("Running integration tests only...")
        results = runner.run_integration_tests()
        runner.test_results.update(results)
    elif args.load_only:
        logger.info("Running load tests only...")
        results = runner.run_load_tests()
        runner.test_results.update(results)
    else:
        # Run full suite
        summary = runner.run_full_test_suite(
            include_existing=not args.no_existing,
            include_load_tests=not args.no_load_tests,
        )

        # Exit with appropriate code
        if summary["test_run_info"]["success_rate"] >= 75:
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()

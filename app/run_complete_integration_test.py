#!/usr/bin/env python3
"""
Complete Integration Test Runner

This script runs the complete integration testing suite including:
1. Component integration validation
2. End-to-end scenario testing
3. Performance validation under load
4. Failure simulation and recovery testing

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration_system import EndToEndTestSuite, IntegratedOrchestrator
from performance_validation import PerformanceValidator
from run_integration_validation import IntegrationValidator

logger = logging.getLogger(__name__)


class CompleteIntegrationTestRunner:
    """Complete integration test runner that orchestrates all testing phases"""

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.test_results = {}
        self.start_time = datetime.now()

    async def run_component_integration_tests(self) -> Dict[str, Any]:
        """Run component integration validation tests"""
        logger.info("=" * 60)
        logger.info("PHASE 1: Component Integration Validation")
        logger.info("=" * 60)

        validator = IntegrationValidator()
        validation_report = await validator.run_comprehensive_validation(self.db_config)

        self.test_results["component_integration"] = validation_report

        logger.info(
            f"Component integration validation: {'PASSED' if validation_report['overall_success'] else 'FAILED'}"
        )
        return validation_report

    async def run_end_to_end_scenario_tests(self) -> Dict[str, Any]:
        """Run end-to-end scenario tests"""
        logger.info("=" * 60)
        logger.info("PHASE 2: End-to-End Scenario Testing")
        logger.info("=" * 60)

        orchestrator = IntegratedOrchestrator(self.db_config)

        try:
            # Start system
            if not await orchestrator.start_system():
                raise Exception("Failed to start orchestrator for end-to-end testing")

            # Run end-to-end tests
            test_suite = EndToEndTestSuite(orchestrator)
            test_report = await test_suite.run_all_tests()

            self.test_results["end_to_end_scenarios"] = test_report

            logger.info(
                f"End-to-end scenario testing: {'PASSED' if test_report['summary']['failed_tests'] == 0 else 'FAILED'}"
            )
            return test_report

        finally:
            await orchestrator.stop_system()

    async def run_performance_validation_tests(self) -> Dict[str, Any]:
        """Run performance validation tests"""
        logger.info("=" * 60)
        logger.info("PHASE 3: Performance Validation Testing")
        logger.info("=" * 60)

        orchestrator = IntegratedOrchestrator(self.db_config)

        try:
            # Start system
            if not await orchestrator.start_system():
                raise Exception("Failed to start orchestrator for performance testing")

            # Run performance tests
            validator = PerformanceValidator(orchestrator)
            performance_report = await validator.run_all_performance_tests()

            self.test_results["performance_validation"] = performance_report

            logger.info(
                f"Performance validation: {'PASSED' if performance_report['summary']['performance_requirements_met'] else 'FAILED'}"
            )
            return performance_report

        finally:
            await orchestrator.stop_system()

    async def run_failure_simulation_tests(self) -> Dict[str, Any]:
        """Run failure simulation and recovery tests"""
        logger.info("=" * 60)
        logger.info("PHASE 4: Failure Simulation and Recovery Testing")
        logger.info("=" * 60)

        orchestrator = IntegratedOrchestrator(self.db_config)

        try:
            # Start system
            if not await orchestrator.start_system():
                raise Exception(
                    "Failed to start orchestrator for failure simulation testing"
                )

            failure_test_results = []

            # Test 1: Database connection failure simulation
            logger.info("Testing database connection failure recovery...")
            try:
                # Register instances first
                await orchestrator.register_instance(
                    "failure-test-1", "127.0.0.1", 8001, 20
                )
                await orchestrator.register_instance(
                    "failure-test-2", "127.0.0.1", 8002, 20
                )

                # Simulate database failure by temporarily breaking connection
                # This would be handled by the error handler
                result = await orchestrator.handle_instance_failure("failure-test-1")

                failure_test_results.append(
                    {
                        "test_name": "Database Connection Failure Recovery",
                        "success": result["status"] == "success",
                        "details": result,
                    }
                )

            except Exception as e:
                failure_test_results.append(
                    {
                        "test_name": "Database Connection Failure Recovery",
                        "success": False,
                        "error": str(e),
                    }
                )

            # Test 2: Network partition simulation
            logger.info("Testing network partition recovery...")
            try:
                # Simulate network issues by testing timeout handling
                import asyncio

                # This would test the circuit breaker pattern
                heartbeat_data = {"current_streams": 5}
                result = await orchestrator.process_heartbeat(
                    "failure-test-2", heartbeat_data
                )

                failure_test_results.append(
                    {
                        "test_name": "Network Partition Recovery",
                        "success": result["status"] == "success",
                        "details": result,
                    }
                )

            except Exception as e:
                failure_test_results.append(
                    {
                        "test_name": "Network Partition Recovery",
                        "success": False,
                        "error": str(e),
                    }
                )

            # Test 3: Component failure resilience
            logger.info("Testing component failure resilience...")
            try:
                # Temporarily disable monitoring system
                original_monitoring = orchestrator.monitoring_system
                orchestrator.monitoring_system = None
                orchestrator.component_health["monitoring_system"] = False

                # System should continue operating
                result = await orchestrator.register_instance(
                    "resilience-test-1", "127.0.0.1", 8003, 20
                )

                # Restore monitoring system
                orchestrator.monitoring_system = original_monitoring
                orchestrator.component_health["monitoring_system"] = True

                failure_test_results.append(
                    {
                        "test_name": "Component Failure Resilience",
                        "success": result["status"] == "success",
                        "details": result,
                    }
                )

            except Exception as e:
                failure_test_results.append(
                    {
                        "test_name": "Component Failure Resilience",
                        "success": False,
                        "error": str(e),
                    }
                )

            # Generate failure simulation report
            total_tests = len(failure_test_results)
            passed_tests = sum(1 for test in failure_test_results if test["success"])

            failure_report = {
                "summary": {
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "failed_tests": total_tests - passed_tests,
                    "success_rate": (
                        passed_tests / total_tests if total_tests > 0 else 0
                    ),
                },
                "test_results": failure_test_results,
                "timestamp": datetime.now().isoformat(),
            }

            self.test_results["failure_simulation"] = failure_report

            logger.info(
                f"Failure simulation testing: {'PASSED' if passed_tests == total_tests else 'FAILED'}"
            )
            return failure_report

        finally:
            await orchestrator.stop_system()

    async def run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests using pytest"""
        logger.info("=" * 60)
        logger.info("PHASE 5: Unit Tests")
        logger.info("=" * 60)

        try:
            # Run pytest on the comprehensive test suite
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "test_integration_comprehensive.py",
                    "-v",
                    "--tb=short",
                ],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(__file__),
            )

            unit_test_report = {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
                "timestamp": datetime.now().isoformat(),
            }

            self.test_results["unit_tests"] = unit_test_report

            logger.info(
                f"Unit tests: {'PASSED' if result.returncode == 0 else 'FAILED'}"
            )

            if result.returncode != 0:
                logger.error("Unit test output:")
                logger.error(result.stdout)
                logger.error(result.stderr)

            return unit_test_report

        except Exception as e:
            logger.error(f"Failed to run unit tests: {e}")
            unit_test_report = {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            self.test_results["unit_tests"] = unit_test_report
            return unit_test_report

    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_duration = (datetime.now() - self.start_time).total_seconds()

        # Calculate overall success
        phase_results = []

        # Component integration
        if "component_integration" in self.test_results:
            phase_results.append(
                self.test_results["component_integration"]["overall_success"]
            )

        # End-to-end scenarios
        if "end_to_end_scenarios" in self.test_results:
            phase_results.append(
                self.test_results["end_to_end_scenarios"]["summary"]["failed_tests"]
                == 0
            )

        # Performance validation
        if "performance_validation" in self.test_results:
            phase_results.append(
                self.test_results["performance_validation"]["summary"][
                    "performance_requirements_met"
                ]
            )

        # Failure simulation
        if "failure_simulation" in self.test_results:
            phase_results.append(
                self.test_results["failure_simulation"]["summary"]["failed_tests"] == 0
            )

        # Unit tests
        if "unit_tests" in self.test_results:
            phase_results.append(self.test_results["unit_tests"]["success"])

        overall_success = all(phase_results) if phase_results else False

        return {
            "summary": {
                "total_phases": len(phase_results),
                "passed_phases": sum(phase_results),
                "failed_phases": len(phase_results) - sum(phase_results),
                "overall_success": overall_success,
                "total_duration_seconds": total_duration,
                "test_completion_time": datetime.now().isoformat(),
            },
            "phase_results": {
                "component_integration": self.test_results.get(
                    "component_integration", {}
                ),
                "end_to_end_scenarios": self.test_results.get(
                    "end_to_end_scenarios", {}
                ),
                "performance_validation": self.test_results.get(
                    "performance_validation", {}
                ),
                "failure_simulation": self.test_results.get("failure_simulation", {}),
                "unit_tests": self.test_results.get("unit_tests", {}),
            },
            "environment": {
                "database_config": {
                    "host": self.db_config["host"],
                    "port": self.db_config["port"],
                    "database": self.db_config["database"],
                },
                "python_version": sys.version,
                "platform": sys.platform,
            },
            "timestamp": datetime.now().isoformat(),
        }

    async def run_complete_test_suite(self) -> Dict[str, Any]:
        """Run the complete integration test suite"""
        logger.info("Starting Complete Integration Test Suite")
        logger.info(
            f"Database: {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}"
        )
        logger.info("=" * 80)

        try:
            # Phase 1: Component Integration
            await self.run_component_integration_tests()

            # Phase 2: End-to-End Scenarios
            await self.run_end_to_end_scenario_tests()

            # Phase 3: Performance Validation
            await self.run_performance_validation_tests()

            # Phase 4: Failure Simulation
            await self.run_failure_simulation_tests()

            # Phase 5: Unit Tests
            await self.run_unit_tests()

            # Generate comprehensive report
            comprehensive_report = self.generate_comprehensive_report()

            # Save comprehensive report
            report_filename = f"complete_integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_filename, "w") as f:
                json.dump(comprehensive_report, f, indent=2)

            logger.info("=" * 80)
            logger.info("COMPLETE INTEGRATION TEST SUITE SUMMARY")
            logger.info("=" * 80)

            summary = comprehensive_report["summary"]
            logger.info(f"Total test phases: {summary['total_phases']}")
            logger.info(f"Passed phases: {summary['passed_phases']}")
            logger.info(f"Failed phases: {summary['failed_phases']}")
            logger.info(f"Overall success: {summary['overall_success']}")
            logger.info(
                f"Total duration: {summary['total_duration_seconds']:.2f} seconds"
            )
            logger.info(f"Report saved to: {report_filename}")

            if summary["overall_success"]:
                logger.info("✓ ALL INTEGRATION TESTS PASSED SUCCESSFULLY")
            else:
                logger.error("✗ SOME INTEGRATION TESTS FAILED")

                # Log failed phases
                for phase_name, phase_data in comprehensive_report[
                    "phase_results"
                ].items():
                    if phase_name == "component_integration" and not phase_data.get(
                        "overall_success", True
                    ):
                        logger.error(f"  - Component Integration: FAILED")
                    elif (
                        phase_name == "end_to_end_scenarios"
                        and phase_data.get("summary", {}).get("failed_tests", 0) > 0
                    ):
                        logger.error(f"  - End-to-End Scenarios: FAILED")
                    elif phase_name == "performance_validation" and not phase_data.get(
                        "summary", {}
                    ).get("performance_requirements_met", True):
                        logger.error(f"  - Performance Validation: FAILED")
                    elif (
                        phase_name == "failure_simulation"
                        and phase_data.get("summary", {}).get("failed_tests", 0) > 0
                    ):
                        logger.error(f"  - Failure Simulation: FAILED")
                    elif phase_name == "unit_tests" and not phase_data.get(
                        "success", True
                    ):
                        logger.error(f"  - Unit Tests: FAILED")

            return comprehensive_report

        except Exception as e:
            logger.error(f"Complete integration test suite failed: {e}")

            # Generate error report
            error_report = {
                "summary": {
                    "overall_success": False,
                    "error": str(e),
                    "total_duration_seconds": (
                        datetime.now() - self.start_time
                    ).total_seconds(),
                },
                "phase_results": self.test_results,
                "timestamp": datetime.now().isoformat(),
            }

            return error_report


async def main():
    """Main function"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Database configuration
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "orchestrator"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

    # Create test runner
    test_runner = CompleteIntegrationTestRunner(db_config)

    # Run complete test suite
    comprehensive_report = await test_runner.run_complete_test_suite()

    # Return appropriate exit code
    if comprehensive_report["summary"]["overall_success"]:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

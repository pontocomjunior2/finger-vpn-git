#!/usr/bin/env python3
"""
Test script for enhanced health check endpoints.

This script validates the improved health check functionality including:
- Basic health endpoint with detailed service status
- Readiness probe for container orchestration
- Detailed health check with comprehensive diagnostics

Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Any

import aiohttp
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HealthCheckTester:
    """Test class for health check endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def test_health_endpoint(self) -> Dict[str, Any]:
        """
        Test the main /health endpoint.
        
        Returns:
            dict: Test results
        """
        logger.info("Testing /health endpoint...")
        
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/health") as response:
                response_time = time.time() - start_time
                
                data = await response.json()
                
                # Validate response structure
                required_fields = ["status", "timestamp", "services", "application_components", "details"]
                missing_fields = [field for field in required_fields if field not in data]
                
                # Validate services
                services = data.get("services", {})
                expected_services = ["postgresql", "redis"]
                missing_services = [svc for svc in expected_services if svc not in services]
                
                # Validate application components
                app_components = data.get("application_components", {})
                expected_components = ["enhanced_orchestrator", "resilient_orchestrator", "system_metrics"]
                missing_components = [comp for comp in expected_components if comp not in app_components]
                
                return {
                    "endpoint": "/health",
                    "status_code": response.status,
                    "response_time_ms": round(response_time * 1000, 2),
                    "data": data,
                    "validation": {
                        "structure_valid": len(missing_fields) == 0,
                        "missing_fields": missing_fields,
                        "services_complete": len(missing_services) == 0,
                        "missing_services": missing_services,
                        "components_complete": len(missing_components) == 0,
                        "missing_components": missing_components,
                        "has_system_metrics": "system_metrics" in data,
                        "has_errors": "errors" in data
                    }
                }
                
        except Exception as e:
            logger.error(f"Health endpoint test failed: {e}")
            return {
                "endpoint": "/health",
                "status_code": None,
                "error": str(e),
                "validation": {"structure_valid": False}
            }
    
    async def test_readiness_endpoint(self) -> Dict[str, Any]:
        """
        Test the /ready endpoint.
        
        Returns:
            dict: Test results
        """
        logger.info("Testing /ready endpoint...")
        
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/ready") as response:
                response_time = time.time() - start_time
                
                data = await response.json()
                
                # Validate response structure
                required_fields = ["status", "timestamp", "services", "details"]
                missing_fields = [field for field in required_fields if field not in data]
                
                # Validate services
                services = data.get("services", {})
                expected_services = ["postgresql", "redis", "orchestrator"]
                missing_services = [svc for svc in expected_services if svc not in services]
                
                return {
                    "endpoint": "/ready",
                    "status_code": response.status,
                    "response_time_ms": round(response_time * 1000, 2),
                    "data": data,
                    "validation": {
                        "structure_valid": len(missing_fields) == 0,
                        "missing_fields": missing_fields,
                        "services_complete": len(missing_services) == 0,
                        "missing_services": missing_services,
                        "is_readiness_probe": data.get("details", {}).get("check_type") == "readiness_probe",
                        "has_fast_timeout": "short" in str(data.get("details", {}).get("timeout_used", ""))
                    }
                }
                
        except Exception as e:
            logger.error(f"Readiness endpoint test failed: {e}")
            return {
                "endpoint": "/ready",
                "status_code": None,
                "error": str(e),
                "validation": {"structure_valid": False}
            }
    
    async def test_detailed_health_endpoint(self) -> Dict[str, Any]:
        """
        Test the /health/detailed endpoint.
        
        Returns:
            dict: Test results
        """
        logger.info("Testing /health/detailed endpoint...")
        
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/health/detailed") as response:
                response_time = time.time() - start_time
                
                data = await response.json()
                
                # Validate response structure
                required_fields = [
                    "status", "timestamp", "services", "application_components",
                    "orchestrator_internal", "configuration", "performance", "diagnostics"
                ]
                missing_fields = [field for field in required_fields if field not in data]
                
                # Validate detailed sections
                has_config_validation = "configuration" in data and "status" in data.get("configuration", {})
                has_diagnostics = "diagnostics" in data and "recommendations" in data.get("diagnostics", {})
                has_performance = "performance" in data and "system_metrics" in data.get("performance", {})
                
                return {
                    "endpoint": "/health/detailed",
                    "status_code": response.status,
                    "response_time_ms": round(response_time * 1000, 2),
                    "data": data,
                    "validation": {
                        "structure_valid": len(missing_fields) == 0,
                        "missing_fields": missing_fields,
                        "has_config_validation": has_config_validation,
                        "has_diagnostics": has_diagnostics,
                        "has_performance_metrics": has_performance,
                        "is_detailed_check": data.get("check_type") == "detailed_health_check",
                        "has_recommendations": len(data.get("diagnostics", {}).get("recommendations", [])) > 0
                    }
                }
                
        except Exception as e:
            logger.error(f"Detailed health endpoint test failed: {e}")
            return {
                "endpoint": "/health/detailed",
                "status_code": None,
                "error": str(e),
                "validation": {"structure_valid": False}
            }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all health check tests.
        
        Returns:
            dict: Complete test results
        """
        logger.info("Starting comprehensive health check endpoint tests...")
        
        test_results = {
            "test_run": {
                "timestamp": datetime.now().isoformat(),
                "base_url": self.base_url
            },
            "tests": {},
            "summary": {}
        }
        
        # Run individual tests
        test_results["tests"]["health"] = await self.test_health_endpoint()
        test_results["tests"]["readiness"] = await self.test_readiness_endpoint()
        test_results["tests"]["detailed_health"] = await self.test_detailed_health_endpoint()
        
        # Generate summary
        total_tests = len(test_results["tests"])
        passed_tests = sum(
            1 for test in test_results["tests"].values()
            if test.get("validation", {}).get("structure_valid", False)
        )
        
        test_results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": round((passed_tests / total_tests) * 100, 2) if total_tests > 0 else 0,
            "all_tests_passed": passed_tests == total_tests
        }
        
        return test_results


async def main():
    """Main test function."""
    print("🔍 Enhanced Health Check Endpoint Tests")
    print("=" * 50)
    
    # Test with default orchestrator URL
    async with HealthCheckTester() as tester:
        results = await tester.run_all_tests()
        
        # Print results
        print(f"\n📊 Test Results Summary:")
        print(f"Total Tests: {results['summary']['total_tests']}")
        print(f"Passed: {results['summary']['passed_tests']}")
        print(f"Failed: {results['summary']['failed_tests']}")
        print(f"Success Rate: {results['summary']['success_rate']}%")
        
        # Print detailed results
        print(f"\n📋 Detailed Results:")
        for test_name, test_result in results["tests"].items():
            status = "✅ PASS" if test_result.get("validation", {}).get("structure_valid", False) else "❌ FAIL"
            response_time = test_result.get("response_time_ms", "N/A")
            status_code = test_result.get("status_code", "N/A")
            
            print(f"{status} {test_name.upper()}: {status_code} ({response_time}ms)")
            
            # Print validation details
            validation = test_result.get("validation", {})
            for key, value in validation.items():
                if key != "structure_valid":
                    print(f"  - {key}: {value}")
        
        # Save results to file
        with open("health_check_test_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Full results saved to: health_check_test_results.json")
        
        # Exit with appropriate code
        if results["summary"]["all_tests_passed"]:
            print("\n🎉 All health check tests passed!")
            return 0
        else:
            print("\n⚠️  Some health check tests failed!")
            return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        sys.exit(1)
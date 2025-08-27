#!/usr/bin/env python3
"""
Unit tests for health check helper functions.

This script tests the individual helper functions used in the enhanced health check
endpoints without requiring a running orchestrator instance.

Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add the app directory to the path so we can import orchestrator modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the functions we want to test
try:
    from orchestrator import (
        _get_application_components_status,
        _get_system_metrics,
        _validate_configuration,
        _get_system_warnings,
        _get_system_recommendations,
        HAS_PSUTIL,
        HAS_SMART_BALANCER,
        HAS_RESILIENT_ORCHESTRATOR,
        OPTIONAL_MODULES
    )
except ImportError as e:
    print(f"Failed to import orchestrator functions: {e}")
    sys.exit(1)


class TestHealthCheckFunctions(unittest.TestCase):
    """Test cases for health check helper functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock orchestrator
        self.mock_orchestrator = Mock()
        self.mock_orchestrator.enhanced_orchestrator = None
        self.mock_orchestrator.resilient_orchestrator = None
        
    def test_get_application_components_status(self):
        """Test _get_application_components_status function."""
        print("Testing _get_application_components_status...")
        
        # Test with no optional components
        components = _get_application_components_status(self.mock_orchestrator)
        
        # Validate structure
        self.assertIsInstance(components, dict)
        self.assertIn("enhanced_orchestrator", components)
        self.assertIn("resilient_orchestrator", components)
        self.assertIn("system_metrics", components)
        
        # Validate enhanced orchestrator status
        enhanced = components["enhanced_orchestrator"]
        self.assertIn("name", enhanced)
        self.assertIn("status", enhanced)
        self.assertIn("details", enhanced)
        self.assertEqual(enhanced["status"], "unavailable")
        
        # Validate resilient orchestrator status
        resilient = components["resilient_orchestrator"]
        self.assertIn("name", resilient)
        self.assertIn("status", resilient)
        self.assertIn("details", resilient)
        self.assertEqual(resilient["status"], "unavailable")
        
        # Validate system metrics status
        metrics = components["system_metrics"]
        self.assertIn("name", metrics)
        self.assertIn("status", metrics)
        self.assertIn("details", metrics)
        
        print("✅ _get_application_components_status test passed")
    
    def test_get_application_components_status_with_modules(self):
        """Test _get_application_components_status with available modules."""
        print("Testing _get_application_components_status with available modules...")
        
        # Mock orchestrator with available modules
        self.mock_orchestrator.enhanced_orchestrator = Mock()
        self.mock_orchestrator.resilient_orchestrator = Mock()
        
        components = _get_application_components_status(self.mock_orchestrator)
        
        # If modules are actually available, status should reflect that
        if HAS_SMART_BALANCER:
            self.assertEqual(components["enhanced_orchestrator"]["status"], "available")
        
        if HAS_RESILIENT_ORCHESTRATOR:
            self.assertEqual(components["resilient_orchestrator"]["status"], "available")
        
        print("✅ _get_application_components_status with modules test passed")
    
    def test_validate_configuration(self):
        """Test _validate_configuration function."""
        print("Testing _validate_configuration...")
        
        config = _validate_configuration()
        
        # Validate structure
        self.assertIsInstance(config, dict)
        self.assertIn("status", config)
        self.assertIn("issues", config)
        self.assertIn("environment_variables", config)
        self.assertIn("database_config", config)
        self.assertIn("timeouts", config)
        
        # Validate status is valid string
        self.assertIn(config["status"], ["valid", "issues_found"])
        
        # Validate issues is a list
        self.assertIsInstance(config["issues"], list)
        
        # Validate environment variables section
        env_vars = config["environment_variables"]
        self.assertIsInstance(env_vars, dict)
        
        # Validate database config section
        db_config = config["database_config"]
        self.assertIsInstance(db_config, dict)
        self.assertIn("host", db_config)
        self.assertIn("port", db_config)
        self.assertIn("database", db_config)
        
        # Validate timeouts section
        timeouts = config["timeouts"]
        self.assertIsInstance(timeouts, dict)
        self.assertIn("postgres_startup_timeout", timeouts)
        self.assertIn("redis_startup_timeout", timeouts)
        
        print("✅ _validate_configuration test passed")
    
    def test_get_system_warnings(self):
        """Test _get_system_warnings function."""
        print("Testing _get_system_warnings...")
        
        warnings = _get_system_warnings()
        
        # Validate structure
        self.assertIsInstance(warnings, list)
        
        # Check that warnings are strings
        for warning in warnings:
            self.assertIsInstance(warning, str)
            self.assertTrue(len(warning) > 0)
        
        # Should have warnings about missing optional modules
        warning_text = " ".join(warnings).lower()
        
        if not HAS_SMART_BALANCER:
            self.assertIn("enhanced orchestrator", warning_text)
        
        if not HAS_RESILIENT_ORCHESTRATOR:
            self.assertIn("resilient orchestrator", warning_text)
        
        if not HAS_PSUTIL:
            self.assertIn("system metrics", warning_text)
        
        print("✅ _get_system_warnings test passed")
    
    def test_get_system_recommendations(self):
        """Test _get_system_recommendations function."""
        print("Testing _get_system_recommendations...")
        
        # Mock service status
        service_status = {
            "overall_status": "ready",
            "errors": []
        }
        
        # Mock app components
        app_components = {
            "enhanced_orchestrator": {"status": "unavailable"},
            "resilient_orchestrator": {"status": "unavailable"},
            "system_metrics": {"status": "unavailable"}
        }
        
        recommendations = _get_system_recommendations(service_status, app_components)
        
        # Validate structure
        self.assertIsInstance(recommendations, list)
        
        # Check that recommendations are strings
        for rec in recommendations:
            self.assertIsInstance(rec, str)
            self.assertTrue(len(rec) > 0)
        
        # Should have recommendations for missing components
        rec_text = " ".join(recommendations).lower()
        self.assertIn("enhanced orchestrator", rec_text)
        self.assertIn("resilient orchestrator", rec_text)
        
        print("✅ _get_system_recommendations test passed")
    
    @patch('orchestrator.psutil')
    def test_get_system_metrics_with_psutil(self, mock_psutil):
        """Test _get_system_metrics function with mocked psutil."""
        print("Testing _get_system_metrics with mocked psutil...")
        
        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 25.5
        
        mock_memory = Mock()
        mock_memory.percent = 60.2
        mock_memory.used = 8 * 1024**3  # 8GB
        mock_memory.total = 16 * 1024**3  # 16GB
        mock_memory.available = 8 * 1024**3  # 8GB
        mock_psutil.virtual_memory.return_value = mock_memory
        
        mock_disk = Mock()
        mock_disk.used = 100 * 1024**3  # 100GB
        mock_disk.free = 400 * 1024**3  # 400GB
        mock_disk.total = 500 * 1024**3  # 500GB
        mock_psutil.disk_usage.return_value = mock_disk
        
        mock_psutil.getloadavg.return_value = [1.0, 1.5, 2.0]
        mock_psutil.boot_time.return_value = 1000000000
        
        # Mock the HAS_PSUTIL flag
        with patch('orchestrator.HAS_PSUTIL', True):
            metrics = _get_system_metrics()
        
        if metrics:  # Only test if metrics were returned
            # Validate structure
            self.assertIsInstance(metrics, dict)
            self.assertIn("cpu_percent", metrics)
            self.assertIn("memory", metrics)
            self.assertIn("disk", metrics)
            
            # Validate values
            self.assertEqual(metrics["cpu_percent"], 25.5)
            self.assertIsInstance(metrics["memory"], dict)
            self.assertIsInstance(metrics["disk"], dict)
        
        print("✅ _get_system_metrics test passed")
    
    def test_get_system_metrics_without_psutil(self):
        """Test _get_system_metrics function without psutil."""
        print("Testing _get_system_metrics without psutil...")
        
        # Mock the HAS_PSUTIL flag as False
        with patch('orchestrator.HAS_PSUTIL', False):
            metrics = _get_system_metrics()
        
        # Should return None when psutil is not available
        self.assertIsNone(metrics)
        
        print("✅ _get_system_metrics without psutil test passed")


def run_tests():
    """Run all tests and return results."""
    print("🔍 Health Check Helper Functions Tests")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestHealthCheckFunctions)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"📊 Test Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n❌ Failures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print(f"\n💥 Errors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    if len(result.failures) == 0 and len(result.errors) == 0:
        print(f"\n🎉 All tests passed!")
        return True
    else:
        print(f"\n⚠️  Some tests failed!")
        return False


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        sys.exit(1)
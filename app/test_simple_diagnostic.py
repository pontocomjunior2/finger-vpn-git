#!/usr/bin/env python3
"""
Simple test for diagnostic logging functionality.
"""

import sys
from pathlib import Path

# Add app directory to path
sys.path.append(str(Path(__file__).parent))

from diagnostic_logger import diagnostic_logger, environment_validator


def test_basic_logging():
    """Test basic diagnostic logging functionality."""
    print("Testing basic diagnostic logging...")
    
    diagnostic_logger.set_phase("TESTING")
    
    # Test different log levels
    diagnostic_logger.info("This is an info message", context={"test": "basic_logging"})
    diagnostic_logger.warning("This is a warning message", suggested_solution="No action needed - this is a test")
    
    try:
        raise ValueError("Test exception")
    except Exception as e:
        diagnostic_logger.error("This is an error message", 
                               exception=e, 
                               suggested_solution="This is just a test error")
    
    diagnostic_logger.success("Basic logging test completed")
    print("✓ Basic logging test passed")


def test_environment_validation():
    """Test environment validation."""
    print("Testing environment validation...")
    
    validation_result = environment_validator.validate_all()
    
    print(f"Validation status: {validation_result['overall_status']}")
    print(f"Issues found: {len(validation_result['issues'])}")
    print(f"Warnings found: {len(validation_result['warnings'])}")
    
    print("✓ Environment validation test passed")


if __name__ == "__main__":
    print("🔍 SIMPLE DIAGNOSTIC LOGGING TEST")
    print("=" * 50)
    
    try:
        test_basic_logging()
        test_environment_validation()
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
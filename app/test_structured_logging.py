#!/usr/bin/env python3
"""
Test structured logging functionality specifically.
"""

import sys
from pathlib import Path

# Add app directory to path
sys.path.append(str(Path(__file__).parent))

from diagnostic_logger import diagnostic_logger


def test_structured_logging():
    """Test structured logging with JSON output."""
    print("Testing structured logging with JSON output...")
    
    diagnostic_logger.set_phase("STRUCTURED_TEST")
    
    # Test info with context
    diagnostic_logger.info("Testing structured info logging", 
                          context={"test_type": "structured", "component": "logger", "data": {"key": "value"}})
    
    # Test warning with solution
    diagnostic_logger.warning("Testing structured warning logging", 
                             context={"severity": "medium", "component": "test"},
                             suggested_solution="This is a test warning - no action needed")
    
    # Test error with exception
    try:
        raise ValueError("Structured test exception")
    except Exception as e:
        diagnostic_logger.error("Testing structured error logging", 
                               context={"error_type": "test", "component": "exception_handler"},
                               exception=e,
                               suggested_solution="This is a test error - no action needed")
    
    diagnostic_logger.success("Structured logging test completed")
    
    # Check if JSON file was created
    json_file = Path("app/logs/orchestrator_structured.jsonl")
    if json_file.exists():
        print(f"✓ JSON log file created: {json_file}")
        print(f"  File size: {json_file.stat().st_size} bytes")
        
        # Read and display last few lines
        with open(json_file, 'r') as f:
            lines = f.readlines()
            print(f"  Total log entries: {len(lines)}")
            if lines:
                print("  Last entry:")
                print(f"    {lines[-1].strip()}")
    else:
        print(f"❌ JSON log file not found: {json_file}")
    
    print("✓ Structured logging test completed")


if __name__ == "__main__":
    print("🔍 STRUCTURED LOGGING TEST")
    print("=" * 40)
    
    try:
        test_structured_logging()
        print("\n🎉 Test completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
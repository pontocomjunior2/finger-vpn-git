#!/usr/bin/env python3
"""
Simple test to verify graceful degradation when optional modules are missing.
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

def test_missing_enhanced_orchestrator():
    """Test behavior when enhanced_orchestrator is missing."""
    print("Testing graceful degradation when enhanced_orchestrator is missing...")
    
    # Temporarily rename the enhanced_orchestrator.py file
    enhanced_file = Path("enhanced_orchestrator.py")
    backup_file = Path("enhanced_orchestrator.py.backup")
    
    if enhanced_file.exists():
        shutil.move(str(enhanced_file), str(backup_file))
        print("Temporarily moved enhanced_orchestrator.py")
    
    try:
        # Import orchestrator module
        if 'orchestrator' in sys.modules:
            del sys.modules['orchestrator']
        
        import orchestrator
        
        # Check that enhanced orchestrator is marked as unavailable
        assert not orchestrator.HAS_SMART_BALANCER, "Enhanced orchestrator should be unavailable"
        print("✓ Enhanced orchestrator correctly marked as unavailable")
        
        # Check that the system can still initialize
        orch = orchestrator.StreamOrchestrator()
        assert orch.enhanced_orchestrator is None, "Enhanced orchestrator should be None"
        print("✓ StreamOrchestrator initialized successfully without enhanced orchestrator")
        
        # Check module status
        status = orch.get_optional_modules_status()
        assert not status["modules"]["enhanced_orchestrator"]["available"], "Enhanced orchestrator should be unavailable in status"
        assert not status["functionality"]["smart_load_balancing"], "Smart load balancing should be disabled"
        assert status["functionality"]["basic_orchestration"], "Basic orchestration should still work"
        print("✓ Module status correctly reflects missing enhanced orchestrator")
        
        print("✓ All tests passed - graceful degradation working correctly")
        
    finally:
        # Restore the file
        if backup_file.exists():
            shutil.move(str(backup_file), str(enhanced_file))
            print("Restored enhanced_orchestrator.py")

def test_missing_resilient_orchestrator():
    """Test behavior when resilient_orchestrator is missing."""
    print("\nTesting graceful degradation when resilient_orchestrator is missing...")
    
    # Temporarily rename the resilient_orchestrator.py file
    resilient_file = Path("resilient_orchestrator.py")
    backup_file = Path("resilient_orchestrator.py.backup")
    
    if resilient_file.exists():
        shutil.move(str(resilient_file), str(backup_file))
        print("Temporarily moved resilient_orchestrator.py")
    
    try:
        # Clear module cache
        modules_to_clear = [name for name in sys.modules.keys() if 'orchestrator' in name or 'resilient' in name]
        for module_name in modules_to_clear:
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        import orchestrator
        
        # Check that resilient orchestrator is marked as unavailable
        assert not orchestrator.HAS_RESILIENT_ORCHESTRATOR, "Resilient orchestrator should be unavailable"
        print("✓ Resilient orchestrator correctly marked as unavailable")
        
        # Check that the system can still initialize
        orch = orchestrator.StreamOrchestrator()
        assert orch.resilient_orchestrator is None, "Resilient orchestrator should be None"
        print("✓ StreamOrchestrator initialized successfully without resilient orchestrator")
        
        # Check module status
        status = orch.get_optional_modules_status()
        assert not status["modules"]["resilient_orchestrator"]["available"], "Resilient orchestrator should be unavailable in status"
        assert not status["functionality"]["enhanced_failure_handling"], "Enhanced failure handling should be disabled"
        assert status["functionality"]["basic_orchestration"], "Basic orchestration should still work"
        print("✓ Module status correctly reflects missing resilient orchestrator")
        
        print("✓ All tests passed - graceful degradation working correctly")
        
    finally:
        # Restore the file
        if backup_file.exists():
            shutil.move(str(backup_file), str(resilient_file))
            print("Restored resilient_orchestrator.py")

if __name__ == "__main__":
    print("Testing optional module loading with graceful degradation...")
    print("=" * 60)
    
    try:
        test_missing_enhanced_orchestrator()
        test_missing_resilient_orchestrator()
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED - Graceful degradation is working correctly!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
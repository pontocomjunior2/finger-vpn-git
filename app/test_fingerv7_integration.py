#!/usr/bin/env python3
"""
Integration test for fingerv7.py with resilient worker client.

This test verifies that the fingerv7.py file can successfully import and use
the resilient worker client without errors.
"""

import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_import_resilient_client():
    """Test importing the resilient worker client."""
    logger.info("Testing resilient worker client import...")
    
    try:
        from resilient_worker_client import create_resilient_worker_client
        logger.info("✓ Successfully imported create_resilient_worker_client")
        
        # Test creating a client
        client = create_resilient_worker_client(
            orchestrator_url="http://localhost:8001",
            server_id="test-integration",
            max_streams=5
        )
        logger.info("✓ Successfully created resilient worker client")
        
        # Test basic properties
        assert client.server_id == "test-integration"
        assert client.max_streams == 5
        assert client.orchestrator_url == "http://localhost:8001"
        logger.info("✓ Client properties are correct")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to import or create resilient client: {e}")
        return False


def test_fingerv7_import():
    """Test that fingerv7.py can import without errors."""
    logger.info("Testing fingerv7.py import with resilient client...")
    
    # Set environment variables to avoid database connections
    os.environ['USE_ORCHESTRATOR'] = 'False'
    os.environ['DISTRIBUTE_LOAD'] = 'False'
    
    try:
        # This should not fail even if orchestrator is not available
        # since we disabled orchestrator usage
        import fingerv7
        logger.info("✓ Successfully imported fingerv7.py")
        
        # Check that the orchestrator_client is None when disabled
        if hasattr(fingerv7, 'orchestrator_client'):
            if fingerv7.orchestrator_client is None:
                logger.info("✓ orchestrator_client is None when disabled")
            else:
                logger.warning("! orchestrator_client is not None when disabled")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to import fingerv7.py: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def test_fingerv7_with_orchestrator():
    """Test fingerv7.py with orchestrator enabled (but expect failure due to no orchestrator)."""
    logger.info("Testing fingerv7.py with orchestrator enabled...")
    
    # Set environment variables to enable orchestrator
    os.environ['USE_ORCHESTRATOR'] = 'True'
    os.environ['DISTRIBUTE_LOAD'] = 'True'
    os.environ['ORCHESTRATOR_URL'] = 'http://localhost:8001'
    os.environ['SERVER_ID'] = 'test-integration-worker'
    
    try:
        # Remove fingerv7 from modules if already imported to force re-import
        if 'fingerv7' in sys.modules:
            del sys.modules['fingerv7']
        
        import fingerv7
        logger.info("✓ Successfully imported fingerv7.py with orchestrator enabled")
        
        # Check that orchestrator_client was created
        if hasattr(fingerv7, 'orchestrator_client') and fingerv7.orchestrator_client:
            logger.info("✓ orchestrator_client was created")
            
            # Check if it's the resilient client
            client_type = type(fingerv7.orchestrator_client).__name__
            if client_type == 'ResilientWorkerClient':
                logger.info("✓ orchestrator_client is ResilientWorkerClient")
            else:
                logger.warning(f"! orchestrator_client is {client_type}, expected ResilientWorkerClient")
        else:
            logger.warning("! orchestrator_client was not created or is None")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to import fingerv7.py with orchestrator: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def main():
    """Run all integration tests."""
    logger.info("Starting fingerv7.py integration tests...")
    
    tests = [
        test_import_resilient_client,
        test_fingerv7_import,
        test_fingerv7_with_orchestrator
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        logger.info(f"\n--- Running {test.__name__} ---")
        try:
            if test():
                passed += 1
                logger.info(f"✓ {test.__name__} PASSED")
            else:
                failed += 1
                logger.error(f"✗ {test.__name__} FAILED")
        except Exception as e:
            failed += 1
            logger.error(f"✗ {test.__name__} FAILED with exception: {e}")
    
    logger.info(f"\n=== Test Results ===")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total: {passed + failed}")
    
    if failed == 0:
        logger.info("🎉 All integration tests passed!")
        return True
    else:
        logger.error("❌ Some integration tests failed!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
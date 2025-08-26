#!/usr/bin/env python3
"""
Simple Integration Test

A basic test to verify that all components can be imported and initialized.
"""

import asyncio
import logging
import os
import sys

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

async def test_basic_integration():
    """Test basic integration of all components"""
    try:
        # Test imports
        logger.info("Testing component imports...")
        
        from integration_system import (EndToEndTestSuite,
                                        IntegratedOrchestrator,
                                        IntegrationStatus)
        logger.info("✓ Integration system imported successfully")
        
        # Test database configuration
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'orchestrator'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
        
        # Test orchestrator creation
        logger.info("Testing orchestrator creation...")
        orchestrator = IntegratedOrchestrator(db_config)
        logger.info("✓ Integrated orchestrator created successfully")
        
        # Test component initialization (without starting)
        logger.info("Testing component initialization...")
        success = await orchestrator.initialize_components()
        
        if success:
            logger.info("✓ All components initialized successfully")
            logger.info(f"Components health: {orchestrator.component_health}")
            logger.info(f"Healthy components: {orchestrator.metrics.components_healthy}/{orchestrator.metrics.components_total}")
        else:
            logger.error("✗ Component initialization failed")
            return False
        
        # Test system status (without starting background tasks)
        logger.info("Testing system status...")
        status = await orchestrator.get_system_status()
        logger.info(f"✓ System status retrieved: {status['status']}")
        
        logger.info("✓ Basic integration test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Basic integration test failed: {e}")
        return False

async def main():
    """Main test function"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting basic integration test")
    
    success = await test_basic_integration()
    
    if success:
        logger.info("Basic integration test PASSED")
        return 0
    else:
        logger.error("Basic integration test FAILED")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
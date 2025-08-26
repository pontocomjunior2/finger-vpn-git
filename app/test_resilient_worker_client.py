#!/usr/bin/env python3
"""
Test script for the resilient worker client implementation.

This script tests the circuit breaker, retry logic, and local operation mode
of the resilient worker client.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resilient_worker_client import (CircuitBreakerConfig,
                                     ResilientWorkerClient, RetryConfig,
                                     create_resilient_worker_client)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


async def test_circuit_breaker():
    """Test circuit breaker functionality."""
    logger.info("=== Testing Circuit Breaker ===")
    
    # Create client with aggressive circuit breaker settings for testing
    client = create_resilient_worker_client(
        orchestrator_url="http://invalid-url:9999",  # Invalid URL to trigger failures
        server_id="test-worker-1",
        max_streams=5,
        circuit_failure_threshold=3,  # Open after 3 failures
        circuit_recovery_timeout=10,  # Test recovery after 10 seconds
        retry_max_attempts=2,  # Reduce retries for faster testing
        retry_base_delay=0.5
    )
    
    logger.info("Testing circuit breaker with invalid orchestrator URL...")
    
    # Test multiple failures to trigger circuit breaker
    for i in range(5):
        try:
            logger.info(f"Attempt {i+1}: Trying to register...")
            success = await client.register()
            logger.info(f"Registration result: {success}")
        except Exception as e:
            logger.info(f"Registration failed as expected: {e}")
        
        # Check circuit breaker stats
        stats = client.circuit_breaker.get_stats()
        logger.info(f"Circuit breaker state: {stats['state']}")
        
        await asyncio.sleep(1)
    
    # Test local mode activation
    logger.info("Testing local mode...")
    health = await client.health_check()
    logger.info(f"Health check: {health}")
    
    # Test stream operations in local mode
    logger.info("Testing stream operations in local mode...")
    streams = await client.request_streams(3)
    logger.info(f"Requested streams (local mode): {streams}")
    
    # Test stream processing check
    can_process = client.can_process_stream(1)
    logger.info(f"Can process stream 1: {can_process}")
    
    # Record stream processing
    client.record_stream_processing(1)
    logger.info("Recorded stream processing for stream 1")
    
    # Get detailed status
    status = client.get_detailed_status()
    logger.info(f"Detailed status: {status}")
    
    await client.shutdown()
    logger.info("Circuit breaker test completed")


async def test_retry_logic():
    """Test retry logic with exponential backoff."""
    logger.info("=== Testing Retry Logic ===")
    
    client = create_resilient_worker_client(
        orchestrator_url="http://localhost:8001",  # Assume orchestrator might be running
        server_id="test-worker-2",
        max_streams=10,
        retry_max_attempts=3,
        retry_base_delay=0.5
    )
    
    logger.info("Testing retry logic...")
    
    # Test registration (might succeed if orchestrator is running)
    try:
        success = await client.register()
        logger.info(f"Registration result: {success}")
        
        if success:
            # Test heartbeat
            heartbeat_success = await client.send_heartbeat()
            logger.info(f"Heartbeat result: {heartbeat_success}")
            
            # Test stream request
            streams = await client.request_streams(2)
            logger.info(f"Requested streams: {streams}")
            
            # Test stream release
            if streams:
                release_success = await client.release_streams(streams)
                logger.info(f"Stream release result: {release_success}")
        
    except Exception as e:
        logger.info(f"Operations failed as expected (no orchestrator): {e}")
    
    await client.shutdown()
    logger.info("Retry logic test completed")


async def test_local_operation_mode():
    """Test local operation mode functionality."""
    logger.info("=== Testing Local Operation Mode ===")
    
    client = ResilientWorkerClient(
        orchestrator_url="http://unreachable:9999",
        server_id="test-worker-3",
        max_streams=5
    )
    
    # Force local mode activation
    client._activate_local_mode()
    
    # Simulate some assigned streams
    client.local_state.assigned_streams = [1, 2, 3]
    client._save_local_state()
    
    logger.info("Testing local mode operations...")
    
    # Test stream operations in local mode
    streams = await client.request_streams()
    logger.info(f"Local mode streams: {streams}")
    
    # Test stream processing
    for stream_id in [1, 2, 3]:
        can_process = client.can_process_stream(stream_id)
        logger.info(f"Can process stream {stream_id}: {can_process}")
        
        if can_process:
            client.record_stream_processing(stream_id)
            logger.info(f"Recorded processing for stream {stream_id}")
    
    # Test stream release in local mode
    release_success = await client.release_streams([1, 2])
    logger.info(f"Local mode stream release: {release_success}")
    
    # Check health in local mode
    health = await client.health_check()
    logger.info(f"Local mode health: {health}")
    
    await client.shutdown()
    logger.info("Local operation mode test completed")


async def test_configuration_options():
    """Test different configuration options."""
    logger.info("=== Testing Configuration Options ===")
    
    # Test with custom circuit breaker config
    circuit_config = CircuitBreakerConfig(
        failure_threshold=2,
        recovery_timeout=5,
        success_threshold=2,
        timeout=15
    )
    
    # Test with custom retry config
    retry_config = RetryConfig(
        max_attempts=4,
        base_delay=0.25,
        max_delay=30.0,
        exponential_base=1.5,
        jitter=False
    )
    
    client = ResilientWorkerClient(
        orchestrator_url="http://localhost:8001",
        server_id="test-worker-4",
        max_streams=8,
        circuit_config=circuit_config,
        retry_config=retry_config
    )
    
    logger.info("Testing with custom configurations...")
    
    # Test operations with custom config
    try:
        success = await client.register()
        logger.info(f"Custom config registration: {success}")
    except Exception as e:
        logger.info(f"Custom config test failed as expected: {e}")
    
    # Check configuration in status
    status = client.get_detailed_status()
    config = status.get('configuration', {})
    logger.info(f"Circuit breaker config: {config.get('circuit_breaker')}")
    logger.info(f"Retry config: {config.get('retry')}")
    
    await client.shutdown()
    logger.info("Configuration options test completed")


async def main():
    """Run all tests."""
    logger.info("Starting resilient worker client tests...")
    logger.info(f"Test started at: {datetime.now()}")
    
    try:
        await test_circuit_breaker()
        await asyncio.sleep(2)
        
        await test_retry_logic()
        await asyncio.sleep(2)
        
        await test_local_operation_mode()
        await asyncio.sleep(2)
        
        await test_configuration_options()
        
        logger.info("All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    logger.info(f"Test completed at: {datetime.now()}")


if __name__ == "__main__":
    asyncio.run(main())
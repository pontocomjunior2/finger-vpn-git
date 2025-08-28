#!/usr/bin/env python3
"""
Demonstration of Resilient Orchestrator Features

This script demonstrates the enhanced resilient orchestrator functionality including:
- Robust heartbeat monitoring with configurable timeouts
- Emergency recovery procedures for critical system failures
- Graceful instance failure handling with automatic stream redistribution
- Circuit breaker pattern for database operations
- Comprehensive monitoring and alerting

Requirements: 1.2, 4.1, 5.2
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List

from resilient_config import get_environment_config_summary, load_resilient_config

# Import resilient orchestrator components
from resilient_orchestrator import (
    FailureRecoveryConfig,
    HeartbeatConfig,
    InstanceFailureInfo,
    InstanceStatus,
    ResilientOrchestrator,
    SystemHealthStatus,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ResilientOrchestratorDemo:
    """Demonstration class for resilient orchestrator features"""

    def __init__(self):
        # Mock database configuration for demo
        self.db_config = {
            "host": "localhost",
            "database": "demo_db",
            "user": "demo_user",
            "password": "demo_pass",
            "port": 5432,
        }

        # Create test configurations
        self.heartbeat_config = HeartbeatConfig(
            timeout_seconds=60,
            warning_threshold_seconds=30,
            max_missed_heartbeats=2,
            check_interval_seconds=10,
            emergency_threshold_seconds=120,
        )

        self.recovery_config = FailureRecoveryConfig(
            max_retry_attempts=3,
            retry_delay_seconds=2,
            exponential_backoff=True,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout_seconds=30,
            emergency_recovery_enabled=True,
        )

        self.orchestrator = None

    async def initialize_orchestrator(self):
        """Initialize the resilient orchestrator"""
        logger.info("Initializing resilient orchestrator for demo...")

        try:
            # Note: In real usage, this would connect to actual database
            # For demo purposes, we'll mock the database operations
            self.orchestrator = ResilientOrchestrator(
                self.db_config, self.heartbeat_config, self.recovery_config
            )

            logger.info("Resilient orchestrator initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            return False

    def demonstrate_configuration(self):
        """Demonstrate configuration management"""
        logger.info("=== Configuration Management Demo ===")

        # Show current configuration
        config_summary = get_environment_config_summary()
        logger.info("Current environment configuration:")
        logger.info(json.dumps(config_summary, indent=2))

        # Show heartbeat configuration
        logger.info(f"Heartbeat timeout: {self.heartbeat_config.timeout_seconds}s")
        logger.info(
            f"Warning threshold: {self.heartbeat_config.warning_threshold_seconds}s"
        )
        logger.info(
            f"Emergency threshold: {self.heartbeat_config.emergency_threshold_seconds}s"
        )

        # Show recovery configuration
        logger.info(f"Max retry attempts: {self.recovery_config.max_retry_attempts}")
        logger.info(
            f"Circuit breaker threshold: {self.recovery_config.circuit_breaker_threshold}"
        )
        logger.info(
            f"Emergency recovery enabled: {self.recovery_config.emergency_recovery_enabled}"
        )

    def demonstrate_circuit_breaker(self):
        """Demonstrate circuit breaker functionality"""
        logger.info("=== Circuit Breaker Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        service_key = "demo_service"

        # Test normal operation
        logger.info(
            f"Circuit breaker status for {service_key}: {'OPEN' if self.orchestrator._is_circuit_breaker_open(service_key) else 'CLOSED'}"
        )

        # Simulate failures
        logger.info("Simulating service failures...")
        for i in range(self.recovery_config.circuit_breaker_threshold + 1):
            self.orchestrator._record_circuit_breaker_failure(service_key)
            status = (
                "OPEN"
                if self.orchestrator._is_circuit_breaker_open(service_key)
                else "CLOSED"
            )
            logger.info(f"After failure {i+1}: Circuit breaker is {status}")

        # Test recovery
        logger.info("Simulating service recovery...")
        self.orchestrator._reset_circuit_breaker(service_key)
        status = (
            "OPEN"
            if self.orchestrator._is_circuit_breaker_open(service_key)
            else "CLOSED"
        )
        logger.info(f"After reset: Circuit breaker is {status}")

    async def demonstrate_heartbeat_monitoring(self):
        """Demonstrate heartbeat monitoring and failure detection"""
        logger.info("=== Heartbeat Monitoring Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        # Simulate instance heartbeats
        test_instances = ["server1", "server2", "server3"]

        logger.info("Simulating instance heartbeats...")
        for server_id in test_instances:
            self.orchestrator.instance_heartbeats[server_id] = datetime.now()
            logger.info(f"Heartbeat recorded for {server_id}")

        # Simulate heartbeat timeout for one instance
        logger.info("Simulating heartbeat timeout for server2...")
        timeout_time = datetime.now() - timedelta(
            seconds=self.heartbeat_config.timeout_seconds + 10
        )
        self.orchestrator.instance_heartbeats["server2"] = timeout_time

        # Show current heartbeat status
        current_time = datetime.now()
        for server_id, last_heartbeat in self.orchestrator.instance_heartbeats.items():
            age = (current_time - last_heartbeat).total_seconds()
            status = (
                "TIMEOUT" if age > self.heartbeat_config.timeout_seconds else "HEALTHY"
            )
            logger.info(f"{server_id}: Last heartbeat {age:.1f}s ago - {status}")

    async def demonstrate_failure_handling(self):
        """Demonstrate instance failure handling"""
        logger.info("=== Failure Handling Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        # Simulate instance failure
        server_id = "demo_server_1"
        current_streams = 5
        failure_reason = "Demo heartbeat timeout"

        logger.info(
            f"Simulating failure for {server_id} with {current_streams} streams..."
        )

        await self.orchestrator._handle_instance_heartbeat_failure(
            server_id, current_streams, failure_reason
        )

        # Check failure was recorded
        if server_id in self.orchestrator.failed_instances:
            failure_info = self.orchestrator.failed_instances[server_id]
            logger.info(f"Failure recorded: {failure_info.failure_reason}")
            logger.info(f"Streams affected: {failure_info.streams_affected}")
            logger.info(f"Recovery attempts: {failure_info.recovery_attempts}")
        else:
            logger.warning("Failure was not recorded properly")

    async def demonstrate_emergency_recovery(self):
        """Demonstrate emergency recovery procedures"""
        logger.info("=== Emergency Recovery Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        server_id = "emergency_server"
        reason = "Demo emergency failure"

        logger.info(f"Triggering emergency recovery for {server_id}...")

        # Note: In real implementation, this would perform actual database operations
        # For demo, we'll just show the process
        try:
            await self.orchestrator._execute_emergency_recovery(server_id, reason)
            logger.info("Emergency recovery completed successfully")
        except Exception as e:
            logger.error(f"Emergency recovery failed: {e}")

    async def demonstrate_system_health_monitoring(self):
        """Demonstrate system health monitoring"""
        logger.info("=== System Health Monitoring Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        # Show initial health status
        logger.info(
            f"Initial system health: {self.orchestrator.system_health_status.value}"
        )

        # Simulate health degradation
        logger.info("Simulating system health degradation...")
        self.orchestrator.system_health_status = SystemHealthStatus.DEGRADED
        logger.info(
            f"System health updated to: {self.orchestrator.system_health_status.value}"
        )

        # Add critical failure
        critical_failure = {
            "server_id": "critical_server",
            "failure_time": datetime.now(),
            "reason": "Demo critical failure",
            "streams_affected": 10,
            "severity": "critical",
        }
        self.orchestrator.critical_failures.append(critical_failure)
        logger.info("Critical failure added to system")

        # Show resilience status
        status = self.orchestrator.get_resilience_status()
        logger.info("Current resilience status:")
        logger.info(json.dumps(status, indent=2, default=str))

    async def demonstrate_recovery_attempts(self):
        """Demonstrate instance recovery attempts"""
        logger.info("=== Recovery Attempts Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        # Create a failed instance for recovery demo
        server_id = "recovery_demo_server"
        failure_info = InstanceFailureInfo(
            server_id=server_id,
            failure_time=datetime.now() - timedelta(minutes=5),
            failure_reason="Demo failure for recovery",
            streams_affected=3,
            recovery_attempts=0,
        )

        self.orchestrator.failed_instances[server_id] = failure_info
        logger.info(f"Created failed instance: {server_id}")

        # Simulate recovery attempts
        logger.info("Simulating recovery attempts...")
        for attempt in range(self.recovery_config.max_retry_attempts):
            failure_info.recovery_attempts += 1
            failure_info.last_recovery_attempt = datetime.now()

            # Calculate delay with exponential backoff
            delay = self.recovery_config.retry_delay_seconds
            if self.recovery_config.exponential_backoff:
                delay *= 2**attempt

            logger.info(f"Recovery attempt {attempt + 1}: delay = {delay}s")

            # Simulate recovery success on last attempt
            if attempt == self.recovery_config.max_retry_attempts - 1:
                del self.orchestrator.failed_instances[server_id]
                logger.info(f"Recovery successful for {server_id}")
                break

    async def demonstrate_monitoring_lifecycle(self):
        """Demonstrate monitoring lifecycle management"""
        logger.info("=== Monitoring Lifecycle Demo ===")

        if not self.orchestrator:
            logger.error("Orchestrator not initialized")
            return

        # Start monitoring
        logger.info("Starting resilient monitoring...")
        await self.orchestrator.start_monitoring()
        logger.info(f"Monitoring active: {self.orchestrator.monitoring_active}")
        logger.info(
            f"Active monitoring tasks: {len(self.orchestrator.monitoring_tasks)}"
        )

        # Let monitoring run for a short time
        logger.info("Letting monitoring run for 5 seconds...")
        await asyncio.sleep(5)

        # Stop monitoring
        logger.info("Stopping resilient monitoring...")
        await self.orchestrator.stop_monitoring()
        logger.info(f"Monitoring active: {self.orchestrator.monitoring_active}")
        logger.info(
            f"Active monitoring tasks: {len(self.orchestrator.monitoring_tasks)}"
        )

    async def run_complete_demo(self):
        """Run complete demonstration of all features"""
        logger.info("Starting Resilient Orchestrator Complete Demo")
        logger.info("=" * 60)

        # Initialize
        if not await self.initialize_orchestrator():
            logger.error("Failed to initialize orchestrator, aborting demo")
            return

        try:
            # Run all demonstrations
            self.demonstrate_configuration()
            await asyncio.sleep(1)

            self.demonstrate_circuit_breaker()
            await asyncio.sleep(1)

            await self.demonstrate_heartbeat_monitoring()
            await asyncio.sleep(1)

            await self.demonstrate_failure_handling()
            await asyncio.sleep(1)

            await self.demonstrate_emergency_recovery()
            await asyncio.sleep(1)

            await self.demonstrate_system_health_monitoring()
            await asyncio.sleep(1)

            await self.demonstrate_recovery_attempts()
            await asyncio.sleep(1)

            await self.demonstrate_monitoring_lifecycle()

            logger.info("=" * 60)
            logger.info("Resilient Orchestrator Demo Completed Successfully")

        except Exception as e:
            logger.error(f"Demo failed with error: {e}")
            raise


async def main():
    """Main demo function"""
    demo = ResilientOrchestratorDemo()
    await demo.run_complete_demo()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())

#!/usr/bin/env python3
"""
Resilient Orchestrator Service with Enhanced Failure Handling

This module provides enhanced orchestrator functionality with:
- Robust heartbeat monitoring with configurable timeouts
- Emergency recovery procedures for critical system failures
- Graceful instance failure handling with automatic stream redistribution
- Circuit breaker pattern for database operations
- Comprehensive error handling and retry logic

Requirements: 1.2, 4.1, 5.2
"""

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from fastapi import HTTPException

# Import enhanced components
try:
    from database_error_handler import DatabaseErrorHandler
    from enhanced_db_manager import EnhancedDatabaseManager
    from enhanced_orchestrator import EnhancedStreamOrchestrator
    from smart_load_balancer import RebalanceReason
    HAS_ENHANCED_COMPONENTS = True
except ImportError as e:
    HAS_ENHANCED_COMPONENTS = False
    logging.warning(f"Enhanced components not available: {e}")

logger = logging.getLogger(__name__)


class InstanceStatus(Enum):
    """Instance status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    RECOVERING = "recovering"
    MAINTENANCE = "maintenance"


class SystemHealthStatus(Enum):
    """System health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class HeartbeatConfig:
    """Configuration for heartbeat monitoring"""
    timeout_seconds: int = 300  # 5 minutes default
    warning_threshold_seconds: int = 120  # 2 minutes warning
    max_missed_heartbeats: int = 3
    check_interval_seconds: int = 30
    emergency_threshold_seconds: int = 600  # 10 minutes for emergency


@dataclass
class FailureRecoveryConfig:
    """Configuration for failure recovery procedures"""
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5
    exponential_backoff: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    emergency_recovery_enabled: bool = True


@dataclass
class InstanceFailureInfo:
    """Information about instance failure"""
    server_id: str
    failure_time: datetime
    failure_reason: str
    streams_affected: int
    recovery_attempts: int = 0
    last_recovery_attempt: Optional[datetime] = None


class ResilientOrchestrator:
    """
    Enhanced orchestrator with resilient operations and failure handling.
    
    This class provides:
    - Robust heartbeat monitoring with configurable timeouts
    - Emergency recovery procedures for critical system failures
    - Graceful instance failure handling with automatic redistribution
    - Circuit breaker pattern for database operations
    - Comprehensive monitoring and alerting
    """
    
    def __init__(self, db_config: Dict, heartbeat_config: Optional[HeartbeatConfig] = None,
                 recovery_config: Optional[FailureRecoveryConfig] = None):
        self.db_config = db_config
        self.heartbeat_config = heartbeat_config or HeartbeatConfig()
        self.recovery_config = recovery_config or FailureRecoveryConfig()
        
        # Initialize enhanced components if available
        if HAS_ENHANCED_COMPONENTS:
            try:
                self.enhanced_orchestrator = EnhancedStreamOrchestrator(db_config)
                self.db_manager = EnhancedDatabaseManager(db_config)
                self.error_handler = DatabaseErrorHandler()
                logger.info("Enhanced components initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize enhanced components: {e}")
                self.enhanced_orchestrator = None
                self.db_manager = None
                self.error_handler = None
        else:
            self.enhanced_orchestrator = None
            self.db_manager = None
            self.error_handler = None
        
        # Instance tracking
        self.active_instances: Dict[str, dict] = {}
        self.failed_instances: Dict[str, InstanceFailureInfo] = {}
        self.instance_heartbeats: Dict[str, datetime] = {}
        self.instance_failure_counts: Dict[str, int] = {}
        
        # System health monitoring
        self.system_health_status = SystemHealthStatus.HEALTHY
        self.last_health_check = datetime.now()
        self.critical_failures: List[dict] = []
        
        # Circuit breaker state
        self.circuit_breaker_state = {}
        self.circuit_breaker_failures = {}
        self.circuit_breaker_last_failure = {}
        
        # Background monitoring
        self.monitoring_active = False
        self.monitoring_tasks = []
        
        logger.info("Resilient orchestrator initialized with enhanced failure handling")
    
    def get_db_connection(self):
        """Get database connection with circuit breaker protection"""
        if self.db_manager:
            return self.db_manager.get_connection()
        
        # Fallback to basic connection with circuit breaker
        connection_key = "database"
        
        if self._is_circuit_breaker_open(connection_key):
            raise Exception("Database circuit breaker is open")
        
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.autocommit = True
            self._reset_circuit_breaker(connection_key)
            return conn
        except Exception as e:
            self._record_circuit_breaker_failure(connection_key)
            logger.error(f"Database connection failed: {e}")
            raise
    
    def _is_circuit_breaker_open(self, key: str) -> bool:
        """Check if circuit breaker is open for given key"""
        if key not in self.circuit_breaker_state:
            return False
        
        state = self.circuit_breaker_state[key]
        if state == "open":
            # Check if timeout has passed
            last_failure = self.circuit_breaker_last_failure.get(key)
            if last_failure:
                timeout_passed = (datetime.now() - last_failure).total_seconds() > \
                               self.recovery_config.circuit_breaker_timeout_seconds
                if timeout_passed:
                    self.circuit_breaker_state[key] = "half_open"
                    return False
            return True
        
        return False
    
    def _record_circuit_breaker_failure(self, key: str):
        """Record circuit breaker failure"""
        if key not in self.circuit_breaker_failures:
            self.circuit_breaker_failures[key] = 0
        
        self.circuit_breaker_failures[key] += 1
        self.circuit_breaker_last_failure[key] = datetime.now()
        
        if self.circuit_breaker_failures[key] >= self.recovery_config.circuit_breaker_threshold:
            self.circuit_breaker_state[key] = "open"
            logger.warning(f"Circuit breaker opened for {key} after {self.circuit_breaker_failures[key]} failures")
    
    def _reset_circuit_breaker(self, key: str):
        """Reset circuit breaker for successful operation"""
        if key in self.circuit_breaker_failures:
            self.circuit_breaker_failures[key] = 0
        if key in self.circuit_breaker_state:
            self.circuit_breaker_state[key] = "closed"
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        
        # Start heartbeat monitoring
        heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self.monitoring_tasks.append(heartbeat_task)
        
        # Start system health monitoring
        health_task = asyncio.create_task(self._system_health_monitor())
        self.monitoring_tasks.append(health_task)
        
        # Start failure recovery monitoring
        recovery_task = asyncio.create_task(self._failure_recovery_monitor())
        self.monitoring_tasks.append(recovery_task)
        
        logger.info("Resilient monitoring tasks started")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks"""
        self.monitoring_active = False
        
        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self.monitoring_tasks.clear()
        logger.info("Resilient monitoring tasks stopped")
    
    async def _heartbeat_monitor(self):
        """Monitor instance heartbeats and detect failures"""
        while self.monitoring_active:
            try:
                await self._check_instance_heartbeats()
                await asyncio.sleep(self.heartbeat_config.check_interval_seconds)
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)  # Short delay on error
    
    async def _check_instance_heartbeats(self):
        """Check all instance heartbeats and handle failures"""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            current_time = datetime.now()
            
            # Get all active instances with their last heartbeat
            cursor.execute("""
                SELECT server_id, last_heartbeat, current_streams, status
                FROM orchestrator_instances 
                WHERE status IN ('active', 'recovering')
            """)
            
            instances = cursor.fetchall()
            
            for instance in instances:
                server_id = instance['server_id']
                last_heartbeat = instance['last_heartbeat']
                current_streams = instance['current_streams']
                status = instance['status']
                
                if not last_heartbeat:
                    continue
                
                # Calculate time since last heartbeat
                heartbeat_age = (current_time - last_heartbeat).total_seconds()
                
                # Check for different severity levels
                if heartbeat_age > self.heartbeat_config.emergency_threshold_seconds:
                    # Emergency threshold - immediate action required
                    await self._handle_emergency_instance_failure(server_id, current_streams, 
                                                                "Emergency heartbeat timeout")
                
                elif heartbeat_age > self.heartbeat_config.timeout_seconds:
                    # Standard timeout - mark as failed and redistribute
                    await self._handle_instance_heartbeat_failure(server_id, current_streams,
                                                                "Heartbeat timeout")
                
                elif heartbeat_age > self.heartbeat_config.warning_threshold_seconds:
                    # Warning threshold - log warning but don't take action yet
                    logger.warning(f"Instance {server_id} heartbeat delayed: {heartbeat_age:.1f}s")
                    
                    # Update instance status to indicate warning
                    if status == 'active':
                        cursor.execute("""
                            UPDATE orchestrator_instances 
                            SET status = 'recovering'
                            WHERE server_id = %s
                        """, (server_id,))
        
        except Exception as e:
            logger.error(f"Error checking instance heartbeats: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def _handle_instance_heartbeat_failure(self, server_id: str, current_streams: int, reason: str):
        """Handle instance failure due to heartbeat timeout"""
        logger.warning(f"Handling heartbeat failure for instance {server_id}: {reason}")
        
        # Record failure information
        failure_info = InstanceFailureInfo(
            server_id=server_id,
            failure_time=datetime.now(),
            failure_reason=reason,
            streams_affected=current_streams
        )
        self.failed_instances[server_id] = failure_info
        
        # Increment failure count
        if server_id not in self.instance_failure_counts:
            self.instance_failure_counts[server_id] = 0
        self.instance_failure_counts[server_id] += 1
        
        # Handle the failure gracefully
        await self._graceful_instance_failure_handling(server_id, reason)
    
    async def _handle_emergency_instance_failure(self, server_id: str, current_streams: int, reason: str):
        """Handle emergency instance failure with immediate action"""
        logger.error(f"Emergency instance failure detected: {server_id} - {reason}")
        
        # Record as critical failure
        critical_failure = {
            "server_id": server_id,
            "failure_time": datetime.now(),
            "reason": reason,
            "streams_affected": current_streams,
            "severity": "emergency"
        }
        self.critical_failures.append(critical_failure)
        
        # Update system health status
        self.system_health_status = SystemHealthStatus.EMERGENCY
        
        # Execute emergency recovery
        if self.recovery_config.emergency_recovery_enabled:
            await self._execute_emergency_recovery(server_id, reason)
        else:
            await self._graceful_instance_failure_handling(server_id, reason)
    
    async def _graceful_instance_failure_handling(self, server_id: str, reason: str):
        """
        Gracefully handle instance failure with automatic stream redistribution.
        
        This implements requirement 1.2: automatic stream redistribution when instances disconnect.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            logger.info(f"Starting graceful failure handling for instance {server_id}")
            
            # Mark instance as failed
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET status = 'failed', current_streams = 0
                WHERE server_id = %s
            """, (server_id,))
            
            # Get orphaned streams
            cursor.execute("""
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND status = 'active'
            """, (server_id,))
            
            orphaned_streams = [row[0] for row in cursor.fetchall()]
            
            if not orphaned_streams:
                logger.info(f"No orphaned streams found for failed instance {server_id}")
                return
            
            logger.info(f"Found {len(orphaned_streams)} orphaned streams from {server_id}")
            
            # Use enhanced orchestrator for smart redistribution if available
            if self.enhanced_orchestrator:
                try:
                    result = self.enhanced_orchestrator.handle_instance_failure(server_id)
                    if result.success:
                        logger.info(f"Smart redistribution completed: {result.streams_moved} streams moved")
                        return
                    else:
                        logger.warning(f"Smart redistribution failed: {result.error_message}")
                        # Fall back to basic redistribution
                except Exception as e:
                    logger.error(f"Error in smart redistribution: {e}")
            
            # Basic redistribution as fallback
            await self._basic_stream_redistribution(cursor, orphaned_streams, server_id)
            
        except Exception as e:
            logger.error(f"Error in graceful failure handling: {e}")
            # Try emergency recovery as last resort
            if self.recovery_config.emergency_recovery_enabled:
                await self._execute_emergency_recovery(server_id, f"Graceful handling failed: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def _basic_stream_redistribution(self, cursor, orphaned_streams: List[int], failed_server_id: str):
        """Basic stream redistribution algorithm"""
        # Get active instances with available capacity
        cursor.execute("""
            SELECT server_id, current_streams, max_streams
            FROM orchestrator_instances 
            WHERE status = 'active' 
              AND server_id != %s
              AND current_streams < max_streams
            ORDER BY current_streams ASC
        """, (failed_server_id,))
        
        available_instances = cursor.fetchall()
        
        if not available_instances:
            logger.error("No available instances for stream redistribution")
            return
        
        # Remove orphaned assignments
        cursor.execute("""
            DELETE FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
        """, (failed_server_id,))
        
        # Distribute streams round-robin to available instances
        assignments = []
        instance_index = 0
        
        for stream_id in orphaned_streams:
            # Find next instance with capacity
            attempts = 0
            while attempts < len(available_instances):
                instance = available_instances[instance_index]
                server_id, current_streams, max_streams = instance
                
                if current_streams < max_streams:
                    assignments.append((stream_id, server_id))
                    # Update local tracking
                    available_instances[instance_index] = (server_id, current_streams + 1, max_streams)
                    break
                
                instance_index = (instance_index + 1) % len(available_instances)
                attempts += 1
            
            if attempts >= len(available_instances):
                logger.warning(f"No capacity available for stream {stream_id}")
                break
            
            instance_index = (instance_index + 1) % len(available_instances)
        
        # Execute assignments
        if assignments:
            cursor.executemany("""
                INSERT INTO orchestrator_stream_assignments 
                (stream_id, server_id, assigned_at, status)
                VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
            """, assignments)
            
            # Update instance stream counts
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = (
                    SELECT COUNT(*) 
                    FROM orchestrator_stream_assignments 
                    WHERE server_id = orchestrator_instances.server_id 
                      AND status = 'active'
                )
                WHERE status = 'active'
            """)
            
            logger.info(f"Redistributed {len(assignments)} streams to {len(set(a[1] for a in assignments))} instances")
    
    async def _execute_emergency_recovery(self, server_id: str, reason: str):
        """
        Execute emergency recovery procedures for critical system failures.
        
        This implements requirement 5.2: emergency recovery procedures.
        """
        logger.error(f"Executing emergency recovery for {server_id}: {reason}")
        
        recovery_steps = [
            ("Force release all streams", self._emergency_force_release_streams),
            ("Redistribute to healthy instances", self._emergency_redistribute_streams),
            ("Verify system consistency", self._emergency_verify_consistency),
            ("Reset failed instance state", self._emergency_reset_instance_state)
        ]
        
        for step_name, step_func in recovery_steps:
            try:
                logger.info(f"Emergency recovery step: {step_name}")
                await step_func(server_id)
                logger.info(f"Emergency recovery step completed: {step_name}")
            except Exception as e:
                logger.error(f"Emergency recovery step failed: {step_name} - {e}")
                # Continue with next step even if one fails
        
        logger.info(f"Emergency recovery completed for {server_id}")
    
    async def _emergency_force_release_streams(self, server_id: str):
        """Force release all streams from failed instance"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Force delete all assignments for the failed instance
            cursor.execute("""
                DELETE FROM orchestrator_stream_assignments 
                WHERE server_id = %s
            """, (server_id,))
            
            deleted_count = cursor.rowcount
            logger.info(f"Force released {deleted_count} streams from {server_id}")
            
        finally:
            cursor.close()
            conn.close()
    
    async def _emergency_redistribute_streams(self, server_id: str):
        """Emergency redistribution of available streams"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get all unassigned streams
            cursor.execute("""
                SELECT id FROM streams 
                WHERE id NOT IN (
                    SELECT stream_id FROM orchestrator_stream_assignments 
                    WHERE status = 'active'
                )
                LIMIT 100
            """)
            
            unassigned_streams = [row[0] for row in cursor.fetchall()]
            
            if unassigned_streams:
                await self._basic_stream_redistribution(cursor, unassigned_streams, server_id)
            
        finally:
            cursor.close()
            conn.close()
    
    async def _emergency_verify_consistency(self, server_id: str):
        """Verify system consistency after emergency recovery"""
        if self.enhanced_orchestrator:
            try:
                consistency_report = self.enhanced_orchestrator.verify_system_consistency()
                if not consistency_report.get("consistent", False):
                    logger.warning(f"System inconsistency detected after emergency recovery: {consistency_report}")
                else:
                    logger.info("System consistency verified after emergency recovery")
            except Exception as e:
                logger.error(f"Error verifying system consistency: {e}")
    
    async def _emergency_reset_instance_state(self, server_id: str):
        """Reset failed instance state for potential recovery"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = 0, status = 'failed'
                WHERE server_id = %s
            """, (server_id,))
            
            logger.info(f"Reset instance state for {server_id}")
            
        finally:
            cursor.close()
            conn.close()
    
    async def _system_health_monitor(self):
        """Monitor overall system health"""
        while self.monitoring_active:
            try:
                await self._check_system_health()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in system health monitor: {e}")
                await asyncio.sleep(10)
    
    async def _check_system_health(self):
        """Check overall system health and update status"""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Get system statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_instances,
                    COUNT(*) FILTER (WHERE status = 'active') as active_instances,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_instances,
                    COALESCE(SUM(current_streams), 0) as total_streams,
                    COALESCE(SUM(max_streams), 0) as total_capacity
                FROM orchestrator_instances
            """)
            
            stats = cursor.fetchone()
            
            # Determine health status
            active_ratio = stats['active_instances'] / max(stats['total_instances'], 1)
            capacity_utilization = stats['total_streams'] / max(stats['total_capacity'], 1)
            
            previous_status = self.system_health_status
            
            if active_ratio < 0.5:  # Less than 50% instances active
                self.system_health_status = SystemHealthStatus.CRITICAL
            elif active_ratio < 0.8 or capacity_utilization > 0.9:  # Less than 80% active or over 90% capacity
                self.system_health_status = SystemHealthStatus.DEGRADED
            elif len(self.critical_failures) > 0:
                # Clear old critical failures (older than 1 hour)
                cutoff_time = datetime.now() - timedelta(hours=1)
                self.critical_failures = [f for f in self.critical_failures if f['failure_time'] > cutoff_time]
                
                if len(self.critical_failures) > 0:
                    self.system_health_status = SystemHealthStatus.DEGRADED
                else:
                    self.system_health_status = SystemHealthStatus.HEALTHY
            else:
                self.system_health_status = SystemHealthStatus.HEALTHY
            
            # Log status changes
            if self.system_health_status != previous_status:
                logger.info(f"System health status changed: {previous_status.value} -> {self.system_health_status.value}")
            
            self.last_health_check = datetime.now()
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            self.system_health_status = SystemHealthStatus.CRITICAL
        finally:
            cursor.close()
            conn.close()
    
    async def _failure_recovery_monitor(self):
        """Monitor and attempt recovery of failed instances"""
        while self.monitoring_active:
            try:
                await self._attempt_instance_recovery()
                await asyncio.sleep(120)  # Check every 2 minutes
            except Exception as e:
                logger.error(f"Error in failure recovery monitor: {e}")
                await asyncio.sleep(30)
    
    async def _attempt_instance_recovery(self):
        """Attempt to recover failed instances"""
        current_time = datetime.now()
        
        for server_id, failure_info in list(self.failed_instances.items()):
            # Skip if too many recovery attempts
            if failure_info.recovery_attempts >= self.recovery_config.max_retry_attempts:
                continue
            
            # Check if enough time has passed since last attempt
            if failure_info.last_recovery_attempt:
                time_since_attempt = (current_time - failure_info.last_recovery_attempt).total_seconds()
                min_delay = self.recovery_config.retry_delay_seconds
                
                if self.recovery_config.exponential_backoff:
                    min_delay *= (2 ** failure_info.recovery_attempts)
                
                if time_since_attempt < min_delay:
                    continue
            
            # Attempt recovery
            logger.info(f"Attempting recovery for failed instance {server_id} (attempt {failure_info.recovery_attempts + 1})")
            
            success = await self._try_instance_recovery(server_id, failure_info)
            
            failure_info.recovery_attempts += 1
            failure_info.last_recovery_attempt = current_time
            
            if success:
                logger.info(f"Successfully recovered instance {server_id}")
                del self.failed_instances[server_id]
                # Reset failure count on successful recovery
                if server_id in self.instance_failure_counts:
                    self.instance_failure_counts[server_id] = 0
            else:
                logger.warning(f"Recovery attempt failed for instance {server_id}")
    
    async def _try_instance_recovery(self, server_id: str, failure_info: InstanceFailureInfo) -> bool:
        """Try to recover a specific failed instance"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if instance has sent recent heartbeat (indicating it's back online)
            cursor.execute("""
                SELECT last_heartbeat, status 
                FROM orchestrator_instances 
                WHERE server_id = %s
            """, (server_id,))
            
            result = cursor.fetchone()
            if not result:
                return False
            
            last_heartbeat, status = result
            
            if last_heartbeat:
                time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()
                
                # If recent heartbeat, mark as recovering
                if time_since_heartbeat < self.heartbeat_config.timeout_seconds:
                    cursor.execute("""
                        UPDATE orchestrator_instances 
                        SET status = 'recovering'
                        WHERE server_id = %s
                    """, (server_id,))
                    
                    logger.info(f"Instance {server_id} showing signs of recovery (recent heartbeat)")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error attempting recovery for {server_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_resilience_status(self) -> Dict:
        """Get comprehensive resilience and health status"""
        return {
            "system_health": self.system_health_status.value,
            "last_health_check": self.last_health_check.isoformat(),
            "monitoring_active": self.monitoring_active,
            "heartbeat_config": {
                "timeout_seconds": self.heartbeat_config.timeout_seconds,
                "warning_threshold_seconds": self.heartbeat_config.warning_threshold_seconds,
                "check_interval_seconds": self.heartbeat_config.check_interval_seconds
            },
            "active_instances": len(self.active_instances),
            "failed_instances": len(self.failed_instances),
            "critical_failures": len(self.critical_failures),
            "circuit_breaker_states": dict(self.circuit_breaker_state),
            "instance_failure_counts": dict(self.instance_failure_counts),
            "failed_instance_details": [
                {
                    "server_id": info.server_id,
                    "failure_time": info.failure_time.isoformat(),
                    "failure_reason": info.failure_reason,
                    "streams_affected": info.streams_affected,
                    "recovery_attempts": info.recovery_attempts
                }
                for info in self.failed_instances.values()
            ]
        }
    
    async def force_instance_recovery(self, server_id: str) -> Dict:
        """Force recovery attempt for a specific instance"""
        if server_id in self.failed_instances:
            failure_info = self.failed_instances[server_id]
            success = await self._try_instance_recovery(server_id, failure_info)
            
            if success:
                del self.failed_instances[server_id]
                return {"status": "success", "message": f"Instance {server_id} recovery successful"}
            else:
                return {"status": "failed", "message": f"Instance {server_id} recovery failed"}
        else:
            return {"status": "not_found", "message": f"Instance {server_id} not in failed state"}
    
    async def trigger_emergency_recovery(self, server_id: str, reason: str = "Manual trigger") -> Dict:
        """Manually trigger emergency recovery for an instance"""
        try:
            await self._execute_emergency_recovery(server_id, reason)
            return {"status": "success", "message": f"Emergency recovery completed for {server_id}"}
        except Exception as e:
            logger.error(f"Manual emergency recovery failed: {e}")
            return {"status": "error", "message": f"Emergency recovery failed: {e}"}
#!/usr/bin/env python3
"""
Monitoring Integration Module

This module integrates the monitoring system with existing orchestrator and worker components,
providing seamless monitoring capabilities across the entire system.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from monitoring_system import (AlertSeverity, FailureEvent, MonitoringSystem,
                               create_monitoring_system)

logger = logging.getLogger(__name__)


class MonitoredOperation:
    """Context manager for monitoring operations"""
    
    def __init__(self, monitoring_system: MonitoringSystem, operation_name: str):
        self.monitoring_system = monitoring_system
        self.operation_name = operation_name
        self.operation_id = None
        self.start_time = None
    
    def __enter__(self):
        self.operation_id = self.monitoring_system.record_operation_start(self.operation_name)
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        success = exc_type is None
        if self.operation_id:
            self.monitoring_system.record_operation_end(self.operation_id, success)
        
        # Record failure if exception occurred
        if not success and exc_type:
            self.monitoring_system.record_failure(
                source=self.operation_name,
                failure_type=exc_type.__name__,
                severity=AlertSeverity.WARNING,
                metadata={
                    'exception': str(exc_val),
                    'duration_ms': (time.time() - self.start_time) * 1000 if self.start_time else 0
                }
            )


@asynccontextmanager
async def monitored_async_operation(monitoring_system: MonitoringSystem, operation_name: str):
    """Async context manager for monitoring operations"""
    operation_id = monitoring_system.record_operation_start(operation_name)
    start_time = time.time()
    
    try:
        yield
        monitoring_system.record_operation_end(operation_id, success=True)
    except Exception as e:
        monitoring_system.record_operation_end(operation_id, success=False)
        monitoring_system.record_failure(
            source=operation_name,
            failure_type=type(e).__name__,
            severity=AlertSeverity.WARNING,
            metadata={
                'exception': str(e),
                'duration_ms': (time.time() - start_time) * 1000
            }
        )
        raise


class OrchestratorMonitoringMixin:
    """Mixin to add monitoring capabilities to orchestrator classes"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitoring_system: Optional[MonitoringSystem] = None
        self._monitoring_initialized = False
    
    def initialize_monitoring(self, db_config: Optional[Dict] = None):
        """Initialize monitoring system"""
        if not self._monitoring_initialized:
            self.monitoring_system = create_monitoring_system(db_config)
            self._monitoring_initialized = True
            logger.info("Orchestrator monitoring initialized")
    
    async def start_monitoring(self):
        """Start monitoring tasks"""
        if self.monitoring_system:
            await self.monitoring_system.start_monitoring()
    
    async def stop_monitoring(self):
        """Stop monitoring tasks"""
        if self.monitoring_system:
            await self.monitoring_system.stop_monitoring()
    
    def monitor_operation(self, operation_name: str):
        """Get monitored operation context manager"""
        if self.monitoring_system:
            return MonitoredOperation(self.monitoring_system, operation_name)
        else:
            return DummyMonitoredOperation()
    
    def record_instance_failure(self, server_id: str, failure_reason: str, streams_affected: int = 0):
        """Record instance failure for monitoring"""
        if self.monitoring_system:
            self.monitoring_system.record_failure(
                source=f"instance_{server_id}",
                failure_type="instance_failure",
                severity=AlertSeverity.CRITICAL,
                metadata={
                    'server_id': server_id,
                    'failure_reason': failure_reason,
                    'streams_affected': streams_affected,
                    'timestamp': datetime.now().isoformat()
                }
            )
    
    def record_heartbeat_failure(self, server_id: str, last_heartbeat: datetime, timeout_seconds: int):
        """Record heartbeat failure for monitoring"""
        if self.monitoring_system:
            age_seconds = (datetime.now() - last_heartbeat).total_seconds()
            self.monitoring_system.record_failure(
                source=f"heartbeat_{server_id}",
                failure_type="heartbeat_timeout",
                severity=AlertSeverity.WARNING if age_seconds < timeout_seconds * 2 else AlertSeverity.CRITICAL,
                metadata={
                    'server_id': server_id,
                    'last_heartbeat': last_heartbeat.isoformat(),
                    'age_seconds': age_seconds,
                    'timeout_seconds': timeout_seconds
                }
            )
    
    def record_rebalancing_event(self, reason: str, streams_moved: int, instances_affected: List[str]):
        """Record rebalancing event for monitoring"""
        if self.monitoring_system:
            # Record as info-level event
            self.monitoring_system.alert_manager.create_alert(
                severity=AlertSeverity.INFO,
                title="Stream Rebalancing Executed",
                description=f"Rebalanced {streams_moved} streams across {len(instances_affected)} instances. Reason: {reason}",
                source="rebalancer",
                metadata={
                    'reason': reason,
                    'streams_moved': streams_moved,
                    'instances_affected': instances_affected,
                    'timestamp': datetime.now().isoformat()
                }
            )
    
    def record_database_operation(self, operation: str, duration_ms: float, success: bool, error: Optional[str] = None):
        """Record database operation metrics"""
        if self.monitoring_system:
            self.monitoring_system.metrics_collector.record_response_time(f"db_{operation}", duration_ms)
            
            if not success and error:
                self.monitoring_system.record_failure(
                    source="database",
                    failure_type=f"db_{operation}_error",
                    severity=AlertSeverity.WARNING,
                    metadata={
                        'operation': operation,
                        'duration_ms': duration_ms,
                        'error': error
                    }
                )
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get monitoring status"""
        if self.monitoring_system:
            return self.monitoring_system.get_monitoring_status()
        return {'monitoring_active': False, 'message': 'Monitoring not initialized'}


class WorkerMonitoringMixin:
    """Mixin to add monitoring capabilities to worker classes"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitoring_system: Optional[MonitoringSystem] = None
        self._monitoring_initialized = False
    
    def initialize_monitoring(self):
        """Initialize monitoring system for worker"""
        if not self._monitoring_initialized:
            self.monitoring_system = create_monitoring_system()
            self._monitoring_initialized = True
            logger.info("Worker monitoring initialized")
    
    async def start_monitoring(self):
        """Start monitoring tasks"""
        if self.monitoring_system:
            await self.monitoring_system.start_monitoring()
    
    async def stop_monitoring(self):
        """Stop monitoring tasks"""
        if self.monitoring_system:
            await self.monitoring_system.stop_monitoring()
    
    def record_orchestrator_communication(self, operation: str, duration_ms: float, success: bool, error: Optional[str] = None):
        """Record orchestrator communication metrics"""
        if self.monitoring_system:
            self.monitoring_system.metrics_collector.record_response_time(f"orchestrator_{operation}", duration_ms)
            
            if not success and error:
                self.monitoring_system.record_failure(
                    source="orchestrator_communication",
                    failure_type=f"orchestrator_{operation}_error",
                    severity=AlertSeverity.WARNING,
                    metadata={
                        'operation': operation,
                        'duration_ms': duration_ms,
                        'error': error
                    }
                )
    
    def record_circuit_breaker_event(self, state: str, failure_count: int):
        """Record circuit breaker state changes"""
        if self.monitoring_system:
            severity = AlertSeverity.INFO
            if state == "open":
                severity = AlertSeverity.CRITICAL
            elif state == "half_open":
                severity = AlertSeverity.WARNING
            
            self.monitoring_system.alert_manager.create_alert(
                severity=severity,
                title=f"Circuit Breaker {state.title()}",
                description=f"Circuit breaker transitioned to {state} state after {failure_count} failures",
                source="circuit_breaker",
                metadata={
                    'state': state,
                    'failure_count': failure_count,
                    'timestamp': datetime.now().isoformat()
                }
            )
    
    def record_local_mode_activation(self, reason: str, assigned_streams: int):
        """Record local mode activation"""
        if self.monitoring_system:
            self.monitoring_system.alert_manager.create_alert(
                severity=AlertSeverity.WARNING,
                title="Local Mode Activated",
                description=f"Worker entered local mode: {reason}. Processing {assigned_streams} streams locally.",
                source="local_mode",
                metadata={
                    'reason': reason,
                    'assigned_streams': assigned_streams,
                    'timestamp': datetime.now().isoformat()
                }
            )
    
    def record_stream_processing(self, stream_id: int, duration_ms: float, success: bool, error: Optional[str] = None):
        """Record stream processing metrics"""
        if self.monitoring_system:
            self.monitoring_system.metrics_collector.record_response_time("stream_processing", duration_ms)
            
            if not success and error:
                self.monitoring_system.record_failure(
                    source="stream_processing",
                    failure_type="processing_error",
                    severity=AlertSeverity.WARNING,
                    metadata={
                        'stream_id': stream_id,
                        'duration_ms': duration_ms,
                        'error': error
                    }
                )


class DummyMonitoredOperation:
    """Dummy context manager when monitoring is not available"""
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MonitoringDecorator:
    """Decorator for adding monitoring to functions"""
    
    def __init__(self, monitoring_system: MonitoringSystem, operation_name: str):
        self.monitoring_system = monitoring_system
        self.operation_name = operation_name
    
    def __call__(self, func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                async with monitored_async_operation(self.monitoring_system, self.operation_name):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                with MonitoredOperation(self.monitoring_system, self.operation_name):
                    return func(*args, **kwargs)
            return sync_wrapper


def monitor_function(monitoring_system: MonitoringSystem, operation_name: str):
    """Decorator factory for monitoring functions"""
    return MonitoringDecorator(monitoring_system, operation_name)


class SystemHealthChecker:
    """Comprehensive system health checker"""
    
    def __init__(self, monitoring_system: MonitoringSystem):
        self.monitoring_system = monitoring_system
    
    async def check_orchestrator_health(self, orchestrator) -> Dict[str, Any]:
        """Check orchestrator health"""
        health_status = {
            'status': 'healthy',
            'checks': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check database connectivity
            if hasattr(orchestrator, 'get_db_connection'):
                with orchestrator.monitor_operation("health_check_database"):
                    conn = orchestrator.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    conn.close()
                    health_status['checks']['database'] = 'healthy'
            
            # Check active instances
            if hasattr(orchestrator, 'active_instances'):
                active_count = len(orchestrator.active_instances)
                health_status['checks']['active_instances'] = active_count
                
                if active_count == 0:
                    health_status['status'] = 'critical'
                    health_status['checks']['active_instances_status'] = 'no_active_instances'
            
            # Check system health status
            if hasattr(orchestrator, 'system_health_status'):
                health_status['checks']['system_health'] = orchestrator.system_health_status.value
                
                if orchestrator.system_health_status.value in ['critical', 'emergency']:
                    health_status['status'] = 'critical'
            
            # Check monitoring system
            if self.monitoring_system:
                monitoring_status = self.monitoring_system.get_monitoring_status()
                health_status['checks']['monitoring'] = {
                    'active': monitoring_status['monitoring_active'],
                    'active_alerts': monitoring_status['active_alerts'],
                    'critical_alerts': monitoring_status['critical_alerts']
                }
                
                if monitoring_status['critical_alerts'] > 0:
                    health_status['status'] = 'degraded'
        
        except Exception as e:
            health_status['status'] = 'critical'
            health_status['error'] = str(e)
            
            # Record health check failure
            self.monitoring_system.record_failure(
                source="health_check",
                failure_type="orchestrator_health_check_failed",
                severity=AlertSeverity.CRITICAL,
                metadata={'error': str(e)}
            )
        
        return health_status
    
    async def check_worker_health(self, worker) -> Dict[str, Any]:
        """Check worker health"""
        health_status = {
            'status': 'healthy',
            'checks': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check orchestrator connectivity
            if hasattr(worker, 'orchestrator_available'):
                health_status['checks']['orchestrator_available'] = worker.orchestrator_available
                
                if not worker.orchestrator_available:
                    health_status['status'] = 'degraded'
            
            # Check local mode status
            if hasattr(worker, 'local_state'):
                health_status['checks']['local_mode'] = worker.local_state.is_active
                health_status['checks']['assigned_streams'] = len(worker.local_state.assigned_streams)
            
            # Check circuit breaker status
            if hasattr(worker, 'circuit_breaker'):
                cb_stats = worker.circuit_breaker.get_stats()
                health_status['checks']['circuit_breaker'] = cb_stats['state']
                
                if cb_stats['state'] == 'open':
                    health_status['status'] = 'degraded'
            
            # Check monitoring system
            if self.monitoring_system:
                monitoring_status = self.monitoring_system.get_monitoring_status()
                health_status['checks']['monitoring'] = {
                    'active': monitoring_status['monitoring_active'],
                    'active_alerts': monitoring_status['active_alerts']
                }
        
        except Exception as e:
            health_status['status'] = 'critical'
            health_status['error'] = str(e)
            
            # Record health check failure
            self.monitoring_system.record_failure(
                source="health_check",
                failure_type="worker_health_check_failed",
                severity=AlertSeverity.CRITICAL,
                metadata={'error': str(e)}
            )
        
        return health_status


# Utility functions for easy integration

def add_monitoring_to_orchestrator(orchestrator_class):
    """Class decorator to add monitoring capabilities to orchestrator"""
    
    class MonitoredOrchestrator(OrchestratorMonitoringMixin, orchestrator_class):
        pass
    
    return MonitoredOrchestrator


def add_monitoring_to_worker(worker_class):
    """Class decorator to add monitoring capabilities to worker"""
    
    class MonitoredWorker(WorkerMonitoringMixin, worker_class):
        pass
    
    return MonitoredWorker


# Integration helper functions

async def setup_orchestrator_monitoring(orchestrator, db_config: Optional[Dict] = None):
    """Setup monitoring for an orchestrator instance"""
    if hasattr(orchestrator, 'initialize_monitoring'):
        orchestrator.initialize_monitoring(db_config)
        await orchestrator.start_monitoring()
        logger.info("Orchestrator monitoring setup complete")
    else:
        logger.warning("Orchestrator does not support monitoring integration")


async def setup_worker_monitoring(worker):
    """Setup monitoring for a worker instance"""
    if hasattr(worker, 'initialize_monitoring'):
        worker.initialize_monitoring()
        await worker.start_monitoring()
        logger.info("Worker monitoring setup complete")
    else:
        logger.warning("Worker does not support monitoring integration")


async def shutdown_monitoring(component):
    """Shutdown monitoring for a component"""
    if hasattr(component, 'stop_monitoring'):
        await component.stop_monitoring()
        logger.info("Monitoring shutdown complete")
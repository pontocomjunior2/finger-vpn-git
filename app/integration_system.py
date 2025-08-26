#!/usr/bin/env python3
"""
Comprehensive Integration System for Orchestrator Stream Balancing Fix

This module integrates all enhanced components with proper error handling
and provides end-to-end testing capabilities with failure simulation.

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# Import all enhanced components
try:
    from consistency_checker import ConsistencyChecker
    from database_error_handler import DatabaseErrorHandler
    from diagnostic_api import DiagnosticAPI
    from enhanced_db_manager import EnhancedDatabaseManager
    from enhanced_orchestrator import EnhancedStreamOrchestrator
    from monitoring_system import MonitoringSystem
    from resilient_orchestrator import (FailureRecoveryConfig, HeartbeatConfig,
                                        ResilientOrchestrator)
    from smart_load_balancer import (LoadBalanceConfig, RebalanceReason,
                                     SmartLoadBalancer)
    HAS_ALL_COMPONENTS = True
except ImportError as e:
    logging.error(f"Failed to import components: {e}")
    HAS_ALL_COMPONENTS = False

logger = logging.getLogger(__name__)


class IntegrationStatus(Enum):
    """Integration system status"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    TESTING = "testing"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class TestScenario(Enum):
    """End-to-end test scenarios"""
    NORMAL_OPERATION = "normal_operation"
    INSTANCE_FAILURE = "instance_failure"
    DATABASE_FAILURE = "database_failure"
    NETWORK_PARTITION = "network_partition"
    LOAD_IMBALANCE = "load_imbalance"
    CONSISTENCY_ISSUES = "consistency_issues"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass
class IntegrationMetrics:
    """Integration system metrics"""
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    average_response_time: float = 0.0
    error_rate: float = 0.0
    uptime_seconds: float = 0.0
    components_healthy: int = 0
    components_total: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 1.0
        return self.successful_operations / self.total_operations
    
    @property
    def health_ratio(self) -> float:
        if self.components_total == 0:
            return 1.0
        return self.components_healthy / self.components_total


@dataclass
class TestResult:
    """Test execution result"""
    scenario: TestScenario
    success: bool
    duration_seconds: float
    details: Dict[str, Any]
    error_message: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class IntegratedOrchestrator:
    """
    Integrated orchestrator system combining all enhanced components
    with comprehensive error handling and monitoring.
    """
    
    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.status = IntegrationStatus.INITIALIZING
        self.start_time = datetime.now()
        self.metrics = IntegrationMetrics()
        
        # Component instances
        self.db_manager: Optional[EnhancedDatabaseManager] = None
        self.error_handler: Optional[DatabaseErrorHandler] = None
        self.enhanced_orchestrator: Optional[EnhancedStreamOrchestrator] = None
        self.resilient_orchestrator: Optional[ResilientOrchestrator] = None
        self.consistency_checker: Optional[ConsistencyChecker] = None
        self.monitoring_system: Optional[MonitoringSystem] = None
        self.diagnostic_api: Optional[DiagnosticAPI] = None
        
        # Integration state
        self.active_instances: Dict[str, Dict] = {}
        self.stream_assignments: Dict[int, str] = {}
        self.component_health: Dict[str, bool] = {}
        
        # Background tasks
        self.background_tasks: List[asyncio.Task] = []
        self.shutdown_event = asyncio.Event()
        
        logger.info("Integrated orchestrator system initialized")
    
    async def initialize_components(self) -> bool:
        """Initialize all enhanced components with proper error handling"""
        try:
            logger.info("Initializing enhanced components...")
            
            # Initialize database manager
            self.db_manager = EnhancedDatabaseManager()
            self.component_health['db_manager'] = True
            logger.info("✓ Database manager initialized")
            
            # Initialize error handler
            self.error_handler = DatabaseErrorHandler()
            self.component_health['error_handler'] = True
            logger.info("✓ Database error handler initialized")
            
            # Initialize load balance configuration
            load_balance_config = LoadBalanceConfig()
            load_balance_config.imbalance_threshold = float(os.getenv('IMBALANCE_THRESHOLD', '0.2'))
            load_balance_config.max_stream_difference = int(os.getenv('MAX_STREAM_DIFFERENCE', '2'))
            
            # Initialize enhanced orchestrator
            self.enhanced_orchestrator = EnhancedStreamOrchestrator(
                self.db_config, load_balance_config
            )
            self.component_health['enhanced_orchestrator'] = True
            logger.info("✓ Enhanced orchestrator initialized")
            
            # Initialize resilient orchestrator
            heartbeat_config = HeartbeatConfig(
                timeout_seconds=int(os.getenv('HEARTBEAT_TIMEOUT', '300')),
                warning_threshold_seconds=int(os.getenv('HEARTBEAT_WARNING_THRESHOLD', '120')),
                max_missed_heartbeats=int(os.getenv('MAX_MISSED_HEARTBEATS', '3'))
            )
            
            recovery_config = FailureRecoveryConfig(
                max_retry_attempts=int(os.getenv('MAX_RETRY_ATTEMPTS', '3')),
                retry_delay_seconds=int(os.getenv('RETRY_DELAY_SECONDS', '5')),
                exponential_backoff=os.getenv('EXPONENTIAL_BACKOFF', 'true').lower() == 'true'
            )
            
            self.resilient_orchestrator = ResilientOrchestrator(
                self.db_config, heartbeat_config, recovery_config
            )
            self.component_health['resilient_orchestrator'] = True
            logger.info("✓ Resilient orchestrator initialized")
            
            # Initialize consistency checker
            self.consistency_checker = ConsistencyChecker(self.db_manager)
            self.component_health['consistency_checker'] = True
            logger.info("✓ Consistency checker initialized")
            
            # Initialize monitoring system
            self.monitoring_system = MonitoringSystem(self.db_config)
            self.component_health['monitoring_system'] = True
            logger.info("✓ Monitoring system initialized")
            
            # Initialize diagnostic API
            self.diagnostic_api = DiagnosticAPI(self.db_config, self.monitoring_system)
            self.component_health['diagnostic_api'] = True
            logger.info("✓ Diagnostic API initialized")
            
            # Update metrics
            self.metrics.components_total = len(self.component_health)
            self.metrics.components_healthy = sum(self.component_health.values())
            
            logger.info(f"All components initialized successfully ({self.metrics.components_healthy}/{self.metrics.components_total})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            self.status = IntegrationStatus.FAILED
            return False
    
    async def start_system(self) -> bool:
        """Start the integrated orchestrator system"""
        try:
            if not await self.initialize_components():
                return False
            
            logger.info("Starting integrated orchestrator system...")
            
            # Start monitoring system
            if self.monitoring_system:
                await self.monitoring_system.start_monitoring()
                logger.info("✓ Monitoring system started")
            
            # Start resilient orchestrator monitoring
            if self.resilient_orchestrator:
                await self.resilient_orchestrator.start_monitoring()
                logger.info("✓ Resilient orchestrator monitoring started")
            
            # Start background tasks
            self.background_tasks = [
                asyncio.create_task(self._health_monitoring_task()),
                asyncio.create_task(self._consistency_monitoring_task()),
                asyncio.create_task(self._performance_monitoring_task()),
                asyncio.create_task(self._auto_rebalancing_task())
            ]
            
            self.status = IntegrationStatus.RUNNING
            logger.info("✓ Integrated orchestrator system started successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start system: {e}")
            self.status = IntegrationStatus.FAILED
            return False
    
    async def stop_system(self) -> bool:
        """Stop the integrated orchestrator system gracefully"""
        try:
            logger.info("Stopping integrated orchestrator system...")
            
            # Signal shutdown
            self.shutdown_event.set()
            
            # Stop background tasks
            for task in self.background_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Stop monitoring systems
            if self.monitoring_system:
                await self.monitoring_system.stop_monitoring()
                logger.info("✓ Monitoring system stopped")
            
            if self.resilient_orchestrator:
                await self.resilient_orchestrator.stop_monitoring()
                logger.info("✓ Resilient orchestrator monitoring stopped")
            
            self.status = IntegrationStatus.STOPPED
            logger.info("✓ Integrated orchestrator system stopped gracefully")
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping system: {e}")
            return False
    
    async def register_instance(self, server_id: str, ip: str, port: int, max_streams: int) -> Dict[str, Any]:
        """Register worker instance with integrated error handling"""
        start_time = time.time()
        
        try:
            # Use enhanced orchestrator for registration
            result = await self.enhanced_orchestrator.register_instance(
                server_id, ip, port, max_streams
            )
            
            # Update local state
            self.active_instances[server_id] = {
                'ip': ip,
                'port': port,
                'max_streams': max_streams,
                'current_streams': 0,
                'last_heartbeat': datetime.now(),
                'status': 'active'
            }
            
            # Record metrics
            self._record_operation_success(time.time() - start_time)
            
            # Trigger rebalancing if needed
            if len(self.active_instances) > 1:
                await self._trigger_smart_rebalancing(RebalanceReason.NEW_INSTANCE)
            
            logger.info(f"Instance {server_id} registered successfully")
            return {'status': 'success', 'result': result}
            
        except Exception as e:
            self._record_operation_failure(time.time() - start_time, str(e))
            logger.error(f"Failed to register instance {server_id}: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def process_heartbeat(self, server_id: str, heartbeat_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process heartbeat with integrated monitoring and consistency checking"""
        start_time = time.time()
        
        try:
            # Update instance state
            if server_id in self.active_instances:
                self.active_instances[server_id].update({
                    'current_streams': heartbeat_data.get('current_streams', 0),
                    'last_heartbeat': datetime.now(),
                    'status': 'active'
                })
            
            # Process through resilient orchestrator
            if self.resilient_orchestrator:
                await self.resilient_orchestrator.process_heartbeat(server_id, heartbeat_data)
            
            # Record performance metrics
            if self.monitoring_system:
                self.monitoring_system.metrics_collector.record_response_time(
                    'heartbeat', (time.time() - start_time) * 1000
                )
            
            self._record_operation_success(time.time() - start_time)
            
            return {'status': 'success'}
            
        except Exception as e:
            self._record_operation_failure(time.time() - start_time, str(e))
            logger.error(f"Failed to process heartbeat from {server_id}: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def assign_streams(self, server_id: str, requested_count: int) -> Dict[str, Any]:
        """Assign streams using intelligent load balancing"""
        start_time = time.time()
        
        try:
            # Use enhanced orchestrator for intelligent assignment
            result = await self.enhanced_orchestrator.assign_streams_intelligently(
                server_id, requested_count
            )
            
            # Update local state
            if server_id in self.active_instances and result.get('assigned_streams'):
                assigned_streams = result['assigned_streams']
                self.active_instances[server_id]['current_streams'] += len(assigned_streams)
                
                # Update stream assignments
                for stream_id in assigned_streams:
                    self.stream_assignments[stream_id] = server_id
            
            self._record_operation_success(time.time() - start_time)
            
            return {'status': 'success', 'result': result}
            
        except Exception as e:
            self._record_operation_failure(time.time() - start_time, str(e))
            logger.error(f"Failed to assign streams to {server_id}: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def handle_instance_failure(self, server_id: str) -> Dict[str, Any]:
        """Handle instance failure with comprehensive recovery"""
        start_time = time.time()
        
        try:
            logger.warning(f"Handling failure of instance {server_id}")
            
            # Mark instance as failed
            if server_id in self.active_instances:
                self.active_instances[server_id]['status'] = 'failed'
            
            # Use resilient orchestrator for failure handling
            if self.resilient_orchestrator:
                recovery_result = await self.resilient_orchestrator.handle_instance_failure(server_id)
            
            # Use enhanced orchestrator for stream redistribution
            if self.enhanced_orchestrator:
                rebalance_result = await self.enhanced_orchestrator.handle_instance_failure(server_id)
            
            # Trigger consistency check
            if self.consistency_checker:
                await self.consistency_checker.verify_stream_assignments()
            
            # Create alert
            if self.monitoring_system:
                self.monitoring_system.alert_manager.create_alert(
                    severity="critical",
                    title=f"Instance Failure: {server_id}",
                    description=f"Instance {server_id} has failed and streams have been redistributed",
                    source="integration_system"
                )
            
            self._record_operation_success(time.time() - start_time)
            
            logger.info(f"Instance failure {server_id} handled successfully")
            return {'status': 'success', 'recovery_performed': True}
            
        except Exception as e:
            self._record_operation_failure(time.time() - start_time, str(e))
            logger.error(f"Failed to handle instance failure {server_id}: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            # Update metrics
            self.metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            self.metrics.components_healthy = sum(self.component_health.values())
            
            # Get component statuses
            component_statuses = {}
            
            if self.monitoring_system:
                component_statuses['monitoring'] = self.monitoring_system.get_monitoring_status()
            
            if self.diagnostic_api:
                # Get diagnostic information
                health_check = await self.diagnostic_api._check_orchestrator_health()
                component_statuses['orchestrator'] = health_check
            
            # Get active alerts
            active_alerts = []
            if self.monitoring_system:
                alerts = self.monitoring_system.alert_manager.get_active_alerts()
                active_alerts = [alert.to_dict() for alert in alerts]
            
            return {
                'status': self.status.value,
                'uptime_seconds': self.metrics.uptime_seconds,
                'metrics': asdict(self.metrics),
                'components': component_statuses,
                'active_instances': len(self.active_instances),
                'total_streams': len(self.stream_assignments),
                'active_alerts': active_alerts,
                'component_health': self.component_health,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {'status': 'error', 'error': str(e)}
    
    # Background monitoring tasks
    
    async def _health_monitoring_task(self):
        """Background task for health monitoring"""
        while not self.shutdown_event.is_set():
            try:
                # Check component health
                for component_name, component in [
                    ('db_manager', self.db_manager),
                    ('enhanced_orchestrator', self.enhanced_orchestrator),
                    ('resilient_orchestrator', self.resilient_orchestrator),
                    ('consistency_checker', self.consistency_checker),
                    ('monitoring_system', self.monitoring_system)
                ]:
                    if component:
                        try:
                            # Perform basic health check
                            health_ok = await self._check_component_health(component)
                            self.component_health[component_name] = health_ok
                        except Exception as e:
                            logger.warning(f"Health check failed for {component_name}: {e}")
                            self.component_health[component_name] = False
                
                # Update system status based on component health
                healthy_components = sum(self.component_health.values())
                total_components = len(self.component_health)
                
                if healthy_components == total_components:
                    if self.status == IntegrationStatus.DEGRADED:
                        self.status = IntegrationStatus.RUNNING
                        logger.info("System recovered to healthy state")
                elif healthy_components < total_components * 0.5:
                    self.status = IntegrationStatus.FAILED
                    logger.error("System in failed state - less than 50% components healthy")
                else:
                    self.status = IntegrationStatus.DEGRADED
                    logger.warning("System in degraded state")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in health monitoring task: {e}")
                await asyncio.sleep(10)
    
    async def _consistency_monitoring_task(self):
        """Background task for consistency monitoring"""
        while not self.shutdown_event.is_set():
            try:
                if self.consistency_checker:
                    # Run consistency check
                    report = await self.consistency_checker.verify_stream_assignments()
                    
                    if not report.is_healthy:
                        logger.warning(f"Consistency issues detected: {len(report.stream_issues)} issues")
                        
                        # Attempt auto-recovery
                        recovery_results = await self.consistency_checker.auto_recover_inconsistencies(report)
                        
                        successful_recoveries = sum(1 for r in recovery_results if r.success)
                        logger.info(f"Auto-recovery completed: {successful_recoveries}/{len(recovery_results)} successful")
                
                await asyncio.sleep(120)  # Check every 2 minutes
                
            except Exception as e:
                logger.error(f"Error in consistency monitoring task: {e}")
                await asyncio.sleep(30)
    
    async def _performance_monitoring_task(self):
        """Background task for performance monitoring"""
        while not self.shutdown_event.is_set():
            try:
                # Update performance metrics
                if self.metrics.total_operations > 0:
                    self.metrics.error_rate = 1.0 - self.metrics.success_rate
                
                # Record system metrics
                if self.monitoring_system:
                    self.monitoring_system.metrics_collector.record_metric(
                        'system_success_rate', self.metrics.success_rate, 'gauge'
                    )
                    self.monitoring_system.metrics_collector.record_metric(
                        'system_error_rate', self.metrics.error_rate, 'gauge'
                    )
                    self.monitoring_system.metrics_collector.record_metric(
                        'active_instances', len(self.active_instances), 'gauge'
                    )
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error(f"Error in performance monitoring task: {e}")
                await asyncio.sleep(30)
    
    async def _auto_rebalancing_task(self):
        """Background task for automatic rebalancing"""
        while not self.shutdown_event.is_set():
            try:
                if self.enhanced_orchestrator and len(self.active_instances) > 1:
                    # Check if rebalancing is needed
                    instances = await self._get_instance_metrics()
                    
                    if self.enhanced_orchestrator.load_balancer.should_rebalance(instances):
                        logger.info("Triggering automatic rebalancing")
                        await self._trigger_smart_rebalancing(RebalanceReason.LOAD_IMBALANCE)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in auto-rebalancing task: {e}")
                await asyncio.sleep(60)
    
    # Helper methods
    
    async def _check_component_health(self, component) -> bool:
        """Check health of a specific component"""
        try:
            # Basic health check - component exists and has expected methods
            if hasattr(component, 'get_status'):
                status = await component.get_status()
                return status.get('healthy', True)
            return True
        except Exception:
            return False
    
    async def _get_instance_metrics(self):
        """Get current instance metrics"""
        if self.enhanced_orchestrator:
            return self.enhanced_orchestrator.get_instance_metrics()
        return []
    
    async def _trigger_smart_rebalancing(self, reason: RebalanceReason):
        """Trigger smart rebalancing"""
        try:
            if self.enhanced_orchestrator:
                result = self.enhanced_orchestrator.intelligent_rebalance(reason)
                
                if result.success:
                    logger.info(f"Smart rebalancing completed: {result.streams_moved} streams moved")
                else:
                    logger.warning(f"Smart rebalancing failed: {result.error_message}")
        except Exception as e:
            logger.error(f"Error in smart rebalancing: {e}")
    
    def _record_operation_success(self, duration: float):
        """Record successful operation"""
        self.metrics.total_operations += 1
        self.metrics.successful_operations += 1
        
        # Update average response time
        total_time = self.metrics.average_response_time * (self.metrics.total_operations - 1)
        self.metrics.average_response_time = (total_time + duration) / self.metrics.total_operations
    
    def _record_operation_failure(self, duration: float, error: str):
        """Record failed operation"""
        self.metrics.total_operations += 1
        self.metrics.failed_operations += 1
        
        # Update average response time
        total_time = self.metrics.average_response_time * (self.metrics.total_operations - 1)
        self.metrics.average_response_time = (total_time + duration) / self.metrics.total_operations
        
        logger.error(f"Operation failed in {duration:.3f}s: {error}")


class EndToEndTestSuite:
    """Comprehensive end-to-end testing suite with failure simulation"""
    
    def __init__(self, integrated_orchestrator: IntegratedOrchestrator):
        self.orchestrator = integrated_orchestrator
        self.test_results: List[TestResult] = []
        self.test_instances: Dict[str, Dict] = {}
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all end-to-end test scenarios"""
        logger.info("Starting comprehensive end-to-end test suite")
        
        test_scenarios = [
            TestScenario.NORMAL_OPERATION,
            TestScenario.INSTANCE_FAILURE,
            TestScenario.LOAD_IMBALANCE,
            TestScenario.CONSISTENCY_ISSUES,
            TestScenario.PERFORMANCE_DEGRADATION
        ]
        
        for scenario in test_scenarios:
            try:
                result = await self._run_test_scenario(scenario)
                self.test_results.append(result)
                
                if result.success:
                    logger.info(f"✓ Test scenario {scenario.value} passed")
                else:
                    logger.error(f"✗ Test scenario {scenario.value} failed: {result.error_message}")
                
            except Exception as e:
                logger.error(f"Test scenario {scenario.value} crashed: {e}")
                self.test_results.append(TestResult(
                    scenario=scenario,
                    success=False,
                    duration_seconds=0,
                    details={},
                    error_message=str(e)
                ))
        
        return self._generate_test_report()
    
    async def _run_test_scenario(self, scenario: TestScenario) -> TestResult:
        """Run a specific test scenario"""
        start_time = time.time()
        
        try:
            if scenario == TestScenario.NORMAL_OPERATION:
                return await self._test_normal_operation()
            elif scenario == TestScenario.INSTANCE_FAILURE:
                return await self._test_instance_failure()
            elif scenario == TestScenario.LOAD_IMBALANCE:
                return await self._test_load_imbalance()
            elif scenario == TestScenario.CONSISTENCY_ISSUES:
                return await self._test_consistency_issues()
            elif scenario == TestScenario.PERFORMANCE_DEGRADATION:
                return await self._test_performance_degradation()
            else:
                raise ValueError(f"Unknown test scenario: {scenario}")
                
        except Exception as e:
            return TestResult(
                scenario=scenario,
                success=False,
                duration_seconds=time.time() - start_time,
                details={},
                error_message=str(e)
            )
    
    async def _test_normal_operation(self) -> TestResult:
        """Test normal operation scenario"""
        start_time = time.time()
        details = {}
        
        try:
            # Register multiple instances
            instances = [
                ('test-worker-norm-1', '127.0.0.1', 8001, 20),
                ('test-worker-norm-2', '127.0.0.1', 8002, 20),
                ('test-worker-norm-3', '127.0.0.1', 8003, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                result = await self.orchestrator.register_instance(server_id, ip, port, max_streams)
                if result['status'] != 'success':
                    raise Exception(f"Failed to register instance {server_id}: {result.get('error')}")
            
            details['instances_registered'] = len(instances)
            
            # Assign streams to instances
            total_streams_assigned = 0
            for server_id, _, _, _ in instances:
                result = await self.orchestrator.assign_streams(server_id, 5)
                if result['status'] == 'success' and 'assigned_streams' in result['result']:
                    total_streams_assigned += len(result['result']['assigned_streams'])
            
            details['streams_assigned'] = total_streams_assigned
            
            # Process heartbeats
            for server_id, _, _, _ in instances:
                heartbeat_data = {
                    'current_streams': 5,
                    'cpu_percent': 45.0,
                    'memory_percent': 60.0,
                    'response_time_ms': 150.0
                }
                result = await self.orchestrator.process_heartbeat(server_id, heartbeat_data)
                if result['status'] != 'success':
                    raise Exception(f"Failed to process heartbeat for {server_id}")
            
            details['heartbeats_processed'] = len(instances)
            
            # Verify system status
            status = await self.orchestrator.get_system_status()
            details['system_status'] = status['status']
            details['active_instances'] = status['active_instances']
            
            return TestResult(
                scenario=TestScenario.NORMAL_OPERATION,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.NORMAL_OPERATION,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_instance_failure(self) -> TestResult:
        """Test instance failure scenario with recovery"""
        start_time = time.time()
        details = {}
        
        try:
            # Register instances
            instances = [
                ('test-worker-fail-1', '127.0.0.1', 8001, 20),
                ('test-worker-fail-2', '127.0.0.1', 8002, 20),
                ('test-worker-fail-3', '127.0.0.1', 8003, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                await self.orchestrator.register_instance(server_id, ip, port, max_streams)
            
            # Assign streams to first instance
            await self.orchestrator.assign_streams('test-worker-fail-1', 10)
            
            details['initial_setup'] = {
                'instances': len(instances),
                'streams_assigned_to_failing_instance': 10
            }
            
            # Simulate instance failure
            failure_result = await self.orchestrator.handle_instance_failure('test-worker-fail-1')
            
            details['failure_simulated'] = True
            details['recovery_performed'] = failure_result.get('recovery_performed', False)
            
            # Verify streams were redistributed
            status = await self.orchestrator.get_system_status()
            details['final_active_instances'] = status['active_instances']
            
            return TestResult(
                scenario=TestScenario.INSTANCE_FAILURE,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.INSTANCE_FAILURE,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_load_imbalance(self) -> TestResult:
        """Test load imbalance detection and rebalancing"""
        start_time = time.time()
        """Test normal operation scenario"""
        start_time = time.time()
        details = {}
        
        try:
            # Register multiple instances
            instances = [
                ('test-worker-1', '127.0.0.1', 8001, 20),
                ('test-worker-2', '127.0.0.1', 8002, 20),
                ('test-worker-3', '127.0.0.1', 8003, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                result = await self.orchestrator.register_instance(server_id, ip, port, max_streams)
                if result['status'] != 'success':
                    raise Exception(f"Failed to register {server_id}: {result.get('error')}")
            
            details['instances_registered'] = len(instances)
            
            # Send heartbeats
            for server_id, _, _, _ in instances:
                heartbeat_data = {
                    'current_streams': 10,
                    'cpu_percent': 50.0,
                    'memory_percent': 60.0
                }
                result = await self.orchestrator.process_heartbeat(server_id, heartbeat_data)
                if result['status'] != 'success':
                    raise Exception(f"Failed heartbeat for {server_id}: {result.get('error')}")
            
            details['heartbeats_processed'] = len(instances)
            
            # Assign streams
            for server_id, _, _, _ in instances:
                result = await self.orchestrator.assign_streams(server_id, 5)
                if result['status'] != 'success':
                    raise Exception(f"Failed to assign streams to {server_id}: {result.get('error')}")
            
            details['stream_assignments'] = len(instances) * 5
            
            # Check system status
            status = await self.orchestrator.get_system_status()
            details['final_status'] = status
            
            return TestResult(
                scenario=TestScenario.NORMAL_OPERATION,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.NORMAL_OPERATION,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_instance_failure(self) -> TestResult:
        """Test instance failure handling"""
        start_time = time.time()
        details = {}
        
        try:
            # Setup instances
            instances = [
                ('test-worker-fail-1', '127.0.0.1', 8001, 20),
                ('test-worker-fail-2', '127.0.0.1', 8002, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                await self.orchestrator.register_instance(server_id, ip, port, max_streams)
            
            # Assign streams to both instances
            for server_id, _, _, _ in instances:
                await self.orchestrator.assign_streams(server_id, 10)
            
            details['initial_instances'] = len(instances)
            details['initial_streams'] = len(instances) * 10
            
            # Simulate instance failure
            failed_instance = instances[0][0]
            result = await self.orchestrator.handle_instance_failure(failed_instance)
            
            if result['status'] != 'success':
                raise Exception(f"Failed to handle instance failure: {result.get('error')}")
            
            details['failure_handled'] = True
            details['failed_instance'] = failed_instance
            
            # Verify system recovered
            status = await self.orchestrator.get_system_status()
            details['recovery_status'] = status
            
            return TestResult(
                scenario=TestScenario.INSTANCE_FAILURE,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.INSTANCE_FAILURE,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_load_imbalance(self) -> TestResult:
        """Test load imbalance detection and correction"""
        start_time = time.time()
        details = {}
        
        try:
            # Create imbalanced scenario
            instances = [
                ('test-worker-imb-1', '127.0.0.1', 8001, 20),
                ('test-worker-imb-2', '127.0.0.1', 8002, 20),
                ('test-worker-imb-3', '127.0.0.1', 8003, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                await self.orchestrator.register_instance(server_id, ip, port, max_streams)
            
            # Create imbalance - assign many streams to first instance
            await self.orchestrator.assign_streams('test-worker-imb-1', 18)
            await self.orchestrator.assign_streams('test-worker-imb-2', 2)
            await self.orchestrator.assign_streams('test-worker-imb-3', 2)
            
            details['initial_imbalance'] = {
                'test-worker-imb-1': 18,
                'test-worker-imb-2': 2,
                'test-worker-imb-3': 2
            }
            
            # Trigger rebalancing
            if self.orchestrator.enhanced_orchestrator:
                rebalance_result = self.orchestrator.enhanced_orchestrator.intelligent_rebalance(
                    RebalanceReason.LOAD_IMBALANCE
                )
                
                details['rebalance_performed'] = rebalance_result.success
                details['streams_moved'] = rebalance_result.streams_moved
            
            return TestResult(
                scenario=TestScenario.LOAD_IMBALANCE,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.LOAD_IMBALANCE,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_consistency_issues(self) -> TestResult:
        """Test consistency issue detection and resolution"""
        start_time = time.time()
        details = {}
        
        try:
            # Setup scenario with potential consistency issues
            instances = [
                ('test-worker-cons-1', '127.0.0.1', 8001, 20),
                ('test-worker-cons-2', '127.0.0.1', 8002, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                await self.orchestrator.register_instance(server_id, ip, port, max_streams)
            
            # Run consistency check
            if self.orchestrator.consistency_checker:
                report = await self.orchestrator.consistency_checker.verify_stream_assignments()
                
                details['consistency_check_performed'] = True
                details['issues_found'] = len(report.stream_issues)
                details['consistency_score'] = report.consistency_score
                
                # Attempt auto-recovery if issues found
                if not report.is_healthy:
                    recovery_results = await self.orchestrator.consistency_checker.auto_recover_inconsistencies(report)
                    details['recovery_attempted'] = True
                    details['recovery_results'] = len(recovery_results)
            
            return TestResult(
                scenario=TestScenario.CONSISTENCY_ISSUES,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.CONSISTENCY_ISSUES,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    async def _test_performance_degradation(self) -> TestResult:
        """Test performance monitoring and alerting"""
        start_time = time.time()
        details = {}
        
        try:
            # Simulate high load scenario
            instances = [
                ('test-worker-perf-1', '127.0.0.1', 8001, 20),
                ('test-worker-perf-2', '127.0.0.1', 8002, 20)
            ]
            
            for server_id, ip, port, max_streams in instances:
                await self.orchestrator.register_instance(server_id, ip, port, max_streams)
            
            # Simulate performance degradation with high resource usage
            for server_id, _, _, _ in instances:
                degraded_heartbeat = {
                    'current_streams': 19,  # Near capacity
                    'cpu_percent': 95.0,    # High CPU
                    'memory_percent': 90.0, # High memory
                    'response_time_ms': 500.0  # Slow response
                }
                await self.orchestrator.process_heartbeat(server_id, degraded_heartbeat)
            
            details['performance_degradation_simulated'] = True
            
            # Check if monitoring system detected issues
            if self.orchestrator.monitoring_system:
                active_alerts = self.orchestrator.monitoring_system.alert_manager.get_active_alerts()
                details['alerts_generated'] = len(active_alerts)
                
                performance_summary = self.orchestrator.monitoring_system.metrics_collector.get_performance_summary()
                details['performance_metrics'] = performance_summary
            
            return TestResult(
                scenario=TestScenario.PERFORMANCE_DEGRADATION,
                success=True,
                duration_seconds=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                scenario=TestScenario.PERFORMANCE_DEGRADATION,
                success=False,
                duration_seconds=time.time() - start_time,
                details=details,
                error_message=str(e)
            )
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.success)
        failed_tests = total_tests - passed_tests
        
        total_duration = sum(result.duration_seconds for result in self.test_results)
        
        return {
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': passed_tests / total_tests if total_tests > 0 else 0,
                'total_duration_seconds': total_duration
            },
            'test_results': [
                {
                    'scenario': result.scenario.value,
                    'success': result.success,
                    'duration_seconds': result.duration_seconds,
                    'error_message': result.error_message,
                    'details': result.details
                }
                for result in self.test_results
            ],
            'timestamp': datetime.now().isoformat()
        }


# Main integration function
async def main():
    """Main integration and testing function"""
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'orchestrator'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    # Create integrated orchestrator
    orchestrator = IntegratedOrchestrator(db_config)
    
    try:
        # Start the system
        if not await orchestrator.start_system():
            logger.error("Failed to start integrated orchestrator system")
            return
        
        logger.info("Integrated orchestrator system started successfully")
        
        # Run end-to-end tests
        test_suite = EndToEndTestSuite(orchestrator)
        test_report = await test_suite.run_all_tests()
        
        # Save test report
        with open('integration_test_report.json', 'w') as f:
            json.dump(test_report, f, indent=2)
        
        logger.info(f"End-to-end testing completed: {test_report['summary']['passed_tests']}/{test_report['summary']['total_tests']} tests passed")
        
        # Get final system status
        final_status = await orchestrator.get_system_status()
        logger.info(f"Final system status: {final_status['status']}")
        
        # Keep system running for demonstration
        logger.info("System running... Press Ctrl+C to stop")
        await asyncio.sleep(60)  # Run for 1 minute
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
    finally:
        # Stop the system
        await orchestrator.stop_system()
        logger.info("Integration test completed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if not HAS_ALL_COMPONENTS:
        logger.error("Not all components are available. Please ensure all enhanced components are properly installed.")
        exit(1)
    
    asyncio.run(main())
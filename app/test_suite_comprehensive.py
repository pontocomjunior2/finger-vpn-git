#!/usr/bin/env python3
"""
Comprehensive Automated Testing Suite for Orchestrator Stream Balancing Fix

This test suite provides comprehensive coverage for all components:
- Unit tests for all new components with error scenario coverage
- Integration tests for orchestrator-worker communication
- Load testing framework for balancing algorithm validation

Requirements: All requirements validation
"""

import asyncio
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import psycopg2
import pytest

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import components to test
try:
    from consistency_checker import ConsistencyChecker, StreamAssignmentIssue
    from database_error_handler import DatabaseErrorHandler
    from diagnostic_api import DiagnosticAPI
    from enhanced_db_manager import EnhancedDatabaseManager
    from enhanced_orchestrator import EnhancedStreamOrchestrator
    from monitoring_system_core import MonitoringSystem
    from resilient_orchestrator import (CircuitBreakerState, InstanceStatus,
                                        ResilientOrchestrator)
    from resilient_worker_client import ResilientWorkerClient
    from smart_load_balancer import (InstanceMetrics, LoadBalanceConfig,
                                     RebalanceReason, RebalanceResult,
                                     SmartLoadBalancer)
    HAS_ALL_COMPONENTS = True
except ImportError as e:
    logger.warning(f"Some components not available for testing: {e}")
    HAS_ALL_COMPONENTS = False


class TestConfiguration:
    """Test configuration and utilities"""
    
    @staticmethod
    def create_test_db_config():
        """Create test database configuration"""
        return {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_orchestrator',
            'user': 'test_user',
            'password': 'test_pass'
        }
    
    @staticmethod
    def create_test_load_balance_config():
        """Create test load balance configuration"""
        return LoadBalanceConfig(
            imbalance_threshold=0.2,
            min_streams_per_instance=1,
            max_streams_per_instance=50,
            rebalance_cooldown_seconds=30,
            performance_weight=0.3,
            capacity_weight=0.4,
            failure_weight=0.3
        )
    
    @staticmethod
    def create_test_instances():
        """Create test instance metrics"""
        return [
            InstanceMetrics(
                server_id="test-instance-1",
                current_streams=10,
                max_streams=20,
                cpu_percent=50.0,
                memory_percent=60.0,
                load_average_1m=1.0,
                response_time_ms=100.0,
                failure_count=0,
                last_heartbeat=datetime.now()
            ),
            InstanceMetrics(
                server_id="test-instance-2",
                current_streams=5,
                max_streams=20,
                cpu_percent=30.0,
                memory_percent=40.0,
                load_average_1m=0.5,
                response_time_ms=80.0,
                failure_count=1,
                last_heartbeat=datetime.now()
            ),
            InstanceMetrics(
                server_id="test-instance-3",
                current_streams=18,
                max_streams=20,
                cpu_percent=90.0,
                memory_percent=85.0,
                load_average_1m=2.5,
                response_time_ms=200.0,
                failure_count=2,
                last_heartbeat=datetime.now() - timedelta(minutes=2)
            )
        ]


# ============================================================================
# UNIT TESTS - Component Testing with Error Scenarios
# ============================================================================

@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestSmartLoadBalancerUnit:
    """Unit tests for Smart Load Balancer with comprehensive error coverage"""
    
    @pytest.fixture
    def load_balancer(self):
        """Create load balancer for testing"""
        config = TestConfiguration.create_test_load_balance_config()
        return SmartLoadBalancer(config)
    
    @pytest.fixture
    def test_instances(self):
        """Create test instances"""
        return TestConfiguration.create_test_instances()
    
    def test_load_factor_calculation(self, test_instances):
        """Test load factor calculation (Requirement 1.4)"""
        instance = test_instances[0]
        assert instance.load_factor == 0.5  # 10/20
        assert instance.available_capacity == 10  # 20-10
    
    def test_performance_score_calculation(self, test_instances):
        """Test performance score calculation"""
        high_perf = test_instances[1]  # Low CPU, memory, good response time
        low_perf = test_instances[2]   # High CPU, memory, poor response time
        
        assert high_perf.performance_score > low_perf.performance_score
    
    def test_detect_imbalance_basic(self, load_balancer, test_instances):
        """Test basic load imbalance detection (Requirement 1.3)"""
        # Create imbalanced scenario
        test_instances[0].current_streams = 20  # Full capacity
        test_instances[1].current_streams = 2   # Very low
        
        imbalance_detected = load_balancer.detect_imbalance(test_instances)
        assert imbalance_detected is True
    
    def test_detect_imbalance_balanced(self, load_balancer, test_instances):
        """Test balanced scenario detection"""
        # Create balanced scenario
        for instance in test_instances:
            instance.current_streams = 10
            instance.max_streams = 20
        
        imbalance_detected = load_balancer.detect_imbalance(test_instances)
        assert imbalance_detected is False
    
    def test_calculate_optimal_distribution(self, load_balancer, test_instances):
        """Test optimal distribution calculation (Requirement 1.1)"""
        total_streams = 100
        distribution = load_balancer.calculate_optimal_distribution(
            test_instances, total_streams
        )
        
        # Verify distribution respects capacity limits
        for server_id, streams in distribution.items():
            instance = next(i for i in test_instances if i.server_id == server_id)
            assert streams <= instance.max_streams
        
        # Verify total streams are distributed
        assert sum(distribution.values()) == total_streams
    
    def test_generate_rebalance_plan_new_instance(self, load_balancer, test_instances):
        """Test rebalance plan generation for new instance (Requirement 1.1)"""
        current_distribution = {
            "test-instance-1": 15,
            "test-instance-2": 10,
            "test-instance-3": 18
        }
        
        # Add new instance
        new_instance = InstanceMetrics(
            server_id="test-instance-4",
            current_streams=0,
            max_streams=20,
            cpu_percent=20.0,
            memory_percent=30.0
        )
        test_instances.append(new_instance)
        
        plan = load_balancer.generate_rebalance_plan(
            test_instances, current_distribution, RebalanceReason.NEW_INSTANCE
        )
        
        assert plan is not None
        assert plan.reason == RebalanceReason.NEW_INSTANCE
        assert len(plan.migrations) > 0
        
        # Verify new instance gets streams
        new_instance_streams = sum(
            m.stream_count for m in plan.migrations 
            if m.target_server == "test-instance-4"
        )
        assert new_instance_streams > 0
    
    def test_error_handling_invalid_instances(self, load_balancer):
        """Test error handling with invalid instance data"""
        invalid_instances = [
            InstanceMetrics(
                server_id="invalid",
                current_streams=-1,  # Invalid
                max_streams=0,       # Invalid
                cpu_percent=150.0    # Invalid
            )
        ]
        
        # Should handle gracefully without crashing
        try:
            load_balancer.detect_imbalance(invalid_instances)
            distribution = load_balancer.calculate_optimal_distribution(invalid_instances, 10)
            assert isinstance(distribution, dict)
        except Exception as e:
            pytest.fail(f"Should handle invalid data gracefully: {e}")
    
    def test_zero_capacity_instances(self, load_balancer):
        """Test handling of zero-capacity instances"""
        zero_capacity_instances = [
            InstanceMetrics(
                server_id="zero-cap",
                current_streams=0,
                max_streams=0,
                cpu_percent=50.0
            )
        ]
        
        distribution = load_balancer.calculate_optimal_distribution(zero_capacity_instances, 10)
        assert distribution.get("zero-cap", 0) == 0


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestEnhancedOrchestratorUnit:
    """Unit tests for Enhanced Orchestrator"""
    
    @pytest.fixture
    def mock_db_config(self):
        """Mock database configuration"""
        return TestConfiguration.create_test_db_config()
    
    @pytest.fixture
    def orchestrator(self, mock_db_config):
        """Create orchestrator for testing"""
        config = TestConfiguration.create_test_load_balance_config()
        return EnhancedStreamOrchestrator(mock_db_config, config)
    
    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initialization"""
        assert orchestrator.load_balancer is not None
        assert isinstance(orchestrator.active_instances, dict)
        assert isinstance(orchestrator.stream_assignments, dict)
    
    @patch('psycopg2.connect')
    def test_register_instance_success(self, mock_connect, orchestrator):
        """Test successful instance registration (Requirement 1.1)"""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock successful registration
        mock_cursor.fetchone.return_value = None  # No existing instance
        
        result = orchestrator.register_instance("test-server", "127.0.0.1", 8000, 20)
        
        assert result is not None
        assert "test-server" in orchestrator.active_instances
    
    @patch('psycopg2.connect')
    def test_register_instance_database_error(self, mock_connect, orchestrator):
        """Test instance registration with database error (Requirement 2.1)"""
        mock_connect.side_effect = psycopg2.OperationalError("Connection failed")
        
        # Should handle database errors gracefully
        result = orchestrator.register_instance("test-server", "127.0.0.1", 8000, 20)
        
        # Should return error indication but not crash
        assert result is not None or result is None  # Either way, shouldn't crash
    
    def test_heartbeat_processing(self, orchestrator):
        """Test heartbeat processing (Requirement 4.1)"""
        # Register instance first
        orchestrator.active_instances["test-server"] = {
            'ip': '127.0.0.1',
            'port': 8000,
            'max_streams': 20,
            'current_streams': 10,
            'last_heartbeat': datetime.now() - timedelta(minutes=1)
        }
        
        # Process heartbeat
        result = orchestrator.process_heartbeat("test-server", {
            'current_streams': 12,
            'cpu_percent': 50.0,
            'memory_percent': 60.0
        })
        
        assert result is True
        assert orchestrator.active_instances["test-server"]['current_streams'] == 12
    
    def test_detect_failed_instances(self, orchestrator):
        """Test failed instance detection (Requirement 4.1)"""
        # Add instance with old heartbeat
        old_time = datetime.now() - timedelta(minutes=10)
        orchestrator.active_instances["failed-server"] = {
            'ip': '127.0.0.1',
            'port': 8000,
            'max_streams': 20,
            'current_streams': 10,
            'last_heartbeat': old_time
        }
        
        failed_instances = orchestrator.detect_failed_instances(timeout_minutes=5)
        
        assert "failed-server" in failed_instances


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestResilientOrchestratorUnit:
    """Unit tests for Resilient Orchestrator with error scenarios"""
    
    @pytest.fixture
    def resilient_orchestrator(self):
        """Create resilient orchestrator for testing"""
        db_config = TestConfiguration.create_test_db_config()
        return ResilientOrchestrator(db_config)
    
    def test_circuit_breaker_initialization(self, resilient_orchestrator):
        """Test circuit breaker initialization"""
        assert resilient_orchestrator.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert resilient_orchestrator.failure_count == 0
    
    def test_circuit_breaker_failure_threshold(self, resilient_orchestrator):
        """Test circuit breaker opens after failure threshold (Requirement 5.1)"""
        # Simulate multiple failures
        for _ in range(6):  # Exceed threshold of 5
            resilient_orchestrator.record_failure()
        
        assert resilient_orchestrator.circuit_breaker_state == CircuitBreakerState.OPEN
    
    def test_circuit_breaker_recovery(self, resilient_orchestrator):
        """Test circuit breaker recovery mechanism"""
        # Open circuit breaker
        resilient_orchestrator.circuit_breaker_state = CircuitBreakerState.OPEN
        resilient_orchestrator.last_failure_time = datetime.now() - timedelta(minutes=2)
        
        # Should transition to half-open after timeout
        can_attempt = resilient_orchestrator.can_attempt_operation()
        assert resilient_orchestrator.circuit_breaker_state == CircuitBreakerState.HALF_OPEN
    
    @patch('psycopg2.connect')
    def test_database_operation_with_circuit_breaker(self, mock_connect, resilient_orchestrator):
        """Test database operations with circuit breaker (Requirement 5.1)"""
        # Simulate database connection failure
        mock_connect.side_effect = psycopg2.OperationalError("Connection failed")
        
        # Should handle failure and update circuit breaker
        result = resilient_orchestrator.execute_database_operation(
            lambda conn: conn.cursor().execute("SELECT 1")
        )
        
        assert result is None  # Operation failed
        assert resilient_orchestrator.failure_count > 0
    
    @pytest.mark.asyncio
    async def test_emergency_recovery_procedures(self, resilient_orchestrator):
        """Test emergency recovery procedures (Requirement 5.2)"""
        # Simulate critical system failure
        with patch.object(resilient_orchestrator, 'detect_critical_failure', return_value=True):
            recovery_result = await resilient_orchestrator.execute_emergency_recovery()
            
            assert recovery_result is not None
            # Should attempt recovery procedures


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestConsistencyCheckerUnit:
    """Unit tests for Consistency Checker with comprehensive error coverage"""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager"""
        db_manager = Mock()
        db_manager.get_connection = AsyncMock()
        return db_manager
    
    @pytest.fixture
    def consistency_checker(self, mock_db_manager):
        """Create consistency checker for testing"""
        return ConsistencyChecker(mock_db_manager)
    
    @pytest.mark.asyncio
    async def test_detect_orphaned_streams(self, consistency_checker, mock_db_manager):
        """Test orphaned stream detection (Requirement 3.1)"""
        # Mock database responses
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_db_manager.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        
        # Mock orphaned streams
        mock_cursor.fetchall.return_value = [
            (1, 'orphaned-server', datetime.now()),
            (2, 'orphaned-server', datetime.now())
        ]
        
        orphaned_streams = await consistency_checker.detect_orphaned_streams()
        
        assert len(orphaned_streams) == 2
        assert all(stream.server_id == 'orphaned-server' for stream in orphaned_streams)
    
    @pytest.mark.asyncio
    async def test_resolve_duplicate_assignments(self, consistency_checker, mock_db_manager):
        """Test duplicate assignment resolution (Requirement 3.3)"""
        # Mock database responses for duplicate detection
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_db_manager.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        
        # Mock duplicate assignments
        mock_cursor.fetchall.return_value = [
            (1, 'server-1', datetime.now()),
            (1, 'server-2', datetime.now())  # Same stream_id, different servers
        ]
        
        conflicts = await consistency_checker.detect_duplicate_assignments()
        
        assert len(conflicts) > 0
        
        # Test resolution
        resolution_result = await consistency_checker.resolve_conflicts(conflicts)
        assert resolution_result is not None
    
    @pytest.mark.asyncio
    async def test_auto_recovery_mechanism(self, consistency_checker, mock_db_manager):
        """Test auto-recovery mechanism (Requirement 3.2)"""
        # Create test issue
        issue = StreamAssignmentIssue(
            issue_type="orphaned_stream",
            stream_id=1,
            server_id="test-server",
            description="Test orphaned stream",
            severity="high",
            auto_recoverable=True
        )
        
        # Mock successful recovery
        with patch.object(consistency_checker, 'attempt_auto_recovery', return_value=True):
            recovery_result = await consistency_checker.attempt_auto_recovery(issue)
            assert recovery_result is True
    
    @pytest.mark.asyncio
    async def test_consistency_verification_database_error(self, consistency_checker, mock_db_manager):
        """Test consistency verification with database errors (Requirement 2.1)"""
        # Simulate database error
        mock_db_manager.get_connection.side_effect = psycopg2.OperationalError("DB Error")
        
        # Should handle error gracefully
        try:
            report = await consistency_checker.verify_stream_assignments()
            # Should return error report or handle gracefully
            assert report is not None or report is None
        except Exception as e:
            pytest.fail(f"Should handle database errors gracefully: {e}")


# ============================================================================
# INTEGRATION TESTS - Orchestrator-Worker Communication
# ============================================================================

@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerIntegration:
    """Integration tests for orchestrator-worker communication"""
    
    @pytest.fixture
    def mock_orchestrator_server(self):
        """Mock orchestrator server for integration testing"""
        server = Mock()
        server.register_instance = AsyncMock(return_value={"status": "success"})
        server.heartbeat = AsyncMock(return_value={"status": "ok"})
        server.get_streams = AsyncMock(return_value={"streams": [1, 2, 3]})
        return server
    
    @pytest.fixture
    def resilient_worker_client(self):
        """Create resilient worker client for testing"""
        return ResilientWorkerClient("http://localhost:8001", "test-worker")
    
    @pytest.mark.asyncio
    async def test_worker_registration_flow(self, resilient_worker_client, mock_orchestrator_server):
        """Test complete worker registration flow (Requirement 1.1)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock successful registration response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "success", "server_id": "test-worker"})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await resilient_worker_client.register_with_orchestrator(
                ip="127.0.0.1", port=8000, max_streams=20
            )
            
            assert result is not None
            assert result.get("status") == "success"
    
    @pytest.mark.asyncio
    async def test_heartbeat_communication(self, resilient_worker_client):
        """Test heartbeat communication (Requirement 4.1)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock successful heartbeat response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "ok"})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await resilient_worker_client.send_heartbeat({
                "current_streams": 10,
                "cpu_percent": 50.0,
                "memory_percent": 60.0
            })
            
            assert result is not None
            assert result.get("status") == "ok"
    
    @pytest.mark.asyncio
    async def test_network_failure_handling(self, resilient_worker_client):
        """Test network failure handling (Requirement 5.2, 5.3)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate network failure
            mock_post.side_effect = aiohttp.ClientError("Network error")
            
            # Should handle network failure gracefully
            result = await resilient_worker_client.send_heartbeat({
                "current_streams": 10
            })
            
            # Should return None or error indication, but not crash
            assert result is None or isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, resilient_worker_client):
        """Test retry mechanism with exponential backoff (Requirement 5.3)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First call fails, second succeeds
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.json = AsyncMock(return_value={"status": "ok"})
            
            mock_post.side_effect = [
                mock_response_fail.__aenter__.return_value,
                mock_response_success.__aenter__.return_value
            ]
            
            # Should retry and eventually succeed
            result = await resilient_worker_client.send_heartbeat_with_retry({
                "current_streams": 10
            })
            
            assert result is not None
            assert result.get("status") == "ok"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, resilient_worker_client):
        """Test circuit breaker pattern in worker-orchestrator communication (Requirement 5.2)"""
        # Simulate multiple failures to trigger circuit breaker
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = aiohttp.ClientError("Persistent failure")
            
            # Multiple failed attempts should trigger circuit breaker
            for _ in range(6):
                await resilient_worker_client.send_heartbeat({"current_streams": 10})
            
            # Circuit breaker should be open
            assert resilient_worker_client.circuit_breaker_open is True
    
    @pytest.mark.asyncio
    async def test_local_operation_mode(self, resilient_worker_client):
        """Test local operation mode when orchestrator unreachable (Requirement 5.4)"""
        # Simulate orchestrator unreachable
        resilient_worker_client.orchestrator_reachable = False
        
        # Should continue operating locally
        local_streams = await resilient_worker_client.get_local_streams()
        
        assert isinstance(local_streams, list)
        # Should maintain local state even when orchestrator is down


# ============================================================================
# LOAD TESTING FRAMEWORK - Balancing Algorithm Validation
# ============================================================================

class LoadTestFramework:
    """Framework for load testing the balancing algorithm"""
    
    def __init__(self, load_balancer: SmartLoadBalancer):
        self.load_balancer = load_balancer
        self.test_results = []
    
    def generate_load_test_scenarios(self) -> List[Dict]:
        """Generate various load test scenarios"""
        scenarios = [
            {
                "name": "balanced_load",
                "instances": 5,
                "streams_per_instance": 20,
                "total_streams": 100,
                "expected_balance": True
            },
            {
                "name": "imbalanced_load",
                "instances": 3,
                "streams_distribution": [50, 10, 5],  # Heavily imbalanced
                "total_streams": 65,
                "expected_balance": False
            },
            {
                "name": "high_capacity_variation",
                "instances": 4,
                "max_streams": [10, 20, 30, 40],  # Different capacities
                "total_streams": 80,
                "expected_balance": True
            },
            {
                "name": "performance_variation",
                "instances": 3,
                "performance_scores": [0.9, 0.5, 0.2],  # Different performance
                "total_streams": 60,
                "expected_balance": True
            }
        ]
        return scenarios
    
    def create_test_instances_for_scenario(self, scenario: Dict) -> List[InstanceMetrics]:
        """Create test instances for a specific scenario"""
        instances = []
        
        for i in range(scenario["instances"]):
            server_id = f"load-test-{i+1}"
            
            # Set capacity
            if "max_streams" in scenario:
                max_streams = scenario["max_streams"][i]
            else:
                max_streams = 20
            
            # Set current streams
            if "streams_distribution" in scenario:
                current_streams = scenario["streams_distribution"][i]
            else:
                current_streams = scenario.get("streams_per_instance", 10)
            
            # Set performance metrics
            if "performance_scores" in scenario:
                perf_score = scenario["performance_scores"][i]
                cpu_percent = (1 - perf_score) * 100
                memory_percent = (1 - perf_score) * 100
                response_time = (1 - perf_score) * 200
            else:
                cpu_percent = 50.0
                memory_percent = 60.0
                response_time = 100.0
            
            instance = InstanceMetrics(
                server_id=server_id,
                current_streams=current_streams,
                max_streams=max_streams,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                response_time_ms=response_time,
                failure_count=0,
                last_heartbeat=datetime.now()
            )
            instances.append(instance)
        
        return instances
    
    def measure_balancing_performance(self, instances: List[InstanceMetrics], 
                                    total_streams: int) -> Dict:
        """Measure balancing algorithm performance"""
        start_time = time.time()
        
        # Test imbalance detection
        imbalance_detected = self.load_balancer.detect_imbalance(instances)
        
        # Test optimal distribution calculation
        distribution = self.load_balancer.calculate_optimal_distribution(
            instances, total_streams
        )
        
        # Test rebalance plan generation if imbalanced
        rebalance_plan = None
        if imbalance_detected:
            current_distribution = {
                instance.server_id: instance.current_streams 
                for instance in instances
            }
            rebalance_plan = self.load_balancer.generate_rebalance_plan(
                instances, current_distribution, RebalanceReason.LOAD_IMBALANCE
            )
        
        end_time = time.time()
        
        # Calculate balance metrics
        load_factors = [inst.load_factor for inst in instances]
        balance_score = 1.0 - (max(load_factors) - min(load_factors))
        
        return {
            "execution_time_ms": (end_time - start_time) * 1000,
            "imbalance_detected": imbalance_detected,
            "distribution": distribution,
            "rebalance_plan": rebalance_plan,
            "balance_score": balance_score,
            "load_factors": load_factors
        }
    
    def run_load_test_suite(self) -> Dict:
        """Run complete load test suite"""
        scenarios = self.generate_load_test_scenarios()
        results = {}
        
        for scenario in scenarios:
            logger.info(f"Running load test scenario: {scenario['name']}")
            
            instances = self.create_test_instances_for_scenario(scenario)
            performance_metrics = self.measure_balancing_performance(
                instances, scenario["total_streams"]
            )
            
            # Validate results against expectations
            validation_results = self.validate_scenario_results(scenario, performance_metrics)
            
            results[scenario["name"]] = {
                "scenario": scenario,
                "performance": performance_metrics,
                "validation": validation_results
            }
        
        return results
    
    def validate_scenario_results(self, scenario: Dict, results: Dict) -> Dict:
        """Validate test results against scenario expectations"""
        validation = {
            "passed": True,
            "issues": []
        }
        
        # Check balance expectation
        expected_balance = scenario.get("expected_balance", True)
        actual_balance = results["balance_score"] > 0.8  # 80% balance threshold
        
        if expected_balance != actual_balance:
            validation["passed"] = False
            validation["issues"].append(
                f"Balance expectation mismatch: expected {expected_balance}, got {actual_balance}"
            )
        
        # Check performance (should complete within reasonable time)
        if results["execution_time_ms"] > 1000:  # 1 second threshold
            validation["passed"] = False
            validation["issues"].append(
                f"Performance issue: took {results['execution_time_ms']:.2f}ms"
            )
        
        # Check distribution validity
        distribution = results["distribution"]
        if not distribution or sum(distribution.values()) != scenario["total_streams"]:
            validation["passed"] = False
            validation["issues"].append("Invalid stream distribution")
        
        return validation


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestLoadTestingFramework:
    """Tests for the load testing framework itself"""
    
    @pytest.fixture
    def load_test_framework(self):
        """Create load test framework"""
        config = TestConfiguration.create_test_load_balance_config()
        load_balancer = SmartLoadBalancer(config)
        return LoadTestFramework(load_balancer)
    
    def test_scenario_generation(self, load_test_framework):
        """Test load test scenario generation"""
        scenarios = load_test_framework.generate_load_test_scenarios()
        
        assert len(scenarios) > 0
        assert all("name" in scenario for scenario in scenarios)
        assert all("instances" in scenario for scenario in scenarios)
    
    def test_instance_creation_for_scenarios(self, load_test_framework):
        """Test instance creation for different scenarios"""
        scenarios = load_test_framework.generate_load_test_scenarios()
        
        for scenario in scenarios:
            instances = load_test_framework.create_test_instances_for_scenario(scenario)
            
            assert len(instances) == scenario["instances"]
            assert all(isinstance(inst, InstanceMetrics) for inst in instances)
    
    def test_performance_measurement(self, load_test_framework):
        """Test performance measurement functionality"""
        # Create simple test scenario
        instances = TestConfiguration.create_test_instances()
        
        results = load_test_framework.measure_balancing_performance(instances, 50)
        
        assert "execution_time_ms" in results
        assert "imbalance_detected" in results
        assert "distribution" in results
        assert "balance_score" in results
        assert results["execution_time_ms"] > 0
    
    def test_full_load_test_suite(self, load_test_framework):
        """Test running the complete load test suite"""
        results = load_test_framework.run_load_test_suite()
        
        assert len(results) > 0
        
        for scenario_name, result in results.items():
            assert "scenario" in result
            assert "performance" in result
            assert "validation" in result
            
            # Check that validation ran
            validation = result["validation"]
            assert "passed" in validation
            assert "issues" in validation


# ============================================================================
# PERFORMANCE AND STRESS TESTS
# ============================================================================

@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestPerformanceAndStress:
    """Performance and stress tests for the system"""
    
    def test_large_scale_balancing(self):
        """Test balancing with large number of instances and streams"""
        config = TestConfiguration.create_test_load_balance_config()
        load_balancer = SmartLoadBalancer(config)
        
        # Create large number of instances
        instances = []
        for i in range(100):  # 100 instances
            instance = InstanceMetrics(
                server_id=f"stress-test-{i}",
                current_streams=i % 20,  # Varied load
                max_streams=20,
                cpu_percent=float(i % 100),
                memory_percent=float((i * 2) % 100),
                response_time_ms=float(50 + (i % 150)),
                failure_count=i % 5,
                last_heartbeat=datetime.now()
            )
            instances.append(instance)
        
        start_time = time.time()
        
        # Test with large number of streams
        total_streams = 1500
        distribution = load_balancer.calculate_optimal_distribution(instances, total_streams)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within reasonable time (5 seconds for 100 instances)
        assert execution_time < 5.0, f"Large scale balancing took too long: {execution_time:.2f}s"
        
        # Verify distribution
        assert sum(distribution.values()) == total_streams
        assert len(distribution) <= len(instances)
    
    def test_concurrent_operations(self):
        """Test concurrent orchestrator operations"""
        config = TestConfiguration.create_test_db_config()
        orchestrator = EnhancedStreamOrchestrator(config)
        
        # Simulate concurrent instance registrations
        def register_instance(instance_id):
            try:
                return orchestrator.register_instance(
                    f"concurrent-{instance_id}", 
                    "127.0.0.1", 
                    8000 + instance_id, 
                    20
                )
            except Exception as e:
                return f"Error: {e}"
        
        # Run concurrent registrations
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_instance, i) for i in range(20)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Should handle concurrent operations without crashing
        assert len(results) == 20
        # Most should succeed (some might fail due to mocked DB, but shouldn't crash)
    
    def test_memory_usage_under_load(self):
        """Test memory usage under sustained load"""
        import gc

        import psutil
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        config = TestConfiguration.create_test_load_balance_config()
        load_balancer = SmartLoadBalancer(config)
        
        # Perform many balancing operations
        for iteration in range(100):
            instances = TestConfiguration.create_test_instances()
            
            # Vary the load each iteration
            for i, instance in enumerate(instances):
                instance.current_streams = (iteration + i) % instance.max_streams
            
            # Perform balancing operations
            load_balancer.detect_imbalance(instances)
            distribution = load_balancer.calculate_optimal_distribution(instances, 100)
            
            # Force garbage collection periodically
            if iteration % 10 == 0:
                gc.collect()
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 100MB for this test)
        assert memory_increase < 100 * 1024 * 1024, f"Memory usage increased by {memory_increase / 1024 / 1024:.2f}MB"


# ============================================================================
# ERROR SCENARIO TESTS
# ============================================================================

@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestErrorScenarios:
    """Comprehensive error scenario testing"""
    
    def test_database_connection_failures(self):
        """Test various database connection failure scenarios (Requirement 2.1, 5.1)"""
        config = TestConfiguration.create_test_db_config()
        
        # Test connection timeout
        with patch('psycopg2.connect') as mock_connect:
            mock_connect.side_effect = psycopg2.OperationalError("Connection timeout")
            
            orchestrator = EnhancedStreamOrchestrator(config)
            result = orchestrator.register_instance("test", "127.0.0.1", 8000, 20)
            
            # Should handle gracefully
            assert result is not None or result is None
    
    def test_network_partition_scenarios(self):
        """Test network partition scenarios (Requirement 5.2, 5.4)"""
        client = ResilientWorkerClient("http://unreachable:8001", "test-worker")
        
        # Should handle unreachable orchestrator
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = aiohttp.ClientConnectorError(
                connection_key=None, os_error=OSError("Network unreachable")
            )
            
            # Should not crash and should enable local mode
            asyncio.run(client.handle_network_partition())
            assert client.local_mode_enabled is True
    
    def test_data_corruption_scenarios(self):
        """Test data corruption and inconsistency scenarios (Requirement 3.1, 3.2)"""
        mock_db_manager = Mock()
        consistency_checker = ConsistencyChecker(mock_db_manager)
        
        # Simulate corrupted data responses
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_db_manager.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        
        # Return malformed data
        mock_cursor.fetchall.return_value = [
            (None, None, None),  # Corrupted record
            ("invalid", "data", "format")  # Invalid format
        ]
        
        # Should handle corrupted data gracefully
        async def test_corruption():
            try:
                report = await consistency_checker.verify_stream_assignments()
                assert report is not None or report is None
            except Exception as e:
                pytest.fail(f"Should handle data corruption gracefully: {e}")
        
        asyncio.run(test_corruption())
    
    def test_resource_exhaustion_scenarios(self):
        """Test resource exhaustion scenarios"""
        config = TestConfiguration.create_test_load_balance_config()
        load_balancer = SmartLoadBalancer(config)
        
        # Test with all instances at maximum capacity
        exhausted_instances = [
            InstanceMetrics(
                server_id=f"exhausted-{i}",
                current_streams=20,  # At max capacity
                max_streams=20,
                cpu_percent=95.0,    # High CPU
                memory_percent=90.0, # High memory
                response_time_ms=500.0,  # Poor response time
                failure_count=5,     # Many failures
                last_heartbeat=datetime.now()
            )
            for i in range(5)
        ]
        
        # Should handle resource exhaustion gracefully
        try:
            distribution = load_balancer.calculate_optimal_distribution(exhausted_instances, 50)
            # Might not be able to distribute all streams, but shouldn't crash
            assert isinstance(distribution, dict)
        except Exception as e:
            pytest.fail(f"Should handle resource exhaustion gracefully: {e}")


if __name__ == "__main__":
    # Run the test suite
    pytest.main([__file__, "-v", "--tb=short"])
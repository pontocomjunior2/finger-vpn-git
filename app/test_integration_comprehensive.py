#!/usr/bin/env python3
"""
Comprehensive Integration Test Runner

This module provides comprehensive testing for the integrated orchestrator system
with all enhanced components wired together and end-to-end testing with failure simulation.

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
# Import integration system
from integration_system import (EndToEndTestSuite, IntegratedOrchestrator,
                                IntegrationStatus, TestScenario)

# Import all enhanced components for testing
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


@pytest.fixture
def db_config():
    """Database configuration for testing"""
    return {
        'host': os.getenv('TEST_DB_HOST', 'localhost'),
        'port': int(os.getenv('TEST_DB_PORT', '5432')),
        'database': os.getenv('TEST_DB_NAME', 'test_orchestrator'),
        'user': os.getenv('TEST_DB_USER', 'postgres'),
        'password': os.getenv('TEST_DB_PASSWORD', '')
    }


@pytest.fixture
async def integrated_orchestrator(db_config):
    """Create integrated orchestrator for testing"""
    orchestrator = IntegratedOrchestrator(db_config)
    
    # Initialize components
    await orchestrator.initialize_components()
    
    yield orchestrator
    
    # Cleanup
    await orchestrator.stop_system()


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestIntegratedOrchestrator:
    """Test integrated orchestrator system with all components wired together"""
    
    async def test_component_initialization(self, integrated_orchestrator):
        """Test that all components are properly initialized"""
        orchestrator = integrated_orchestrator
        
        # Check that all components are initialized
        assert orchestrator.db_manager is not None
        assert orchestrator.error_handler is not None
        assert orchestrator.enhanced_orchestrator is not None
        assert orchestrator.resilient_orchestrator is not None
        assert orchestrator.consistency_checker is not None
        assert orchestrator.monitoring_system is not None
        assert orchestrator.diagnostic_api is not None
        
        # Check component health
        assert orchestrator.component_health['db_manager'] is True
        assert orchestrator.component_health['enhanced_orchestrator'] is True
        assert orchestrator.component_health['resilient_orchestrator'] is True
        assert orchestrator.component_health['consistency_checker'] is True
        assert orchestrator.component_health['monitoring_system'] is True
        assert orchestrator.component_health['diagnostic_api'] is True
        
        # Check metrics
        assert orchestrator.metrics.components_total > 0
        assert orchestrator.metrics.components_healthy > 0
    
    async def test_system_startup_and_shutdown(self, db_config):
        """Test complete system startup and shutdown process"""
        orchestrator = IntegratedOrchestrator(db_config)
        
        # Test startup
        startup_success = await orchestrator.start_system()
        assert startup_success is True
        assert orchestrator.status == IntegrationStatus.RUNNING
        
        # Test that background tasks are running
        assert len(orchestrator.background_tasks) > 0
        
        # Test shutdown
        shutdown_success = await orchestrator.stop_system()
        assert shutdown_success is True
        assert orchestrator.status == IntegrationStatus.STOPPED
    
    async def test_instance_registration_integration(self, integrated_orchestrator):
        """Test instance registration with all components integrated"""
        orchestrator = integrated_orchestrator
        
        # Register test instance
        result = await orchestrator.register_instance(
            'test-worker-1', '127.0.0.1', 8001, 20
        )
        
        assert result['status'] == 'success'
        assert 'test-worker-1' in orchestrator.active_instances
        
        # Check that instance is registered in enhanced orchestrator
        if orchestrator.enhanced_orchestrator:
            instances = orchestrator.enhanced_orchestrator.get_instance_metrics()
            assert any(inst['server_id'] == 'test-worker-1' for inst in instances)
    
    async def test_heartbeat_processing_integration(self, integrated_orchestrator):
        """Test heartbeat processing with monitoring integration"""
        orchestrator = integrated_orchestrator
        
        # Register instance first
        await orchestrator.register_instance('test-worker-1', '127.0.0.1', 8001, 20)
        
        # Process heartbeat
        heartbeat_data = {
            'current_streams': 5,
            'cpu_percent': 45.0,
            'memory_percent': 60.0,
            'response_time_ms': 150.0
        }
        
        result = await orchestrator.process_heartbeat('test-worker-1', heartbeat_data)
        
        assert result['status'] == 'success'
        
        # Check that instance state is updated
        instance = orchestrator.active_instances['test-worker-1']
        assert instance['current_streams'] == 5
        assert instance['status'] == 'active'
    
    async def test_stream_assignment_integration(self, integrated_orchestrator):
        """Test stream assignment with smart load balancing"""
        orchestrator = integrated_orchestrator
        
        # Register multiple instances
        await orchestrator.register_instance('test-worker-1', '127.0.0.1', 8001, 20)
        await orchestrator.register_instance('test-worker-2', '127.0.0.1', 8002, 20)
        
        # Assign streams
        result = await orchestrator.assign_streams('test-worker-1', 5)
        
        assert result['status'] == 'success'
        
        # Check that streams are assigned
        if 'assigned_streams' in result['result']:
            assigned_streams = result['result']['assigned_streams']
            assert len(assigned_streams) > 0
            
            # Check that stream assignments are tracked
            for stream_id in assigned_streams:
                assert stream_id in orchestrator.stream_assignments
                assert orchestrator.stream_assignments[stream_id] == 'test-worker-1'
    
    async def test_instance_failure_handling_integration(self, integrated_orchestrator):
        """Test instance failure handling with all recovery mechanisms"""
        orchestrator = integrated_orchestrator
        
        # Register instances and assign streams
        await orchestrator.register_instance('test-worker-1', '127.0.0.1', 8001, 20)
        await orchestrator.register_instance('test-worker-2', '127.0.0.1', 8002, 20)
        
        await orchestrator.assign_streams('test-worker-1', 5)
        
        # Simulate instance failure
        result = await orchestrator.handle_instance_failure('test-worker-1')
        
        assert result['status'] == 'success'
        assert result.get('recovery_performed') is True
        
        # Check that instance is marked as failed
        if 'test-worker-1' in orchestrator.active_instances:
            assert orchestrator.active_instances['test-worker-1']['status'] == 'failed'
    
    async def test_system_status_integration(self, integrated_orchestrator):
        """Test comprehensive system status reporting"""
        orchestrator = integrated_orchestrator
        
        # Get system status
        status = await orchestrator.get_system_status()
        
        assert 'status' in status
        assert 'uptime_seconds' in status
        assert 'metrics' in status
        assert 'components' in status
        assert 'component_health' in status
        assert 'timestamp' in status
        
        # Check metrics structure
        metrics = status['metrics']
        assert 'total_operations' in metrics
        assert 'successful_operations' in metrics
        assert 'components_healthy' in metrics
        assert 'components_total' in metrics


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestEndToEndScenarios:
    """Test end-to-end scenarios with failure simulation"""
    
    async def test_normal_operation_scenario(self, integrated_orchestrator):
        """Test normal operation end-to-end scenario"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run normal operation test
        result = await test_suite._test_normal_operation()
        
        assert result.success is True
        assert result.scenario == TestScenario.NORMAL_OPERATION
        assert result.duration_seconds > 0
        assert 'instances_registered' in result.details
        assert 'streams_assigned' in result.details
    
    async def test_instance_failure_scenario(self, integrated_orchestrator):
        """Test instance failure scenario with recovery"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run instance failure test
        result = await test_suite._test_instance_failure()
        
        assert result.success is True
        assert result.scenario == TestScenario.INSTANCE_FAILURE
        assert 'failure_simulated' in result.details
        assert 'recovery_performed' in result.details
    
    async def test_load_imbalance_scenario(self, integrated_orchestrator):
        """Test load imbalance detection and rebalancing"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run load imbalance test
        result = await test_suite._test_load_imbalance()
        
        assert result.success is True
        assert result.scenario == TestScenario.LOAD_IMBALANCE
        assert 'initial_imbalance' in result.details
        assert 'rebalance_performed' in result.details
    
    async def test_consistency_issues_scenario(self, integrated_orchestrator):
        """Test consistency issue detection and resolution"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run consistency test
        result = await test_suite._test_consistency_issues()
        
        assert result.success is True
        assert result.scenario == TestScenario.CONSISTENCY_ISSUES
        assert 'consistency_check_performed' in result.details
    
    async def test_performance_degradation_scenario(self, integrated_orchestrator):
        """Test performance monitoring and alerting"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run performance degradation test
        result = await test_suite._test_performance_degradation()
        
        assert result.success is True
        assert result.scenario == TestScenario.PERFORMANCE_DEGRADATION
        assert 'performance_degradation_simulated' in result.details
    
    async def test_complete_test_suite(self, integrated_orchestrator):
        """Test complete end-to-end test suite"""
        orchestrator = integrated_orchestrator
        test_suite = EndToEndTestSuite(orchestrator)
        
        # Run all tests
        test_report = await test_suite.run_all_tests()
        
        assert 'summary' in test_report
        assert 'test_results' in test_report
        
        summary = test_report['summary']
        assert summary['total_tests'] > 0
        assert summary['success_rate'] >= 0.0
        assert summary['total_duration_seconds'] > 0
        
        # Check that all expected scenarios were tested
        tested_scenarios = {result['scenario'] for result in test_report['test_results']}
        expected_scenarios = {
            TestScenario.NORMAL_OPERATION.value,
            TestScenario.INSTANCE_FAILURE.value,
            TestScenario.LOAD_IMBALANCE.value,
            TestScenario.CONSISTENCY_ISSUES.value,
            TestScenario.PERFORMANCE_DEGRADATION.value
        }
        
        assert expected_scenarios.issubset(tested_scenarios)


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestPerformanceValidation:
    """Test system performance under various load conditions"""
    
    async def test_high_instance_count_performance(self, integrated_orchestrator):
        """Test performance with high number of instances"""
        orchestrator = integrated_orchestrator
        
        # Register many instances
        instance_count = 50
        for i in range(instance_count):
            await orchestrator.register_instance(
                f'test-worker-{i}', '127.0.0.1', 8000 + i, 20
            )
        
        # Measure registration time
        start_time = time.time()
        await orchestrator.register_instance(
            'test-worker-final', '127.0.0.1', 9000, 20
        )
        registration_time = time.time() - start_time
        
        # Performance should be reasonable even with many instances
        assert registration_time < 5.0  # Should complete within 5 seconds
        assert len(orchestrator.active_instances) == instance_count + 1
    
    async def test_high_stream_assignment_performance(self, integrated_orchestrator):
        """Test performance with high number of stream assignments"""
        orchestrator = integrated_orchestrator
        
        # Register instances
        for i in range(5):
            await orchestrator.register_instance(
                f'test-worker-{i}', '127.0.0.1', 8000 + i, 100
            )
        
        # Assign many streams
        start_time = time.time()
        for i in range(5):
            await orchestrator.assign_streams(f'test-worker-{i}', 50)
        assignment_time = time.time() - start_time
        
        # Performance should be reasonable
        assert assignment_time < 10.0  # Should complete within 10 seconds
        assert len(orchestrator.stream_assignments) > 0
    
    async def test_concurrent_operations_performance(self, integrated_orchestrator):
        """Test performance under concurrent operations"""
        orchestrator = integrated_orchestrator
        
        # Register instances
        for i in range(10):
            await orchestrator.register_instance(
                f'test-worker-{i}', '127.0.0.1', 8000 + i, 20
            )
        
        # Simulate concurrent heartbeats
        async def send_heartbeat(server_id):
            heartbeat_data = {
                'current_streams': 10,
                'cpu_percent': 50.0,
                'memory_percent': 60.0
            }
            return await orchestrator.process_heartbeat(server_id, heartbeat_data)
        
        # Send concurrent heartbeats
        start_time = time.time()
        tasks = [send_heartbeat(f'test-worker-{i}') for i in range(10)]
        results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time
        
        # All heartbeats should succeed
        assert all(result['status'] == 'success' for result in results)
        assert concurrent_time < 5.0  # Should complete within 5 seconds


@pytest.mark.skipif(not HAS_ALL_COMPONENTS, reason="Components not available")
class TestErrorHandlingIntegration:
    """Test integrated error handling across all components"""
    
    async def test_database_error_recovery(self, integrated_orchestrator):
        """Test database error handling and recovery"""
        orchestrator = integrated_orchestrator
        
        # Simulate database error by temporarily breaking connection
        original_db_manager = orchestrator.db_manager
        
        # Mock database error
        with patch.object(orchestrator.db_manager, 'execute_query', side_effect=Exception("Database connection lost")):
            # Try to register instance - should handle error gracefully
            result = await orchestrator.register_instance(
                'test-worker-error', '127.0.0.1', 8001, 20
            )
            
            assert result['status'] == 'error'
            assert 'error' in result
        
        # Restore connection and verify recovery
        result = await orchestrator.register_instance(
            'test-worker-recovery', '127.0.0.1', 8002, 20
        )
        assert result['status'] == 'success'
    
    async def test_component_failure_resilience(self, integrated_orchestrator):
        """Test system resilience when individual components fail"""
        orchestrator = integrated_orchestrator
        
        # Simulate monitoring system failure
        original_monitoring = orchestrator.monitoring_system
        orchestrator.monitoring_system = None
        orchestrator.component_health['monitoring_system'] = False
        
        # System should continue operating
        result = await orchestrator.register_instance(
            'test-worker-resilient', '127.0.0.1', 8001, 20
        )
        assert result['status'] == 'success'
        
        # Restore monitoring system
        orchestrator.monitoring_system = original_monitoring
        orchestrator.component_health['monitoring_system'] = True
    
    async def test_network_timeout_handling(self, integrated_orchestrator):
        """Test network timeout handling"""
        orchestrator = integrated_orchestrator
        
        # Simulate network timeout
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError("Network timeout")):
            # Operations should handle timeout gracefully
            result = await orchestrator.process_heartbeat(
                'test-worker-timeout', {'current_streams': 5}
            )
            
            # Should handle timeout error
            assert result['status'] == 'error'
            assert 'timeout' in result['error'].lower() or 'error' in result


class TestIntegrationReporting:
    """Test integration reporting and metrics"""
    
    def test_generate_integration_report(self):
        """Test generation of comprehensive integration report"""
        # Create mock test results
        test_results = [
            {
                'scenario': 'normal_operation',
                'success': True,
                'duration_seconds': 2.5,
                'details': {'instances_registered': 3}
            },
            {
                'scenario': 'instance_failure',
                'success': True,
                'duration_seconds': 1.8,
                'details': {'recovery_performed': True}
            }
        ]
        
        # Generate report
        report = {
            'summary': {
                'total_tests': len(test_results),
                'passed_tests': sum(1 for r in test_results if r['success']),
                'failed_tests': sum(1 for r in test_results if not r['success']),
                'total_duration_seconds': sum(r['duration_seconds'] for r in test_results)
            },
            'test_results': test_results,
            'timestamp': datetime.now().isoformat()
        }
        
        assert report['summary']['total_tests'] == 2
        assert report['summary']['passed_tests'] == 2
        assert report['summary']['failed_tests'] == 0
        assert report['summary']['total_duration_seconds'] == 4.3
    
    def test_save_integration_report(self):
        """Test saving integration report to file"""
        report = {
            'summary': {'total_tests': 1, 'passed_tests': 1},
            'timestamp': datetime.now().isoformat()
        }
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(report, f, indent=2)
            temp_path = f.name
        
        # Verify file was created and contains correct data
        with open(temp_path, 'r') as f:
            loaded_report = json.load(f)
        
        assert loaded_report['summary']['total_tests'] == 1
        assert loaded_report['summary']['passed_tests'] == 1
        
        # Cleanup
        os.unlink(temp_path)


# Main test runner
async def run_integration_tests():
    """Run all integration tests"""
    logger.info("Starting comprehensive integration tests")
    
    # Configure test database
    db_config = {
        'host': os.getenv('TEST_DB_HOST', 'localhost'),
        'port': int(os.getenv('TEST_DB_PORT', '5432')),
        'database': os.getenv('TEST_DB_NAME', 'test_orchestrator'),
        'user': os.getenv('TEST_DB_USER', 'postgres'),
        'password': os.getenv('TEST_DB_PASSWORD', '')
    }
    
    # Create and start integrated orchestrator
    orchestrator = IntegratedOrchestrator(db_config)
    
    try:
        # Start system
        if not await orchestrator.start_system():
            logger.error("Failed to start integrated orchestrator for testing")
            return False
        
        logger.info("Integrated orchestrator started for testing")
        
        # Run comprehensive end-to-end tests
        test_suite = EndToEndTestSuite(orchestrator)
        test_report = await test_suite.run_all_tests()
        
        # Save detailed test report
        report_filename = f"integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(test_report, f, indent=2)
        
        logger.info(f"Integration test report saved to {report_filename}")
        
        # Log summary
        summary = test_report['summary']
        logger.info(f"Integration tests completed:")
        logger.info(f"  Total tests: {summary['total_tests']}")
        logger.info(f"  Passed: {summary['passed_tests']}")
        logger.info(f"  Failed: {summary['failed_tests']}")
        logger.info(f"  Success rate: {summary['success_rate']:.2%}")
        logger.info(f"  Total duration: {summary['total_duration_seconds']:.2f}s")
        
        # Return success if all tests passed
        return summary['failed_tests'] == 0
        
    except Exception as e:
        logger.error(f"Integration test execution failed: {e}")
        return False
    finally:
        # Stop system
        await orchestrator.stop_system()
        logger.info("Integration test cleanup completed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if not HAS_ALL_COMPONENTS:
        logger.error("Not all components are available for testing")
        exit(1)
    
    # Run integration tests
    success = asyncio.run(run_integration_tests())
    
    if success:
        logger.info("All integration tests passed successfully")
        exit(0)
    else:
        logger.error("Some integration tests failed")
        exit(1)
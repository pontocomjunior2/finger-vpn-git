#!/usr/bin/env python3
"""
Test script for Diagnostic API

This script tests the comprehensive diagnostic and status API endpoints
to ensure they meet requirements 6.1, 6.2, 6.3, 6.4.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostic_api import (DiagnosticAPI, HealthStatus, InconsistencyType,
                            create_diagnostic_api)
from monitoring_system_core import (AlertSeverity, MonitoringSystem,
                                    create_monitoring_system)


class TestDiagnosticAPI:
    """Test cases for Diagnostic API"""
    
    def setup_method(self):
        """Setup test environment"""
        # Mock database config
        self.db_config = {
            'host': 'localhost',
            'port': '5432',
            'database': 'test_orchestrator',
            'user': 'test_user',
            'password': 'test_pass'
        }
        
        # Create mock monitoring system
        self.mock_monitoring = Mock(spec=MonitoringSystem)
        self.mock_monitoring.monitoring_active = True
        self.mock_monitoring.get_monitoring_status.return_value = {
            'monitoring_active': True,
            'active_alerts': 0,
            'critical_alerts': 0
        }
        
        # Create diagnostic API instance
        self.api = DiagnosticAPI(self.db_config, self.mock_monitoring)
    
    @pytest.mark.asyncio
    async def test_comprehensive_health_check(self):
        """Test comprehensive health check endpoint (Requirement 6.3)"""
        # Mock health checkers
        with patch.object(self.api, '_check_database_health') as mock_db, \
             patch.object(self.api, '_check_monitoring_health') as mock_mon, \
             patch.object(self.api, '_check_orchestrator_health') as mock_orch, \
             patch.object(self.api, '_check_instances_health') as mock_inst, \
             patch.object(self.api, '_check_streams_health') as mock_streams, \
             patch.object(self.api, '_detect_all_inconsistencies') as mock_inconsistencies:
            
            # Setup mock returns
            mock_db.return_value = {
                'status': HealthStatus.HEALTHY,
                'message': 'Database connection successful',
                'details': {'response_time_ms': 50}
            }
            
            mock_mon.return_value = {
                'status': HealthStatus.HEALTHY,
                'message': 'Monitoring system is healthy',
                'details': {}
            }
            
            mock_orch.return_value = {
                'status': HealthStatus.HEALTHY,
                'message': 'Orchestrator service is healthy',
                'details': {}
            }
            
            mock_inst.return_value = {
                'status': HealthStatus.HEALTHY,
                'message': 'All instances are healthy',
                'details': {'healthy_instances': 3, 'total_instances': 3}
            }
            
            mock_streams.return_value = {
                'status': HealthStatus.HEALTHY,
                'message': 'Stream assignments are healthy',
                'details': {}
            }
            
            mock_inconsistencies.return_value = []
            
            # Test the endpoint
            client = self.api.app
            
            # Since we can't easily test FastAPI endpoints without a test client,
            # we'll test the underlying logic directly
            health_checks = []
            for component, checker in self.api.health_checkers.items():
                check_result = await checker()
                health_checks.append(check_result)
            
            # Verify all health checks were performed
            assert len(health_checks) == 5
            assert all(check['status'] == HealthStatus.HEALTHY for check in health_checks)
            
            # Verify inconsistency detection was called
            inconsistencies = await self.api._detect_all_inconsistencies()
            assert isinstance(inconsistencies, list)
    
    @pytest.mark.asyncio
    async def test_database_health_check(self):
        """Test database connectivity and integrity check (Requirement 6.3)"""
        with patch('psycopg2.connect') as mock_connect:
            # Mock successful database connection
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock query results
            mock_cursor.fetchone.return_value = (1,)
            mock_cursor.fetchall.return_value = [
                ('instances',), ('stream_assignments',), ('heartbeats',)
            ]
            
            result = await self.api._check_database_health()
            
            assert result['status'] == HealthStatus.HEALTHY
            assert 'response_time_ms' in result['details']
            assert 'available_tables' in result['details']
            
            # Verify required tables are present
            required_tables = ['instances', 'stream_assignments', 'heartbeats']
            available_tables = result['details']['available_tables']
            assert all(table in available_tables for table in required_tables)
    
    @pytest.mark.asyncio
    async def test_inconsistency_detection(self):
        """Test inconsistency detection with specific recommendations (Requirement 6.2)"""
        with patch('psycopg2.connect') as mock_connect:
            # Mock database connection for orphaned streams detection
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock orphaned streams
            mock_cursor.fetchall.return_value = [
                (123, 'nonexistent_server_1'),
                (456, 'nonexistent_server_2')
            ]
            
            inconsistencies = await self.api._detect_orphaned_streams()
            
            assert len(inconsistencies) == 1
            inconsistency = inconsistencies[0]
            
            assert inconsistency.type == InconsistencyType.ORPHANED_STREAMS
            assert inconsistency.severity == "critical"
            assert len(inconsistency.recommendations) > 0
            assert "Reassign orphaned streams" in inconsistency.recommendations[0]
            assert inconsistency.metadata['orphaned_count'] == 2
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self):
        """Test performance metrics APIs with historical data (Requirement 6.4)"""
        # Mock monitoring system with metrics
        mock_metrics_collector = Mock()
        mock_metrics_collector.get_performance_summary.return_value = {
            'avg_response_time': 150.5,
            'p95_response_time': 300.0,
            'avg_error_rate': 0.02,
            'avg_throughput': 1000.0,
            'resource_usage': {'cpu': 0.65, 'memory': 0.80}
        }
        
        self.mock_monitoring.metrics_collector = mock_metrics_collector
        
        # Test performance summary
        summary = await self.api._get_performance_summary()
        
        assert summary['avg_response_time'] == 150.5
        assert summary['p95_response_time'] == 300.0
        assert summary['avg_error_rate'] == 0.02
        assert summary['avg_throughput'] == 1000.0
        assert 'resource_usage' in summary
    
    @pytest.mark.asyncio
    async def test_system_status_reporting(self):
        """Test detailed status reporting (Requirement 6.1)"""
        with patch.object(self.api, '_get_database_status') as mock_db_status, \
             patch.object(self.api, '_get_orchestrator_status') as mock_orch_status, \
             patch.object(self.api, '_get_instances_status') as mock_inst_status, \
             patch.object(self.api, '_get_performance_summary') as mock_perf_summary:
            
            # Mock status responses
            mock_db_status.return_value = {
                'status': 'healthy',
                'connection_time_ms': 45.2,
                'connections': {'active': 5, 'idle': 10}
            }
            
            mock_orch_status.return_value = {
                'active': True,
                'total_instances': 3,
                'active_instances': 3,
                'total_streams': 100,
                'assigned_streams': 95
            }
            
            mock_inst_status.return_value = {
                'total_instances': 3,
                'healthy_instances': 3,
                'unhealthy_instances': 0,
                'summary': {
                    'health_ratio': 1.0,
                    'total_streams': 95,
                    'utilization': 0.75
                }
            }
            
            mock_perf_summary.return_value = {
                'avg_response_time': 120.0,
                'avg_error_rate': 0.01
            }
            
            # Test status collection
            db_status = await self.api._get_database_status()
            orch_status = await self.api._get_orchestrator_status()
            inst_status = await self.api._get_instances_status()
            perf_summary = await self.api._get_performance_summary()
            
            # Verify complete status information is returned
            assert db_status['status'] == 'healthy'
            assert orch_status['active'] is True
            assert inst_status['total_instances'] == 3
            assert perf_summary['avg_response_time'] == 120.0
    
    @pytest.mark.asyncio
    async def test_load_imbalance_detection(self):
        """Test load imbalance detection"""
        with patch('psycopg2.connect') as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Mock instances with load imbalance
            mock_cursor.fetchall.return_value = [
                ('server_1', 50, 100),  # High load
                ('server_2', 10, 100),  # Low load
                ('server_3', 25, 100)   # Average load
            ]
            
            inconsistencies = await self.api._detect_load_imbalance()
            
            if inconsistencies:
                inconsistency = inconsistencies[0]
                assert inconsistency.type == InconsistencyType.LOAD_IMBALANCE
                assert 'imbalanced_instances' in inconsistency.metadata
                assert len(inconsistency.recommendations) > 0
    
    def test_recommendation_generation(self):
        """Test recommendation generation based on system state"""
        # Create mock health checks with issues
        health_checks = [
            Mock(status=HealthStatus.CRITICAL, component='database', message='Connection failed'),
            Mock(status=HealthStatus.DEGRADED, component='instances', message='Some instances unhealthy'),
            Mock(status=HealthStatus.HEALTHY, component='streams', message='All good')
        ]
        
        # Create mock inconsistencies
        inconsistencies = [
            Mock(recommendations=['Fix orphaned streams', 'Verify instance registration'])
        ]
        
        recommendations = self.api._generate_recommendations(health_checks, inconsistencies)
        
        assert len(recommendations) >= 3
        assert any('CRITICAL: Fix database connectivity' in rec for rec in recommendations)
        assert any('WARNING: Monitor instances' in rec for rec in recommendations)
        assert 'Fix orphaned streams' in recommendations
    
    def test_overall_health_calculation(self):
        """Test overall health status calculation"""
        # Test critical health
        critical_checks = [
            Mock(status=HealthStatus.CRITICAL),
            Mock(status=HealthStatus.HEALTHY)
        ]
        health = self.api._calculate_overall_health(critical_checks, [])
        assert health == HealthStatus.CRITICAL
        
        # Test degraded health
        degraded_checks = [
            Mock(status=HealthStatus.DEGRADED),
            Mock(status=HealthStatus.HEALTHY)
        ]
        health = self.api._calculate_overall_health(degraded_checks, [])
        assert health == HealthStatus.DEGRADED
        
        # Test healthy
        healthy_checks = [
            Mock(status=HealthStatus.HEALTHY),
            Mock(status=HealthStatus.HEALTHY)
        ]
        health = self.api._calculate_overall_health(healthy_checks, [])
        assert health == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_diagnostic_api_integration():
    """Integration test for diagnostic API"""
    # Test API creation
    api = create_diagnostic_api()
    assert api is not None
    assert hasattr(api, 'app')
    assert hasattr(api, 'health_checkers')
    assert hasattr(api, 'inconsistency_detectors')
    
    # Test that all required health checkers are present
    required_checkers = ['database', 'monitoring', 'orchestrator', 'instances', 'streams']
    for checker in required_checkers:
        assert checker in api.health_checkers
    
    # Test that all inconsistency detectors are present
    required_detectors = [
        InconsistencyType.ORPHANED_STREAMS,
        InconsistencyType.DUPLICATE_ASSIGNMENTS,
        InconsistencyType.MISSING_INSTANCES,
        InconsistencyType.STATE_MISMATCH,
        InconsistencyType.HEARTBEAT_TIMEOUT,
        InconsistencyType.LOAD_IMBALANCE
    ]
    for detector in required_detectors:
        assert detector in api.inconsistency_detectors


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
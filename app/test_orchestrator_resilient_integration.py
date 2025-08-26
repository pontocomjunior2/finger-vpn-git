#!/usr/bin/env python3
"""
Integration test for Orchestrator with Resilient functionality

This test verifies that the main orchestrator properly integrates
the resilient orchestrator functionality.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
# Import the main orchestrator
from orchestrator import StreamOrchestrator
from resilient_orchestrator import (FailureRecoveryConfig, HeartbeatConfig,
                                    ResilientOrchestrator, SystemHealthStatus)

logger = logging.getLogger(__name__)


class TestOrchestratorResilientIntegration:
    """Integration tests for orchestrator with resilient functionality"""
    
    @pytest.fixture
    def mock_db_config(self):
        """Mock database configuration"""
        return {
            "host": "localhost",
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",
            "port": 5432
        }
    
    @pytest.fixture
    def orchestrator(self, mock_db_config):
        """Create orchestrator instance with mocked database"""
        with patch('orchestrator.psycopg2.connect'), \
             patch.dict('os.environ', {
                 'HEARTBEAT_TIMEOUT': '60',
                 'HEARTBEAT_WARNING_THRESHOLD': '30',
                 'MAX_RETRY_ATTEMPTS': '2',
                 'CIRCUIT_BREAKER_THRESHOLD': '3'
             }):
            orchestrator = StreamOrchestrator()
            return orchestrator
    
    def test_resilient_orchestrator_initialization(self, orchestrator):
        """Test that resilient orchestrator is properly initialized"""
        # Check if resilient orchestrator was created
        assert orchestrator.resilient_orchestrator is not None
        assert isinstance(orchestrator.resilient_orchestrator, ResilientOrchestrator)
        
        # Check configuration
        heartbeat_config = orchestrator.resilient_orchestrator.heartbeat_config
        assert heartbeat_config.timeout_seconds == 60
        assert heartbeat_config.warning_threshold_seconds == 30
        
        recovery_config = orchestrator.resilient_orchestrator.recovery_config
        assert recovery_config.max_retry_attempts == 2
        assert recovery_config.circuit_breaker_threshold == 3
    
    def test_resilient_database_connection(self, orchestrator):
        """Test that database connections use resilient orchestrator when available"""
        with patch.object(orchestrator.resilient_orchestrator, 'get_db_connection') as mock_resilient_conn, \
             patch('orchestrator.psycopg2.connect') as mock_basic_conn:
            
            # Mock successful resilient connection
            mock_resilient_conn.return_value = Mock()
            
            # Get connection
            conn = orchestrator.get_db_connection()
            
            # Verify resilient connection was used
            mock_resilient_conn.assert_called_once()
            mock_basic_conn.assert_not_called()
    
    def test_resilient_database_connection_fallback(self, orchestrator):
        """Test fallback to basic connection when resilient fails"""
        with patch.object(orchestrator.resilient_orchestrator, 'get_db_connection') as mock_resilient_conn, \
             patch('orchestrator.psycopg2.connect') as mock_basic_conn:
            
            # Mock resilient connection failure
            mock_resilient_conn.side_effect = Exception("Resilient connection failed")
            mock_basic_conn.return_value = Mock()
            
            # Get connection
            conn = orchestrator.get_db_connection()
            
            # Verify fallback was used
            mock_resilient_conn.assert_called_once()
            mock_basic_conn.assert_called_once()
    
    def test_heartbeat_integration_with_resilient_orchestrator(self, orchestrator):
        """Test that heartbeat updates integrate with resilient orchestrator"""
        from orchestrator import HeartbeatRequest, SystemMetrics

        # Create test heartbeat
        heartbeat = HeartbeatRequest(
            server_id="test_server",
            current_streams=5,
            status="active",
            system_metrics=SystemMetrics(
                cpu_percent=50.0,
                memory_percent=60.0,
                memory_used_gb=4.0,
                memory_total_gb=8.0,
                disk_percent=70.0,
                disk_free_gb=100.0,
                disk_total_gb=500.0
            )
        )
        
        with patch.object(orchestrator, 'get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1,)  # Mock instance ID
            
            # Update heartbeat
            result = orchestrator.update_heartbeat(heartbeat)
            
            # Verify heartbeat was recorded in resilient orchestrator
            assert heartbeat.server_id in orchestrator.resilient_orchestrator.instance_heartbeats
            
            # Verify result
            assert result["status"] == "heartbeat_updated"
    
    def test_failed_instance_heartbeat_recovery(self, orchestrator):
        """Test that failed instances can recover through heartbeat"""
        from orchestrator import HeartbeatRequest
        from resilient_orchestrator import InstanceFailureInfo
        
        server_id = "recovery_test_server"
        
        # Add instance to failed instances
        failure_info = InstanceFailureInfo(
            server_id=server_id,
            failure_time=datetime.now() - timedelta(minutes=5),
            failure_reason="Test failure",
            streams_affected=3
        )
        orchestrator.resilient_orchestrator.failed_instances[server_id] = failure_info
        
        # Send heartbeat from previously failed instance
        heartbeat = HeartbeatRequest(
            server_id=server_id,
            current_streams=2,
            status="active"
        )
        
        with patch.object(orchestrator, 'get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (1,)  # Mock instance ID
            
            # Update heartbeat
            result = orchestrator.update_heartbeat(heartbeat)
            
            # Verify heartbeat was recorded
            assert server_id in orchestrator.resilient_orchestrator.instance_heartbeats
            
            # Verify the instance is still in failed instances (recovery happens in monitoring loop)
            assert server_id in orchestrator.resilient_orchestrator.failed_instances
    
    @pytest.mark.asyncio
    async def test_resilient_monitoring_lifecycle_integration(self, orchestrator):
        """Test that resilient monitoring integrates with orchestrator lifecycle"""
        # Mock the monitoring methods
        with patch.object(orchestrator.resilient_orchestrator, 'start_monitoring') as mock_start, \
             patch.object(orchestrator.resilient_orchestrator, 'stop_monitoring') as mock_stop:
            
            # Simulate lifecycle startup
            if orchestrator.resilient_orchestrator:
                await orchestrator.resilient_orchestrator.start_monitoring()
            
            # Verify monitoring was started
            mock_start.assert_called_once()
            
            # Simulate lifecycle shutdown
            if orchestrator.resilient_orchestrator:
                await orchestrator.resilient_orchestrator.stop_monitoring()
            
            # Verify monitoring was stopped
            mock_stop.assert_called_once()
    
    def test_system_health_status_integration(self, orchestrator):
        """Test system health status integration"""
        # Set health status in resilient orchestrator
        orchestrator.resilient_orchestrator.system_health_status = SystemHealthStatus.DEGRADED
        
        # Get resilience status
        status = orchestrator.resilient_orchestrator.get_resilience_status()
        
        # Verify status is properly reported
        assert status["system_health"] == "degraded"
        assert "monitoring_active" in status
        assert "failed_instances" in status
    
    def test_circuit_breaker_integration(self, orchestrator):
        """Test circuit breaker integration with database operations"""
        service_key = "database"
        
        # Test circuit breaker functionality
        assert not orchestrator.resilient_orchestrator._is_circuit_breaker_open(service_key)
        
        # Trigger circuit breaker
        for _ in range(orchestrator.resilient_orchestrator.recovery_config.circuit_breaker_threshold):
            orchestrator.resilient_orchestrator._record_circuit_breaker_failure(service_key)
        
        # Verify circuit breaker is open
        assert orchestrator.resilient_orchestrator._is_circuit_breaker_open(service_key)
        
        # Reset circuit breaker
        orchestrator.resilient_orchestrator._reset_circuit_breaker(service_key)
        assert not orchestrator.resilient_orchestrator._is_circuit_breaker_open(service_key)
    
    @pytest.mark.asyncio
    async def test_emergency_recovery_integration(self, orchestrator):
        """Test emergency recovery integration"""
        server_id = "emergency_test_server"
        reason = "Integration test emergency"
        
        # Mock database operations for emergency recovery
        with patch.object(orchestrator.resilient_orchestrator, 'get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            
            # Trigger emergency recovery
            result = await orchestrator.resilient_orchestrator.trigger_emergency_recovery(server_id, reason)
            
            # Verify result
            assert result["status"] == "success"
            assert server_id in result["message"]
    
    def test_configuration_environment_integration(self, orchestrator):
        """Test that configuration is properly loaded from environment"""
        # Verify environment variables were used
        heartbeat_config = orchestrator.resilient_orchestrator.heartbeat_config
        recovery_config = orchestrator.resilient_orchestrator.recovery_config
        
        # These should match the values set in the fixture
        assert heartbeat_config.timeout_seconds == 60
        assert heartbeat_config.warning_threshold_seconds == 30
        assert recovery_config.max_retry_attempts == 2
        assert recovery_config.circuit_breaker_threshold == 3


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v"])
#!/usr/bin/env python3
"""
Comprehensive Test Suite for Monitoring System

This module provides comprehensive tests for the monitoring and alerting system,
including unit tests, integration tests, and performance tests.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from monitoring_api import MonitoringAPI, create_monitoring_api
from monitoring_config import AlertRuleConfig, MonitoringConfigManager
from monitoring_dashboard import AlertNotificationSystem, MonitoringDashboard
from monitoring_integration import (MonitoredOperation,
                                    OrchestratorMonitoringMixin,
                                    SystemHealthChecker, WorkerMonitoringMixin)
from monitoring_system import (Alert, AlertManager, AlertSeverity,
                               FailureEvent, FailurePattern, Metric,
                               MetricsCollector, MetricType, MonitoringSystem,
                               PatternDetector, create_monitoring_system)


class TestMonitoringSystem:
    """Test suite for MonitoringSystem"""
    
    @pytest.fixture
    def monitoring_system(self):
        """Create monitoring system for testing"""
        return create_monitoring_system()
    
    def test_monitoring_system_initialization(self, monitoring_system):
        """Test monitoring system initialization"""
        assert monitoring_system is not None
        assert monitoring_system.metrics_collector is not None
        assert monitoring_system.pattern_detector is not None
        assert monitoring_system.alert_manager is not None
        assert not monitoring_system.monitoring_active
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, monitoring_system):
        """Test starting and stopping monitoring"""
        # Start monitoring
        await monitoring_system.start_monitoring()
        assert monitoring_system.monitoring_active
        assert len(monitoring_system.monitoring_tasks) > 0
        
        # Stop monitoring
        await monitoring_system.stop_monitoring()
        assert not monitoring_system.monitoring_active
        assert len(monitoring_system.monitoring_tasks) == 0
    
    def test_record_operation(self, monitoring_system):
        """Test operation recording"""
        # Start operation
        operation_id = monitoring_system.record_operation_start("test_operation")
        assert operation_id is not None
        assert operation_id in monitoring_system.operation_timers
        
        # End operation successfully
        monitoring_system.record_operation_end(operation_id, success=True)
        assert operation_id not in monitoring_system.operation_timers
        assert monitoring_system.operation_counters["test_operation_success"] == 1
    
    def test_record_failure(self, monitoring_system):
        """Test failure recording"""
        monitoring_system.record_failure(
            source="test_source",
            failure_type="test_failure",
            severity=AlertSeverity.WARNING
        )
        
        assert monitoring_system.error_counters["test_source"] == 1
        assert len(monitoring_system.pattern_detector.failure_events) == 1
    
    def test_get_monitoring_status(self, monitoring_system):
        """Test monitoring status retrieval"""
        status = monitoring_system.get_monitoring_status()
        
        assert "monitoring_active" in status
        assert "active_alerts" in status
        assert "performance_summary" in status
        assert "operation_counters" in status


class TestMetricsCollector:
    """Test suite for MetricsCollector"""
    
    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector for testing"""
        return MetricsCollector(retention_hours=1)
    
    def test_record_metric(self, metrics_collector):
        """Test metric recording"""
        metrics_collector.record_metric("test_metric", 100.0, MetricType.GAUGE)
        
        assert "test_metric" in metrics_collector.metrics
        assert len(metrics_collector.metrics["test_metric"]) == 1
        assert metrics_collector.metrics["test_metric"][0].value == 100.0
    
    def test_record_response_time(self, metrics_collector):
        """Test response time recording"""
        metrics_collector.record_response_time("test_op", 150.0)
        
        assert len(metrics_collector.performance_metrics.response_times) == 1
        assert metrics_collector.performance_metrics.response_times[0] == 150.0
    
    def test_record_error_rate(self, metrics_collector):
        """Test error rate recording"""
        metrics_collector.record_error_rate("test_op", 5, 100)
        
        assert len(metrics_collector.performance_metrics.error_rates) == 1
        assert metrics_collector.performance_metrics.error_rates[0] == 0.05
    
    def test_get_performance_summary(self, metrics_collector):
        """Test performance summary"""
        # Add some test data
        metrics_collector.record_response_time("test", 100.0)
        metrics_collector.record_response_time("test", 200.0)
        metrics_collector.record_error_rate("test", 1, 10)
        
        summary = metrics_collector.get_performance_summary()
        
        assert "avg_response_time" in summary
        assert "p95_response_time" in summary
        assert "avg_error_rate" in summary
        assert summary["avg_response_time"] == 150.0


class TestPatternDetector:
    """Test suite for PatternDetector"""
    
    @pytest.fixture
    def pattern_detector(self):
        """Create pattern detector for testing"""
        return PatternDetector(window_size=50)
    
    def test_add_failure_event(self, pattern_detector):
        """Test adding failure events"""
        event = FailureEvent(
            timestamp=datetime.now(),
            source="test_source",
            failure_type="test_failure",
            severity=AlertSeverity.WARNING
        )
        
        pattern_detector.add_failure_event(event)
        assert len(pattern_detector.failure_events) == 1
    
    def test_detect_cascading_failures(self, pattern_detector):
        """Test cascading failure detection"""
        # Add multiple failures from different sources
        current_time = datetime.now()
        
        for i in range(6):
            for source in ["source1", "source2", "source3"]:
                event = FailureEvent(
                    timestamp=current_time - timedelta(seconds=i*10),
                    source=source,
                    failure_type="connection_error",
                    severity=AlertSeverity.WARNING
                )
                pattern_detector.add_failure_event(event)
        
        patterns = pattern_detector.detect_patterns()
        
        # Should detect cascading failures
        cascading_patterns = [p for p, _ in patterns if p == FailurePattern.CASCADING_FAILURES]
        assert len(cascading_patterns) > 0
    
    def test_detect_network_partition(self, pattern_detector):
        """Test network partition detection"""
        current_time = datetime.now()
        
        # Add network-related failures
        for i in range(5):
            event = FailureEvent(
                timestamp=current_time - timedelta(seconds=i*30),
                source=f"instance_{i}",
                failure_type="network_timeout",
                severity=AlertSeverity.WARNING
            )
            pattern_detector.add_failure_event(event)
        
        patterns = pattern_detector.detect_patterns()
        
        # Should detect network partition
        network_patterns = [p for p, _ in patterns if p == FailurePattern.NETWORK_PARTITION]
        assert len(network_patterns) > 0


class TestAlertManager:
    """Test suite for AlertManager"""
    
    @pytest.fixture
    def alert_manager(self):
        """Create alert manager for testing"""
        return AlertManager()
    
    def test_create_alert(self, alert_manager):
        """Test alert creation"""
        alert = alert_manager.create_alert(
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            description="This is a test alert",
            source="test_source"
        )
        
        assert alert is not None
        assert alert.id in alert_manager.active_alerts
        assert len(alert_manager.alert_history) == 1
    
    def test_resolve_alert(self, alert_manager):
        """Test alert resolution"""
        alert = alert_manager.create_alert(
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            description="This is a test alert",
            source="test_source"
        )
        
        success = alert_manager.resolve_alert(alert.id)
        
        assert success
        assert alert.id not in alert_manager.active_alerts
        assert alert.resolved
        assert alert.resolved_at is not None
    
    def test_get_active_alerts(self, alert_manager):
        """Test getting active alerts"""
        # Create alerts with different severities
        alert_manager.create_alert(AlertSeverity.WARNING, "Warning", "Test", "source1")
        alert_manager.create_alert(AlertSeverity.CRITICAL, "Critical", "Test", "source2")
        
        all_alerts = alert_manager.get_active_alerts()
        critical_alerts = alert_manager.get_active_alerts(AlertSeverity.CRITICAL)
        
        assert len(all_alerts) == 2
        assert len(critical_alerts) == 1
        assert critical_alerts[0].severity == AlertSeverity.CRITICAL


class TestMonitoringAPI:
    """Test suite for MonitoringAPI"""
    
    @pytest.fixture
    def monitoring_api(self):
        """Create monitoring API for testing"""
        monitoring_system = create_monitoring_system()
        return create_monitoring_api(monitoring_system)
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, monitoring_api):
        """Test health endpoint"""
        # Mock the health check
        with patch.object(monitoring_api.monitoring_system, 'monitoring_active', True):
            # This would require a test client to properly test
            # For now, just verify the API object is created correctly
            assert monitoring_api.app is not None
            assert monitoring_api.monitoring_system is not None


class TestMonitoringIntegration:
    """Test suite for monitoring integration"""
    
    def test_orchestrator_monitoring_mixin(self):
        """Test orchestrator monitoring mixin"""
        
        class TestOrchestrator(OrchestratorMonitoringMixin):
            def __init__(self):
                super().__init__()
        
        orchestrator = TestOrchestrator()
        orchestrator.initialize_monitoring()
        
        assert orchestrator.monitoring_system is not None
        assert orchestrator._monitoring_initialized
    
    def test_worker_monitoring_mixin(self):
        """Test worker monitoring mixin"""
        
        class TestWorker(WorkerMonitoringMixin):
            def __init__(self):
                super().__init__()
        
        worker = TestWorker()
        worker.initialize_monitoring()
        
        assert worker.monitoring_system is not None
        assert worker._monitoring_initialized
    
    def test_monitored_operation(self):
        """Test monitored operation context manager"""
        monitoring_system = create_monitoring_system()
        
        with MonitoredOperation(monitoring_system, "test_operation") as op:
            assert op.operation_id is not None
            time.sleep(0.1)  # Simulate work
        
        # Operation should be recorded
        assert len(monitoring_system.operation_counters) > 0


class TestMonitoringConfig:
    """Test suite for monitoring configuration"""
    
    @pytest.fixture
    def config_manager(self):
        """Create config manager for testing"""
        return MonitoringConfigManager("test_config.json")
    
    def test_config_initialization(self, config_manager):
        """Test configuration initialization"""
        config = config_manager.get_config()
        
        assert config is not None
        assert config.retention_hours > 0
        assert len(config.alert_rules) > 0
    
    def test_add_alert_rule(self, config_manager):
        """Test adding alert rule"""
        rule = AlertRuleConfig(
            name="test_rule",
            metric_name="test_metric",
            threshold=100.0,
            severity="warning"
        )
        
        config_manager.add_alert_rule(rule)
        
        assert "test_rule" in config_manager.config.alert_rules
        assert config_manager.config.alert_rules["test_rule"].threshold == 100.0
    
    def test_config_validation(self, config_manager):
        """Test configuration validation"""
        validation = config_manager.validate_config()
        
        assert "valid" in validation
        assert "warnings" in validation
        assert "errors" in validation


class TestMonitoringDashboard:
    """Test suite for monitoring dashboard"""
    
    @pytest.fixture
    def dashboard(self):
        """Create dashboard for testing"""
        monitoring_system = create_monitoring_system()
        return MonitoringDashboard(monitoring_system)
    
    def test_dashboard_initialization(self, dashboard):
        """Test dashboard initialization"""
        assert dashboard.monitoring_system is not None
        assert dashboard.template_dir.exists()
    
    def test_generate_dashboard_data(self, dashboard):
        """Test dashboard data generation"""
        data = dashboard.generate_dashboard_data()
        
        assert "status" in data
        assert "metrics" in data
        assert "timestamp" in data


class TestAlertNotificationSystem:
    """Test suite for alert notification system"""
    
    @pytest.fixture
    def notification_system(self):
        """Create notification system for testing"""
        monitoring_system = create_monitoring_system()
        return AlertNotificationSystem(monitoring_system)
    
    def test_notification_system_initialization(self, notification_system):
        """Test notification system initialization"""
        assert notification_system.monitoring_system is not None
        assert len(notification_system.notification_handlers) > 0
    
    def test_send_notification(self, notification_system):
        """Test sending notifications"""
        alert = Alert(
            id="test_alert",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            description="Test description",
            timestamp=datetime.now(),
            source="test_source"
        )
        
        notification_system.send_notification(alert)
        
        assert len(notification_system.notification_history) == 1


class TestPerformanceAndLoad:
    """Performance and load tests for monitoring system"""
    
    @pytest.fixture
    def monitoring_system(self):
        """Create monitoring system for performance testing"""
        return create_monitoring_system()
    
    def test_high_volume_metrics(self, monitoring_system):
        """Test handling high volume of metrics"""
        start_time = time.time()
        
        # Record many metrics quickly
        for i in range(1000):
            monitoring_system.metrics_collector.record_metric(
                f"test_metric_{i % 10}",
                float(i),
                MetricType.GAUGE
            )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle 1000 metrics in reasonable time (< 1 second)
        assert duration < 1.0
        assert len(monitoring_system.metrics_collector.metrics) > 0
    
    def test_high_volume_failures(self, monitoring_system):
        """Test handling high volume of failure events"""
        start_time = time.time()
        
        # Record many failures quickly
        for i in range(500):
            monitoring_system.record_failure(
                source=f"source_{i % 5}",
                failure_type="test_failure",
                severity=AlertSeverity.WARNING
            )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle 500 failures in reasonable time
        assert duration < 2.0
        assert len(monitoring_system.pattern_detector.failure_events) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, monitoring_system):
        """Test concurrent monitoring operations"""
        
        async def simulate_operations():
            for i in range(100):
                op_id = monitoring_system.record_operation_start(f"op_{i}")
                await asyncio.sleep(0.001)  # Simulate work
                monitoring_system.record_operation_end(op_id, success=True)
        
        # Run multiple concurrent operation simulations
        tasks = [simulate_operations() for _ in range(5)]
        await asyncio.gather(*tasks)
        
        # Should have recorded all operations
        total_success = sum(
            count for name, count in monitoring_system.operation_counters.items()
            if 'success' in name
        )
        assert total_success == 500


# Integration test scenarios
class TestIntegrationScenarios:
    """Integration test scenarios"""
    
    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow"""
        # Create monitoring system
        monitoring_system = create_monitoring_system()
        
        # Start monitoring
        await monitoring_system.start_monitoring()
        
        try:
            # Simulate some operations and failures
            for i in range(10):
                op_id = monitoring_system.record_operation_start("test_operation")
                await asyncio.sleep(0.01)
                
                if i % 3 == 0:  # Simulate some failures
                    monitoring_system.record_operation_end(op_id, success=False)
                    monitoring_system.record_failure(
                        source="test_source",
                        failure_type="test_failure",
                        severity=AlertSeverity.WARNING
                    )
                else:
                    monitoring_system.record_operation_end(op_id, success=True)
            
            # Wait a bit for monitoring tasks to process
            await asyncio.sleep(0.1)
            
            # Check results
            status = monitoring_system.get_monitoring_status()
            assert status['monitoring_active']
            assert status['operation_counters']['test_operation_success'] > 0
            assert status['operation_counters']['test_operation_error'] > 0
            
        finally:
            # Stop monitoring
            await monitoring_system.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_alert_lifecycle(self):
        """Test complete alert lifecycle"""
        monitoring_system = create_monitoring_system()
        
        # Create alert
        alert = monitoring_system.alert_manager.create_alert(
            severity=AlertSeverity.CRITICAL,
            title="Test Critical Alert",
            description="This is a test critical alert",
            source="integration_test"
        )
        
        # Verify alert is active
        active_alerts = monitoring_system.alert_manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].id == alert.id
        
        # Resolve alert
        success = monitoring_system.alert_manager.resolve_alert(alert.id)
        assert success
        
        # Verify alert is resolved
        active_alerts = monitoring_system.alert_manager.get_active_alerts()
        assert len(active_alerts) == 0
        
        # Check alert history
        history = monitoring_system.alert_manager.get_alert_history()
        assert len(history) == 1
        assert history[0].resolved


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
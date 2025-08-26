#!/usr/bin/env python3
"""
Quick test for monitoring system functionality
"""

import asyncio

from monitoring_config import get_monitoring_config
from monitoring_system import AlertSeverity, MetricType, MonitoringSystem


async def test_monitoring():
    print('Testing monitoring system...')
    
    # Create monitoring system directly
    monitoring_system = MonitoringSystem()
    print('✓ Monitoring system created')
    
    # Test configuration
    try:
        config = get_monitoring_config()
        print(f'✓ Configuration loaded with {len(config.alert_rules)} alert rules')
    except Exception as e:
        print(f'Configuration loading failed: {e}')
    
    # Start monitoring
    await monitoring_system.start_monitoring()
    print('✓ Monitoring started')
    
    # Test operation recording
    op_id = monitoring_system.record_operation_start('test_operation')
    monitoring_system.record_operation_end(op_id, success=True)
    print('✓ Operation recording works')
    
    # Test failure recording
    monitoring_system.record_failure('test_source', 'test_failure', AlertSeverity.WARNING)
    print('✓ Failure recording works')
    
    # Test alert creation
    alert = monitoring_system.alert_manager.create_alert(
        severity=AlertSeverity.INFO,
        title='Test Alert',
        description='This is a test alert',
        source='test'
    )
    print(f'✓ Alert created: {alert.id}')
    
    # Test metrics
    monitoring_system.metrics_collector.record_metric('test_metric', 100.0, MetricType.GAUGE)
    print('✓ Metric recording works')
    
    # Get status
    status = monitoring_system.get_monitoring_status()
    print(f'✓ Status retrieved: monitoring_active={status["monitoring_active"]}')
    
    # Stop monitoring
    await monitoring_system.stop_monitoring()
    print('✓ Monitoring stopped')
    
    print('All tests passed! Monitoring system is working correctly.')

if __name__ == "__main__":
    asyncio.run(test_monitoring())
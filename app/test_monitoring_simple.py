#!/usr/bin/env python3
"""
Simple test to verify monitoring system functionality
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_monitoring_system():
    print("Testing monitoring system components...")
    
    try:
        # Test if we can execute the monitoring_system.py file
        exec(open('monitoring_system.py').read(), globals())
        print("✓ Monitoring system code executed successfully")
        
        # Test if classes are available
        if 'MonitoringSystem' in globals():
            print("✓ MonitoringSystem class is available")
            
            # Create instance
            monitoring_system = MonitoringSystem()
            print("✓ MonitoringSystem instance created")
            
            # Test basic functionality
            op_id = monitoring_system.record_operation_start('test_operation')
            monitoring_system.record_operation_end(op_id, success=True)
            print("✓ Operation recording works")
            
            # Test alert creation
            alert = monitoring_system.alert_manager.create_alert(
                severity=AlertSeverity.INFO,
                title='Test Alert',
                description='This is a test alert',
                source='test'
            )
            print(f"✓ Alert created: {alert.id}")
            
            # Test metrics
            monitoring_system.metrics_collector.record_metric('test_metric', 100.0, MetricType.GAUGE)
            print("✓ Metric recording works")
            
            # Get status
            status = monitoring_system.get_monitoring_status()
            print(f"✓ Status retrieved: monitoring_active={status['monitoring_active']}")
            
            print("All basic tests passed! Monitoring system is working correctly.")
            
        else:
            print("✗ MonitoringSystem class not found")
            
    except Exception as e:
        print(f"✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_monitoring_system()
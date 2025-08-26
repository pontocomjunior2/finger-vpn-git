# Comprehensive Monitoring and Alerting System

This document describes the comprehensive monitoring and alerting system implemented for the orchestrator stream balancing system.

## Overview

The monitoring system provides proactive failure detection, detailed metrics collection, and alerting for critical failures and performance degradation. It addresses requirements 4.1, 4.2, 4.3, and 4.4 from the specification.

## Features

### 1. Proactive Failure Detection with Pattern Analysis

- **Failure Pattern Detection**: Automatically detects patterns like cascading failures, resource exhaustion, network partitions, database contention, heartbeat degradation, and load imbalance
- **Pattern Analysis**: Uses configurable thresholds and time windows to identify concerning trends
- **Confidence Scoring**: Provides confidence levels for detected patterns to prioritize response

### 2. Detailed Metrics Collection for Performance Monitoring

- **Response Time Tracking**: Monitors operation response times with percentile calculations
- **Error Rate Monitoring**: Tracks error rates across different operations and sources
- **Throughput Metrics**: Measures requests per second and processing capacity
- **Resource Usage**: Monitors CPU, memory, and disk usage
- **Custom Metrics**: Supports custom metric types (counters, gauges, histograms, timers)

### 3. Alert System for Critical Failures and Performance Degradation

- **Severity Levels**: INFO, WARNING, CRITICAL, EMERGENCY
- **Configurable Rules**: Customizable alert rules with thresholds and durations
- **Multiple Notification Channels**: Console, file, email (extensible)
- **Alert Lifecycle**: Creation, active monitoring, resolution tracking
- **Alert History**: Maintains history for analysis and reporting

## Architecture

### Core Components

1. **MonitoringSystem**: Main coordinator for all monitoring activities
2. **MetricsCollector**: Collects and manages system metrics
3. **PatternDetector**: Analyzes failure patterns for proactive alerting
4. **AlertManager**: Manages alerts and notifications
5. **MonitoringAPI**: REST API for accessing monitoring data
6. **MonitoringDashboard**: Web-based dashboard for visualization
7. **MonitoringIntegration**: Integration mixins for orchestrator and worker classes

### Data Models

- **Alert**: Represents an alert with severity, title, description, and metadata
- **Metric**: Represents a metric value with timestamp and labels
- **FailureEvent**: Represents a failure event for pattern analysis
- **PerformanceMetrics**: Aggregated performance data

## Installation and Setup

### 1. Basic Setup

```python
from monitoring_system import create_monitoring_system
from setup_monitoring import MonitoringSetup

# Create monitoring system
monitoring_system = create_monitoring_system()

# Start monitoring
await monitoring_system.start_monitoring()
```

### 2. Full Setup with API and Dashboard

```python
from setup_monitoring import MonitoringSetup

setup = MonitoringSetup()

# Setup everything
await setup.setup_monitoring_system()
await setup.setup_monitoring_api(host="0.0.0.0", port=8080)
await setup.setup_dashboard_and_notifications()

# Start monitoring
await setup.start_monitoring()

# Run API server
await setup.run_monitoring_server()
```

### 3. Command Line Setup

```bash
# Setup monitoring system
python setup_monitoring.py --action=setup

# Run monitoring server
python setup_monitoring.py --action=run --host=0.0.0.0 --port=8080

# Validate setup
python setup_monitoring.py --action=validate

# Create example configuration
python setup_monitoring.py --action=config --config-file=my_config.json
```

## Integration with Existing Components

### Orchestrator Integration

```python
from monitoring_integration import add_monitoring_to_orchestrator

# Add monitoring to existing orchestrator class
@add_monitoring_to_orchestrator
class MyOrchestrator:
    def __init__(self):
        super().__init__()
        self.initialize_monitoring()
    
    async def start(self):
        await self.start_monitoring()
        # ... existing code
    
    def register_instance(self, server_id, instance_info):
        with self.monitor_operation("register_instance"):
            # ... existing code
            pass
    
    def handle_instance_failure(self, server_id):
        self.record_instance_failure(server_id, "Connection timeout")
        # ... existing code
```

### Worker Integration

```python
from monitoring_integration import add_monitoring_to_worker

@add_monitoring_to_worker
class MyWorker:
    def __init__(self):
        super().__init__()
        self.initialize_monitoring()
    
    async def start(self):
        await self.start_monitoring()
        # ... existing code
    
    def process_stream(self, stream_id):
        start_time = time.time()
        try:
            # ... processing code
            duration_ms = (time.time() - start_time) * 1000
            self.record_stream_processing(stream_id, duration_ms, True)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.record_stream_processing(stream_id, duration_ms, False, str(e))
            raise
```

## Configuration

### Configuration File Format

```json
{
  "retention_hours": 24,
  "pattern_window_size": 100,
  "monitoring_interval": 30,
  "response_time_warning": 5000.0,
  "response_time_critical": 10000.0,
  "error_rate_warning": 0.1,
  "error_rate_critical": 0.25,
  "resource_usage_warning": 85.0,
  "resource_usage_critical": 95.0,
  "enable_console_notifications": true,
  "enable_file_notifications": true,
  "enable_email_notifications": false,
  "api_host": "0.0.0.0",
  "api_port": 8080,
  "alert_rules": {
    "high_response_time": {
      "name": "high_response_time",
      "metric_name": "response_time",
      "threshold": 5000.0,
      "severity": "warning",
      "duration": 300,
      "enabled": true,
      "description": "Response time exceeds warning threshold"
    }
  }
}
```

### Adding Custom Alert Rules

```python
from monitoring_config import add_custom_alert_rule

# Add custom alert rule
add_custom_alert_rule(
    name="custom_metric_alert",
    metric_name="custom_metric",
    threshold=100.0,
    severity="warning",
    duration=300,
    description="Custom metric exceeds threshold"
)
```

## API Endpoints

### Health and Status

- `GET /health` - System health status
- `GET /status` - Comprehensive monitoring status
- `GET /detailed-metrics` - Detailed metrics for analysis

### Alerts

- `GET /alerts` - Get alerts with filtering options
- `POST /alerts/{alert_id}/resolve` - Resolve an alert
- `POST /test-alert` - Create test alert

### Metrics

- `GET /metrics` - Get metrics with filtering
- `GET /performance` - Performance metrics summary

### Patterns

- `GET /patterns` - Get detected failure patterns

## Dashboard

The web dashboard provides real-time visualization of:

- System health status
- Active alerts
- Performance metrics
- Response time trends
- Detected failure patterns

Access the dashboard at `http://localhost:8080/dashboard.html` when running the API server.

## Failure Pattern Detection

### Supported Patterns

1. **Cascading Failures**: Multiple sources failing simultaneously
2. **Resource Exhaustion**: High resource usage leading to failures
3. **Network Partition**: Network connectivity issues
4. **Database Contention**: Database lock and deadlock issues
5. **Heartbeat Degradation**: Instance health check failures
6. **Load Imbalance**: Uneven distribution of work

### Pattern Configuration

```python
# Configure pattern detection thresholds
pattern_detector.pattern_thresholds[FailurePattern.CASCADING_FAILURES] = {
    'min_events': 5,
    'time_window': 300,  # 5 minutes
    'failure_rate_threshold': 0.8
}
```

## Alerting and Notifications

### Alert Severities

- **INFO**: Informational messages
- **WARNING**: Issues that need attention
- **CRITICAL**: Serious issues requiring immediate action
- **EMERGENCY**: System-threatening issues

### Notification Handlers

```python
def custom_notification_handler(alert):
    # Send to external system
    send_to_slack(alert.title, alert.description)

# Add custom handler
monitoring_system.alert_manager.add_alert_handler(custom_notification_handler)
```

## Performance Considerations

- **Efficient Data Structures**: Uses deques and optimized collections
- **Configurable Retention**: Automatic cleanup of old data
- **Async Processing**: Non-blocking monitoring tasks
- **Resource Monitoring**: Monitors its own resource usage
- **Batch Processing**: Efficient handling of high-volume metrics

## Testing

### Running Tests

```bash
# Run all tests
python -m pytest test_monitoring_system.py -v

# Run specific test categories
python -m pytest test_monitoring_system.py::TestMonitoringSystem -v
python -m pytest test_monitoring_system.py::TestPerformanceAndLoad -v
```

### Test Coverage

- Unit tests for all components
- Integration tests for component interaction
- Performance tests for high-volume scenarios
- End-to-end workflow tests

## Troubleshooting

### Common Issues

1. **High Memory Usage**: Reduce retention_hours or pattern_window_size
2. **Slow Performance**: Increase monitoring_interval or reduce metric frequency
3. **Missing Alerts**: Check alert rule configuration and thresholds
4. **API Errors**: Verify monitoring system is started and healthy

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger('monitoring_system').setLevel(logging.DEBUG)

# Get detailed status
status = monitoring_system.get_detailed_metrics()
print(json.dumps(status, indent=2))
```

## Best Practices

1. **Start Simple**: Begin with default configuration and adjust as needed
2. **Monitor the Monitor**: Keep an eye on monitoring system resource usage
3. **Tune Thresholds**: Adjust alert thresholds based on your system's normal behavior
4. **Regular Validation**: Periodically validate configuration and test alerts
5. **Documentation**: Document custom alert rules and notification handlers

## Future Enhancements

- Machine learning-based anomaly detection
- Predictive failure analysis
- Advanced visualization and reporting
- Integration with external monitoring systems
- Automated remediation actions

## Support

For issues or questions about the monitoring system:

1. Check the logs for error messages
2. Validate configuration using `validate_monitoring_config()`
3. Run the test suite to verify functionality
4. Review this documentation for configuration options

## License

This monitoring system is part of the orchestrator stream balancing project and follows the same licensing terms.
#!/usr/bin/env python3
"""
Core Monitoring and Alerting System

This module provides the essential monitoring functionality for task 6:
- Proactive failure detection with pattern analysis
- Detailed metrics collection for performance monitoring
- Alert system for critical failures and performance degradation

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import json
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class MetricType(Enum):
    """Types of metrics"""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class FailurePattern(Enum):
    """Types of failure patterns"""

    CASCADING_FAILURES = "cascading_failures"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    DATABASE_CONTENTION = "database_contention"
    HEARTBEAT_DEGRADATION = "heartbeat_degradation"
    LOAD_IMBALANCE = "load_imbalance"


@dataclass
class Alert:
    """Alert data structure"""

    id: str
    severity: AlertSeverity
    title: str
    description: str
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class Metric:
    """Metric data structure"""

    name: str
    type: MetricType
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class FailureEvent:
    """Failure event for pattern analysis"""

    timestamp: datetime
    source: str
    failure_type: str
    severity: AlertSeverity
    metadata: Dict[str, Any] = field(default_factory=dict)


class PatternDetector:
    """Detects failure patterns for proactive alerting"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.failure_events: deque = deque(maxlen=window_size)

    def add_failure_event(self, event: FailureEvent):
        """Add failure event for pattern analysis"""
        self.failure_events.append(event)

    def detect_patterns(self) -> List[tuple]:
        """Detect failure patterns in recent events"""
        patterns = []
        current_time = datetime.now()

        # Get recent events (last 5 minutes)
        recent_events = [
            event
            for event in self.failure_events
            if (current_time - event.timestamp).total_seconds() < 300
        ]

        if len(recent_events) >= 5:
            # Check for cascading failures
            sources = set(event.source for event in recent_events)
            if len(sources) >= 3:
                confidence = min(len(sources) / 5, 1.0)
                patterns.append(
                    (
                        FailurePattern.CASCADING_FAILURES,
                        {
                            "confidence": confidence,
                            "failing_sources": list(sources),
                            "event_count": len(recent_events),
                        },
                    )
                )

        # Check for network issues
        network_events = [
            event
            for event in recent_events
            if "network" in event.failure_type.lower()
            or "timeout" in event.failure_type.lower()
        ]

        if len(network_events) >= 3:
            confidence = (
                len(network_events) / len(recent_events) if recent_events else 0
            )
            if confidence >= 0.6:
                patterns.append(
                    (
                        FailurePattern.NETWORK_PARTITION,
                        {
                            "confidence": confidence,
                            "network_events": len(network_events),
                            "total_events": len(recent_events),
                        },
                    )
                )

        return patterns


class MetricsCollector:
    """Collects and manages system metrics"""

    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.metrics: Dict[str, List[Metric]] = defaultdict(list)
        self.response_times: List[float] = []
        self.error_rates: List[float] = []
        self.throughput: List[float] = []

    def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Record a metric value"""
        metric = Metric(
            name=name,
            type=metric_type,
            value=value,
            timestamp=datetime.now(),
            labels=labels or {},
        )

        self.metrics[name].append(metric)
        self._cleanup_old_metrics(name)

    def record_response_time(self, operation: str, time_ms: float):
        """Record response time for an operation"""
        self.record_metric(f"response_time_{operation}", time_ms, MetricType.TIMER)
        self.response_times.append(time_ms)
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]

    def record_error_rate(self, operation: str, error_count: int, total_count: int):
        """Record error rate for an operation"""
        rate = error_count / total_count if total_count > 0 else 0
        self.record_metric(f"error_rate_{operation}", rate, MetricType.GAUGE)
        self.error_rates.append(rate)
        if len(self.error_rates) > 100:
            self.error_rates = self.error_rates[-100:]

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary"""
        return {
            "avg_response_time": (
                statistics.mean(self.response_times) if self.response_times else 0.0
            ),
            "p95_response_time": self._get_percentile(self.response_times, 0.95),
            "avg_error_rate": (
                statistics.mean(self.error_rates) if self.error_rates else 0.0
            ),
            "avg_throughput": (
                statistics.mean(self.throughput) if self.throughput else 0.0
            ),
            "resource_usage": {},
        }

    def _get_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(percentile * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]

    def _cleanup_old_metrics(self, name: str):
        """Clean up old metrics beyond retention period"""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        self.metrics[name] = [
            metric for metric in self.metrics[name] if metric.timestamp >= cutoff_time
        ]


class AlertManager:
    """Manages alerts and notifications"""

    def __init__(self):
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.alert_handlers: List = []

    def create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        description: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """Create and process new alert"""
        alert_id = f"{source}_{int(time.time() * 1000)}"

        alert = Alert(
            id=alert_id,
            severity=severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            source=source,
            metadata=metadata or {},
        )

        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)

        # Keep only last 1000 alerts in history
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]

        # Process alert through handlers
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")

        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.now()
            del self.active_alerts[alert_id]
            return True
        return False

    def get_active_alerts(
        self, severity: Optional[AlertSeverity] = None
    ) -> List[Alert]:
        """Get active alerts, optionally filtered by severity"""
        alerts = list(self.active_alerts.values())
        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def add_alert_handler(self, handler):
        """Add alert handler function"""
        self.alert_handlers.append(handler)


class MonitoringSystem:
    """Main monitoring system coordinating all components"""

    def __init__(self, db_config: Optional[Dict] = None):
        self.db_config = db_config
        self.metrics_collector = MetricsCollector()
        self.pattern_detector = PatternDetector()
        self.alert_manager = AlertManager()

        self.monitoring_active = False
        self.monitoring_tasks: List[asyncio.Task] = []
        self.operation_timers: Dict[str, float] = {}
        self.operation_counters: Dict[str, int] = defaultdict(int)
        self.error_counters: Dict[str, int] = defaultdict(int)

        # Setup default alert handlers
        self.alert_manager.add_alert_handler(self._log_alert_handler)

    def _log_alert_handler(self, alert: Alert):
        """Log alert to system logger"""
        level_map = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.ERROR,
            AlertSeverity.EMERGENCY: logging.CRITICAL,
        }
        level = level_map.get(alert.severity, logging.INFO)
        logger.log(
            level,
            f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}",
        )

    async def start_monitoring(self):
        """Start monitoring tasks"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self._start_time = datetime.now()

        # Start monitoring tasks
        tasks = [
            self._pattern_analysis_task(),
            self._performance_monitoring_task(),
            self._system_health_task(),
        ]

        self.monitoring_tasks = [asyncio.create_task(task) for task in tasks]

        # Create startup alert
        self.alert_manager.create_alert(
            severity=AlertSeverity.INFO,
            title="Monitoring System Started",
            description="Comprehensive monitoring and alerting system is now active",
            source="monitoring_system",
        )

        logger.info("Monitoring system started")

    async def stop_monitoring(self):
        """Stop monitoring tasks"""
        self.monitoring_active = False

        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.monitoring_tasks.clear()
        logger.info("Monitoring system stopped")

    async def _pattern_analysis_task(self):
        """Background task for pattern analysis"""
        while self.monitoring_active:
            try:
                patterns = self.pattern_detector.detect_patterns()

                for pattern, info in patterns:
                    confidence = info.get("confidence", 0)
                    severity = (
                        AlertSeverity.CRITICAL
                        if confidence > 0.8
                        else AlertSeverity.WARNING
                    )

                    self.alert_manager.create_alert(
                        severity=severity,
                        title=f"Failure Pattern Detected: {pattern.value}",
                        description=f"Detected {pattern.value} pattern with confidence {confidence:.2f}",
                        source="pattern_detector",
                        metadata={
                            "pattern": pattern.value,
                            "confidence": confidence,
                            "details": info,
                        },
                    )

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error in pattern analysis: {e}")
                await asyncio.sleep(10)

    async def _performance_monitoring_task(self):
        """Background task for performance monitoring"""
        while self.monitoring_active:
            try:
                # Check performance metrics
                summary = self.metrics_collector.get_performance_summary()

                # Check response time
                avg_response_time = summary.get("avg_response_time", 0)
                if avg_response_time > 5000:  # 5 seconds
                    self.alert_manager.create_alert(
                        severity=AlertSeverity.WARNING,
                        title="High Response Time",
                        description=f"Average response time is {avg_response_time:.1f}ms",
                        source="performance_monitor",
                        metadata={"avg_response_time": avg_response_time},
                    )

                # Check error rate
                avg_error_rate = summary.get("avg_error_rate", 0)
                if avg_error_rate > 0.1:  # 10% error rate
                    severity = (
                        AlertSeverity.CRITICAL
                        if avg_error_rate > 0.25
                        else AlertSeverity.WARNING
                    )
                    self.alert_manager.create_alert(
                        severity=severity,
                        title="High Error Rate",
                        description=f"Error rate is {avg_error_rate:.1%}",
                        source="performance_monitor",
                        metadata={"avg_error_rate": avg_error_rate},
                    )

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(10)

    async def _system_health_task(self):
        """Background task for system health monitoring"""
        while self.monitoring_active:
            try:
                # Check for high failure rates
                recent_failures = [
                    event
                    for event in self.pattern_detector.failure_events
                    if (datetime.now() - event.timestamp).total_seconds()
                    < 300  # Last 5 minutes
                ]

                if len(recent_failures) > 10:
                    self.alert_manager.create_alert(
                        severity=AlertSeverity.CRITICAL,
                        title="High Failure Rate Detected",
                        description=f"Detected {len(recent_failures)} failures in the last 5 minutes",
                        source="system_health_monitor",
                        metadata={"failure_count": len(recent_failures)},
                    )

                await asyncio.sleep(120)  # Check every 2 minutes

            except Exception as e:
                logger.error(f"Error in system health monitoring: {e}")
                await asyncio.sleep(30)

    def record_operation_start(self, operation: str) -> str:
        """Record the start of an operation"""
        operation_id = f"{operation}_{int(time.time() * 1000000)}"
        self.operation_timers[operation_id] = time.time()
        return operation_id

    def record_operation_end(self, operation_id: str, success: bool = True):
        """Record the end of an operation"""
        if operation_id in self.operation_timers:
            start_time = self.operation_timers[operation_id]
            duration_ms = (time.time() - start_time) * 1000

            operation = operation_id.split("_")[0]
            self.metrics_collector.record_response_time(operation, duration_ms)

            if success:
                self.operation_counters[f"{operation}_success"] += 1
            else:
                self.operation_counters[f"{operation}_error"] += 1
                self.error_counters[operation] += 1

                # Record failure event
                failure_event = FailureEvent(
                    timestamp=datetime.now(),
                    source=operation,
                    failure_type=f"{operation}_error",
                    severity=AlertSeverity.WARNING,
                )
                self.pattern_detector.add_failure_event(failure_event)

            del self.operation_timers[operation_id]

    def record_failure(
        self,
        source: str,
        failure_type: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record a failure event"""
        failure_event = FailureEvent(
            timestamp=datetime.now(),
            source=source,
            failure_type=failure_type,
            severity=severity,
            metadata=metadata or {},
        )
        self.pattern_detector.add_failure_event(failure_event)
        self.error_counters[source] += 1

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring status"""
        return {
            "monitoring_active": self.monitoring_active,
            "active_alerts": len(self.alert_manager.get_active_alerts()),
            "critical_alerts": len(
                self.alert_manager.get_active_alerts(AlertSeverity.CRITICAL)
            ),
            "performance_summary": self.metrics_collector.get_performance_summary(),
            "recent_patterns": [
                {"pattern": pattern.value, "info": info}
                for pattern, info in self.pattern_detector.detect_patterns()
            ],
            "operation_counters": dict(self.operation_counters),
            "error_counters": dict(self.error_counters),
        }


def create_monitoring_system(db_config: Optional[Dict] = None) -> MonitoringSystem:
    """Create and configure monitoring system"""
    return MonitoringSystem(db_config)


# Example usage
if __name__ == "__main__":

    async def demo():
        # Create monitoring system
        monitoring = create_monitoring_system()

        # Start monitoring
        await monitoring.start_monitoring()

        # Simulate some operations
        for i in range(5):
            op_id = monitoring.record_operation_start("test_operation")
            await asyncio.sleep(0.1)
            monitoring.record_operation_end(op_id, success=i % 3 != 0)

        # Simulate some failures
        for i in range(3):
            monitoring.record_failure(
                "test_source", "connection_error", AlertSeverity.WARNING
            )

        # Wait a bit for processing
        await asyncio.sleep(2)

        # Get status
        status = monitoring.get_monitoring_status()
        print("Monitoring Status:")
        print(f"  Active: {status['monitoring_active']}")
        print(f"  Active Alerts: {status['active_alerts']}")
        print(f"  Critical Alerts: {status['critical_alerts']}")
        print(f"  Operations: {status['operation_counters']}")
        print(f"  Errors: {status['error_counters']}")

        # Stop monitoring
        await monitoring.stop_monitoring()

    asyncio.run(demo())

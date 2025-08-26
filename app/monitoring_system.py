#!/usr/bin/env python3
"""
Comprehensive Monitoring and Alerting System

This module provides proactive failure detection, detailed metrics collection,
and alerting for critical failures and performance degradation.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import json
import logging
import os
import statistics
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

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
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'severity': self.severity.value,
            'title': self.title,
            'description': self.description,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'metadata': self.metadata,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
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
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'type': self.type.value,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'labels': self.labels
        }

@dataclass
class PerformanceMetrics:
    """Performance metrics collection"""
    response_times: List[float] = field(default_factory=list)
    error_rates: List[float] = field(default_factory=list)
    throughput: List[float] = field(default_factory=list)
    resource_usage: Dict[str, List[float]] = field(default_factory=dict)
    
    def add_response_time(self, time_ms: float):
        """Add response time measurement"""
        self.response_times.append(time_ms)
        # Keep only last 1000 measurements
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]
    
    def add_error_rate(self, rate: float):
        """Add error rate measurement"""
        self.error_rates.append(rate)
        if len(self.error_rates) > 100:
            self.error_rates = self.error_rates[-100:]
    
    def add_throughput(self, tps: float):
        """Add throughput measurement"""
        self.throughput.append(tps)
        if len(self.throughput) > 100:
            self.throughput = self.throughput[-100:]
    
    def get_avg_response_time(self) -> float:
        """Get average response time"""
        return statistics.mean(self.response_times) if self.response_times else 0.0
    
    def get_p95_response_time(self) -> float:
        """Get 95th percentile response time"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(0.95 * len(sorted_times))
        return sorted_times[index] if index < len(sorted_times) else sorted_times[-1]


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
        self.pattern_thresholds = {
            FailurePattern.CASCADING_FAILURES: {
                'min_events': 5,
                'time_window': 300,  # 5 minutes
                'failure_rate_threshold': 0.8
            },
            FailurePattern.RESOURCE_EXHAUSTION: {
                'min_events': 3,
                'time_window': 600,  # 10 minutes
                'resource_threshold': 0.9
            },
            FailurePattern.NETWORK_PARTITION: {
                'min_events': 3,
                'time_window': 180,  # 3 minutes
                'network_error_ratio': 0.7
            },
            FailurePattern.DATABASE_CONTENTION: {
                'min_events': 4,
                'time_window': 240,  # 4 minutes
                'db_error_ratio': 0.6
            },
            FailurePattern.HEARTBEAT_DEGRADATION: {
                'min_events': 3,
                'time_window': 300,  # 5 minutes
                'heartbeat_failure_ratio': 0.5
            },
            FailurePattern.LOAD_IMBALANCE: {
                'min_events': 2,
                'time_window': 600,  # 10 minutes
                'imbalance_threshold': 0.3
            }
        }
    
    def add_failure_event(self, event: FailureEvent):
        """Add failure event for pattern analysis"""
        self.failure_events.append(event)
    
    def detect_patterns(self) -> List[Tuple[FailurePattern, Dict[str, Any]]]:
        """Detect failure patterns in recent events"""
        detected_patterns = []
        current_time = datetime.now()
        
        for pattern, config in self.pattern_thresholds.items():
            pattern_info = self._analyze_pattern(pattern, config, current_time)
            if pattern_info:
                detected_patterns.append((pattern, pattern_info))
        
        return detected_patterns
    
    def _analyze_pattern(self, pattern: FailurePattern, config: Dict, current_time: datetime) -> Optional[Dict[str, Any]]:
        """Analyze specific failure pattern"""
        time_window = timedelta(seconds=config['time_window'])
        cutoff_time = current_time - time_window
        
        # Get recent events within time window
        recent_events = [
            event for event in self.failure_events
            if event.timestamp >= cutoff_time
        ]
        
        if len(recent_events) < config['min_events']:
            return None
        
        # Pattern-specific analysis
        if pattern == FailurePattern.CASCADING_FAILURES:
            return self._detect_cascading_failures(recent_events, config)
        elif pattern == FailurePattern.RESOURCE_EXHAUSTION:
            return self._detect_resource_exhaustion(recent_events, config)
        elif pattern == FailurePattern.NETWORK_PARTITION:
            return self._detect_network_partition(recent_events, config)
        elif pattern == FailurePattern.DATABASE_CONTENTION:
            return self._detect_database_contention(recent_events, config)
        elif pattern == FailurePattern.HEARTBEAT_DEGRADATION:
            return self._detect_heartbeat_degradation(recent_events, config)
        elif pattern == FailurePattern.LOAD_IMBALANCE:
            return self._detect_load_imbalance(recent_events, config)
        
        return None
    
    def _detect_cascading_failures(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect cascading failure pattern"""
        # Group events by source
        source_failures = defaultdict(int)
        for event in events:
            source_failures[event.source] += 1
        
        # Check if multiple sources are failing
        failing_sources = [source for source, count in source_failures.items() if count >= 2]
        
        if len(failing_sources) >= 3:  # Multiple sources failing
            failure_rate = len(events) / len(self.failure_events) if self.failure_events else 0
            
            if failure_rate >= config['failure_rate_threshold']:
                return {
                    'failing_sources': failing_sources,
                    'failure_rate': failure_rate,
                    'total_events': len(events),
                    'confidence': min(failure_rate * len(failing_sources) / 5, 1.0)
                }
        
        return None
    
    def _detect_resource_exhaustion(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect resource exhaustion pattern"""
        resource_events = [
            event for event in events
            if 'resource_usage' in event.metadata or 'memory' in event.failure_type.lower() or 'cpu' in event.failure_type.lower()
        ]
        
        if len(resource_events) >= config['min_events']:
            return {
                'resource_events': len(resource_events),
                'total_events': len(events),
                'confidence': len(resource_events) / len(events)
            }
        
        return None
    
    def _detect_network_partition(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect network partition pattern"""
        network_events = [
            event for event in events
            if 'network' in event.failure_type.lower() or 'connection' in event.failure_type.lower() or 'timeout' in event.failure_type.lower()
        ]
        
        network_ratio = len(network_events) / len(events) if events else 0
        
        if network_ratio >= config['network_error_ratio']:
            return {
                'network_events': len(network_events),
                'network_ratio': network_ratio,
                'confidence': network_ratio
            }
        
        return None
    
    def _detect_database_contention(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect database contention pattern"""
        db_events = [
            event for event in events
            if 'database' in event.failure_type.lower() or 'deadlock' in event.failure_type.lower() or 'lock' in event.failure_type.lower()
        ]
        
        db_ratio = len(db_events) / len(events) if events else 0
        
        if db_ratio >= config['db_error_ratio']:
            return {
                'database_events': len(db_events),
                'db_ratio': db_ratio,
                'confidence': db_ratio
            }
        
        return None
    
    def _detect_heartbeat_degradation(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect heartbeat degradation pattern"""
        heartbeat_events = [
            event for event in events
            if 'heartbeat' in event.failure_type.lower() or 'health' in event.failure_type.lower()
        ]
        
        heartbeat_ratio = len(heartbeat_events) / len(events) if events else 0
        
        if heartbeat_ratio >= config['heartbeat_failure_ratio']:
            return {
                'heartbeat_events': len(heartbeat_events),
                'heartbeat_ratio': heartbeat_ratio,
                'confidence': heartbeat_ratio
            }
        
        return None
    
    def _detect_load_imbalance(self, events: List[FailureEvent], config: Dict) -> Optional[Dict[str, Any]]:
        """Detect load imbalance pattern"""
        load_events = [
            event for event in events
            if 'load' in event.failure_type.lower() or 'balance' in event.failure_type.lower() or 'capacity' in event.failure_type.lower()
        ]
        
        if len(load_events) >= config['min_events']:
            return {
                'load_events': len(load_events),
                'confidence': len(load_events) / config['min_events']
            }
        
        return None


class MetricsCollector:
    """Collects and manages system metrics"""
    
    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.metrics: Dict[str, List[Metric]] = defaultdict(list)
        self.performance_metrics = PerformanceMetrics()
        self._lock = threading.Lock()
    
    def record_metric(self, name: str, value: float, metric_type: MetricType, labels: Optional[Dict[str, str]] = None):
        """Record a metric value"""
        with self._lock:
            metric = Metric(
                name=name,
                type=metric_type,
                value=value,
                timestamp=datetime.now(),
                labels=labels or {}
            )
            
            self.metrics[name].append(metric)
            
            # Clean old metrics
            self._cleanup_old_metrics(name)
    
    def record_response_time(self, operation: str, time_ms: float):
        """Record response time for an operation"""
        self.record_metric(f"response_time_{operation}", time_ms, MetricType.TIMER)
        self.performance_metrics.add_response_time(time_ms)
    
    def record_error_rate(self, operation: str, error_count: int, total_count: int):
        """Record error rate for an operation"""
        rate = error_count / total_count if total_count > 0 else 0
        self.record_metric(f"error_rate_{operation}", rate, MetricType.GAUGE)
        self.performance_metrics.add_error_rate(rate)
    
    def record_throughput(self, operation: str, requests_per_second: float):
        """Record throughput for an operation"""
        self.record_metric(f"throughput_{operation}", requests_per_second, MetricType.GAUGE)
        self.performance_metrics.add_throughput(requests_per_second)
    
    def record_resource_usage(self, resource: str, usage_percent: float):
        """Record resource usage percentage"""
        self.record_metric(f"resource_usage_{resource}", usage_percent, MetricType.GAUGE)
        
        if resource not in self.performance_metrics.resource_usage:
            self.performance_metrics.resource_usage[resource] = []
        
        self.performance_metrics.resource_usage[resource].append(usage_percent)
        if len(self.performance_metrics.resource_usage[resource]) > 100:
            self.performance_metrics.resource_usage[resource] = self.performance_metrics.resource_usage[resource][-100:]
    
    def increment_counter(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        current_value = self.get_latest_metric_value(name) or 0
        self.record_metric(name, current_value + 1, MetricType.COUNTER, labels)
    
    def get_latest_metric_value(self, name: str) -> Optional[float]:
        """Get the latest value for a metric"""
        with self._lock:
            if name in self.metrics and self.metrics[name]:
                return self.metrics[name][-1].value
        return None
    
    def get_metric_history(self, name: str, hours: int = 1) -> List[Metric]:
        """Get metric history for specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            if name in self.metrics:
                return [
                    metric for metric in self.metrics[name]
                    if metric.timestamp >= cutoff_time
                ]
        return []
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary"""
        return {
            'avg_response_time': self.performance_metrics.get_avg_response_time(),
            'p95_response_time': self.performance_metrics.get_p95_response_time(),
            'avg_error_rate': statistics.mean(self.performance_metrics.error_rates) if self.performance_metrics.error_rates else 0,
            'avg_throughput': statistics.mean(self.performance_metrics.throughput) if self.performance_metrics.throughput else 0,
            'resource_usage': {
                resource: statistics.mean(values) if values else 0
                for resource, values in self.performance_metrics.resource_usage.items()
            }
        }
    
    def _cleanup_old_metrics(self, name: str):
        """Clean up old metrics beyond retention period"""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        self.metrics[name] = [
            metric for metric in self.metrics[name]
            if metric.timestamp >= cutoff_time
        ]


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self, alert_handlers: Optional[List[Callable]] = None):
        self.alert_handlers = alert_handlers or []
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        # Default alert rules
        self._setup_default_alert_rules()
    
    def _setup_default_alert_rules(self):
        """Setup default alerting rules"""
        self.alert_rules = {
            'high_error_rate': {
                'metric': 'error_rate',
                'threshold': 0.1,  # 10% error rate
                'severity': AlertSeverity.WARNING,
                'duration': 300  # 5 minutes
            },
            'critical_error_rate': {
                'metric': 'error_rate',
                'threshold': 0.25,  # 25% error rate
                'severity': AlertSeverity.CRITICAL,
                'duration': 60  # 1 minute
            },
            'high_response_time': {
                'metric': 'response_time',
                'threshold': 5000,  # 5 seconds
                'severity': AlertSeverity.WARNING,
                'duration': 300
            },
            'critical_response_time': {
                'metric': 'response_time',
                'threshold': 10000,  # 10 seconds
                'severity': AlertSeverity.CRITICAL,
                'duration': 60
            },
            'resource_exhaustion': {
                'metric': 'resource_usage',
                'threshold': 90,  # 90% usage
                'severity': AlertSeverity.WARNING,
                'duration': 300
            },
            'critical_resource_exhaustion': {
                'metric': 'resource_usage',
                'threshold': 95,  # 95% usage
                'severity': AlertSeverity.CRITICAL,
                'duration': 60
            }
        }
    
    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add alert handler function"""
        self.alert_handlers.append(handler)
    
    def create_alert(self, severity: AlertSeverity, title: str, description: str, 
                    source: str, metadata: Optional[Dict[str, Any]] = None) -> Alert:
        """Create and process new alert"""
        alert_id = f"{source}_{int(time.time() * 1000)}"
        
        alert = Alert(
            id=alert_id,
            severity=severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            source=source,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            # Keep only last 1000 alerts in history
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]
        
        # Process alert through handlers
        self._process_alert(alert)
        
        return alert
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert"""
        with self._lock:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.now()
                del self.active_alerts[alert_id]
                
                logger.info(f"Alert resolved: {alert.title}")
                return True
        
        return False
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get active alerts, optionally filtered by severity"""
        with self._lock:
            alerts = list(self.active_alerts.values())
            
            if severity:
                alerts = [alert for alert in alerts if alert.severity == severity]
            
            return sorted(alerts, key=lambda a: a.timestamp, reverse=True)
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            return [
                alert for alert in self.alert_history
                if alert.timestamp >= cutoff_time
            ]
    
    def _process_alert(self, alert: Alert):
        """Process alert through all handlers"""
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")


class MonitoringSystem:
    """Main monitoring system coordinating all components"""
    
    def __init__(self, db_config: Optional[Dict] = None):
        self.db_config = db_config
        self.metrics_collector = MetricsCollector()
        self.pattern_detector = PatternDetector()
        self.alert_manager = AlertManager()
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_tasks: List[asyncio.Task] = []
        
        # Performance tracking
        self.operation_timers: Dict[str, float] = {}
        self.operation_counters: Dict[str, int] = defaultdict(int)
        self.error_counters: Dict[str, int] = defaultdict(int)
        
        # Setup default alert handlers
        self._setup_alert_handlers()
        
        logger.info("Monitoring system initialized")
    
    def _setup_alert_handlers(self):
        """Setup default alert handlers"""
        self.alert_manager.add_alert_handler(self._log_alert_handler)
        self.alert_manager.add_alert_handler(self._file_alert_handler)
    
    def _log_alert_handler(self, alert: Alert):
        """Log alert to system logger"""
        level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.ERROR,
            AlertSeverity.EMERGENCY: logging.CRITICAL
        }.get(alert.severity, logging.INFO)
        
        logger.log(level, f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}")
    
    def _file_alert_handler(self, alert: Alert):
        """Write alert to file"""
        try:
            alert_file = "alerts.json"
            
            # Read existing alerts
            alerts = []
            if os.path.exists(alert_file):
                with open(alert_file, 'r') as f:
                    alerts = json.load(f)
            
            # Add new alert
            alerts.append(alert.to_dict())
            
            # Keep only last 500 alerts
            if len(alerts) > 500:
                alerts = alerts[-500:]
            
            # Write back to file
            with open(alert_file, 'w') as f:
                json.dump(alerts, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to write alert to file: {e}")
    
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
            self._alert_evaluation_task(),
            self._system_health_task()
        ]
        
        self.monitoring_tasks = [asyncio.create_task(task) for task in tasks]
        
        # Create startup alert
        self.alert_manager.create_alert(
            severity=AlertSeverity.INFO,
            title="Monitoring System Started",
            description="Comprehensive monitoring and alerting system is now active",
            source="monitoring_system",
            metadata={'start_time': self._start_time.isoformat()}
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
                    await self._handle_detected_pattern(pattern, info)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in pattern analysis: {e}")
                await asyncio.sleep(10)
    
    async def _performance_monitoring_task(self):
        """Background task for performance monitoring"""
        while self.monitoring_active:
            try:
                # Collect system performance metrics
                await self._collect_system_metrics()
                
                await asyncio.sleep(60)  # Collect every minute
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(10)
    
    async def _alert_evaluation_task(self):
        """Background task for alert rule evaluation"""
        while self.monitoring_active:
            try:
                await self._evaluate_alert_rules()
                
                await asyncio.sleep(30)  # Evaluate every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in alert evaluation: {e}")
                await asyncio.sleep(10)
    
    async def _system_health_task(self):
        """Background task for system health monitoring"""
        while self.monitoring_active:
            try:
                await self._monitor_system_health()
                
                await asyncio.sleep(120)  # Check every 2 minutes
                
            except Exception as e:
                logger.error(f"Error in system health monitoring: {e}")
                await asyncio.sleep(30)
    
    async def _handle_detected_pattern(self, pattern: FailurePattern, info: Dict[str, Any]):
        """Handle detected failure pattern"""
        severity = AlertSeverity.WARNING
        
        # Determine severity based on pattern and confidence
        confidence = info.get('confidence', 0)
        if confidence > 0.8:
            severity = AlertSeverity.CRITICAL
        elif confidence > 0.6:
            severity = AlertSeverity.WARNING
        
        # Create alert for detected pattern
        self.alert_manager.create_alert(
            severity=severity,
            title=f"Failure Pattern Detected: {pattern.value}",
            description=f"Detected {pattern.value} pattern with confidence {confidence:.2f}",
            source="pattern_detector",
            metadata={
                'pattern': pattern.value,
                'confidence': confidence,
                'details': info
            }
        )
    
    async def _collect_system_metrics(self):
        """Collect system-wide metrics"""
        try:
            import psutil

            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics_collector.record_resource_usage('cpu', cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics_collector.record_resource_usage('memory', memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.metrics_collector.record_resource_usage('disk', disk_percent)
            
        except ImportError:
            logger.warning("psutil not available for system metrics collection")
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    async def _evaluate_alert_rules(self):
        """Evaluate alert rules against current metrics"""
        for rule_name, rule_config in self.alert_manager.alert_rules.items():
            try:
                await self._evaluate_single_rule(rule_name, rule_config)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule_name}: {e}")
    
    async def _evaluate_single_rule(self, rule_name: str, rule_config: Dict[str, Any]):
        """Evaluate a single alert rule"""
        metric_name = rule_config['metric']
        threshold = rule_config['threshold']
        severity = rule_config['severity']
        duration = rule_config['duration']
        
        # Get recent metrics for the rule
        recent_metrics = self.metrics_collector.get_metric_history(metric_name, hours=1)
        
        if not recent_metrics:
            return
        
        # Check if threshold is exceeded for the specified duration
        current_time = datetime.now()
        violation_start = None
        
        for metric in reversed(recent_metrics):
            if metric.value > threshold:
                if violation_start is None:
                    violation_start = metric.timestamp
            else:
                violation_start = None
                break
        
        # If violation has been ongoing for the specified duration, create alert
        if violation_start and (current_time - violation_start).total_seconds() >= duration:
            # Check if alert already exists for this rule
            existing_alerts = [
                alert for alert in self.alert_manager.get_active_alerts()
                if alert.source == f"rule_{rule_name}"
            ]
            
            if not existing_alerts:
                latest_value = recent_metrics[-1].value
                self.alert_manager.create_alert(
                    severity=severity,
                    title=f"Alert Rule Triggered: {rule_name}",
                    description=f"{metric_name} value {latest_value} exceeds threshold {threshold} for {duration}s",
                    source=f"rule_{rule_name}",
                    metadata={
                        'rule_name': rule_name,
                        'metric_name': metric_name,
                        'current_value': latest_value,
                        'threshold': threshold,
                        'duration': duration,
                        'violation_start': violation_start.isoformat()
                    }
                )
    
    async def _monitor_system_health(self):
        """Monitor overall system health"""
        try:
            # Check for cascading failures
            recent_failures = [
                event for event in self.pattern_detector.failure_events
                if (datetime.now() - event.timestamp).total_seconds() < 300  # Last 5 minutes
            ]
            
            if len(recent_failures) > 10:  # More than 10 failures in 5 minutes
                self.alert_manager.create_alert(
                    severity=AlertSeverity.CRITICAL,
                    title="High Failure Rate Detected",
                    description=f"Detected {len(recent_failures)} failures in the last 5 minutes",
                    source="system_health_monitor",
                    metadata={
                        'failure_count': len(recent_failures),
                        'time_window': 300,
                        'failure_sources': list(set(event.source for event in recent_failures))
                    }
                )
            
            # Check error rate trends
            error_rates = self.metrics_collector.performance_metrics.error_rates
            if len(error_rates) >= 5:
                recent_avg = sum(error_rates[-5:]) / 5
                if recent_avg > 0.15:  # 15% error rate
                    self.alert_manager.create_alert(
                        severity=AlertSeverity.WARNING,
                        title="Elevated Error Rate",
                        description=f"Average error rate over last 5 measurements: {recent_avg:.1%}",
                        source="error_rate_monitor",
                        metadata={'avg_error_rate': recent_avg}
                    )
            
            # Check response time degradation
            response_times = self.metrics_collector.performance_metrics.response_times
            if len(response_times) >= 10:
                recent_avg = sum(response_times[-10:]) / 10
                overall_avg = sum(response_times) / len(response_times)
                
                if recent_avg > overall_avg * 2:  # Recent average is 2x overall average
                    self.alert_manager.create_alert(
                        severity=AlertSeverity.WARNING,
                        title="Response Time Degradation",
                        description=f"Recent response time ({recent_avg:.1f}ms) is significantly higher than average ({overall_avg:.1f}ms)",
                        source="response_time_monitor",
                        metadata={
                            'recent_avg': recent_avg,
                            'overall_avg': overall_avg,
                            'degradation_factor': recent_avg / overall_avg
                        }
                    )
            
            # Check resource usage trends
            for resource, usage_history in self.metrics_collector.performance_metrics.resource_usage.items():
                if len(usage_history) >= 5:
                    recent_avg = sum(usage_history[-5:]) / 5
                    if recent_avg > 85:  # 85% usage
                        severity = AlertSeverity.CRITICAL if recent_avg > 95 else AlertSeverity.WARNING
                        self.alert_manager.create_alert(
                            severity=severity,
                            title=f"High {resource.title()} Usage",
                            description=f"{resource.title()} usage at {recent_avg:.1f}%",
                            source=f"{resource}_monitor",
                            metadata={
                                'resource': resource,
                                'usage_percent': recent_avg,
                                'threshold': 85
                            }
                        )
        
        except Exception as e:
            logger.error(f"Error in system health monitoring: {e}")
    
    def add_custom_alert_rule(self, rule_name: str, metric_name: str, threshold: float, 
                            severity: AlertSeverity, duration: int = 300):
        """Add custom alert rule"""
        self.alert_manager.alert_rules[rule_name] = {
            'metric': metric_name,
            'threshold': threshold,
            'severity': severity,
            'duration': duration
        }
        logger.info(f"Added custom alert rule: {rule_name}")
    
    def remove_alert_rule(self, rule_name: str) -> bool:
        """Remove alert rule"""
        if rule_name in self.alert_manager.alert_rules:
            del self.alert_manager.alert_rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
            return True
        return False
    
    def get_alert_rules(self) -> Dict[str, Dict[str, Any]]:
        """Get all alert rules"""
        return self.alert_manager.alert_rules.copy()
    
    def simulate_failure(self, source: str, failure_type: str, severity: AlertSeverity = AlertSeverity.WARNING):
        """Simulate a failure for testing purposes"""
        self.record_failure(source, failure_type, severity, {'simulated': True})
        logger.info(f"Simulated failure: {source} - {failure_type}")
    
    def get_system_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive system metrics summary"""
        return {
            'monitoring_status': {
                'active': self.monitoring_active,
                'uptime_seconds': (datetime.now() - self._start_time).total_seconds() if hasattr(self, '_start_time') else 0
            },
            'alerts': {
                'active_count': len(self.alert_manager.get_active_alerts()),
                'critical_count': len(self.alert_manager.get_active_alerts(AlertSeverity.CRITICAL)),
                'warning_count': len(self.alert_manager.get_active_alerts(AlertSeverity.WARNING)),
                'total_history': len(self.alert_manager.alert_history)
            },
            'performance': self.metrics_collector.get_performance_summary(),
            'patterns': {
                'detected_count': len(self.pattern_detector.detect_patterns()),
                'failure_events_count': len(self.pattern_detector.failure_events)
            },
            'operations': {
                'success_count': sum(count for name, count in self.operation_counters.items() if 'success' in name),
                'error_count': sum(count for name, count in self.operation_counters.items() if 'error' in name),
                'total_errors_by_source': dict(self.error_counters)
            }
        }
    
    async def export_monitoring_data(self, filepath: str):
        """Export monitoring data to file"""
        try:
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'system_summary': self.get_system_metrics_summary(),
                'detailed_metrics': self.get_detailed_metrics(),
                'alert_rules': self.get_alert_rules()
            }
            
            import json
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Monitoring data exported to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export monitoring data: {e}")
    
    def _evaluate_rule(self, rule_name: str, rule_config: Dict[str, Any]):
        """Evaluate a single alert rule"""
        metric_name = rule_config['metric']
        threshold = rule_config['threshold']
        severity = rule_config['severity']
        
        # Get recent metric values
        recent_metrics = self.metrics_collector.get_metric_history(metric_name, hours=1)
        
        if not recent_metrics:
            return
        
        # Check if threshold is exceeded
        latest_value = recent_metrics[-1].value
        
        if latest_value > threshold:
            # Check if alert already exists
            existing_alerts = [
                alert for alert in self.alert_manager.get_active_alerts()
                if alert.source == f"rule_{rule_name}"
            ]
            
            if not existing_alerts:
                self.alert_manager.create_alert(
                    severity=severity,
                    title=f"Threshold Exceeded: {rule_name}",
                    description=f"{metric_name} value {latest_value} exceeds threshold {threshold}",
                    source=f"rule_{rule_name}",
                    metadata={
                        'metric': metric_name,
                        'value': latest_value,
                        'threshold': threshold,
                        'rule': rule_name
                    }
                )
    
    async def _monitor_system_health(self):
        """Monitor overall system health"""
        try:
            # Check database connectivity if configured
            if self.db_config:
                await self._check_database_health()
            
            # Check for critical resource usage
            await self._check_resource_health()
            
            # Check for error rate spikes
            await self._check_error_rates()
            
        except Exception as e:
            logger.error(f"Error in system health monitoring: {e}")
    
    async def _check_database_health(self):
        """Check database health"""
        try:
            import psycopg2
            
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            start_time = time.time()
            cursor.execute("SELECT 1")
            response_time = (time.time() - start_time) * 1000
            
            cursor.close()
            conn.close()
            
            self.metrics_collector.record_response_time('database_health_check', response_time)
            
            if response_time > 5000:  # 5 seconds
                self.alert_manager.create_alert(
                    severity=AlertSeverity.WARNING,
                    title="Database Response Time High",
                    description=f"Database health check took {response_time:.2f}ms",
                    source="database_monitor",
                    metadata={'response_time': response_time}
                )
                
        except Exception as e:
            self.alert_manager.create_alert(
                severity=AlertSeverity.CRITICAL,
                title="Database Health Check Failed",
                description=f"Database connectivity check failed: {e}",
                source="database_monitor",
                metadata={'error': str(e)}
            )
    
    async def _check_resource_health(self):
        """Check resource health"""
        performance_summary = self.metrics_collector.get_performance_summary()
        
        for resource, usage in performance_summary.get('resource_usage', {}).items():
            if usage > 95:
                self.alert_manager.create_alert(
                    severity=AlertSeverity.CRITICAL,
                    title=f"Critical Resource Usage: {resource}",
                    description=f"{resource} usage at {usage:.1f}%",
                    source="resource_monitor",
                    metadata={'resource': resource, 'usage': usage}
                )
            elif usage > 85:
                self.alert_manager.create_alert(
                    severity=AlertSeverity.WARNING,
                    title=f"High Resource Usage: {resource}",
                    description=f"{resource} usage at {usage:.1f}%",
                    source="resource_monitor",
                    metadata={'resource': resource, 'usage': usage}
                )
    
    async def _check_error_rates(self):
        """Check for error rate spikes"""
        performance_summary = self.metrics_collector.get_performance_summary()
        error_rate = performance_summary.get('avg_error_rate', 0)
        
        if error_rate > 0.25:  # 25% error rate
            self.alert_manager.create_alert(
                severity=AlertSeverity.CRITICAL,
                title="Critical Error Rate",
                description=f"Error rate at {error_rate:.1%}",
                source="error_monitor",
                metadata={'error_rate': error_rate}
            )
        elif error_rate > 0.1:  # 10% error rate
            self.alert_manager.create_alert(
                severity=AlertSeverity.WARNING,
                title="High Error Rate",
                description=f"Error rate at {error_rate:.1%}",
                source="error_monitor",
                metadata={'error_rate': error_rate}
            )   
 
    # Public API methods
    
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
            
            operation = operation_id.split('_')[0]
            self.metrics_collector.record_response_time(operation, duration_ms)
            
            if success:
                self.operation_counters[f"{operation}_success"] += 1
            else:
                self.operation_counters[f"{operation}_error"] += 1
                self.error_counters[operation] += 1
                
                # Record failure event for pattern analysis
                failure_event = FailureEvent(
                    timestamp=datetime.now(),
                    source=operation,
                    failure_type=f"{operation}_error",
                    severity=AlertSeverity.WARNING
                )
                self.pattern_detector.add_failure_event(failure_event)
            
            del self.operation_timers[operation_id]
    
    def record_failure(self, source: str, failure_type: str, severity: AlertSeverity = AlertSeverity.WARNING, metadata: Optional[Dict[str, Any]] = None):
        """Record a failure event"""
        failure_event = FailureEvent(
            timestamp=datetime.now(),
            source=source,
            failure_type=failure_type,
            severity=severity,
            metadata=metadata or {}
        )
        self.pattern_detector.add_failure_event(failure_event)
        
        # Increment error counter
        self.error_counters[source] += 1
        self.metrics_collector.increment_counter(f"failures_{source}")
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring status"""
        return {
            'monitoring_active': self.monitoring_active,
            'active_alerts': len(self.alert_manager.get_active_alerts()),
            'critical_alerts': len(self.alert_manager.get_active_alerts(AlertSeverity.CRITICAL)),
            'performance_summary': self.metrics_collector.get_performance_summary(),
            'recent_patterns': [
                {'pattern': pattern.value, 'info': info}
                for pattern, info in self.pattern_detector.detect_patterns()
            ],
            'operation_counters': dict(self.operation_counters),
            'error_counters': dict(self.error_counters)
        }
    
    def get_detailed_metrics(self) -> Dict[str, Any]:
        """Get detailed metrics for analysis"""
        return {
            'metrics': {
                name: [metric.to_dict() for metric in metrics[-100:]]  # Last 100 values
                for name, metrics in self.metrics_collector.metrics.items()
            },
            'alerts': {
                'active': [alert.to_dict() for alert in self.alert_manager.get_active_alerts()],
                'recent': [alert.to_dict() for alert in self.alert_manager.get_alert_history(hours=24)]
            },
            'patterns': [
                {'pattern': pattern.value, 'info': info}
                for pattern, info in self.pattern_detector.detect_patterns()
            ]
        }


# Factory function for easy instantiation
def create_monitoring_system(db_config: Optional[Dict] = None) -> MonitoringSystem:
    """Create and configure monitoring system"""
    return MonitoringSystem(db_config)

# Factory function for easy instantiation
def create_monitoring_system(db_config: Optional[Dict] = None) -> MonitoringSystem:
    """Create and configure monitoring system"""
    return MonitoringSystem(db_config)
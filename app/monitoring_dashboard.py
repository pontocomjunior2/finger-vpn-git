#!/usr/bin/env python3
"""
Monitoring Dashboard

This module provides a web-based dashboard for visualizing monitoring data,
alerts, and system health in real-time.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonitoringDashboard:
    """Web-based monitoring dashboard"""

    def __init__(self, monitoring_system, template_dir: str = "templates"):
        self.monitoring_system = monitoring_system
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(exist_ok=True)

        # Create dashboard templates
        self._create_dashboard_templates()

    def _create_dashboard_templates(self):
        """Create HTML templates for dashboard"""

        # Main dashboard template
        dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Orchestrator Monitoring Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .metric-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric-value { font-size: 2em; font-weight: bold; color: #3498db; }
        .metric-label { color: #7f8c8d; margin-top: 5px; }
        .alert-critical { border-left: 5px solid #e74c3c; }
        .alert-warning { border-left: 5px solid #f39c12; }
        .alert-info { border-left: 5px solid #3498db; }
        .status-healthy { color: #27ae60; }
        .status-warning { color: #f39c12; }
        .status-critical { color: #e74c3c; }
        .refresh-btn { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #2980b9; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .pattern-item { background: #ecf0f1; padding: 10px; margin: 5px 0; border-radius: 4px; }
        .confidence-high { border-left: 3px solid #e74c3c; }
        .confidence-medium { border-left: 3px solid #f39c12; }
        .confidence-low { border-left: 3px solid #3498db; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Orchestrator Monitoring Dashboard</h1>
            <p>Real-time monitoring and alerting system</p>
            <button class="refresh-btn" onclick="refreshDashboard()">Refresh Data</button>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value" id="active-alerts">-</div>
                <div class="metric-label">Active Alerts</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="avg-response-time">-</div>
                <div class="metric-label">Avg Response Time (ms)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="error-rate">-</div>
                <div class="metric-label">Error Rate (%)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="system-status">-</div>
                <div class="metric-label">System Status</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3>Response Time Trend</h3>
            <canvas id="responseTimeChart" width="400" height="200"></canvas>
        </div>
        
        <div class="chart-container">
            <h3>Active Alerts</h3>
            <div id="alerts-container">Loading alerts...</div>
        </div>
        
        <div class="chart-container">
            <h3>Detected Failure Patterns</h3>
            <div id="patterns-container">Loading patterns...</div>
        </div>
    </div>
    
    <script>
        let responseTimeChart;
        
        async function refreshDashboard() {
            try {
                // Fetch monitoring status
                const statusResponse = await fetch('/status');
                const status = await statusResponse.json();
                
                // Update metrics
                document.getElementById('active-alerts').textContent = status.active_alerts || 0;
                document.getElementById('avg-response-time').textContent = 
                    (status.performance_summary?.avg_response_time || 0).toFixed(1);
                document.getElementById('error-rate').textContent = 
                    ((status.performance_summary?.avg_error_rate || 0) * 100).toFixed(1);
                
                // Update system status
                const statusElement = document.getElementById('system-status');
                if (status.critical_alerts > 0) {
                    statusElement.textContent = 'Critical';
                    statusElement.className = 'metric-value status-critical';
                } else if (status.active_alerts > 0) {
                    statusElement.textContent = 'Warning';
                    statusElement.className = 'metric-value status-warning';
                } else {
                    statusElement.textContent = 'Healthy';
                    statusElement.className = 'metric-value status-healthy';
                }
                
                // Fetch and display alerts
                const alertsResponse = await fetch('/alerts?active_only=true');
                const alerts = await alertsResponse.json();
                displayAlerts(alerts);
                
                // Fetch and display patterns
                const patternsResponse = await fetch('/patterns');
                const patterns = await patternsResponse.json();
                displayPatterns(patterns);
                
                // Update response time chart
                updateResponseTimeChart();
                
            } catch (error) {
                console.error('Failed to refresh dashboard:', error);
            }
        }
        
        function displayAlerts(alerts) {
            const container = document.getElementById('alerts-container');
            if (alerts.length === 0) {
                container.innerHTML = '<p>No active alerts</p>';
                return;
            }
            
            let html = '';
            alerts.forEach(alert => {
                const alertClass = `alert-${alert.severity}`;
                html += `
                    <div class="metric-card ${alertClass}">
                        <h4>${alert.title}</h4>
                        <p>${alert.description}</p>
                        <small>Source: ${alert.source} | ${new Date(alert.timestamp).toLocaleString()}</small>
                    </div>
                `;
            });
            container.innerHTML = html;
        }
        
        function displayPatterns(patterns) {
            const container = document.getElementById('patterns-container');
            if (patterns.length === 0) {
                container.innerHTML = '<p>No failure patterns detected</p>';
                return;
            }
            
            let html = '';
            patterns.forEach(pattern => {
                const confidenceClass = pattern.confidence > 0.8 ? 'confidence-high' : 
                                      pattern.confidence > 0.5 ? 'confidence-medium' : 'confidence-low';
                html += `
                    <div class="pattern-item ${confidenceClass}">
                        <strong>${pattern.pattern.replace('_', ' ').toUpperCase()}</strong>
                        <span style="float: right;">Confidence: ${(pattern.confidence * 100).toFixed(1)}%</span>
                        <br>
                        <small>Detected at: ${new Date(pattern.detected_at).toLocaleString()}</small>
                    </div>
                `;
            });
            container.innerHTML = html;
        }
        
        async function updateResponseTimeChart() {
            try {
                const response = await fetch('/metrics?metric_name=response_time&hours=1');
                const data = await response.json();
                
                if (data.response_time && data.response_time.length > 0) {
                    const labels = data.response_time.map(m => new Date(m.timestamp).toLocaleTimeString());
                    const values = data.response_time.map(m => m.value);
                    
                    if (responseTimeChart) {
                        responseTimeChart.destroy();
                    }
                    
                    const ctx = document.getElementById('responseTimeChart').getContext('2d');
                    responseTimeChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [{
                                label: 'Response Time (ms)',
                                data: values,
                                borderColor: '#3498db',
                                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                tension: 0.1
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                y: {
                                    beginAtZero: true
                                }
                            }
                        }
                    });
                }
            } catch (error) {
                console.error('Failed to update response time chart:', error);
            }
        }
        
        // Auto-refresh every 30 seconds
        setInterval(refreshDashboard, 30000);
        
        // Initial load
        refreshDashboard();
    </script>
</body>
</html>
        """

        with open(self.template_dir / "dashboard.html", "w") as f:
            f.write(dashboard_html)

    def generate_dashboard_data(self) -> Dict[str, Any]:
        """Generate data for dashboard"""
        try:
            status = self.monitoring_system.get_monitoring_status()
            detailed_metrics = self.monitoring_system.get_detailed_metrics()

            return {
                "status": status,
                "metrics": detailed_metrics,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to generate dashboard data: {e}")
            return {"error": str(e)}

    def export_dashboard_report(self, filepath: str):
        """Export dashboard report to file"""
        try:
            report_data = {
                "report_timestamp": datetime.now().isoformat(),
                "dashboard_data": self.generate_dashboard_data(),
                "system_summary": self.monitoring_system.get_system_metrics_summary(),
            }

            with open(filepath, "w") as f:
                json.dump(report_data, f, indent=2, default=str)

            logger.info(f"Dashboard report exported to {filepath}")

        except Exception as e:
            logger.error(f"Failed to export dashboard report: {e}")
            raise


class AlertNotificationSystem:
    """Enhanced alert notification system"""

    def __init__(self, monitoring_system):
        self.monitoring_system = monitoring_system
        self.notification_handlers = []
        self.notification_history = []

        # Setup default notification handlers
        self._setup_default_handlers()

    def _setup_default_handlers(self):
        """Setup default notification handlers"""
        self.add_notification_handler(self._console_notification_handler)
        self.add_notification_handler(self._file_notification_handler)
        self.add_notification_handler(self._email_notification_handler)

    def add_notification_handler(self, handler):
        """Add notification handler"""
        self.notification_handlers.append(handler)

    def _console_notification_handler(self, alert):
        """Console notification handler"""
        severity_colors = {
            "info": "\033[94m",  # Blue
            "warning": "\033[93m",  # Yellow
            "critical": "\033[91m",  # Red
            "emergency": "\033[95m",  # Magenta
        }

        color = severity_colors.get(alert.severity.value, "\033[0m")
        reset = "\033[0m"

        print(f"{color}[{alert.severity.value.upper()}] {alert.title}{reset}")
        print(f"  {alert.description}")
        print(f"  Source: {alert.source} | Time: {alert.timestamp}")
        print("-" * 50)

    def _file_notification_handler(self, alert):
        """File notification handler"""
        try:
            notification_file = "notifications.log"

            with open(notification_file, "a") as f:
                f.write(
                    f"{alert.timestamp.isoformat()} [{alert.severity.value.upper()}] {alert.title}\n"
                )
                f.write(f"  Description: {alert.description}\n")
                f.write(f"  Source: {alert.source}\n")
                f.write(f"  Metadata: {json.dumps(alert.metadata)}\n")
                f.write("-" * 80 + "\n")

        except Exception as e:
            logger.error(f"Failed to write notification to file: {e}")

    def _email_notification_handler(self, alert):
        """Email notification handler (placeholder)"""
        # This would integrate with an email service
        # For now, just log the intent
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]:
            logger.info(f"EMAIL NOTIFICATION: {alert.title} - {alert.description}")

    def send_notification(self, alert):
        """Send notification through all handlers"""
        notification_record = {
            "alert_id": alert.id,
            "timestamp": datetime.now(),
            "handlers_notified": [],
        }

        for handler in self.notification_handlers:
            try:
                handler(alert)
                notification_record["handlers_notified"].append(handler.__name__)
            except Exception as e:
                logger.error(f"Notification handler {handler.__name__} failed: {e}")

        self.notification_history.append(notification_record)

        # Keep only last 1000 notifications
        if len(self.notification_history) > 1000:
            self.notification_history = self.notification_history[-1000:]

    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        return {
            "total_notifications": len(self.notification_history),
            "recent_notifications": len(
                [
                    n
                    for n in self.notification_history
                    if (datetime.now() - n["timestamp"]).total_seconds()
                    < 3600  # Last hour
                ]
            ),
            "handler_count": len(self.notification_handlers),
        }


# Integration function
def setup_comprehensive_monitoring(monitoring_system):
    """Setup comprehensive monitoring with dashboard and notifications"""

    # Create dashboard
    dashboard = MonitoringDashboard(monitoring_system)

    # Create notification system
    notification_system = AlertNotificationSystem(monitoring_system)

    # Add notification handler to alert manager
    monitoring_system.alert_manager.add_alert_handler(
        notification_system.send_notification
    )

    logger.info("Comprehensive monitoring setup complete")

    return {"dashboard": dashboard, "notifications": notification_system}

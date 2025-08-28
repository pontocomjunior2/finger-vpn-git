#!/usr/bin/env python3
"""
Monitoring API Module

This module provides REST API endpoints for accessing monitoring data,
alerts, and system health information.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from monitoring_integration import SystemHealthChecker
from monitoring_system import AlertSeverity, MonitoringSystem, create_monitoring_system
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AlertResponse(BaseModel):
    """Alert response model"""

    id: str
    severity: str
    title: str
    description: str
    timestamp: str
    source: str
    metadata: Dict[str, Any]
    resolved: bool
    resolved_at: Optional[str]


class MetricResponse(BaseModel):
    """Metric response model"""

    name: str
    type: str
    value: float
    timestamp: str
    labels: Dict[str, str]


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    checks: Dict[str, Any]
    timestamp: str
    error: Optional[str] = None


class PerformanceResponse(BaseModel):
    """Performance metrics response model"""

    avg_response_time: float
    p95_response_time: float
    avg_error_rate: float
    avg_throughput: float
    resource_usage: Dict[str, float]


class PatternResponse(BaseModel):
    """Failure pattern response model"""

    pattern: str
    confidence: float
    details: Dict[str, Any]
    detected_at: str


class MonitoringAPI:
    """REST API for monitoring system"""

    def __init__(self, monitoring_system: Optional[MonitoringSystem] = None):
        self.monitoring_system = monitoring_system or create_monitoring_system()
        self.health_checker = SystemHealthChecker(self.monitoring_system)
        self.app = FastAPI(title="Orchestrator Monitoring API", version="1.0.0")
        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes"""

        @self.app.get("/health", response_model=HealthResponse)
        async def get_health():
            """Get system health status"""
            try:
                # Basic health check
                health_status = {
                    "status": "healthy",
                    "checks": {
                        "monitoring_active": self.monitoring_system.monitoring_active,
                        "active_alerts": len(
                            self.monitoring_system.alert_manager.get_active_alerts()
                        ),
                        "critical_alerts": len(
                            self.monitoring_system.alert_manager.get_active_alerts(
                                AlertSeverity.CRITICAL
                            )
                        ),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "timestamp": datetime.now().isoformat(),
                }

                # Check for critical alerts
                critical_alerts = (
                    self.monitoring_system.alert_manager.get_active_alerts(
                        AlertSeverity.CRITICAL
                    )
                )
                if critical_alerts:
                    health_status["status"] = "critical"
                    health_status["checks"]["critical_alert_count"] = len(
                        critical_alerts
                    )

                return HealthResponse(**health_status)

            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return HealthResponse(
                    status="critical",
                    checks={},
                    timestamp=datetime.now().isoformat(),
                    error=str(e),
                )

        @self.app.get("/alerts", response_model=List[AlertResponse])
        async def get_alerts(
            severity: Optional[str] = Query(None, description="Filter by severity"),
            hours: int = Query(24, description="Hours of history to include"),
            active_only: bool = Query(False, description="Show only active alerts"),
        ):
            """Get alerts with optional filtering"""
            try:
                if active_only:
                    alerts = self.monitoring_system.alert_manager.get_active_alerts()
                else:
                    alerts = self.monitoring_system.alert_manager.get_alert_history(
                        hours=hours
                    )

                # Filter by severity if specified
                if severity:
                    try:
                        severity_enum = AlertSeverity(severity.lower())
                        alerts = [
                            alert for alert in alerts if alert.severity == severity_enum
                        ]
                    except ValueError:
                        raise HTTPException(
                            status_code=400, detail=f"Invalid severity: {severity}"
                        )

                return [AlertResponse(**alert.to_dict()) for alert in alerts]

            except Exception as e:
                logger.error(f"Failed to get alerts: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/alerts/{alert_id}/resolve")
        async def resolve_alert(
            alert_id: str = Path(..., description="Alert ID to resolve")
        ):
            """Resolve an active alert"""
            try:
                success = self.monitoring_system.alert_manager.resolve_alert(alert_id)
                if success:
                    return {"message": f"Alert {alert_id} resolved successfully"}
                else:
                    raise HTTPException(
                        status_code=404, detail=f"Alert {alert_id} not found"
                    )

            except Exception as e:
                logger.error(f"Failed to resolve alert {alert_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/metrics", response_model=Dict[str, List[MetricResponse]])
        async def get_metrics(
            metric_name: Optional[str] = Query(
                None, description="Specific metric name"
            ),
            hours: int = Query(1, description="Hours of history to include"),
        ):
            """Get metrics with optional filtering"""
            try:
                if metric_name:
                    metrics_data = {
                        metric_name: self.monitoring_system.metrics_collector.get_metric_history(
                            metric_name, hours
                        )
                    }
                else:
                    # Get all metrics
                    metrics_data = {}
                    for name in self.monitoring_system.metrics_collector.metrics.keys():
                        metrics_data[name] = (
                            self.monitoring_system.metrics_collector.get_metric_history(
                                name, hours
                            )
                        )

                # Convert to response format
                response = {}
                for name, metrics in metrics_data.items():
                    response[name] = [
                        MetricResponse(**metric.to_dict()) for metric in metrics
                    ]

                return response

            except Exception as e:
                logger.error(f"Failed to get metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/performance", response_model=PerformanceResponse)
        async def get_performance():
            """Get performance metrics summary"""
            try:
                summary = (
                    self.monitoring_system.metrics_collector.get_performance_summary()
                )
                return PerformanceResponse(**summary)

            except Exception as e:
                logger.error(f"Failed to get performance metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/patterns", response_model=List[PatternResponse])
        async def get_failure_patterns():
            """Get detected failure patterns"""
            try:
                patterns = self.monitoring_system.pattern_detector.detect_patterns()

                response = []
                for pattern, info in patterns:
                    response.append(
                        PatternResponse(
                            pattern=pattern.value,
                            confidence=info.get("confidence", 0.0),
                            details=info,
                            detected_at=datetime.now().isoformat(),
                        )
                    )

                return response

            except Exception as e:
                logger.error(f"Failed to get failure patterns: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/status")
        async def get_monitoring_status():
            """Get comprehensive monitoring status"""
            try:
                return self.monitoring_system.get_monitoring_status()

            except Exception as e:
                logger.error(f"Failed to get monitoring status: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/detailed-metrics")
        async def get_detailed_metrics():
            """Get detailed metrics for analysis"""
            try:
                return self.monitoring_system.get_detailed_metrics()

            except Exception as e:
                logger.error(f"Failed to get detailed metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/test-alert")
        async def create_test_alert(
            severity: str = Query("info", description="Alert severity"),
            title: str = Query("Test Alert", description="Alert title"),
            description: str = Query(
                "This is a test alert", description="Alert description"
            ),
        ):
            """Create a test alert for testing purposes"""
            try:
                severity_enum = AlertSeverity(severity.lower())
                alert = self.monitoring_system.alert_manager.create_alert(
                    severity=severity_enum,
                    title=title,
                    description=description,
                    source="api_test",
                )
                return {"message": f"Test alert created with ID: {alert.id}"}

            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid severity: {severity}"
                )
            except Exception as e:
                logger.error(f"Failed to create test alert: {e}")
                raise HTTPException(status_code=500, detail=str(e))


# Factory function to create API instance
def create_monitoring_api(
    monitoring_system: Optional[MonitoringSystem] = None,
) -> MonitoringAPI:
    """Create monitoring API instance"""
    return MonitoringAPI(monitoring_system)


# Standalone server function
async def run_monitoring_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    monitoring_system: Optional[MonitoringSystem] = None,
):
    """Run monitoring API server"""
    import uvicorn

    api = create_monitoring_api(monitoring_system)

    # Start monitoring system if not already started
    if not api.monitoring_system.monitoring_active:
        await api.monitoring_system.start_monitoring()

    logger.info(f"Starting monitoring API server on {host}:{port}")

    config = uvicorn.Config(app=api.app, host=host, port=port, log_level="info")

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # Run the monitoring API server
    asyncio.run(run_monitoring_server())

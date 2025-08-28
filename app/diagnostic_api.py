#!/usr/bin/env python3
"""
Comprehensive Diagnostic and Status API

This module provides comprehensive diagnostic endpoints for system health checking,
detailed status reporting with inconsistency detection, and performance metrics APIs
with historical data.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

import asyncio
import json
import logging
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import monitoring and orchestrator components
try:
    from monitoring_system_core import (
        AlertSeverity,
        MonitoringSystem,
        create_monitoring_system,
    )

    HAS_MONITORING = True
except ImportError:
    HAS_MONITORING = False
    MonitoringSystem = None
    AlertSeverity = None

try:
    from monitoring_api import MonitoringAPI, create_monitoring_api

    HAS_MONITORING_API = True
except ImportError:
    HAS_MONITORING_API = False

try:
    import psycopg2
    import psycopg2.extras

    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class InconsistencyType(Enum):
    """Types of system inconsistencies"""

    ORPHANED_STREAMS = "orphaned_streams"
    DUPLICATE_ASSIGNMENTS = "duplicate_assignments"
    MISSING_INSTANCES = "missing_instances"
    STATE_MISMATCH = "state_mismatch"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    LOAD_IMBALANCE = "load_imbalance"


@dataclass
class SystemHealthCheck:
    """System health check result"""

    component: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    response_time_ms: float


@dataclass
class InconsistencyReport:
    """System inconsistency report"""

    type: InconsistencyType
    severity: str
    description: str
    affected_components: List[str]
    recommendations: List[str]
    metadata: Dict[str, Any]
    detected_at: datetime


@dataclass
class PerformanceMetrics:
    """Performance metrics data"""

    metric_name: str
    current_value: float
    average_value: float
    min_value: float
    max_value: float
    percentile_95: float
    trend: str  # "increasing", "decreasing", "stable"
    data_points: int
    time_range_hours: int


class DiagnosticResponse(BaseModel):
    """Diagnostic response model"""

    status: str
    timestamp: str
    checks: List[Dict[str, Any]]
    inconsistencies: List[Dict[str, Any]]
    recommendations: List[str]
    overall_health: str


class StatusResponse(BaseModel):
    """Status response model"""

    system_status: str
    components: Dict[str, Any]
    performance_summary: Dict[str, Any]
    active_alerts: List[Dict[str, Any]]
    timestamp: str


class PerformanceResponse(BaseModel):
    """Performance metrics response model"""

    metrics: List[Dict[str, Any]]
    summary: Dict[str, Any]
    historical_data: Dict[str, List[Dict[str, Any]]]
    timestamp: str


class DiagnosticAPI:
    """Comprehensive diagnostic and status API"""

    def __init__(
        self,
        db_config: Optional[Dict] = None,
        monitoring_system: Optional[MonitoringSystem] = None,
    ):
        self.db_config = db_config or self._get_default_db_config()
        self.monitoring_system = monitoring_system or (
            create_monitoring_system() if HAS_MONITORING else None
        )
        self.app = FastAPI(title="Orchestrator Diagnostic API", version="1.0.0")
        self._setup_routes()

        # Health check components
        self.health_checkers = {
            "database": self._check_database_health,
            "monitoring": self._check_monitoring_health,
            "orchestrator": self._check_orchestrator_health,
            "instances": self._check_instances_health,
            "streams": self._check_streams_health,
        }

        # Inconsistency detectors
        self.inconsistency_detectors = {
            InconsistencyType.ORPHANED_STREAMS: self._detect_orphaned_streams,
            InconsistencyType.DUPLICATE_ASSIGNMENTS: self._detect_duplicate_assignments,
            InconsistencyType.MISSING_INSTANCES: self._detect_missing_instances,
            InconsistencyType.STATE_MISMATCH: self._detect_state_mismatch,
            InconsistencyType.HEARTBEAT_TIMEOUT: self._detect_heartbeat_timeouts,
            InconsistencyType.LOAD_IMBALANCE: self._detect_load_imbalance,
        }

    def _get_default_db_config(self) -> Dict[str, str]:
        """Get default database configuration"""
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "database": os.getenv("DB_NAME", "orchestrator"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", ""),
        }

    def _setup_routes(self):
        """Setup API routes"""

        @self.app.get("/diagnostic/health", response_model=DiagnosticResponse)
        async def comprehensive_health_check():
            """Comprehensive system health check with inconsistency detection"""
            try:
                start_time = time.time()

                # Run all health checks
                health_checks = []
                for component, checker in self.health_checkers.items():
                    try:
                        check_start = time.time()
                        check_result = await checker()
                        check_time = (time.time() - check_start) * 1000

                        health_checks.append(
                            SystemHealthCheck(
                                component=component,
                                status=check_result["status"],
                                message=check_result["message"],
                                details=check_result.get("details", {}),
                                timestamp=datetime.now(),
                                response_time_ms=check_time,
                            )
                        )
                    except Exception as e:
                        logger.error(f"Health check failed for {component}: {e}")
                        health_checks.append(
                            SystemHealthCheck(
                                component=component,
                                status=HealthStatus.CRITICAL,
                                message=f"Health check failed: {str(e)}",
                                details={"error": str(e)},
                                timestamp=datetime.now(),
                                response_time_ms=0,
                            )
                        )

                # Detect inconsistencies
                inconsistencies = await self._detect_all_inconsistencies()

                # Determine overall health
                overall_health = self._calculate_overall_health(
                    health_checks, inconsistencies
                )

                # Generate recommendations
                recommendations = self._generate_recommendations(
                    health_checks, inconsistencies
                )

                total_time = (time.time() - start_time) * 1000

                return DiagnosticResponse(
                    status="completed",
                    timestamp=datetime.now().isoformat(),
                    checks=[asdict(check) for check in health_checks],
                    inconsistencies=[asdict(inc) for inc in inconsistencies],
                    recommendations=recommendations,
                    overall_health=overall_health.value,
                )

            except Exception as e:
                logger.error(f"Comprehensive health check failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Health check failed: {str(e)}"
                )

        @self.app.get("/diagnostic/status", response_model=StatusResponse)
        async def detailed_status():
            """Get detailed system status with component information"""
            try:
                # Get component statuses
                components = {}

                # Database status
                db_status = await self._get_database_status()
                components["database"] = db_status

                # Monitoring status
                if self.monitoring_system:
                    monitoring_status = self.monitoring_system.get_monitoring_status()
                    components["monitoring"] = monitoring_status

                # Orchestrator status
                orchestrator_status = await self._get_orchestrator_status()
                components["orchestrator"] = orchestrator_status

                # Instance status
                instance_status = await self._get_instances_status()
                components["instances"] = instance_status

                # Performance summary
                performance_summary = await self._get_performance_summary()

                # Active alerts
                active_alerts = []
                if self.monitoring_system:
                    alerts = self.monitoring_system.alert_manager.get_active_alerts()
                    active_alerts = [alert.to_dict() for alert in alerts]

                # Determine system status
                system_status = self._determine_system_status(components, active_alerts)

                return StatusResponse(
                    system_status=system_status,
                    components=components,
                    performance_summary=performance_summary,
                    active_alerts=active_alerts,
                    timestamp=datetime.now().isoformat(),
                )

            except Exception as e:
                logger.error(f"Status check failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Status check failed: {str(e)}"
                )

        @self.app.get("/diagnostic/performance", response_model=PerformanceResponse)
        async def performance_metrics(
            hours: int = Query(24, description="Hours of historical data to include"),
            metrics: Optional[str] = Query(
                None, description="Comma-separated list of specific metrics"
            ),
        ):
            """Get performance metrics with historical data"""
            try:
                # Parse requested metrics
                requested_metrics = metrics.split(",") if metrics else None

                # Collect performance metrics
                performance_metrics = await self._collect_performance_metrics(
                    hours, requested_metrics
                )

                # Generate summary
                summary = self._generate_performance_summary(performance_metrics)

                # Get historical data
                historical_data = await self._get_historical_performance_data(
                    hours, requested_metrics
                )

                return PerformanceResponse(
                    metrics=[asdict(metric) for metric in performance_metrics],
                    summary=summary,
                    historical_data=historical_data,
                    timestamp=datetime.now().isoformat(),
                )

            except Exception as e:
                logger.error(f"Performance metrics collection failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Performance metrics failed: {str(e)}"
                )

        @self.app.get("/diagnostic/inconsistencies")
        async def detect_inconsistencies(
            types: Optional[str] = Query(
                None, description="Comma-separated list of inconsistency types to check"
            )
        ):
            """Detect system inconsistencies with specific recommendations"""
            try:
                # Parse requested inconsistency types
                if types:
                    requested_types = [
                        InconsistencyType(t.strip()) for t in types.split(",")
                    ]
                else:
                    requested_types = list(InconsistencyType)

                inconsistencies = []
                for inc_type in requested_types:
                    if inc_type in self.inconsistency_detectors:
                        try:
                            detected = await self.inconsistency_detectors[inc_type]()
                            inconsistencies.extend(detected)
                        except Exception as e:
                            logger.error(
                                f"Inconsistency detection failed for {inc_type}: {e}"
                            )

                return {
                    "inconsistencies": [asdict(inc) for inc in inconsistencies],
                    "total_found": len(inconsistencies),
                    "timestamp": datetime.now().isoformat(),
                }

            except Exception as e:
                logger.error(f"Inconsistency detection failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Inconsistency detection failed: {str(e)}"
                )

        @self.app.post("/diagnostic/fix-inconsistencies")
        async def fix_inconsistencies(
            inconsistency_ids: List[str],
            dry_run: bool = Query(
                False, description="Perform dry run without making changes"
            ),
        ):
            """Fix detected inconsistencies"""
            try:
                results = []

                for inc_id in inconsistency_ids:
                    try:
                        result = await self._fix_inconsistency(inc_id, dry_run)
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Failed to fix inconsistency {inc_id}: {e}")
                        results.append(
                            {
                                "inconsistency_id": inc_id,
                                "status": "failed",
                                "error": str(e),
                            }
                        )

                return {
                    "results": results,
                    "dry_run": dry_run,
                    "timestamp": datetime.now().isoformat(),
                }

            except Exception as e:
                logger.error(f"Fix inconsistencies failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Fix inconsistencies failed: {str(e)}"
                )

        @self.app.get("/diagnostic/recommendations")
        async def get_recommendations():
            """Get system optimization recommendations"""
            try:
                # Run quick health checks
                health_checks = []
                for component, checker in self.health_checkers.items():
                    try:
                        check_result = await checker()
                        health_checks.append(
                            SystemHealthCheck(
                                component=component,
                                status=check_result["status"],
                                message=check_result["message"],
                                details=check_result.get("details", {}),
                                timestamp=datetime.now(),
                                response_time_ms=0,
                            )
                        )
                    except Exception:
                        pass

                # Detect inconsistencies
                inconsistencies = await self._detect_all_inconsistencies()

                # Generate recommendations
                recommendations = self._generate_recommendations(
                    health_checks, inconsistencies
                )

                return {
                    "recommendations": recommendations,
                    "priority_actions": self._get_priority_actions(
                        health_checks, inconsistencies
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

            except Exception as e:
                logger.error(f"Recommendations generation failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Recommendations failed: {str(e)}"
                )

    # Health Check Methods
    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance"""
        try:
            if not HAS_POSTGRES:
                return {
                    "status": HealthStatus.UNKNOWN,
                    "message": "PostgreSQL driver not available",
                    "details": {"error": "psycopg2 not installed"},
                }

            start_time = time.time()

            # Test database connection
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Test basic query
            cursor.execute("SELECT 1")
            cursor.fetchone()

            # Check table existence
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """
            )
            tables = [row[0] for row in cursor.fetchall()]

            # Check for required tables
            required_tables = ["instances", "stream_assignments", "heartbeats"]
            missing_tables = [table for table in required_tables if table not in tables]

            response_time = (time.time() - start_time) * 1000

            cursor.close()
            conn.close()

            if missing_tables:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"Missing required tables: {missing_tables}",
                    "details": {
                        "response_time_ms": response_time,
                        "available_tables": tables,
                        "missing_tables": missing_tables,
                    },
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": "Database connection successful",
                "details": {
                    "response_time_ms": response_time,
                    "available_tables": tables,
                    "table_count": len(tables),
                },
            }

        except Exception as e:
            return {
                "status": HealthStatus.CRITICAL,
                "message": f"Database connection failed: {str(e)}",
                "details": {"error": str(e)},
            }

    async def _check_monitoring_health(self) -> Dict[str, Any]:
        """Check monitoring system health"""
        try:
            if not self.monitoring_system:
                return {
                    "status": HealthStatus.UNKNOWN,
                    "message": "Monitoring system not available",
                    "details": {},
                }

            status = self.monitoring_system.get_monitoring_status()

            if not status["monitoring_active"]:
                return {
                    "status": HealthStatus.CRITICAL,
                    "message": "Monitoring system is not active",
                    "details": status,
                }

            critical_alerts = status.get("critical_alerts", 0)
            if critical_alerts > 0:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"Monitoring system has {critical_alerts} critical alerts",
                    "details": status,
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": "Monitoring system is healthy",
                "details": status,
            }

        except Exception as e:
            return {
                "status": HealthStatus.CRITICAL,
                "message": f"Monitoring health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    async def _check_orchestrator_health(self) -> Dict[str, Any]:
        """Check orchestrator service health"""
        try:
            # This would typically check if orchestrator service is running
            # For now, we'll check basic functionality

            # Check if we can access orchestrator data
            orchestrator_status = await self._get_orchestrator_status()

            if not orchestrator_status.get("active", False):
                return {
                    "status": HealthStatus.CRITICAL,
                    "message": "Orchestrator service is not active",
                    "details": orchestrator_status,
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": "Orchestrator service is healthy",
                "details": orchestrator_status,
            }

        except Exception as e:
            return {
                "status": HealthStatus.CRITICAL,
                "message": f"Orchestrator health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    async def _check_instances_health(self) -> Dict[str, Any]:
        """Check worker instances health"""
        try:
            if not HAS_POSTGRES:
                return {
                    "status": HealthStatus.UNKNOWN,
                    "message": "Cannot check instances without database access",
                    "details": {},
                }

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get instance information
            cursor.execute(
                """
                SELECT server_id, ip, port, max_streams, current_streams, 
                       last_heartbeat, status
                FROM instances
            """
            )
            instances = cursor.fetchall()

            if not instances:
                cursor.close()
                conn.close()
                return {
                    "status": HealthStatus.CRITICAL,
                    "message": "No instances found",
                    "details": {"instance_count": 0},
                }

            # Check instance health
            healthy_instances = 0
            unhealthy_instances = 0
            current_time = datetime.now()

            for instance in instances:
                last_heartbeat = instance["last_heartbeat"]
                if last_heartbeat:
                    time_diff = (current_time - last_heartbeat).total_seconds()
                    if time_diff < 300:  # 5 minutes
                        healthy_instances += 1
                    else:
                        unhealthy_instances += 1
                else:
                    unhealthy_instances += 1

            cursor.close()
            conn.close()

            total_instances = len(instances)
            health_ratio = (
                healthy_instances / total_instances if total_instances > 0 else 0
            )

            if health_ratio < 0.5:
                status = HealthStatus.CRITICAL
                message = (
                    f"Only {healthy_instances}/{total_instances} instances are healthy"
                )
            elif health_ratio < 0.8:
                status = HealthStatus.DEGRADED
                message = f"{healthy_instances}/{total_instances} instances are healthy"
            else:
                status = HealthStatus.HEALTHY
                message = f"All {healthy_instances} instances are healthy"

            return {
                "status": status,
                "message": message,
                "details": {
                    "total_instances": total_instances,
                    "healthy_instances": healthy_instances,
                    "unhealthy_instances": unhealthy_instances,
                    "health_ratio": health_ratio,
                },
            }

        except Exception as e:
            return {
                "status": HealthStatus.CRITICAL,
                "message": f"Instance health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    async def _check_streams_health(self) -> Dict[str, Any]:
        """Check stream assignments health"""
        try:
            if not HAS_POSTGRES:
                return {
                    "status": HealthStatus.UNKNOWN,
                    "message": "Cannot check streams without database access",
                    "details": {},
                }

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Get stream assignment statistics
            cursor.execute(
                """
                SELECT COUNT(*) as total_streams,
                       COUNT(DISTINCT server_id) as assigned_instances,
                       AVG(CASE WHEN server_id IS NOT NULL THEN 1 ELSE 0 END) as assignment_ratio
                FROM stream_assignments
            """
            )
            stream_stats = cursor.fetchone()

            # Check for duplicate assignments
            cursor.execute(
                """
                SELECT stream_id, COUNT(*) as assignment_count
                FROM stream_assignments
                WHERE server_id IS NOT NULL
                GROUP BY stream_id
                HAVING COUNT(*) > 1
            """
            )
            duplicates = cursor.fetchall()

            cursor.close()
            conn.close()

            total_streams = stream_stats[0] if stream_stats else 0
            assigned_instances = stream_stats[1] if stream_stats else 0
            assignment_ratio = stream_stats[2] if stream_stats else 0
            duplicate_count = len(duplicates)

            if duplicate_count > 0:
                status = HealthStatus.CRITICAL
                message = f"Found {duplicate_count} duplicate stream assignments"
            elif assignment_ratio < 0.8:
                status = HealthStatus.DEGRADED
                message = f"Only {assignment_ratio:.1%} of streams are assigned"
            else:
                status = HealthStatus.HEALTHY
                message = f"Stream assignments are healthy"

            return {
                "status": status,
                "message": message,
                "details": {
                    "total_streams": total_streams,
                    "assigned_instances": assigned_instances,
                    "assignment_ratio": assignment_ratio,
                    "duplicate_assignments": duplicate_count,
                },
            }

        except Exception as e:
            return {
                "status": HealthStatus.CRITICAL,
                "message": f"Stream health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    # Inconsistency Detection Methods
    async def _detect_orphaned_streams(self) -> List[InconsistencyReport]:
        """Detect streams assigned to non-existent instances"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT sa.stream_id, sa.server_id
                FROM stream_assignments sa
                LEFT JOIN instances i ON sa.server_id = i.server_id
                WHERE sa.server_id IS NOT NULL AND i.server_id IS NULL
            """
            )
            orphaned = cursor.fetchall()

            cursor.close()
            conn.close()

            if orphaned:
                inconsistencies.append(
                    InconsistencyReport(
                        type=InconsistencyType.ORPHANED_STREAMS,
                        severity="critical",
                        description=f"Found {len(orphaned)} streams assigned to non-existent instances",
                        affected_components=["stream_assignments", "instances"],
                        recommendations=[
                            "Reassign orphaned streams to active instances",
                            "Clean up invalid assignments",
                            "Verify instance registration process",
                        ],
                        metadata={
                            "orphaned_count": len(orphaned),
                            "orphaned_streams": [
                                {"stream_id": s[0], "server_id": s[1]} for s in orphaned
                            ],
                        },
                        detected_at=datetime.now(),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to detect orphaned streams: {e}")

        return inconsistencies

    async def _detect_duplicate_assignments(self) -> List[InconsistencyReport]:
        """Detect streams assigned to multiple instances"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT stream_id, array_agg(server_id) as server_ids, COUNT(*) as assignment_count
                FROM stream_assignments
                WHERE server_id IS NOT NULL
                GROUP BY stream_id
                HAVING COUNT(*) > 1
            """
            )
            duplicates = cursor.fetchall()

            cursor.close()
            conn.close()

            if duplicates:
                inconsistencies.append(
                    InconsistencyReport(
                        type=InconsistencyType.DUPLICATE_ASSIGNMENTS,
                        severity="critical",
                        description=f"Found {len(duplicates)} streams with duplicate assignments",
                        affected_components=["stream_assignments"],
                        recommendations=[
                            "Resolve duplicate assignments by keeping only one",
                            "Implement assignment conflict resolution",
                            "Review assignment logic for race conditions",
                        ],
                        metadata={
                            "duplicate_count": len(duplicates),
                            "duplicates": [
                                {
                                    "stream_id": d[0],
                                    "server_ids": d[1],
                                    "assignment_count": d[2],
                                }
                                for d in duplicates
                            ],
                        },
                        detected_at=datetime.now(),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to detect duplicate assignments: {e}")

        return inconsistencies

    async def _detect_missing_instances(self) -> List[InconsistencyReport]:
        """Detect instances that should be active but are missing"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check for instances with recent heartbeats but marked as inactive
            cursor.execute(
                """
                SELECT server_id, last_heartbeat, status
                FROM instances
                WHERE last_heartbeat > NOW() - INTERVAL '5 minutes'
                AND status != 'active'
            """
            )
            missing_active = cursor.fetchall()

            cursor.close()
            conn.close()

            if missing_active:
                inconsistencies.append(
                    InconsistencyReport(
                        type=InconsistencyType.MISSING_INSTANCES,
                        severity="warning",
                        description=f"Found {len(missing_active)} instances with recent heartbeats but inactive status",
                        affected_components=["instances"],
                        recommendations=[
                            "Update instance status to active",
                            "Review instance status update logic",
                            "Check for status synchronization issues",
                        ],
                        metadata={
                            "missing_active_count": len(missing_active),
                            "instances": [
                                {
                                    "server_id": i[0],
                                    "last_heartbeat": (
                                        i[1].isoformat() if i[1] else None
                                    ),
                                    "status": i[2],
                                }
                                for i in missing_active
                            ],
                        },
                        detected_at=datetime.now(),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to detect missing instances: {e}")

        return inconsistencies

    async def _detect_state_mismatch(self) -> List[InconsistencyReport]:
        """Detect state mismatches between components"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check for stream count mismatches
            cursor.execute(
                """
                SELECT i.server_id, i.current_streams, 
                       COUNT(sa.stream_id) as actual_streams
                FROM instances i
                LEFT JOIN stream_assignments sa ON i.server_id = sa.server_id
                GROUP BY i.server_id, i.current_streams
                HAVING i.current_streams != COUNT(sa.stream_id)
            """
            )
            mismatches = cursor.fetchall()

            cursor.close()
            conn.close()

            if mismatches:
                inconsistencies.append(
                    InconsistencyReport(
                        type=InconsistencyType.STATE_MISMATCH,
                        severity="warning",
                        description=f"Found {len(mismatches)} instances with stream count mismatches",
                        affected_components=["instances", "stream_assignments"],
                        recommendations=[
                            "Synchronize stream counts between instances and assignments",
                            "Implement periodic state reconciliation",
                            "Review stream assignment update logic",
                        ],
                        metadata={
                            "mismatch_count": len(mismatches),
                            "mismatches": [
                                {
                                    "server_id": m[0],
                                    "reported_streams": m[1],
                                    "actual_streams": m[2],
                                }
                                for m in mismatches
                            ],
                        },
                        detected_at=datetime.now(),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to detect state mismatches: {e}")

        return inconsistencies

    async def _detect_heartbeat_timeouts(self) -> List[InconsistencyReport]:
        """Detect instances with heartbeat timeouts"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check for instances with old heartbeats but still marked as active
            cursor.execute(
                """
                SELECT server_id, last_heartbeat, status, current_streams
                FROM instances
                WHERE status = 'active'
                AND (last_heartbeat IS NULL OR last_heartbeat < NOW() - INTERVAL '5 minutes')
            """
            )
            timeout_instances = cursor.fetchall()

            cursor.close()
            conn.close()

            if timeout_instances:
                inconsistencies.append(
                    InconsistencyReport(
                        type=InconsistencyType.HEARTBEAT_TIMEOUT,
                        severity="critical",
                        description=f"Found {len(timeout_instances)} active instances with heartbeat timeouts",
                        affected_components=["instances", "heartbeats"],
                        recommendations=[
                            "Mark timed-out instances as inactive",
                            "Redistribute streams from timed-out instances",
                            "Check network connectivity to instances",
                            "Review heartbeat timeout configuration",
                        ],
                        metadata={
                            "timeout_count": len(timeout_instances),
                            "timeout_instances": [
                                {
                                    "server_id": i[0],
                                    "last_heartbeat": (
                                        i[1].isoformat() if i[1] else None
                                    ),
                                    "status": i[2],
                                    "current_streams": i[3],
                                }
                                for i in timeout_instances
                            ],
                        },
                        detected_at=datetime.now(),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to detect heartbeat timeouts: {e}")

        return inconsistencies

    async def _detect_load_imbalance(self) -> List[InconsistencyReport]:
        """Detect load imbalance between instances"""
        inconsistencies = []

        try:
            if not HAS_POSTGRES:
                return inconsistencies

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Get stream distribution across active instances
            cursor.execute(
                """
                SELECT server_id, current_streams, max_streams
                FROM instances
                WHERE status = 'active'
                ORDER BY current_streams DESC
            """
            )
            instances = cursor.fetchall()

            cursor.close()
            conn.close()

            if len(instances) > 1:
                stream_counts = [i[1] for i in instances if i[1] is not None]

                if stream_counts:
                    max_streams = max(stream_counts)
                    min_streams = min(stream_counts)
                    avg_streams = sum(stream_counts) / len(stream_counts)

                    # Check for significant imbalance (more than 20% difference from average)
                    imbalance_threshold = avg_streams * 0.2
                    imbalanced_instances = [
                        i
                        for i in instances
                        if i[1] is not None
                        and abs(i[1] - avg_streams) > imbalance_threshold
                    ]

                    if imbalanced_instances:
                        inconsistencies.append(
                            InconsistencyReport(
                                type=InconsistencyType.LOAD_IMBALANCE,
                                severity="warning",
                                description=f"Load imbalance detected: {len(imbalanced_instances)} instances significantly deviate from average",
                                affected_components=["instances", "stream_assignments"],
                                recommendations=[
                                    "Execute load rebalancing",
                                    "Review load balancing algorithm",
                                    "Check for instance capacity constraints",
                                    "Consider gradual stream migration",
                                ],
                                metadata={
                                    "max_streams": max_streams,
                                    "min_streams": min_streams,
                                    "avg_streams": avg_streams,
                                    "imbalance_threshold": imbalance_threshold,
                                    "imbalanced_instances": [
                                        {
                                            "server_id": i[0],
                                            "current_streams": i[1],
                                            "max_streams": i[2],
                                            "deviation_from_avg": i[1] - avg_streams,
                                        }
                                        for i in imbalanced_instances
                                    ],
                                },
                                detected_at=datetime.now(),
                            )
                        )

        except Exception as e:
            logger.error(f"Failed to detect load imbalance: {e}")

        return inconsistencies

    # Helper Methods for Status and Performance
    async def _get_database_status(self) -> Dict[str, Any]:
        """Get detailed database status"""
        try:
            if not HAS_POSTGRES:
                return {
                    "status": "unavailable",
                    "message": "PostgreSQL driver not available",
                    "connection_pool": {"active": 0, "idle": 0},
                    "performance": {},
                }

            start_time = time.time()
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Get database size and statistics
            cursor.execute(
                """
                SELECT 
                    pg_database_size(current_database()) as db_size,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') as idle_connections
            """
            )
            db_stats = cursor.fetchone()

            # Get table statistics
            cursor.execute(
                """
                SELECT 
                    schemaname,
                    tablename,
                    n_tup_ins as inserts,
                    n_tup_upd as updates,
                    n_tup_del as deletes,
                    n_live_tup as live_tuples,
                    n_dead_tup as dead_tuples
                FROM pg_stat_user_tables
                ORDER BY n_live_tup DESC
                LIMIT 10
            """
            )
            table_stats = cursor.fetchall()

            response_time = (time.time() - start_time) * 1000

            cursor.close()
            conn.close()

            return {
                "status": "healthy",
                "connection_time_ms": response_time,
                "database_size_bytes": db_stats[0] if db_stats else 0,
                "connections": {
                    "active": db_stats[1] if db_stats else 0,
                    "idle": db_stats[2] if db_stats else 0,
                },
                "table_statistics": [
                    {
                        "schema": row[0],
                        "table": row[1],
                        "inserts": row[2],
                        "updates": row[3],
                        "deletes": row[4],
                        "live_tuples": row[5],
                        "dead_tuples": row[6],
                    }
                    for row in table_stats
                ],
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "connection_time_ms": 0,
                "connections": {"active": 0, "idle": 0},
            }

    async def _get_orchestrator_status(self) -> Dict[str, Any]:
        """Get orchestrator service status"""
        try:
            if not HAS_POSTGRES:
                return {
                    "active": False,
                    "message": "Cannot check orchestrator status without database access",
                }

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Check if orchestrator tables exist and have recent activity
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_instances,
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_instances,
                    COUNT(CASE WHEN last_heartbeat > NOW() - INTERVAL '5 minutes' THEN 1 END) as recent_heartbeats
                FROM instances
            """
            )
            instance_stats = cursor.fetchone()

            # Check stream assignments
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_streams,
                    COUNT(CASE WHEN server_id IS NOT NULL THEN 1 END) as assigned_streams
                FROM stream_assignments
            """
            )
            stream_stats = cursor.fetchone()

            cursor.close()
            conn.close()

            total_instances = instance_stats[0] if instance_stats else 0
            active_instances = instance_stats[1] if instance_stats else 0
            recent_heartbeats = instance_stats[2] if instance_stats else 0

            return {
                "active": total_instances > 0,
                "total_instances": total_instances,
                "active_instances": active_instances,
                "recent_heartbeats": recent_heartbeats,
                "total_streams": stream_stats[0] if stream_stats else 0,
                "assigned_streams": stream_stats[1] if stream_stats else 0,
                "health_score": (
                    (recent_heartbeats / total_instances) if total_instances > 0 else 0
                ),
            }

        except Exception as e:
            return {
                "active": False,
                "message": f"Error checking orchestrator status: {str(e)}",
            }

    async def _get_instances_status(self) -> Dict[str, Any]:
        """Get detailed instances status"""
        try:
            if not HAS_POSTGRES:
                return {"total_instances": 0, "instances": [], "summary": {}}

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute(
                """
                SELECT 
                    server_id,
                    ip,
                    port,
                    max_streams,
                    current_streams,
                    status,
                    last_heartbeat,
                    EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
                FROM instances
                ORDER BY last_heartbeat DESC
            """
            )
            instances = cursor.fetchall()

            cursor.close()
            conn.close()

            # Categorize instances
            healthy = []
            unhealthy = []
            inactive = []

            for instance in instances:
                instance_data = dict(instance)
                seconds_since = instance_data.get(
                    "seconds_since_heartbeat", float("inf")
                )

                if seconds_since is None or seconds_since > 300:  # 5 minutes
                    unhealthy.append(instance_data)
                elif instance_data.get("status") != "active":
                    inactive.append(instance_data)
                else:
                    healthy.append(instance_data)

            return {
                "total_instances": len(instances),
                "healthy_instances": len(healthy),
                "unhealthy_instances": len(unhealthy),
                "inactive_instances": len(inactive),
                "instances": [dict(instance) for instance in instances],
                "summary": {
                    "health_ratio": len(healthy) / len(instances) if instances else 0,
                    "total_streams": sum(
                        i.get("current_streams", 0) or 0 for i in instances
                    ),
                    "total_capacity": sum(
                        i.get("max_streams", 0) or 0 for i in instances
                    ),
                    "utilization": (
                        (
                            sum(i.get("current_streams", 0) or 0 for i in instances)
                            / sum(i.get("max_streams", 0) or 0 for i in instances)
                        )
                        if sum(i.get("max_streams", 0) or 0 for i in instances) > 0
                        else 0
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Failed to get instances status: {e}")
            return {
                "total_instances": 0,
                "instances": [],
                "summary": {},
                "error": str(e),
            }

    async def _get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary"""
        try:
            if self.monitoring_system:
                return (
                    self.monitoring_system.metrics_collector.get_performance_summary()
                )
            else:
                # Basic performance metrics without monitoring system
                return {
                    "avg_response_time": 0.0,
                    "p95_response_time": 0.0,
                    "avg_error_rate": 0.0,
                    "avg_throughput": 0.0,
                    "resource_usage": {},
                    "note": "Monitoring system not available",
                }
        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            return {
                "error": str(e),
                "avg_response_time": 0.0,
                "p95_response_time": 0.0,
                "avg_error_rate": 0.0,
                "avg_throughput": 0.0,
            }

    async def _collect_performance_metrics(
        self, hours: int, requested_metrics: Optional[List[str]]
    ) -> List[PerformanceMetrics]:
        """Collect performance metrics for specified time range"""
        metrics = []

        try:
            if not self.monitoring_system:
                return metrics

            # Get available metrics
            available_metrics = list(
                self.monitoring_system.metrics_collector.metrics.keys()
            )

            if requested_metrics:
                metrics_to_collect = [
                    m for m in requested_metrics if m in available_metrics
                ]
            else:
                metrics_to_collect = available_metrics

            for metric_name in metrics_to_collect:
                metric_history = self.monitoring_system.metrics_collector.metrics.get(
                    metric_name, []
                )

                # Filter by time range
                cutoff_time = datetime.now() - timedelta(hours=hours)
                recent_metrics = [
                    m for m in metric_history if m.timestamp >= cutoff_time
                ]

                if recent_metrics:
                    values = [m.value for m in recent_metrics]

                    # Calculate statistics
                    current_value = recent_metrics[-1].value
                    avg_value = statistics.mean(values)
                    min_value = min(values)
                    max_value = max(values)

                    # Calculate percentile
                    sorted_values = sorted(values)
                    p95_index = int(0.95 * len(sorted_values))
                    percentile_95 = sorted_values[
                        min(p95_index, len(sorted_values) - 1)
                    ]

                    # Determine trend
                    if len(values) >= 2:
                        recent_avg = statistics.mean(values[-min(10, len(values)) :])
                        older_avg = statistics.mean(values[: min(10, len(values))])

                        if recent_avg > older_avg * 1.1:
                            trend = "increasing"
                        elif recent_avg < older_avg * 0.9:
                            trend = "decreasing"
                        else:
                            trend = "stable"
                    else:
                        trend = "stable"

                    metrics.append(
                        PerformanceMetrics(
                            metric_name=metric_name,
                            current_value=current_value,
                            average_value=avg_value,
                            min_value=min_value,
                            max_value=max_value,
                            percentile_95=percentile_95,
                            trend=trend,
                            data_points=len(recent_metrics),
                            time_range_hours=hours,
                        )
                    )

        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {e}")

        return metrics

    async def _get_historical_performance_data(
        self, hours: int, requested_metrics: Optional[List[str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get historical performance data"""
        historical_data = {}

        try:
            if not self.monitoring_system:
                return historical_data

            available_metrics = list(
                self.monitoring_system.metrics_collector.metrics.keys()
            )

            if requested_metrics:
                metrics_to_collect = [
                    m for m in requested_metrics if m in available_metrics
                ]
            else:
                metrics_to_collect = available_metrics

            cutoff_time = datetime.now() - timedelta(hours=hours)

            for metric_name in metrics_to_collect:
                metric_history = self.monitoring_system.metrics_collector.metrics.get(
                    metric_name, []
                )
                recent_metrics = [
                    m for m in metric_history if m.timestamp >= cutoff_time
                ]

                historical_data[metric_name] = [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "value": m.value,
                        "labels": m.labels,
                    }
                    for m in recent_metrics
                ]

        except Exception as e:
            logger.error(f"Failed to get historical performance data: {e}")

        return historical_data

    def _determine_system_status(
        self, components: Dict[str, Any], active_alerts: List[Dict[str, Any]]
    ) -> str:
        """Determine overall system status based on components and alerts"""
        # Check for critical alerts
        critical_alerts = [
            alert for alert in active_alerts if alert.get("severity") == "critical"
        ]
        if critical_alerts:
            return "critical"

        # Check component health
        unhealthy_components = []
        for component, status in components.items():
            if isinstance(status, dict):
                if (
                    status.get("status") == "error"
                    or status.get("status") == "critical"
                ):
                    unhealthy_components.append(component)
                elif (
                    status.get("status") == "degraded"
                    or status.get("health_ratio", 1.0) < 0.8
                ):
                    unhealthy_components.append(component)

        if len(unhealthy_components) >= 2:
            return "critical"
        elif len(unhealthy_components) == 1:
            return "degraded"
        elif len(active_alerts) > 0:
            return "warning"
        else:
            return "healthy"

    def _generate_performance_summary(
        self, performance_metrics: List[PerformanceMetrics]
    ) -> Dict[str, Any]:
        """Generate performance summary from metrics"""
        if not performance_metrics:
            return {
                "total_metrics": 0,
                "healthy_metrics": 0,
                "degraded_metrics": 0,
                "critical_metrics": 0,
            }

        healthy = 0
        degraded = 0
        critical = 0

        for metric in performance_metrics:
            # Simple heuristic for metric health
            if metric.trend == "increasing" and "error" in metric.metric_name.lower():
                critical += 1
            elif (
                metric.trend == "increasing"
                and "response_time" in metric.metric_name.lower()
            ):
                if metric.current_value > metric.average_value * 2:
                    critical += 1
                elif metric.current_value > metric.average_value * 1.5:
                    degraded += 1
                else:
                    healthy += 1
            else:
                healthy += 1

        return {
            "total_metrics": len(performance_metrics),
            "healthy_metrics": healthy,
            "degraded_metrics": degraded,
            "critical_metrics": critical,
            "overall_performance_score": (
                (healthy + degraded * 0.5) / len(performance_metrics)
                if performance_metrics
                else 1.0
            ),
        }

    async def _detect_all_inconsistencies(self) -> List[InconsistencyReport]:
        """Detect all types of inconsistencies"""
        all_inconsistencies = []

        for detector in self.inconsistency_detectors.values():
            try:
                inconsistencies = await detector()
                all_inconsistencies.extend(inconsistencies)
            except Exception as e:
                logger.error(f"Inconsistency detector failed: {e}")

        return all_inconsistencies

    def _calculate_overall_health(
        self,
        health_checks: List[SystemHealthCheck],
        inconsistencies: List[InconsistencyReport],
    ) -> HealthStatus:
        """Calculate overall system health"""
        # Count health statuses
        critical_count = sum(
            1 for check in health_checks if check.status == HealthStatus.CRITICAL
        )
        degraded_count = sum(
            1 for check in health_checks if check.status == HealthStatus.DEGRADED
        )

        # Count critical inconsistencies
        critical_inconsistencies = sum(
            1 for inc in inconsistencies if inc.severity == "critical"
        )

        if critical_count > 0 or critical_inconsistencies > 0:
            return HealthStatus.CRITICAL
        elif degraded_count > 0 or len(inconsistencies) > 0:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY

    def _generate_recommendations(
        self,
        health_checks: List[SystemHealthCheck],
        inconsistencies: List[InconsistencyReport],
    ) -> List[str]:
        """Generate system recommendations based on health checks and inconsistencies"""
        recommendations = []

        # Recommendations based on health checks
        for check in health_checks:
            if check.status == HealthStatus.CRITICAL:
                if check.component == "database":
                    recommendations.append(
                        f"CRITICAL: Fix database connectivity issues - {check.message}"
                    )
                elif check.component == "instances":
                    recommendations.append(
                        f"CRITICAL: Address instance health problems - {check.message}"
                    )
                elif check.component == "streams":
                    recommendations.append(
                        f"CRITICAL: Resolve stream assignment issues - {check.message}"
                    )
            elif check.status == HealthStatus.DEGRADED:
                recommendations.append(
                    f"WARNING: Monitor {check.component} - {check.message}"
                )

        # Recommendations based on inconsistencies
        for inconsistency in inconsistencies:
            recommendations.extend(inconsistency.recommendations)

        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return unique_recommendations

    def _get_priority_actions(
        self,
        health_checks: List[SystemHealthCheck],
        inconsistencies: List[InconsistencyReport],
    ) -> List[Dict[str, Any]]:
        """Get priority actions based on system state"""
        priority_actions = []

        # Critical health issues
        critical_checks = [
            check for check in health_checks if check.status == HealthStatus.CRITICAL
        ]
        for check in critical_checks:
            priority_actions.append(
                {
                    "priority": "critical",
                    "action": f"Fix {check.component} issues",
                    "description": check.message,
                    "component": check.component,
                }
            )

        # Critical inconsistencies
        critical_inconsistencies = [
            inc for inc in inconsistencies if inc.severity == "critical"
        ]
        for inc in critical_inconsistencies:
            priority_actions.append(
                {
                    "priority": "critical",
                    "action": f"Resolve {inc.type.value}",
                    "description": inc.description,
                    "component": "consistency",
                }
            )

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priority_actions.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return priority_actions

    async def _fix_inconsistency(
        self, inconsistency_id: str, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Fix a specific inconsistency (placeholder implementation)"""
        # This is a placeholder - actual implementation would depend on the specific inconsistency
        return {
            "inconsistency_id": inconsistency_id,
            "status": "not_implemented",
            "message": "Inconsistency fixing not yet implemented",
            "dry_run": dry_run,
        }


# Factory function to create diagnostic API
def create_diagnostic_api(
    db_config: Optional[Dict] = None,
    monitoring_system: Optional[MonitoringSystem] = None,
) -> DiagnosticAPI:
    """Create diagnostic API instance"""
    return DiagnosticAPI(db_config, monitoring_system)


# Standalone server function
async def run_diagnostic_server(
    host: str = "0.0.0.0",
    port: int = 8081,
    db_config: Optional[Dict] = None,
    monitoring_system: Optional[MonitoringSystem] = None,
):
    """Run diagnostic API server"""
    import uvicorn

    api = create_diagnostic_api(db_config, monitoring_system)

    logger.info(f"Starting diagnostic API server on {host}:{port}")

    config = uvicorn.Config(app=api.app, host=host, port=port, log_level="info")

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # Run the diagnostic API server
    asyncio.run(run_diagnostic_server())

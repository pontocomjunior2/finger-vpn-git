#!/usr/bin/env python3
"""
Health Check Script
Comprehensive health checking for orchestrator system components
"""
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import requests

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager, get_config


class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a system component"""

    component: str
    status: HealthStatus
    response_time: Optional[float] = None
    error: Optional[str] = None
    details: Dict = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


@dataclass
class SystemHealth:
    """Overall system health status"""

    overall_status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime
    environment: str

    def to_dict(self) -> Dict:
        return {
            "overall_status": self.overall_status.value,
            "components": [asdict(comp) for comp in self.components],
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
        }


class HealthChecker:
    """Comprehensive health checker for orchestrator system"""

    def __init__(self, environment: str = None):
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.config = get_config(self.environment)
        self.logger = logging.getLogger(__name__)

        # Component endpoints for health checks
        self.endpoints = {
            "orchestrator": {
                "url": f"http://{self.config.orchestrator.host}:{self.config.orchestrator.port}/health",
                "timeout": 10,
            },
            "database": {"check_function": self._check_database_health},
            "monitoring": {
                "url": f"http://localhost:{self.config.monitoring.metrics_port}/health",
                "timeout": 5,
            },
        }

    async def check_system_health(self) -> SystemHealth:
        """Check health of all system components"""
        self.logger.info("Starting comprehensive system health check")

        component_healths = []

        # Check each component
        for component, config in self.endpoints.items():
            try:
                if "url" in config:
                    health = await self._check_http_endpoint(
                        component, config["url"], config["timeout"]
                    )
                elif "check_function" in config:
                    health = await config["check_function"]()
                else:
                    health = ComponentHealth(
                        component=component,
                        status=HealthStatus.UNKNOWN,
                        error="No health check method configured",
                    )

                component_healths.append(health)

            except Exception as e:
                self.logger.error(f"Health check failed for {component}: {e}")
                component_healths.append(
                    ComponentHealth(
                        component=component, status=HealthStatus.UNHEALTHY, error=str(e)
                    )
                )

        # Determine overall system health
        overall_status = self._calculate_overall_health(component_healths)

        return SystemHealth(
            overall_status=overall_status,
            components=component_healths,
            timestamp=datetime.now(),
            environment=self.environment,
        )

    async def _check_http_endpoint(
        self, component: str, url: str, timeout: int
    ) -> ComponentHealth:
        """Check health of HTTP endpoint"""
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    response_time = time.time() - start_time

                    if response.status == 200:
                        try:
                            data = await response.json()
                            return ComponentHealth(
                                component=component,
                                status=HealthStatus.HEALTHY,
                                response_time=response_time,
                                details=data,
                            )
                        except:
                            return ComponentHealth(
                                component=component,
                                status=HealthStatus.HEALTHY,
                                response_time=response_time,
                            )
                    else:
                        return ComponentHealth(
                            component=component,
                            status=HealthStatus.UNHEALTHY,
                            response_time=response_time,
                            error=f"HTTP {response.status}",
                        )

        except asyncio.TimeoutError:
            return ComponentHealth(
                component=component,
                status=HealthStatus.UNHEALTHY,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            return ComponentHealth(
                component=component, status=HealthStatus.UNHEALTHY, error=str(e)
            )

    async def _check_database_health(self) -> ComponentHealth:
        """Check database connectivity and performance"""
        try:
            import asyncpg

            start_time = time.time()

            # Create connection string
            conn_str = f"postgresql://{self.config.database.username}:{self.config.database.password}@{self.config.database.host}:{self.config.database.port}/{self.config.database.database}"

            # Test connection
            conn = await asyncpg.connect(conn_str, timeout=self.config.database.timeout)

            # Test basic query
            result = await conn.fetchval("SELECT 1")

            # Test table existence
            tables_exist = await conn.fetchval(
                """
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name IN ('instances', 'stream_assignments')
            """
            )

            await conn.close()

            response_time = time.time() - start_time

            if result == 1 and tables_exist >= 2:
                return ComponentHealth(
                    component="database",
                    status=HealthStatus.HEALTHY,
                    response_time=response_time,
                    details={"connection": "ok", "tables": "ok", "query_test": "ok"},
                )
            else:
                return ComponentHealth(
                    component="database",
                    status=HealthStatus.DEGRADED,
                    response_time=response_time,
                    error="Missing required tables",
                )

        except ImportError:
            return ComponentHealth(
                component="database",
                status=HealthStatus.UNKNOWN,
                error="asyncpg not available",
            )
        except Exception as e:
            return ComponentHealth(
                component="database", status=HealthStatus.UNHEALTHY, error=str(e)
            )

    def _calculate_overall_health(
        self, component_healths: List[ComponentHealth]
    ) -> HealthStatus:
        """Calculate overall system health from component healths"""
        if not component_healths:
            return HealthStatus.UNKNOWN

        healthy_count = sum(
            1 for h in component_healths if h.status == HealthStatus.HEALTHY
        )
        unhealthy_count = sum(
            1 for h in component_healths if h.status == HealthStatus.UNHEALTHY
        )
        degraded_count = sum(
            1 for h in component_healths if h.status == HealthStatus.DEGRADED
        )

        total_count = len(component_healths)

        # All healthy
        if healthy_count == total_count:
            return HealthStatus.HEALTHY

        # More than half unhealthy
        if unhealthy_count > total_count / 2:
            return HealthStatus.UNHEALTHY

        # Some issues but system can function
        if unhealthy_count > 0 or degraded_count > 0:
            return HealthStatus.DEGRADED

        return HealthStatus.UNKNOWN

    async def wait_for_healthy(self, timeout: int = 300, interval: int = 10) -> bool:
        """Wait for system to become healthy"""
        self.logger.info(f"Waiting for system to become healthy (timeout: {timeout}s)")

        start_time = time.time()

        while time.time() - start_time < timeout:
            health = await self.check_system_health()

            if health.overall_status == HealthStatus.HEALTHY:
                self.logger.info("System is healthy")
                return True

            self.logger.info(
                f"System status: {health.overall_status.value}, waiting {interval}s..."
            )

            # Log unhealthy components
            for comp in health.components:
                if comp.status != HealthStatus.HEALTHY:
                    self.logger.warning(
                        f"  {comp.component}: {comp.status.value} - {comp.error}"
                    )

            await asyncio.sleep(interval)

        self.logger.error("Timeout waiting for system to become healthy")
        return False

    def check_readiness(self) -> bool:
        """Quick readiness check for load balancer"""
        try:
            # Simple HTTP check to orchestrator
            response = requests.get(
                f"http://{self.config.orchestrator.host}:{self.config.orchestrator.port}/ready",
                timeout=5,
            )
            return response.status_code == 200
        except:
            return False

    def check_liveness(self) -> bool:
        """Quick liveness check"""
        try:
            # Basic connectivity check
            response = requests.get(
                f"http://{self.config.orchestrator.host}:{self.config.orchestrator.port}/health",
                timeout=3,
            )
            return response.status_code in [
                200,
                503,
            ]  # 503 might indicate degraded but alive
        except:
            return False


async def main():
    """CLI interface for health checking"""
    import argparse

    parser = argparse.ArgumentParser(description="System Health Checker")
    parser.add_argument(
        "--environment", "-e", default=None, help="Environment to check"
    )
    parser.add_argument(
        "--wait",
        "-w",
        type=int,
        default=0,
        help="Wait for system to become healthy (timeout in seconds)",
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=10, help="Check interval when waiting"
    )
    parser.add_argument(
        "--readiness", action="store_true", help="Quick readiness check"
    )
    parser.add_argument("--liveness", action="store_true", help="Quick liveness check")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    health_checker = HealthChecker(args.environment)

    # Quick checks
    if args.readiness:
        ready = health_checker.check_readiness()
        if args.json:
            print(json.dumps({"ready": ready}))
        else:
            print("READY" if ready else "NOT READY")
        sys.exit(0 if ready else 1)

    if args.liveness:
        alive = health_checker.check_liveness()
        if args.json:
            print(json.dumps({"alive": alive}))
        else:
            print("ALIVE" if alive else "NOT ALIVE")
        sys.exit(0 if alive else 1)

    # Wait for healthy if requested
    if args.wait > 0:
        healthy = await health_checker.wait_for_healthy(args.wait, args.interval)
        sys.exit(0 if healthy else 1)

    # Full health check
    health = await health_checker.check_system_health()

    if args.json:
        print(json.dumps(health.to_dict(), indent=2))
    else:
        print(f"Overall Status: {health.overall_status.value.upper()}")
        print(f"Environment: {health.environment}")
        print(f"Timestamp: {health.timestamp}")
        print("\nComponent Status:")

        for comp in health.components:
            status_symbol = {
                HealthStatus.HEALTHY: "✓",
                HealthStatus.UNHEALTHY: "✗",
                HealthStatus.DEGRADED: "⚠",
                HealthStatus.UNKNOWN: "?",
            }.get(comp.status, "?")

            print(f"  {status_symbol} {comp.component}: {comp.status.value}")

            if comp.response_time:
                print(f"    Response time: {comp.response_time:.3f}s")

            if comp.error:
                print(f"    Error: {comp.error}")

            if comp.details:
                for key, value in comp.details.items():
                    print(f"    {key}: {value}")

    # Exit with appropriate code
    exit_code = (
        0
        if health.overall_status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        else 1
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())

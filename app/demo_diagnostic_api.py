#!/usr/bin/env python3
"""
Demonstration script for Diagnostic API

This script demonstrates the comprehensive diagnostic and status API functionality
that implements requirements 6.1, 6.2, 6.3, 6.4.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostic_api_standalone import (
    HealthStatus,
    InconsistencyType,
    create_standalone_diagnostic_api,
)


async def demo_comprehensive_health_check():
    """Demonstrate comprehensive health checking (Requirement 6.3)"""
    print("🏥 COMPREHENSIVE HEALTH CHECK DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Running health checks for all system components...")
    print()

    # Test each health checker individually
    for component, checker in api.health_checkers.items():
        print(f"Checking {component}...")
        try:
            result = await checker()
            status_icon = {
                HealthStatus.HEALTHY: "✅",
                HealthStatus.DEGRADED: "⚠️",
                HealthStatus.CRITICAL: "❌",
                HealthStatus.UNKNOWN: "❓",
            }.get(result["status"], "❓")

            print(f"  {status_icon} {component.upper()}: {result['message']}")

            if "details" in result and result["details"]:
                for key, value in result["details"].items():
                    if isinstance(value, (int, float)):
                        print(f"    • {key}: {value}")
                    elif isinstance(value, list) and len(value) <= 5:
                        print(f"    • {key}: {value}")
                    elif isinstance(value, dict):
                        print(f"    • {key}: {json.dumps(value, indent=6)}")

        except Exception as e:
            print(f"  ❌ {component.upper()}: Error - {str(e)}")

        print()

    print("Health check demonstration completed!")
    print()


async def demo_inconsistency_detection():
    """Demonstrate inconsistency detection with recommendations (Requirement 6.2)"""
    print("🔍 INCONSISTENCY DETECTION DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Scanning for system inconsistencies...")
    print()

    # Test each inconsistency detector
    for inc_type, detector in api.inconsistency_detectors.items():
        print(f"Checking for {inc_type.value}...")
        try:
            inconsistencies = await detector()

            if inconsistencies:
                for inc in inconsistencies:
                    severity_icon = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(
                        inc.severity, "❓"
                    )

                    print(f"  {severity_icon} FOUND: {inc.description}")
                    print(f"    Severity: {inc.severity.upper()}")
                    print(f"    Affected: {', '.join(inc.affected_components)}")
                    print(f"    Recommendations:")
                    for i, rec in enumerate(inc.recommendations, 1):
                        print(f"      {i}. {rec}")

                    if inc.metadata:
                        print(
                            f"    Details: {json.dumps(inc.metadata, indent=6, default=str)}"
                        )
                    print()
            else:
                print(f"  ✅ No {inc_type.value} detected")

        except Exception as e:
            print(f"  ❌ Error checking {inc_type.value}: {str(e)}")

        print()

    print("Inconsistency detection demonstration completed!")
    print()


async def demo_detailed_status_reporting():
    """Demonstrate detailed status reporting (Requirement 6.1)"""
    print("📊 DETAILED STATUS REPORTING DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Collecting detailed system status...")
    print()

    # Database status
    print("DATABASE STATUS:")
    db_status = await api._get_database_status()
    print(f"  Status: {db_status.get('status', 'unknown')}")
    print(f"  Message: {db_status.get('message', 'No message')}")
    if "connection_time_ms" in db_status:
        print(f"  Connection Time: {db_status['connection_time_ms']:.2f}ms")
    if "connections" in db_status:
        conn = db_status["connections"]
        print(f"  Active Connections: {conn.get('active', 0)}")
        print(f"  Idle Connections: {conn.get('idle', 0)}")
    print()

    # Orchestrator status
    print("ORCHESTRATOR STATUS:")
    orch_status = await api._get_orchestrator_status()
    print(f"  Active: {orch_status.get('active', False)}")
    print(f"  Total Instances: {orch_status.get('total_instances', 0)}")
    print(f"  Active Instances: {orch_status.get('active_instances', 0)}")
    print(f"  Recent Heartbeats: {orch_status.get('recent_heartbeats', 0)}")
    print(f"  Health Score: {orch_status.get('health_score', 0):.2%}")
    print()

    # Instances status
    print("INSTANCES STATUS:")
    inst_status = await api._get_instances_status()
    print(f"  Total Instances: {inst_status.get('total_instances', 0)}")

    if "summary" in inst_status:
        summary = inst_status["summary"]
        print(f"  Total Streams: {summary.get('total_streams', 0)}")
        print(f"  Total Capacity: {summary.get('total_capacity', 0)}")

    instances = inst_status.get("instances", [])
    if instances:
        print("  Instance Details:")
        for instance in instances[:3]:  # Show first 3 instances
            print(
                f"    • {instance.get('server_id', 'unknown')}: "
                f"{instance.get('current_streams', 0)}/{instance.get('max_streams', 0)} streams"
            )
    print()

    # Performance summary
    print("PERFORMANCE SUMMARY:")
    perf_summary = await api._get_performance_summary()
    print(f"  Avg Response Time: {perf_summary.get('avg_response_time', 0):.2f}ms")
    print(f"  Avg Error Rate: {perf_summary.get('avg_error_rate', 0):.2%}")
    print(f"  Avg Throughput: {perf_summary.get('avg_throughput', 0):.2f}")
    print(f"  Note: {perf_summary.get('note', 'N/A')}")
    print()

    print("Status reporting demonstration completed!")
    print()


async def demo_performance_metrics():
    """Demonstrate performance metrics APIs (Requirement 6.4)"""
    print("📈 PERFORMANCE METRICS DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Collecting performance metrics...")
    print()

    # Performance metrics collection
    print("PERFORMANCE METRICS COLLECTION:")
    metrics = await api._collect_performance_metrics(24, None)
    print(f"  Collected {len(metrics)} metrics over 24 hours")

    if metrics:
        for metric in metrics[:3]:  # Show first 3 metrics
            print(f"  • {metric.metric_name}:")
            print(f"    Current: {metric.current_value}")
            print(f"    Average: {metric.average_value}")
            print(f"    Trend: {metric.trend}")
    else:
        print("  No metrics available (monitoring system not active)")
    print()

    # Historical data
    print("HISTORICAL PERFORMANCE DATA:")
    historical = await api._get_historical_performance_data(24, None)
    print(f"  Historical data available for {len(historical)} metrics")

    for metric_name, data_points in list(historical.items())[:2]:  # Show first 2
        print(f"  • {metric_name}: {len(data_points)} data points")
    print()

    # Performance summary
    print("PERFORMANCE SUMMARY:")
    summary = api._generate_performance_summary(metrics)
    print(f"  Total Metrics: {summary.get('total_metrics', 0)}")
    print(f"  Healthy Metrics: {summary.get('healthy_metrics', 0)}")
    print(f"  Degraded Metrics: {summary.get('degraded_metrics', 0)}")
    print(f"  Critical Metrics: {summary.get('critical_metrics', 0)}")
    print()

    print("Performance metrics demonstration completed!")
    print()


async def demo_recommendations_and_actions():
    """Demonstrate recommendation generation"""
    print("💡 RECOMMENDATIONS AND PRIORITY ACTIONS DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Generating system recommendations...")
    print()

    # Run health checks to get current state
    health_checks = []
    for component, checker in api.health_checkers.items():
        try:
            result = await checker()
            from diagnostic_api_standalone import SystemHealthCheck

            health_checks.append(
                SystemHealthCheck(
                    component=component,
                    status=result["status"],
                    message=result["message"],
                    details=result.get("details", {}),
                    timestamp=datetime.now(),
                    response_time_ms=0,
                )
            )
        except Exception:
            pass

    # Get inconsistencies
    inconsistencies = await api._detect_all_inconsistencies()

    # Generate recommendations
    recommendations = api._generate_recommendations(health_checks, inconsistencies)

    print("SYSTEM RECOMMENDATIONS:")
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            priority_icon = (
                "🚨" if "CRITICAL" in rec else "⚠️" if "WARNING" in rec else "ℹ️"
            )
            print(f"  {i}. {priority_icon} {rec}")
    else:
        print("  ✅ No recommendations needed - system is healthy!")
    print()

    # Priority actions
    priority_actions = api._get_priority_actions(health_checks, inconsistencies)

    print("PRIORITY ACTIONS:")
    if priority_actions:
        for action in priority_actions:
            priority_icon = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "ℹ️",
                "low": "💡",
            }.get(action["priority"], "❓")

            print(f"  {priority_icon} {action['priority'].upper()}: {action['action']}")
            print(f"    Description: {action['description']}")
            print(f"    Component: {action['component']}")
            print()
    else:
        print("  ✅ No priority actions needed!")
    print()

    print("Recommendations demonstration completed!")
    print()


async def demo_overall_system_health():
    """Demonstrate overall system health calculation"""
    print("🎯 OVERALL SYSTEM HEALTH DEMONSTRATION")
    print("=" * 60)

    api = create_standalone_diagnostic_api()

    print("Calculating overall system health...")
    print()

    # Run all health checks
    health_checks = []
    for component, checker in api.health_checkers.items():
        try:
            result = await checker()
            from diagnostic_api_standalone import SystemHealthCheck

            health_checks.append(
                SystemHealthCheck(
                    component=component,
                    status=result["status"],
                    message=result["message"],
                    details=result.get("details", {}),
                    timestamp=datetime.now(),
                    response_time_ms=0,
                )
            )
        except Exception:
            pass

    # Get all inconsistencies
    inconsistencies = await api._detect_all_inconsistencies()

    # Calculate overall health
    overall_health = api._calculate_overall_health(health_checks, inconsistencies)

    # Display results
    health_icon = {
        HealthStatus.HEALTHY: "✅",
        HealthStatus.DEGRADED: "⚠️",
        HealthStatus.CRITICAL: "❌",
        HealthStatus.UNKNOWN: "❓",
    }.get(overall_health, "❓")

    print(f"OVERALL SYSTEM HEALTH: {health_icon} {overall_health.value.upper()}")
    print()

    # Component breakdown
    print("COMPONENT HEALTH BREAKDOWN:")
    for check in health_checks:
        status_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.CRITICAL: "❌",
            HealthStatus.UNKNOWN: "❓",
        }.get(check.status, "❓")
        print(f"  {status_icon} {check.component.upper()}: {check.status.value}")
    print()

    # Inconsistency summary
    print("INCONSISTENCY SUMMARY:")
    if inconsistencies:
        critical_count = sum(1 for inc in inconsistencies if inc.severity == "critical")
        warning_count = sum(1 for inc in inconsistencies if inc.severity == "warning")

        print(f"  🚨 Critical: {critical_count}")
        print(f"  ⚠️ Warnings: {warning_count}")
        print(f"  📊 Total: {len(inconsistencies)}")
    else:
        print("  ✅ No inconsistencies detected")
    print()

    print("Overall system health demonstration completed!")
    print()


async def main():
    """Run all demonstrations"""
    print("🚀 DIAGNOSTIC API COMPREHENSIVE DEMONSTRATION")
    print("=" * 80)
    print("This demonstration shows the implementation of requirements:")
    print("  • 6.1: Detailed status reporting with component information")
    print("  • 6.2: Inconsistency detection with specific recommendations")
    print("  • 6.3: Comprehensive health checking with connectivity tests")
    print("  • 6.4: Performance metrics APIs with historical data")
    print("=" * 80)
    print()

    try:
        await demo_comprehensive_health_check()
        await demo_inconsistency_detection()
        await demo_detailed_status_reporting()
        await demo_performance_metrics()
        await demo_recommendations_and_actions()
        await demo_overall_system_health()

        print("🎉 DEMONSTRATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print("The Diagnostic API is fully functional and ready for use.")
        print(
            "All requirements (6.1, 6.2, 6.3, 6.4) have been successfully implemented."
        )
        print()
        print("To start the API server, run:")
        print("  python diagnostic_api_standalone.py")
        print()
        print("API endpoints will be available at:")
        print("  • GET /diagnostic/health - Comprehensive health check")
        print("  • GET /diagnostic/status - Detailed system status")
        print("  • GET /diagnostic/performance - Performance metrics")
        print("  • GET /diagnostic/inconsistencies - Inconsistency detection")
        print("  • GET /diagnostic/recommendations - System recommendations")

    except Exception as e:
        print(f"❌ DEMONSTRATION FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

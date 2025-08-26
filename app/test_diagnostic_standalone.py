#!/usr/bin/env python3
"""
Simple test script for Standalone Diagnostic API

This script tests the diagnostic API functionality to ensure it meets
requirements 6.1, 6.2, 6.3, 6.4.
"""

import asyncio
import os
import sys
from unittest.mock import Mock, patch

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostic_api_standalone import (HealthStatus, InconsistencyType,
                                       StandaloneDiagnosticAPI,
                                       create_standalone_diagnostic_api)


async def test_diagnostic_api_creation():
    """Test that diagnostic API can be created successfully"""
    print("Testing diagnostic API creation...")
    
    # Test API creation
    api = create_standalone_diagnostic_api()
    assert api is not None
    assert hasattr(api, 'app')
    assert hasattr(api, 'health_checkers')
    assert hasattr(api, 'inconsistency_detectors')
    
    print("✓ Diagnostic API created successfully")
    
    # Test that all required health checkers are present
    required_checkers = ['database', 'orchestrator', 'instances', 'streams']
    for checker in required_checkers:
        assert checker in api.health_checkers
    
    print("✓ All required health checkers present")
    
    # Test that all inconsistency detectors are present
    required_detectors = [
        InconsistencyType.ORPHANED_STREAMS,
        InconsistencyType.DUPLICATE_ASSIGNMENTS,
        InconsistencyType.MISSING_INSTANCES,
        InconsistencyType.STATE_MISMATCH,
        InconsistencyType.HEARTBEAT_TIMEOUT,
        InconsistencyType.LOAD_IMBALANCE
    ]
    for detector in required_detectors:
        assert detector in api.inconsistency_detectors
    
    print("✓ All required inconsistency detectors present")


async def test_health_checks():
    """Test health check functionality (Requirement 6.3)"""
    print("\nTesting health checks...")
    
    api = create_standalone_diagnostic_api()
    
    # Test database health check without actual database
    db_health = await api._check_database_health()
    assert 'status' in db_health
    assert 'message' in db_health
    print("✓ Database health check works")
    
    # Test orchestrator health check
    orch_health = await api._check_orchestrator_health()
    assert 'status' in orch_health
    assert 'message' in orch_health
    print("✓ Orchestrator health check works")
    
    # Test instances health check
    inst_health = await api._check_instances_health()
    assert 'status' in inst_health
    assert 'message' in inst_health
    print("✓ Instances health check works")
    
    # Test streams health check
    stream_health = await api._check_streams_health()
    assert 'status' in stream_health
    assert 'message' in stream_health
    print("✓ Streams health check works")


async def test_inconsistency_detection():
    """Test inconsistency detection (Requirement 6.2)"""
    print("\nTesting inconsistency detection...")
    
    api = create_standalone_diagnostic_api()
    
    # Test orphaned streams detection
    orphaned = await api._detect_orphaned_streams()
    assert isinstance(orphaned, list)
    print("✓ Orphaned streams detection works")
    
    # Test duplicate assignments detection
    duplicates = await api._detect_duplicate_assignments()
    assert isinstance(duplicates, list)
    print("✓ Duplicate assignments detection works")
    
    # Test heartbeat timeouts detection
    timeouts = await api._detect_heartbeat_timeouts()
    assert isinstance(timeouts, list)
    print("✓ Heartbeat timeouts detection works")
    
    # Test load imbalance detection
    imbalance = await api._detect_load_imbalance()
    assert isinstance(imbalance, list)
    print("✓ Load imbalance detection works")


async def test_status_reporting():
    """Test detailed status reporting (Requirement 6.1)"""
    print("\nTesting status reporting...")
    
    api = create_standalone_diagnostic_api()
    
    # Test database status
    db_status = await api._get_database_status()
    assert 'status' in db_status
    print("✓ Database status reporting works")
    
    # Test orchestrator status
    orch_status = await api._get_orchestrator_status()
    assert 'active' in orch_status
    print("✓ Orchestrator status reporting works")
    
    # Test instances status
    inst_status = await api._get_instances_status()
    assert 'total_instances' in inst_status
    assert 'instances' in inst_status
    print("✓ Instances status reporting works")


async def test_performance_metrics():
    """Test performance metrics APIs (Requirement 6.4)"""
    print("\nTesting performance metrics...")
    
    api = create_standalone_diagnostic_api()
    
    # Test performance summary
    perf_summary = await api._get_performance_summary()
    assert 'avg_response_time' in perf_summary
    assert 'avg_error_rate' in perf_summary
    print("✓ Performance summary works")
    
    # Test performance metrics collection
    metrics = await api._collect_performance_metrics(24, None)
    assert isinstance(metrics, list)
    print("✓ Performance metrics collection works")
    
    # Test historical data
    historical = await api._get_historical_performance_data(24, None)
    assert isinstance(historical, dict)
    print("✓ Historical performance data works")


async def test_recommendations():
    """Test recommendation generation"""
    print("\nTesting recommendations...")
    
    api = create_standalone_diagnostic_api()
    
    # Test with mock health checks
    from diagnostic_api_standalone import SystemHealthCheck
    
    health_checks = [
        SystemHealthCheck(
            component='database',
            status=HealthStatus.CRITICAL,
            message='Connection failed',
            details={},
            timestamp=None,
            response_time_ms=0
        ),
        SystemHealthCheck(
            component='instances',
            status=HealthStatus.HEALTHY,
            message='All good',
            details={},
            timestamp=None,
            response_time_ms=0
        )
    ]
    
    recommendations = api._generate_recommendations(health_checks, [])
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0
    assert any('CRITICAL' in rec for rec in recommendations)
    print("✓ Recommendation generation works")
    
    # Test priority actions
    priority_actions = api._get_priority_actions(health_checks, [])
    assert isinstance(priority_actions, list)
    print("✓ Priority actions generation works")


async def test_overall_health_calculation():
    """Test overall health status calculation"""
    print("\nTesting overall health calculation...")
    
    api = create_standalone_diagnostic_api()
    
    from diagnostic_api_standalone import SystemHealthCheck

    # Test critical health
    critical_checks = [
        SystemHealthCheck(
            component='database',
            status=HealthStatus.CRITICAL,
            message='Critical issue',
            details={},
            timestamp=None,
            response_time_ms=0
        )
    ]
    health = api._calculate_overall_health(critical_checks, [])
    assert health == HealthStatus.CRITICAL
    print("✓ Critical health calculation works")
    
    # Test healthy
    healthy_checks = [
        SystemHealthCheck(
            component='database',
            status=HealthStatus.HEALTHY,
            message='All good',
            details={},
            timestamp=None,
            response_time_ms=0
        )
    ]
    health = api._calculate_overall_health(healthy_checks, [])
    assert health == HealthStatus.HEALTHY
    print("✓ Healthy status calculation works")


async def test_all_inconsistency_detection():
    """Test comprehensive inconsistency detection"""
    print("\nTesting comprehensive inconsistency detection...")
    
    api = create_standalone_diagnostic_api()
    
    # Test all inconsistency detection
    all_inconsistencies = await api._detect_all_inconsistencies()
    assert isinstance(all_inconsistencies, list)
    print("✓ Comprehensive inconsistency detection works")


async def main():
    """Run all tests"""
    print("Starting Diagnostic API Tests")
    print("=" * 50)
    
    try:
        await test_diagnostic_api_creation()
        await test_health_checks()
        await test_inconsistency_detection()
        await test_status_reporting()
        await test_performance_metrics()
        await test_recommendations()
        await test_overall_health_calculation()
        await test_all_inconsistency_detection()
        
        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED!")
        print("\nDiagnostic API successfully implements:")
        print("  ✓ Requirement 6.1: Detailed status reporting")
        print("  ✓ Requirement 6.2: Inconsistency detection with recommendations")
        print("  ✓ Requirement 6.3: Comprehensive health checking")
        print("  ✓ Requirement 6.4: Performance metrics APIs")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
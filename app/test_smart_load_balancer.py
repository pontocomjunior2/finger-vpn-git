#!/usr/bin/env python3
"""
Test script for Smart Load Balancer
Tests the core functionality of the smart load balancing algorithm
"""

import logging
import sys
from datetime import datetime, timedelta

from smart_load_balancer import (InstanceMetrics, LoadBalanceConfig,
                                 RebalanceReason, SmartLoadBalancer)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_test_instances() -> list:
    """Create test instance metrics for testing"""
    instances = [
        InstanceMetrics(
            server_id="instance-1",
            current_streams=15,
            max_streams=20,
            cpu_percent=45.0,
            memory_percent=60.0,
            load_average_1m=1.2,
            response_time_ms=80.0,
            failure_count=0,
            last_heartbeat=datetime.now()
        ),
        InstanceMetrics(
            server_id="instance-2", 
            current_streams=5,
            max_streams=20,
            cpu_percent=25.0,
            memory_percent=40.0,
            load_average_1m=0.8,
            response_time_ms=50.0,
            failure_count=1,
            last_heartbeat=datetime.now()
        ),
        InstanceMetrics(
            server_id="instance-3",
            current_streams=18,
            max_streams=20,
            cpu_percent=85.0,
            memory_percent=90.0,
            load_average_1m=3.5,
            response_time_ms=200.0,
            failure_count=3,
            last_heartbeat=datetime.now()
        )
    ]
    return instances


def test_load_factor_calculation():
    """Test load factor calculation"""
    logger.info("Testing load factor calculation...")
    
    instance = InstanceMetrics(
        server_id="test",
        current_streams=10,
        max_streams=20,
        cpu_percent=50.0,
        memory_percent=60.0
    )
    
    assert instance.load_factor == 0.5, f"Expected 0.5, got {instance.load_factor}"
    assert instance.available_capacity == 10, f"Expected 10, got {instance.available_capacity}"
    
    logger.info("✓ Load factor calculation test passed")


def test_performance_score():
    """Test performance score calculation"""
    logger.info("Testing performance score calculation...")
    
    # High performance instance
    high_perf = InstanceMetrics(
        server_id="high-perf",
        current_streams=5,
        max_streams=20,
        cpu_percent=20.0,
        memory_percent=30.0,
        load_average_1m=0.5,
        response_time_ms=30.0,
        failure_count=0
    )
    
    # Low performance instance
    low_perf = InstanceMetrics(
        server_id="low-perf",
        current_streams=15,
        max_streams=20,
        cpu_percent=90.0,
        memory_percent=95.0,
        load_average_1m=4.0,
        response_time_ms=500.0,
        failure_count=5
    )
    
    assert high_perf.performance_score > low_perf.performance_score, \
        f"High performance score {high_perf.performance_score} should be > low performance score {low_perf.performance_score}"
    
    logger.info(f"✓ Performance score test passed: high={high_perf.performance_score:.3f}, low={low_perf.performance_score:.3f}")


def test_imbalance_detection():
    """Test load imbalance detection"""
    logger.info("Testing imbalance detection...")
    
    config = LoadBalanceConfig()
    balancer = SmartLoadBalancer(config)
    
    # Create imbalanced instances
    instances = create_test_instances()
    
    needs_rebalance, reason = balancer.detect_imbalance(instances)
    
    logger.info(f"Imbalance detection result: {needs_rebalance}, reason: {reason}")
    
    # Should detect imbalance due to stream count difference
    assert needs_rebalance, "Should detect imbalance in test instances"
    
    logger.info("✓ Imbalance detection test passed")


def test_optimal_distribution():
    """Test optimal distribution calculation"""
    logger.info("Testing optimal distribution calculation...")
    
    config = LoadBalanceConfig()
    balancer = SmartLoadBalancer(config)
    
    instances = create_test_instances()
    total_streams = sum(inst.current_streams for inst in instances)
    
    distribution = balancer.calculate_optimal_distribution(instances, total_streams)
    
    logger.info(f"Optimal distribution: {distribution}")
    
    # Verify total streams are preserved
    distributed_total = sum(distribution.values())
    assert distributed_total <= total_streams, f"Distributed {distributed_total} > total {total_streams}"
    
    # Verify no instance exceeds capacity
    for inst in instances:
        assigned = distribution.get(inst.server_id, 0)
        assert assigned <= inst.max_streams, f"Instance {inst.server_id} assigned {assigned} > max {inst.max_streams}"
    
    logger.info("✓ Optimal distribution test passed")


def test_rebalance_plan_generation():
    """Test rebalance plan generation"""
    logger.info("Testing rebalance plan generation...")
    
    config = LoadBalanceConfig()
    balancer = SmartLoadBalancer(config)
    
    instances = create_test_instances()
    total_streams = sum(inst.current_streams for inst in instances)
    
    migrations = balancer.generate_rebalance_plan(instances, total_streams, RebalanceReason.LOAD_IMBALANCE)
    
    logger.info(f"Generated {len(migrations)} migration plans")
    
    for i, migration in enumerate(migrations):
        logger.info(f"  Migration {i+1}: {migration.from_server} -> {migration.to_server} (priority: {migration.priority})")
    
    # Should generate some migrations for imbalanced instances
    assert len(migrations) > 0, "Should generate migration plans for imbalanced instances"
    
    logger.info("✓ Rebalance plan generation test passed")


def test_configuration():
    """Test configuration validation"""
    logger.info("Testing configuration...")
    
    # Test default configuration
    config = LoadBalanceConfig()
    assert config.imbalance_threshold == 0.20
    assert config.max_stream_difference == 2
    assert config.max_migrations_per_cycle == 10
    
    # Test custom configuration
    custom_config = LoadBalanceConfig()
    custom_config.imbalance_threshold = 0.15
    custom_config.max_stream_difference = 3
    
    balancer = SmartLoadBalancer(custom_config)
    assert balancer.config.imbalance_threshold == 0.15
    assert balancer.config.max_stream_difference == 3
    
    logger.info("✓ Configuration test passed")


def test_should_rebalance():
    """Test rebalancing decision logic"""
    logger.info("Testing rebalancing decision logic...")
    
    config = LoadBalanceConfig()
    balancer = SmartLoadBalancer(config)
    
    instances = create_test_instances()
    
    # Test initial decision
    should_rebalance, reason = balancer.should_rebalance(instances)
    logger.info(f"Should rebalance: {should_rebalance}, reason: {reason}")
    
    # Test minimum interval enforcement
    if should_rebalance:
        # Simulate recent rebalancing
        balancer.last_rebalance = datetime.now()
        
        should_rebalance_again, reason_again = balancer.should_rebalance(instances, min_interval_seconds=300)
        logger.info(f"Should rebalance again (with interval): {should_rebalance_again}, reason: {reason_again}")
        
        assert not should_rebalance_again, "Should not rebalance again within minimum interval"
    
    logger.info("✓ Rebalancing decision test passed")


def run_all_tests():
    """Run all tests"""
    logger.info("Starting Smart Load Balancer tests...")
    
    try:
        test_load_factor_calculation()
        test_performance_score()
        test_imbalance_detection()
        test_optimal_distribution()
        test_rebalance_plan_generation()
        test_configuration()
        test_should_rebalance()
        
        logger.info("🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
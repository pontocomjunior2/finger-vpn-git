#!/usr/bin/env python3
"""
Load Testing Framework for Balancing Algorithm Validation

Comprehensive load testing framework that validates the smart load balancing
algorithm under various scenarios including high load, instance failures,
and performance degradation.

Requirements: 1.1, 1.2, 1.3, 1.4 validation under load
"""

import asyncio
import json
import logging
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytest

logger = logging.getLogger(__name__)

# Import components for load testing
try:
    from enhanced_orchestrator import EnhancedStreamOrchestrator
    from smart_load_balancer import (InstanceMetrics, LoadBalanceConfig,
                                     RebalanceReason, RebalanceResult,
                                     SmartLoadBalancer)
    HAS_COMPONENTS = True
except ImportError as e:
    logger.warning(f"Components not available for load testing: {e}")
    HAS_COMPONENTS = False


@dataclass
class LoadTestScenario:
    """Load test scenario configuration"""
    name: str
    instance_count: int
    total_streams: int
    max_streams_per_instance: int
    performance_variation: float  # 0.0 to 1.0
    failure_rate: float  # 0.0 to 1.0
    load_imbalance_factor: float  # 0.0 to 1.0
    duration_seconds: int
    expected_balance_score: float  # Minimum expected balance score


@dataclass
class LoadTestMetrics:
    """Load test execution metrics"""
    scenario_name: str
    execution_time_ms: float
    balance_score: float
    rebalance_operations: int
    failed_operations: int
    average_response_time_ms: float
    max_response_time_ms: float
    throughput_ops_per_second: float
    memory_usage_mb: float
    cpu_usage_percent: float


@dataclass
class PerformanceProfile:
    """Performance profile for instance simulation"""
    cpu_base: float
    cpu_variance: float
    memory_base: float
    memory_variance: float
    response_time_base: float
    response_time_variance: float
    failure_probability: float


class LoadTestInstanceSimulator:
    """Simulates instance behavior under load"""
    
    def __init__(self, server_id: str, max_streams: int, profile: PerformanceProfile):
        self.server_id = server_id
        self.max_streams = max_streams
        self.profile = profile
        self.current_streams = 0
        self.failure_count = 0
        self.last_heartbeat = datetime.now()
        self.performance_history = []
    
    def update_load(self, new_stream_count: int):
        """Update instance load and recalculate performance metrics"""
        self.current_streams = min(new_stream_count, self.max_streams)
        
        # Calculate load-based performance degradation
        load_factor = self.current_streams / self.max_streams if self.max_streams > 0 else 0
        
        # Simulate performance degradation under load
        cpu_degradation = load_factor * 50  # Up to 50% CPU increase under full load
        memory_degradation = load_factor * 30  # Up to 30% memory increase
        response_degradation = load_factor * 100  # Up to 100ms response time increase
        
        # Add random variance
        cpu_variance = random.uniform(-self.profile.cpu_variance, self.profile.cpu_variance)
        memory_variance = random.uniform(-self.profile.memory_variance, self.profile.memory_variance)
        response_variance = random.uniform(-self.profile.response_time_variance, self.profile.response_time_variance)
        
        # Calculate final metrics
        cpu_percent = min(100, self.profile.cpu_base + cpu_degradation + cpu_variance)
        memory_percent = min(100, self.profile.memory_base + memory_degradation + memory_variance)
        response_time = max(10, self.profile.response_time_base + response_degradation + response_variance)
        
        # Simulate random failures
        if random.random() < self.profile.failure_probability:
            self.failure_count += 1
        
        self.last_heartbeat = datetime.now()
        
        # Store performance history
        self.performance_history.append({
            'timestamp': datetime.now(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'response_time_ms': response_time,
            'load_factor': load_factor
        })
        
        # Keep only last 100 entries
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]
    
    def get_metrics(self) -> InstanceMetrics:
        """Get current instance metrics"""
        if not self.performance_history:
            self.update_load(self.current_streams)
        
        latest = self.performance_history[-1]
        
        return InstanceMetrics(
            server_id=self.server_id,
            current_streams=self.current_streams,
            max_streams=self.max_streams,
            cpu_percent=latest['cpu_percent'],
            memory_percent=latest['memory_percent'],
            load_average_1m=latest['cpu_percent'] / 100 * 4,  # Approximate load average
            response_time_ms=latest['response_time_ms'],
            failure_count=self.failure_count,
            last_heartbeat=self.last_heartbeat
        )
    
    def simulate_failure(self):
        """Simulate instance failure"""
        self.failure_count += 10
        self.last_heartbeat = datetime.now() - timedelta(minutes=10)
    
    def simulate_recovery(self):
        """Simulate instance recovery"""
        self.failure_count = 0
        self.last_heartbeat = datetime.now()


class LoadTestFramework:
    """Comprehensive load testing framework for balancing algorithm"""
    
    def __init__(self, load_balancer: SmartLoadBalancer):
        self.load_balancer = load_balancer
        self.test_results = []
        self.instance_simulators = {}
    
    def create_performance_profiles(self) -> Dict[str, PerformanceProfile]:
        """Create different performance profiles for testing"""
        return {
            'high_performance': PerformanceProfile(
                cpu_base=20.0, cpu_variance=10.0,
                memory_base=30.0, memory_variance=10.0,
                response_time_base=50.0, response_time_variance=20.0,
                failure_probability=0.01
            ),
            'medium_performance': PerformanceProfile(
                cpu_base=50.0, cpu_variance=15.0,
                memory_base=60.0, memory_variance=15.0,
                response_time_base=100.0, response_time_variance=30.0,
                failure_probability=0.05
            ),
            'low_performance': PerformanceProfile(
                cpu_base=80.0, cpu_variance=10.0,
                memory_base=85.0, memory_variance=10.0,
                response_time_base=200.0, response_time_variance=50.0,
                failure_probability=0.1
            ),
            'unstable': PerformanceProfile(
                cpu_base=60.0, cpu_variance=30.0,
                memory_base=70.0, memory_variance=25.0,
                response_time_base=150.0, response_time_variance=100.0,
                failure_probability=0.15
            )
        }
    
    def create_load_test_scenarios(self) -> List[LoadTestScenario]:
        """Create comprehensive load test scenarios"""
        return [
            LoadTestScenario(
                name="baseline_balanced_load",
                instance_count=5,
                total_streams=100,
                max_streams_per_instance=25,
                performance_variation=0.1,
                failure_rate=0.01,
                load_imbalance_factor=0.1,
                duration_seconds=30,
                expected_balance_score=0.9
            ),
            LoadTestScenario(
                name="high_load_stress_test",
                instance_count=10,
                total_streams=500,
                max_streams_per_instance=60,
                performance_variation=0.3,
                failure_rate=0.05,
                load_imbalance_factor=0.2,
                duration_seconds=60,
                expected_balance_score=0.8
            ),
            LoadTestScenario(
                name="instance_failure_recovery",
                instance_count=8,
                total_streams=200,
                max_streams_per_instance=30,
                performance_variation=0.2,
                failure_rate=0.2,  # High failure rate
                load_imbalance_factor=0.3,
                duration_seconds=45,
                expected_balance_score=0.7
            ),
            LoadTestScenario(
                name="capacity_variation_test",
                instance_count=6,
                total_streams=150,
                max_streams_per_instance=50,  # Will vary per instance
                performance_variation=0.4,
                failure_rate=0.03,
                load_imbalance_factor=0.4,
                duration_seconds=40,
                expected_balance_score=0.75
            ),
            LoadTestScenario(
                name="extreme_imbalance_recovery",
                instance_count=4,
                total_streams=120,
                max_streams_per_instance=40,
                performance_variation=0.5,
                failure_rate=0.1,
                load_imbalance_factor=0.8,  # Extreme imbalance
                duration_seconds=50,
                expected_balance_score=0.6
            ),
            LoadTestScenario(
                name="rapid_scaling_test",
                instance_count=15,  # Large number of instances
                total_streams=300,
                max_streams_per_instance=25,
                performance_variation=0.3,
                failure_rate=0.02,
                load_imbalance_factor=0.2,
                duration_seconds=35,
                expected_balance_score=0.85
            )
        ]
    
    def setup_scenario_instances(self, scenario: LoadTestScenario) -> List[LoadTestInstanceSimulator]:
        """Setup instance simulators for a scenario"""
        profiles = self.create_performance_profiles()
        profile_names = list(profiles.keys())
        simulators = []
        
        for i in range(scenario.instance_count):
            server_id = f"load-test-{scenario.name}-{i+1}"
            
            # Vary max streams based on scenario
            if scenario.name == "capacity_variation_test":
                # Create varied capacities
                capacities = [10, 20, 30, 40, 50, 60]
                max_streams = capacities[i % len(capacities)]
            else:
                max_streams = scenario.max_streams_per_instance
            
            # Assign performance profile
            profile_name = profile_names[i % len(profile_names)]
            profile = profiles[profile_name]
            
            # Adjust profile based on scenario variation
            if scenario.performance_variation > 0:
                profile.failure_probability *= (1 + scenario.performance_variation)
                profile.cpu_variance *= (1 + scenario.performance_variation)
                profile.memory_variance *= (1 + scenario.performance_variation)
                profile.response_time_variance *= (1 + scenario.performance_variation)
            
            simulator = LoadTestInstanceSimulator(server_id, max_streams, profile)
            simulators.append(simulator)
            
            # Create initial imbalance if specified
            if scenario.load_imbalance_factor > 0:
                if i == 0:  # First instance gets heavy load
                    initial_load = int(max_streams * 0.9)
                elif i == 1:  # Second instance gets light load
                    initial_load = int(max_streams * 0.1)
                else:  # Others get random load
                    initial_load = random.randint(0, max_streams // 2)
                
                simulator.update_load(initial_load)
        
        return simulators
    
    def measure_balance_score(self, instances: List[InstanceMetrics]) -> float:
        """Calculate balance score for instances"""
        if not instances:
            return 0.0
        
        load_factors = [inst.load_factor for inst in instances if inst.max_streams > 0]
        if not load_factors:
            return 1.0
        
        # Calculate coefficient of variation (lower is better)
        mean_load = statistics.mean(load_factors)
        if mean_load == 0:
            return 1.0
        
        std_dev = statistics.stdev(load_factors) if len(load_factors) > 1 else 0
        cv = std_dev / mean_load if mean_load > 0 else 0
        
        # Convert to balance score (1.0 is perfect balance, 0.0 is worst)
        balance_score = max(0.0, 1.0 - cv)
        return balance_score
    
    def simulate_dynamic_load_changes(self, simulators: List[LoadTestInstanceSimulator], 
                                    scenario: LoadTestScenario) -> List[Dict]:
        """Simulate dynamic load changes during test"""
        load_changes = []
        
        # Simulate various load change patterns
        for second in range(scenario.duration_seconds):
            changes = {}
            
            # Random load fluctuations
            for simulator in simulators:
                if random.random() < 0.1:  # 10% chance of load change per second
                    change = random.randint(-5, 5)
                    new_load = max(0, min(simulator.max_streams, simulator.current_streams + change))
                    simulator.update_load(new_load)
                    changes[simulator.server_id] = new_load
            
            # Simulate instance failures
            if random.random() < scenario.failure_rate / scenario.duration_seconds:
                failed_simulator = random.choice(simulators)
                failed_simulator.simulate_failure()
                changes[failed_simulator.server_id] = "FAILED"
            
            # Simulate instance recoveries
            failed_simulators = [s for s in simulators if s.failure_count > 5]
            if failed_simulators and random.random() < 0.3:  # 30% chance of recovery
                recovered_simulator = random.choice(failed_simulators)
                recovered_simulator.simulate_recovery()
                changes[recovered_simulator.server_id] = "RECOVERED"
            
            if changes:
                load_changes.append({
                    'timestamp': second,
                    'changes': changes
                })
        
        return load_changes
    
    def run_load_test_scenario(self, scenario: LoadTestScenario) -> LoadTestMetrics:
        """Run a single load test scenario"""
        logger.info(f"Running load test scenario: {scenario.name}")
        
        # Setup
        simulators = self.setup_scenario_instances(scenario)
        start_time = time.time()
        rebalance_operations = 0
        failed_operations = 0
        response_times = []
        
        # Simulate dynamic load changes
        load_changes = self.simulate_dynamic_load_changes(simulators, scenario)
        
        # Run load test
        for second in range(scenario.duration_seconds):
            iteration_start = time.time()
            
            # Get current instance metrics
            instances = [sim.get_metrics() for sim in simulators]
            
            try:
                # Test imbalance detection
                imbalance_detected = self.load_balancer.detect_imbalance(instances)
                
                # Test distribution calculation
                distribution = self.load_balancer.calculate_optimal_distribution(
                    instances, scenario.total_streams
                )
                
                # Test rebalance plan generation if needed
                if imbalance_detected:
                    current_distribution = {
                        inst.server_id: inst.current_streams for inst in instances
                    }
                    rebalance_plan = self.load_balancer.generate_rebalance_plan(
                        instances, current_distribution, RebalanceReason.LOAD_IMBALANCE
                    )
                    if rebalance_plan:
                        rebalance_operations += 1
                        
                        # Apply rebalance plan to simulators
                        for migration in rebalance_plan.migrations:
                            source_sim = next(
                                (s for s in simulators if s.server_id == migration.source_server), 
                                None
                            )
                            target_sim = next(
                                (s for s in simulators if s.server_id == migration.target_server), 
                                None
                            )
                            
                            if source_sim and target_sim:
                                # Move streams
                                streams_to_move = min(migration.stream_count, source_sim.current_streams)
                                source_sim.update_load(source_sim.current_streams - streams_to_move)
                                target_sim.update_load(target_sim.current_streams + streams_to_move)
                
            except Exception as e:
                logger.error(f"Load test operation failed: {e}")
                failed_operations += 1
            
            iteration_end = time.time()
            response_times.append((iteration_end - iteration_start) * 1000)
            
            # Small delay to simulate real-world timing
            await asyncio.sleep(0.1)
        
        end_time = time.time()
        
        # Calculate final metrics
        final_instances = [sim.get_metrics() for sim in simulators]
        balance_score = self.measure_balance_score(final_instances)
        
        execution_time_ms = (end_time - start_time) * 1000
        average_response_time = statistics.mean(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        throughput = scenario.duration_seconds / (execution_time_ms / 1000) if execution_time_ms > 0 else 0
        
        # Estimate resource usage (simplified)
        memory_usage_mb = len(simulators) * 0.5  # Rough estimate
        cpu_usage_percent = min(100, len(simulators) * 2)  # Rough estimate
        
        metrics = LoadTestMetrics(
            scenario_name=scenario.name,
            execution_time_ms=execution_time_ms,
            balance_score=balance_score,
            rebalance_operations=rebalance_operations,
            failed_operations=failed_operations,
            average_response_time_ms=average_response_time,
            max_response_time_ms=max_response_time,
            throughput_ops_per_second=throughput,
            memory_usage_mb=memory_usage_mb,
            cpu_usage_percent=cpu_usage_percent
        )
        
        logger.info(f"Scenario {scenario.name} completed: Balance Score = {balance_score:.3f}")
        return metrics
    
    def run_concurrent_load_tests(self, scenarios: List[LoadTestScenario]) -> List[LoadTestMetrics]:
        """Run multiple load test scenarios concurrently"""
        results = []
        
        with ThreadPoolExecutor(max_workers=min(4, len(scenarios))) as executor:
            future_to_scenario = {
                executor.submit(self.run_load_test_scenario, scenario): scenario 
                for scenario in scenarios
            }
            
            for future in as_completed(future_to_scenario):
                scenario = future_to_scenario[future]
                try:
                    metrics = future.result()
                    results.append(metrics)
                except Exception as e:
                    logger.error(f"Load test scenario {scenario.name} failed: {e}")
                    # Create error metrics
                    error_metrics = LoadTestMetrics(
                        scenario_name=scenario.name,
                        execution_time_ms=0,
                        balance_score=0,
                        rebalance_operations=0,
                        failed_operations=1,
                        average_response_time_ms=0,
                        max_response_time_ms=0,
                        throughput_ops_per_second=0,
                        memory_usage_mb=0,
                        cpu_usage_percent=0
                    )
                    results.append(error_metrics)
        
        return results
    
    def validate_load_test_results(self, scenario: LoadTestScenario, 
                                 metrics: LoadTestMetrics) -> Dict:
        """Validate load test results against expectations"""
        validation = {
            'passed': True,
            'issues': [],
            'score': 0.0
        }
        
        # Check balance score
        if metrics.balance_score < scenario.expected_balance_score:
            validation['passed'] = False
            validation['issues'].append(
                f"Balance score {metrics.balance_score:.3f} below expected {scenario.expected_balance_score:.3f}"
            )
        else:
            validation['score'] += 25
        
        # Check performance (execution time should be reasonable)
        expected_max_time = scenario.duration_seconds * 2000  # 2x duration in ms
        if metrics.execution_time_ms > expected_max_time:
            validation['passed'] = False
            validation['issues'].append(
                f"Execution time {metrics.execution_time_ms:.0f}ms exceeds expected {expected_max_time:.0f}ms"
            )
        else:
            validation['score'] += 25
        
        # Check failure rate
        max_allowed_failures = max(1, scenario.duration_seconds // 10)  # Max 10% failure rate
        if metrics.failed_operations > max_allowed_failures:
            validation['passed'] = False
            validation['issues'].append(
                f"Failed operations {metrics.failed_operations} exceeds allowed {max_allowed_failures}"
            )
        else:
            validation['score'] += 25
        
        # Check response time
        max_allowed_response_time = 1000  # 1 second max
        if metrics.average_response_time_ms > max_allowed_response_time:
            validation['passed'] = False
            validation['issues'].append(
                f"Average response time {metrics.average_response_time_ms:.0f}ms exceeds {max_allowed_response_time}ms"
            )
        else:
            validation['score'] += 25
        
        return validation
    
    def generate_load_test_report(self, scenarios: List[LoadTestScenario], 
                                results: List[LoadTestMetrics]) -> Dict:
        """Generate comprehensive load test report"""
        report = {
            'summary': {
                'total_scenarios': len(scenarios),
                'passed_scenarios': 0,
                'failed_scenarios': 0,
                'average_balance_score': 0.0,
                'total_execution_time_ms': 0.0,
                'total_rebalance_operations': 0,
                'total_failed_operations': 0
            },
            'scenario_results': [],
            'performance_analysis': {},
            'recommendations': []
        }
        
        # Process results
        balance_scores = []
        execution_times = []
        
        for scenario, metrics in zip(scenarios, results):
            validation = self.validate_load_test_results(scenario, metrics)
            
            if validation['passed']:
                report['summary']['passed_scenarios'] += 1
            else:
                report['summary']['failed_scenarios'] += 1
            
            balance_scores.append(metrics.balance_score)
            execution_times.append(metrics.execution_time_ms)
            
            report['summary']['total_execution_time_ms'] += metrics.execution_time_ms
            report['summary']['total_rebalance_operations'] += metrics.rebalance_operations
            report['summary']['total_failed_operations'] += metrics.failed_operations
            
            scenario_result = {
                'scenario': asdict(scenario),
                'metrics': asdict(metrics),
                'validation': validation
            }
            report['scenario_results'].append(scenario_result)
        
        # Calculate summary statistics
        if balance_scores:
            report['summary']['average_balance_score'] = statistics.mean(balance_scores)
        
        # Performance analysis
        if execution_times:
            report['performance_analysis'] = {
                'average_execution_time_ms': statistics.mean(execution_times),
                'max_execution_time_ms': max(execution_times),
                'min_execution_time_ms': min(execution_times),
                'execution_time_std_dev': statistics.stdev(execution_times) if len(execution_times) > 1 else 0
            }
        
        # Generate recommendations
        if report['summary']['failed_scenarios'] > 0:
            report['recommendations'].append(
                "Some scenarios failed validation. Review balance algorithm parameters."
            )
        
        if report['summary']['average_balance_score'] < 0.8:
            report['recommendations'].append(
                "Average balance score is below 0.8. Consider tuning balance thresholds."
            )
        
        if report['summary']['total_failed_operations'] > len(scenarios):
            report['recommendations'].append(
                "High failure rate detected. Review error handling and retry mechanisms."
            )
        
        return report


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestLoadTestingFramework:
    """Tests for the load testing framework"""
    
    @pytest.fixture
    def load_test_framework(self):
        """Create load test framework"""
        config = LoadBalanceConfig(
            imbalance_threshold=0.2,
            min_streams_per_instance=1,
            max_streams_per_instance=50,
            rebalance_cooldown_seconds=5,  # Shorter for testing
            performance_weight=0.3,
            capacity_weight=0.4,
            failure_weight=0.3
        )
        load_balancer = SmartLoadBalancer(config)
        return LoadTestFramework(load_balancer)
    
    def test_scenario_creation(self, load_test_framework):
        """Test load test scenario creation"""
        scenarios = load_test_framework.create_load_test_scenarios()
        
        assert len(scenarios) > 0
        assert all(isinstance(scenario, LoadTestScenario) for scenario in scenarios)
        assert all(scenario.instance_count > 0 for scenario in scenarios)
        assert all(scenario.total_streams > 0 for scenario in scenarios)
    
    def test_instance_simulator_creation(self, load_test_framework):
        """Test instance simulator creation and behavior"""
        profiles = load_test_framework.create_performance_profiles()
        profile = profiles['medium_performance']
        
        simulator = LoadTestInstanceSimulator("test-instance", 20, profile)
        
        # Test initial state
        assert simulator.server_id == "test-instance"
        assert simulator.max_streams == 20
        assert simulator.current_streams == 0
        
        # Test load update
        simulator.update_load(10)
        assert simulator.current_streams == 10
        
        metrics = simulator.get_metrics()
        assert metrics.server_id == "test-instance"
        assert metrics.current_streams == 10
        assert metrics.max_streams == 20
    
    def test_balance_score_calculation(self, load_test_framework):
        """Test balance score calculation"""
        # Perfect balance
        balanced_instances = [
            InstanceMetrics("inst1", 10, 20, 50.0, 60.0),
            InstanceMetrics("inst2", 10, 20, 50.0, 60.0),
            InstanceMetrics("inst3", 10, 20, 50.0, 60.0)
        ]
        
        balance_score = load_test_framework.measure_balance_score(balanced_instances)
        assert balance_score > 0.9  # Should be near perfect
        
        # Imbalanced
        imbalanced_instances = [
            InstanceMetrics("inst1", 20, 20, 90.0, 90.0),  # Full load
            InstanceMetrics("inst2", 2, 20, 20.0, 30.0),   # Light load
            InstanceMetrics("inst3", 1, 20, 15.0, 25.0)    # Very light load
        ]
        
        imbalance_score = load_test_framework.measure_balance_score(imbalanced_instances)
        assert imbalance_score < 0.5  # Should be poor balance
    
    @pytest.mark.asyncio
    async def test_single_scenario_execution(self, load_test_framework):
        """Test execution of a single load test scenario"""
        scenario = LoadTestScenario(
            name="test_scenario",
            instance_count=3,
            total_streams=30,
            max_streams_per_instance=15,
            performance_variation=0.1,
            failure_rate=0.01,
            load_imbalance_factor=0.2,
            duration_seconds=5,  # Short duration for testing
            expected_balance_score=0.7
        )
        
        metrics = await load_test_framework.run_load_test_scenario(scenario)
        
        assert metrics.scenario_name == "test_scenario"
        assert metrics.execution_time_ms > 0
        assert 0 <= metrics.balance_score <= 1.0
        assert metrics.rebalance_operations >= 0
        assert metrics.failed_operations >= 0
    
    def test_result_validation(self, load_test_framework):
        """Test load test result validation"""
        scenario = LoadTestScenario(
            name="validation_test",
            instance_count=3,
            total_streams=30,
            max_streams_per_instance=15,
            performance_variation=0.1,
            failure_rate=0.01,
            load_imbalance_factor=0.2,
            duration_seconds=10,
            expected_balance_score=0.8
        )
        
        # Good metrics
        good_metrics = LoadTestMetrics(
            scenario_name="validation_test",
            execution_time_ms=5000,
            balance_score=0.85,
            rebalance_operations=2,
            failed_operations=0,
            average_response_time_ms=100,
            max_response_time_ms=200,
            throughput_ops_per_second=2.0,
            memory_usage_mb=10,
            cpu_usage_percent=20
        )
        
        validation = load_test_framework.validate_load_test_results(scenario, good_metrics)
        assert validation['passed'] is True
        assert len(validation['issues']) == 0
        
        # Poor metrics
        poor_metrics = LoadTestMetrics(
            scenario_name="validation_test",
            execution_time_ms=50000,  # Too slow
            balance_score=0.5,        # Poor balance
            rebalance_operations=2,
            failed_operations=5,      # Too many failures
            average_response_time_ms=2000,  # Too slow
            max_response_time_ms=5000,
            throughput_ops_per_second=0.2,
            memory_usage_mb=10,
            cpu_usage_percent=20
        )
        
        validation = load_test_framework.validate_load_test_results(scenario, poor_metrics)
        assert validation['passed'] is False
        assert len(validation['issues']) > 0
    
    def test_report_generation(self, load_test_framework):
        """Test load test report generation"""
        scenarios = [
            LoadTestScenario(
                name="report_test_1",
                instance_count=3, total_streams=30, max_streams_per_instance=15,
                performance_variation=0.1, failure_rate=0.01, load_imbalance_factor=0.2,
                duration_seconds=10, expected_balance_score=0.8
            ),
            LoadTestScenario(
                name="report_test_2",
                instance_count=5, total_streams=50, max_streams_per_instance=15,
                performance_variation=0.2, failure_rate=0.02, load_imbalance_factor=0.3,
                duration_seconds=15, expected_balance_score=0.7
            )
        ]
        
        results = [
            LoadTestMetrics(
                scenario_name="report_test_1", execution_time_ms=5000, balance_score=0.85,
                rebalance_operations=2, failed_operations=0, average_response_time_ms=100,
                max_response_time_ms=200, throughput_ops_per_second=2.0,
                memory_usage_mb=10, cpu_usage_percent=20
            ),
            LoadTestMetrics(
                scenario_name="report_test_2", execution_time_ms=7000, balance_score=0.75,
                rebalance_operations=3, failed_operations=1, average_response_time_ms=150,
                max_response_time_ms=300, throughput_ops_per_second=2.1,
                memory_usage_mb=15, cpu_usage_percent=25
            )
        ]
        
        report = load_test_framework.generate_load_test_report(scenarios, results)
        
        assert 'summary' in report
        assert 'scenario_results' in report
        assert 'performance_analysis' in report
        assert 'recommendations' in report
        
        assert report['summary']['total_scenarios'] == 2
        assert len(report['scenario_results']) == 2


if __name__ == "__main__":
    # Run load testing framework tests
    pytest.main([__file__, "-v", "--tb=short"])
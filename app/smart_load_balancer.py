"""
Smart Load Balancing Algorithm
Implements intelligent stream distribution that considers instance capacity and performance
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RebalanceReason(Enum):
    """Reasons for triggering rebalancing"""

    NEW_INSTANCE = "new_instance"
    INSTANCE_FAILURE = "instance_failure"
    LOAD_IMBALANCE = "load_imbalance"
    MANUAL = "manual"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass
class InstanceMetrics:
    """Performance metrics for an instance"""

    server_id: str
    current_streams: int
    max_streams: int
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    load_average_1m: float = 0.0
    response_time_ms: float = 0.0
    failure_count: int = 0
    last_heartbeat: datetime = None

    @property
    def load_factor(self) -> float:
        """Calculate current load factor (0.0 to 1.0)"""
        if self.max_streams == 0:
            return 1.0
        return self.current_streams / self.max_streams

    @property
    def available_capacity(self) -> int:
        """Available stream capacity"""
        return max(0, self.max_streams - self.current_streams)

    @property
    def performance_score(self) -> float:
        """Calculate performance score (higher is better, 0.0 to 1.0)"""
        # Base score from resource utilization (inverted - lower usage is better)
        cpu_score = max(0, 1.0 - (self.cpu_percent / 100.0))
        memory_score = max(0, 1.0 - (self.memory_percent / 100.0))
        load_score = max(0, 1.0 - min(1.0, self.load_average_1m / 4.0))

        # Penalty for failures
        failure_penalty = max(0, 1.0 - (self.failure_count * 0.1))

        # Response time penalty
        response_penalty = max(0, 1.0 - (self.response_time_ms / 1000.0))

        # Weighted average
        score = (
            cpu_score * 0.3
            + memory_score * 0.3
            + load_score * 0.2
            + failure_penalty * 0.1
            + response_penalty * 0.1
        )

        return max(0.1, min(1.0, score))


@dataclass
class MigrationPlan:
    """Plan for migrating streams between instances"""

    from_server: str
    to_server: str
    stream_ids: List[int]
    priority: int = 0
    estimated_impact: float = 0.0


@dataclass
class RebalanceResult:
    """Result of a rebalancing operation"""

    success: bool
    reason: RebalanceReason
    migrations: List[MigrationPlan]
    streams_moved: int
    instances_affected: int
    execution_time_ms: float
    error_message: Optional[str] = None


class LoadBalanceConfig:
    """Configuration for load balancing algorithm"""

    def __init__(self):
        self.imbalance_threshold = 0.20
        self.max_stream_difference = 2
        self.performance_threshold = 0.3
        self.max_migrations_per_cycle = 10
        self.migration_batch_size = 3
        self.migration_delay_seconds = 5
        self.min_instances_for_rebalance = 2
        self.max_load_factor = 0.9
        self.emergency_threshold = 0.95


class SmartLoadBalancer:
    """Intelligent load balancer for stream distribution"""

    def __init__(self, config: Optional[LoadBalanceConfig] = None):
        self.config = config or LoadBalanceConfig()
        self.last_rebalance = None
        self.rebalance_history = []

    def calculate_optimal_distribution(
        self, instances: List[InstanceMetrics], total_streams: int
    ) -> Dict[str, int]:
        """Calculate optimal stream distribution"""
        if not instances:
            return {}

        active_instances = [
            inst
            for inst in instances
            if inst.max_streams > 0 and inst.load_factor < self.config.max_load_factor
        ]

        if not active_instances:
            return {}

        # Simple weighted distribution based on capacity and performance
        total_weighted_capacity = sum(
            inst.max_streams * inst.performance_score for inst in active_instances
        )

        if total_weighted_capacity == 0:
            # Equal distribution fallback
            streams_per_instance = total_streams // len(active_instances)
            remainder = total_streams % len(active_instances)

            distribution = {}
            for i, inst in enumerate(active_instances):
                base_streams = streams_per_instance
                if i < remainder:
                    base_streams += 1
                distribution[inst.server_id] = min(base_streams, inst.max_streams)

            return distribution

        # Weighted distribution
        distribution = {}
        remaining_streams = total_streams

        for inst in active_instances:
            weight = (
                inst.max_streams * inst.performance_score
            ) / total_weighted_capacity
            ideal_streams = int(total_streams * weight)
            max_assignable = min(inst.max_streams, remaining_streams)
            assigned_streams = min(ideal_streams, max_assignable)

            distribution[inst.server_id] = assigned_streams
            remaining_streams -= assigned_streams

        return distribution

    def detect_imbalance(self, instances: List[InstanceMetrics]) -> Tuple[bool, str]:
        """Detect if load imbalance exists"""
        if len(instances) < self.config.min_instances_for_rebalance:
            return False, "Insufficient instances for rebalancing"

        active_instances = [inst for inst in instances if inst.max_streams > 0]

        if not active_instances:
            return False, "No active instances"

        # Check for emergency situations
        emergency_instances = [
            inst
            for inst in active_instances
            if inst.load_factor >= self.config.emergency_threshold
        ]

        if emergency_instances:
            return (
                True,
                f"Emergency: {len(emergency_instances)} instances at >95% capacity",
            )

        # Check load factor imbalance
        load_factors = [inst.load_factor for inst in active_instances]
        max_load = max(load_factors)
        min_load = min(load_factors)

        if max_load - min_load > self.config.imbalance_threshold:
            return (
                True,
                f"Load imbalance: {max_load:.2f} - {min_load:.2f} > {self.config.imbalance_threshold}",
            )

        # Check stream count difference
        stream_counts = [inst.current_streams for inst in active_instances]
        avg_streams = sum(stream_counts) / len(stream_counts)
        max_diff = max(abs(count - avg_streams) for count in stream_counts)

        if max_diff > self.config.max_stream_difference:
            return (
                True,
                f"Stream count imbalance: max difference {max_diff:.1f} > {self.config.max_stream_difference}",
            )

        return False, "System is balanced"

    def generate_rebalance_plan(
        self,
        instances: List[InstanceMetrics],
        total_streams: int,
        reason: RebalanceReason,
    ) -> List[MigrationPlan]:
        """Generate rebalance plan"""
        optimal_distribution = self.calculate_optimal_distribution(
            instances, total_streams
        )
        current_distribution = {
            inst.server_id: inst.current_streams for inst in instances
        }

        migrations = []

        # Find sources (over-allocated) and targets (under-allocated)
        sources = []
        targets = []

        for inst in instances:
            current = current_distribution.get(inst.server_id, 0)
            optimal = optimal_distribution.get(inst.server_id, 0)

            if current > optimal:
                excess = current - optimal
                sources.append((inst.server_id, excess, inst.performance_score))
            elif current < optimal and inst.load_factor < self.config.max_load_factor:
                deficit = optimal - current
                available_capacity = min(deficit, inst.available_capacity)
                if available_capacity > 0:
                    targets.append(
                        (inst.server_id, available_capacity, inst.performance_score)
                    )

        # Sort sources by performance (worst first) and targets by performance (best first)
        sources.sort(key=lambda x: x[2])
        targets.sort(key=lambda x: x[2], reverse=True)

        # Create migration plans
        migration_count = 0
        for source_id, excess, _ in sources:
            if migration_count >= self.config.max_migrations_per_cycle:
                break

            remaining_excess = excess

            for target_id, capacity, target_perf in targets:
                if (
                    remaining_excess <= 0
                    or migration_count >= self.config.max_migrations_per_cycle
                ):
                    break

                migration_size = min(
                    remaining_excess, capacity, self.config.migration_batch_size
                )

                if migration_size > 0:
                    migration = MigrationPlan(
                        from_server=source_id,
                        to_server=target_id,
                        stream_ids=[],
                        priority=self._calculate_priority(reason, target_perf),
                        estimated_impact=migration_size * 0.1,
                    )

                    migrations.append(migration)
                    remaining_excess -= migration_size
                    migration_count += 1

        migrations.sort(key=lambda x: x.priority, reverse=True)
        return migrations

    def _calculate_priority(
        self, reason: RebalanceReason, target_performance: float
    ) -> int:
        """Calculate migration priority"""
        base_priority = {
            RebalanceReason.NEW_INSTANCE: 50,
            RebalanceReason.INSTANCE_FAILURE: 100,
            RebalanceReason.LOAD_IMBALANCE: 70,
            RebalanceReason.PERFORMANCE_DEGRADATION: 80,
            RebalanceReason.MANUAL: 60,
        }.get(reason, 50)

        performance_boost = int(target_performance * 20)
        return base_priority + performance_boost

    def should_rebalance(
        self, instances: List[InstanceMetrics], min_interval_seconds: int = 60
    ) -> Tuple[bool, str]:
        """Determine if rebalancing should be performed"""
        if self.last_rebalance and datetime.now() - self.last_rebalance < timedelta(
            seconds=min_interval_seconds
        ):
            return (
                False,
                f"Too soon since last rebalance ({min_interval_seconds}s minimum)",
            )

        return self.detect_imbalance(instances)

    def get_rebalance_statistics(self) -> Dict:
        """Get rebalancing statistics"""
        if not self.rebalance_history:
            return {
                "total_rebalances": 0,
                "successful_rebalances": 0,
                "total_streams_moved": 0,
                "average_execution_time_ms": 0,
                "last_rebalance": None,
                "success_rate": 0,
            }

        successful = [r for r in self.rebalance_history if r.success]

        return {
            "total_rebalances": len(self.rebalance_history),
            "successful_rebalances": len(successful),
            "total_streams_moved": sum(r.streams_moved for r in self.rebalance_history),
            "average_execution_time_ms": sum(
                r.execution_time_ms for r in self.rebalance_history
            )
            / len(self.rebalance_history),
            "last_rebalance": (
                self.last_rebalance.isoformat() if self.last_rebalance else None
            ),
            "success_rate": (
                len(successful) / len(self.rebalance_history)
                if self.rebalance_history
                else 0
            ),
        }

"""
Consistency Verification and Auto-Recovery System

This module implements comprehensive consistency checking between orchestrator and workers,
auto-recovery mechanisms for state synchronization issues, and conflict resolution
for duplicate stream assignments.

Requirements addressed: 3.1, 3.2, 3.3, 3.4
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ConsistencyStatus(Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    CONFLICT = "conflict"
    ORPHANED = "orphaned"
    DUPLICATE = "duplicate"


class RecoveryAction(Enum):
    REASSIGN = "reassign"
    REMOVE = "remove"
    SYNC = "sync"
    FORCE_REGISTER = "force_register"
    RESOLVE_CONFLICT = "resolve_conflict"


@dataclass
class StreamAssignmentIssue:
    stream_id: int
    issue_type: ConsistencyStatus
    orchestrator_assignment: Optional[str] = None
    worker_assignments: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)
    severity: str = "medium"
    description: str = ""


@dataclass
class InstanceStateIssue:
    instance_id: str
    issue_type: ConsistencyStatus
    orchestrator_state: Optional[Dict] = None
    worker_state: Optional[Dict] = None
    detected_at: datetime = field(default_factory=datetime.now)
    description: str = ""


@dataclass
class ConsistencyReport:
    timestamp: datetime
    total_streams_checked: int
    total_instances_checked: int
    stream_issues: List[StreamAssignmentIssue]
    instance_issues: List[InstanceStateIssue]
    consistency_score: float
    recommendations: List[str]

    @property
    def is_healthy(self) -> bool:
        return self.consistency_score >= 0.95 and len(self.stream_issues) == 0

    @property
    def critical_issues(self) -> List[StreamAssignmentIssue]:
        return [issue for issue in self.stream_issues if issue.severity == "critical"]


@dataclass
class RecoveryResult:
    action_taken: RecoveryAction
    success: bool
    details: str
    timestamp: datetime = field(default_factory=datetime.now)
    affected_streams: List[int] = field(default_factory=list)
    affected_instances: List[str] = field(default_factory=list)


class ConsistencyChecker:
    """
    Comprehensive consistency checking system that verifies state synchronization
    between orchestrator and workers, detects conflicts, and provides auto-recovery.
    """

    def __init__(self, db_manager, orchestrator_client=None):
        self.db_manager = db_manager
        self.orchestrator_client = orchestrator_client
        self.recovery_attempts = {}  # Track recovery attempts per issue
        self.max_recovery_attempts = 3
        self.consistency_history = []

    async def verify_stream_assignments(self) -> ConsistencyReport:
        """
        Verify consistency of stream assignments between orchestrator and workers.

        Requirements: 3.1, 3.3
        """
        logger.info("Starting comprehensive stream assignment verification")

        try:
            # Get orchestrator state
            orchestrator_assignments = await self._get_orchestrator_assignments()

            # Get worker states
            worker_assignments = await self._get_worker_assignments()

            # Detect issues
            stream_issues = []

            # Check for orphaned streams (in orchestrator but not in any worker)
            orphaned_streams = await self._detect_orphaned_streams(
                orchestrator_assignments, worker_assignments
            )
            stream_issues.extend(orphaned_streams)

            # Check for duplicate assignments
            duplicate_assignments = await self._detect_duplicate_assignments(
                orchestrator_assignments, worker_assignments
            )
            stream_issues.extend(duplicate_assignments)

            # Check for unauthorized streams (in worker but not in orchestrator)
            unauthorized_streams = await self._detect_unauthorized_streams(
                orchestrator_assignments, worker_assignments
            )
            stream_issues.extend(unauthorized_streams)

            # Check instance states
            instance_issues = await self._verify_instance_states()

            # Calculate consistency score
            total_streams = len(orchestrator_assignments) + sum(
                len(assignments) for assignments in worker_assignments.values()
            )
            consistency_score = self._calculate_consistency_score(
                total_streams, len(stream_issues)
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                stream_issues, instance_issues
            )

            report = ConsistencyReport(
                timestamp=datetime.now(),
                total_streams_checked=total_streams,
                total_instances_checked=len(worker_assignments),
                stream_issues=stream_issues,
                instance_issues=instance_issues,
                consistency_score=consistency_score,
                recommendations=recommendations,
            )

            # Store in history
            self.consistency_history.append(report)
            if len(self.consistency_history) > 100:  # Keep last 100 reports
                self.consistency_history.pop(0)

            logger.info(
                f"Consistency check completed. Score: {consistency_score:.2f}, "
                f"Issues found: {len(stream_issues)}"
            )

            return report

        except Exception as e:
            logger.error(f"Error during consistency verification: {e}")
            raise

    async def detect_orphaned_streams(self) -> List[StreamAssignmentIssue]:
        """
        Detect streams that exist in orchestrator but are not assigned to any active worker.

        Requirements: 3.1, 3.3
        """
        orchestrator_assignments = await self._get_orchestrator_assignments()
        worker_assignments = await self._get_worker_assignments()

        return await self._detect_orphaned_streams(
            orchestrator_assignments, worker_assignments
        )

    async def resolve_conflicts(
        self, conflicts: List[StreamAssignmentIssue]
    ) -> List[RecoveryResult]:
        """
        Resolve conflicts in stream assignments automatically.

        Requirements: 3.2, 3.3
        """
        results = []

        for conflict in conflicts:
            try:
                result = await self._resolve_single_conflict(conflict)
                results.append(result)

                # Track recovery attempts
                conflict_key = f"{conflict.stream_id}_{conflict.issue_type.value}"
                self.recovery_attempts[conflict_key] = (
                    self.recovery_attempts.get(conflict_key, 0) + 1
                )

            except Exception as e:
                logger.error(
                    f"Failed to resolve conflict for stream {conflict.stream_id}: {e}"
                )
                results.append(
                    RecoveryResult(
                        action_taken=RecoveryAction.RESOLVE_CONFLICT,
                        success=False,
                        details=f"Error resolving conflict: {e}",
                        affected_streams=[conflict.stream_id],
                    )
                )

        return results

    async def synchronize_instance_state(self, instance_id: str) -> RecoveryResult:
        """
        Synchronize state between orchestrator and specific worker instance.

        Requirements: 3.1, 3.2, 3.4
        """
        logger.info(f"Synchronizing state for instance {instance_id}")

        try:
            # Get current states
            orchestrator_state = await self._get_instance_state_from_orchestrator(
                instance_id
            )
            worker_state = await self._get_instance_state_from_worker(instance_id)

            if not orchestrator_state and not worker_state:
                return RecoveryResult(
                    action_taken=RecoveryAction.SYNC,
                    success=False,
                    details=f"Instance {instance_id} not found in orchestrator or worker",
                    affected_instances=[instance_id],
                )

            # Determine sync strategy
            if not orchestrator_state and worker_state:
                # Worker exists but not in orchestrator - force re-register
                result = await self._force_reregister_instance(
                    instance_id, worker_state
                )
            elif orchestrator_state and not worker_state:
                # Orchestrator has instance but worker is gone - clean up
                result = await self._cleanup_orphaned_instance(
                    instance_id, orchestrator_state
                )
            else:
                # Both exist - sync differences
                result = await self._sync_instance_differences(
                    instance_id, orchestrator_state, worker_state
                )

            return result

        except Exception as e:
            logger.error(f"Error synchronizing instance {instance_id}: {e}")
            return RecoveryResult(
                action_taken=RecoveryAction.SYNC,
                success=False,
                details=f"Synchronization error: {e}",
                affected_instances=[instance_id],
            )

    async def auto_recover_inconsistencies(
        self, report: ConsistencyReport
    ) -> List[RecoveryResult]:
        """
        Automatically attempt to recover from detected inconsistencies.

        Requirements: 3.2, 3.4
        """
        logger.info("Starting auto-recovery for detected inconsistencies")
        results = []

        # Prioritize critical issues first
        critical_issues = [
            issue for issue in report.stream_issues if issue.severity == "critical"
        ]
        other_issues = [
            issue for issue in report.stream_issues if issue.severity != "critical"
        ]

        # Process critical issues first
        for issue in critical_issues:
            if self._should_attempt_recovery(issue):
                try:
                    result = await self._auto_recover_issue(issue)
                    results.append(result)
                except Exception as e:
                    logger.error(
                        f"Auto-recovery failed for critical issue {issue.stream_id}: {e}"
                    )

        # Process other issues
        for issue in other_issues:
            if self._should_attempt_recovery(issue):
                try:
                    result = await self._auto_recover_issue(issue)
                    results.append(result)
                except Exception as e:
                    logger.error(
                        f"Auto-recovery failed for issue {issue.stream_id}: {e}"
                    )

        # Process instance issues
        for instance_issue in report.instance_issues:
            try:
                result = await self.synchronize_instance_state(
                    instance_issue.instance_id
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Instance sync failed for {instance_issue.instance_id}: {e}"
                )

        successful_recoveries = len([r for r in results if r.success])
        logger.info(
            f"Auto-recovery completed. {successful_recoveries}/{len(results)} successful"
        )

        return results

    # Private helper methods

    async def _get_orchestrator_assignments(self) -> Dict[int, str]:
        """Get current stream assignments from orchestrator database."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT stream_id, server_id 
                    FROM stream_assignments 
                    WHERE status = 'active'
                """
                )
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting orchestrator assignments: {e}")
            return {}

    async def _get_worker_assignments(self) -> Dict[str, List[int]]:
        """Get current stream assignments from all workers."""
        # This would typically query each worker's local state
        # For now, we'll simulate by checking the database
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT DISTINCT server_id FROM instances WHERE status = 'active'
                """
                )
                instances = [row[0] for row in await cursor.fetchall()]

                worker_assignments = {}
                for instance_id in instances:
                    # In a real implementation, this would query the worker directly
                    # For now, we'll use the orchestrator's view
                    cursor = await conn.execute(
                        """
                        SELECT stream_id FROM stream_assignments 
                        WHERE server_id = ? AND status = 'active'
                    """,
                        (instance_id,),
                    )
                    streams = [row[0] for row in await cursor.fetchall()]
                    worker_assignments[instance_id] = streams

                return worker_assignments
        except Exception as e:
            logger.error(f"Error getting worker assignments: {e}")
            return {}

    async def _detect_orphaned_streams(
        self,
        orchestrator_assignments: Dict[int, str],
        worker_assignments: Dict[str, List[int]],
    ) -> List[StreamAssignmentIssue]:
        """Detect streams assigned in orchestrator but not present in any worker."""
        issues = []

        # Get all streams assigned to workers
        worker_streams = set()
        for streams in worker_assignments.values():
            worker_streams.update(streams)

        # Find orphaned streams
        for stream_id, server_id in orchestrator_assignments.items():
            if stream_id not in worker_streams:
                issues.append(
                    StreamAssignmentIssue(
                        stream_id=stream_id,
                        issue_type=ConsistencyStatus.ORPHANED,
                        orchestrator_assignment=server_id,
                        worker_assignments=[],
                        severity="high",
                        description=f"Stream {stream_id} assigned to {server_id} in orchestrator but not found in any worker",
                    )
                )

        return issues

    async def _detect_duplicate_assignments(
        self,
        orchestrator_assignments: Dict[int, str],
        worker_assignments: Dict[str, List[int]],
    ) -> List[StreamAssignmentIssue]:
        """Detect streams assigned to multiple workers."""
        issues = []

        # Track which workers have each stream
        stream_workers = {}
        for worker_id, streams in worker_assignments.items():
            for stream_id in streams:
                if stream_id not in stream_workers:
                    stream_workers[stream_id] = []
                stream_workers[stream_id].append(worker_id)

        # Find duplicates
        for stream_id, workers in stream_workers.items():
            if len(workers) > 1:
                orchestrator_assignment = orchestrator_assignments.get(stream_id)
                issues.append(
                    StreamAssignmentIssue(
                        stream_id=stream_id,
                        issue_type=ConsistencyStatus.DUPLICATE,
                        orchestrator_assignment=orchestrator_assignment,
                        worker_assignments=workers,
                        severity="critical",
                        description=f"Stream {stream_id} assigned to multiple workers: {workers}",
                    )
                )

        return issues

    async def _detect_unauthorized_streams(
        self,
        orchestrator_assignments: Dict[int, str],
        worker_assignments: Dict[str, List[int]],
    ) -> List[StreamAssignmentIssue]:
        """Detect streams in workers but not assigned by orchestrator."""
        issues = []

        orchestrator_streams = set(orchestrator_assignments.keys())

        for worker_id, streams in worker_assignments.items():
            for stream_id in streams:
                if stream_id not in orchestrator_streams:
                    issues.append(
                        StreamAssignmentIssue(
                            stream_id=stream_id,
                            issue_type=ConsistencyStatus.INCONSISTENT,
                            orchestrator_assignment=None,
                            worker_assignments=[worker_id],
                            severity="medium",
                            description=f"Stream {stream_id} found in worker {worker_id} but not assigned by orchestrator",
                        )
                    )

        return issues

    async def _verify_instance_states(self) -> List[InstanceStateIssue]:
        """Verify consistency of instance states."""
        issues = []

        try:
            async with self.db_manager.get_connection() as conn:
                # Get instances from orchestrator
                cursor = await conn.execute(
                    """
                    SELECT server_id, status, current_streams, max_streams, last_heartbeat
                    FROM instances
                """
                )
                orchestrator_instances = {
                    row[0]: {
                        "status": row[1],
                        "current_streams": row[2],
                        "max_streams": row[3],
                        "last_heartbeat": row[4],
                    }
                    for row in await cursor.fetchall()
                }

                # Check for stale heartbeats
                stale_threshold = datetime.now() - timedelta(minutes=5)
                for instance_id, state in orchestrator_instances.items():
                    if state["last_heartbeat"]:
                        last_heartbeat = datetime.fromisoformat(state["last_heartbeat"])
                        if (
                            last_heartbeat < stale_threshold
                            and state["status"] == "active"
                        ):
                            issues.append(
                                InstanceStateIssue(
                                    instance_id=instance_id,
                                    issue_type=ConsistencyStatus.INCONSISTENT,
                                    orchestrator_state=state,
                                    description=f"Instance {instance_id} has stale heartbeat but marked as active",
                                )
                            )

        except Exception as e:
            logger.error(f"Error verifying instance states: {e}")

        return issues

    def _calculate_consistency_score(
        self, total_streams: int, issues_count: int
    ) -> float:
        """Calculate overall consistency score (0.0 to 1.0)."""
        if total_streams == 0:
            return 1.0

        # Base score calculation
        error_rate = issues_count / total_streams
        base_score = max(0.0, 1.0 - error_rate)

        # Apply penalties for critical issues
        critical_penalty = 0.1 * len(
            [
                issue
                for issue in getattr(self, "_current_issues", [])
                if getattr(issue, "severity", "") == "critical"
            ]
        )

        return max(0.0, base_score - critical_penalty)

    def _generate_recommendations(
        self,
        stream_issues: List[StreamAssignmentIssue],
        instance_issues: List[InstanceStateIssue],
    ) -> List[str]:
        """Generate actionable recommendations based on detected issues."""
        recommendations = []

        # Stream-related recommendations
        orphaned_count = len(
            [i for i in stream_issues if i.issue_type == ConsistencyStatus.ORPHANED]
        )
        duplicate_count = len(
            [i for i in stream_issues if i.issue_type == ConsistencyStatus.DUPLICATE]
        )
        unauthorized_count = len(
            [i for i in stream_issues if i.issue_type == ConsistencyStatus.INCONSISTENT]
        )

        if orphaned_count > 0:
            recommendations.append(
                f"Reassign {orphaned_count} orphaned streams to active workers"
            )

        if duplicate_count > 0:
            recommendations.append(
                f"Resolve {duplicate_count} duplicate stream assignments immediately"
            )

        if unauthorized_count > 0:
            recommendations.append(
                f"Synchronize {unauthorized_count} unauthorized streams with orchestrator"
            )

        # Instance-related recommendations
        stale_instances = len(
            [i for i in instance_issues if "stale heartbeat" in i.description]
        )
        if stale_instances > 0:
            recommendations.append(
                f"Check connectivity for {stale_instances} instances with stale heartbeats"
            )

        # General recommendations
        if len(stream_issues) > 10:
            recommendations.append(
                "Consider running full system rebalancing due to high inconsistency count"
            )

        if not recommendations:
            recommendations.append("System consistency is good - continue monitoring")

        return recommendations

    async def _resolve_single_conflict(
        self, conflict: StreamAssignmentIssue
    ) -> RecoveryResult:
        """Resolve a single stream assignment conflict."""

        if conflict.issue_type == ConsistencyStatus.DUPLICATE:
            return await self._resolve_duplicate_assignment(conflict)
        elif conflict.issue_type == ConsistencyStatus.ORPHANED:
            return await self._resolve_orphaned_stream(conflict)
        elif conflict.issue_type == ConsistencyStatus.INCONSISTENT:
            return await self._resolve_unauthorized_stream(conflict)
        else:
            return RecoveryResult(
                action_taken=RecoveryAction.RESOLVE_CONFLICT,
                success=False,
                details=f"Unknown conflict type: {conflict.issue_type}",
                affected_streams=[conflict.stream_id],
            )

    async def _resolve_duplicate_assignment(
        self, conflict: StreamAssignmentIssue
    ) -> RecoveryResult:
        """Resolve duplicate stream assignment by keeping one and removing others."""
        try:
            # Keep the assignment that matches orchestrator, or first worker if no orchestrator assignment
            keeper = conflict.orchestrator_assignment or conflict.worker_assignments[0]

            # Remove from other workers (in a real implementation, this would call worker APIs)
            removed_from = []
            for worker_id in conflict.worker_assignments:
                if worker_id != keeper:
                    # Simulate removal - in real implementation, call worker API
                    removed_from.append(worker_id)

            # Update orchestrator if needed
            if not conflict.orchestrator_assignment:
                async with self.db_manager.get_connection() as conn:
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO stream_assignments (stream_id, server_id, status, assigned_at)
                        VALUES (?, ?, 'active', ?)
                    """,
                        (conflict.stream_id, keeper, datetime.now().isoformat()),
                    )
                    await conn.commit()

            return RecoveryResult(
                action_taken=RecoveryAction.RESOLVE_CONFLICT,
                success=True,
                details=f"Kept assignment to {keeper}, removed from {removed_from}",
                affected_streams=[conflict.stream_id],
                affected_instances=removed_from,
            )

        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.RESOLVE_CONFLICT,
                success=False,
                details=f"Failed to resolve duplicate: {e}",
                affected_streams=[conflict.stream_id],
            )

    async def _resolve_orphaned_stream(
        self, conflict: StreamAssignmentIssue
    ) -> RecoveryResult:
        """Resolve orphaned stream by reassigning to an available worker."""
        try:
            # Find an available worker
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT server_id, current_streams, max_streams 
                    FROM instances 
                    WHERE status = 'active' AND current_streams < max_streams
                    ORDER BY current_streams ASC
                    LIMIT 1
                """
                )
                available_worker = await cursor.fetchone()

                if not available_worker:
                    return RecoveryResult(
                        action_taken=RecoveryAction.REASSIGN,
                        success=False,
                        details="No available workers for reassignment",
                        affected_streams=[conflict.stream_id],
                    )

                worker_id = available_worker[0]

                # Update assignment
                await conn.execute(
                    """
                    UPDATE stream_assignments 
                    SET server_id = ?, assigned_at = ?
                    WHERE stream_id = ?
                """,
                    (worker_id, datetime.now().isoformat(), conflict.stream_id),
                )

                # Update worker stream count
                await conn.execute(
                    """
                    UPDATE instances 
                    SET current_streams = current_streams + 1
                    WHERE server_id = ?
                """,
                    (worker_id,),
                )

                await conn.commit()

                return RecoveryResult(
                    action_taken=RecoveryAction.REASSIGN,
                    success=True,
                    details=f"Reassigned orphaned stream to {worker_id}",
                    affected_streams=[conflict.stream_id],
                    affected_instances=[worker_id],
                )

        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.REASSIGN,
                success=False,
                details=f"Failed to reassign orphaned stream: {e}",
                affected_streams=[conflict.stream_id],
            )

    async def _resolve_unauthorized_stream(
        self, conflict: StreamAssignmentIssue
    ) -> RecoveryResult:
        """Resolve unauthorized stream by either legitimizing or removing it."""
        try:
            worker_id = conflict.worker_assignments[0]

            # Check if worker can legitimately have this stream
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT current_streams, max_streams 
                    FROM instances 
                    WHERE server_id = ? AND status = 'active'
                """,
                    (worker_id,),
                )
                worker_info = await cursor.fetchone()

                if worker_info and worker_info[0] < worker_info[1]:
                    # Worker has capacity - legitimize the assignment
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO stream_assignments (stream_id, server_id, status, assigned_at)
                        VALUES (?, ?, 'active', ?)
                    """,
                        (conflict.stream_id, worker_id, datetime.now().isoformat()),
                    )

                    await conn.execute(
                        """
                        UPDATE instances 
                        SET current_streams = current_streams + 1
                        WHERE server_id = ?
                    """,
                        (worker_id,),
                    )

                    await conn.commit()

                    return RecoveryResult(
                        action_taken=RecoveryAction.SYNC,
                        success=True,
                        details=f"Legitimized unauthorized stream assignment to {worker_id}",
                        affected_streams=[conflict.stream_id],
                        affected_instances=[worker_id],
                    )
                else:
                    # Worker at capacity or inactive - remove assignment
                    # In real implementation, would call worker API to stop processing
                    return RecoveryResult(
                        action_taken=RecoveryAction.REMOVE,
                        success=True,
                        details=f"Removed unauthorized stream from overloaded/inactive worker {worker_id}",
                        affected_streams=[conflict.stream_id],
                        affected_instances=[worker_id],
                    )

        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.SYNC,
                success=False,
                details=f"Failed to resolve unauthorized stream: {e}",
                affected_streams=[conflict.stream_id],
            )

    def _should_attempt_recovery(self, issue: StreamAssignmentIssue) -> bool:
        """Determine if auto-recovery should be attempted for an issue."""
        issue_key = f"{issue.stream_id}_{issue.issue_type.value}"
        attempts = self.recovery_attempts.get(issue_key, 0)

        # Don't attempt if we've already tried too many times
        if attempts >= self.max_recovery_attempts:
            logger.warning(f"Max recovery attempts reached for {issue_key}")
            return False

        # Always attempt recovery for critical issues
        if issue.severity == "critical":
            return True

        # For non-critical issues, be more conservative
        return attempts < 2

    async def _auto_recover_issue(self, issue: StreamAssignmentIssue) -> RecoveryResult:
        """Automatically recover from a detected issue."""
        logger.info(
            f"Attempting auto-recovery for stream {issue.stream_id}, type: {issue.issue_type}"
        )

        return await self._resolve_single_conflict(issue)

    async def _get_instance_state_from_orchestrator(
        self, instance_id: str
    ) -> Optional[Dict]:
        """Get instance state from orchestrator database."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT server_id, status, current_streams, max_streams, last_heartbeat
                    FROM instances WHERE server_id = ?
                """,
                    (instance_id,),
                )
                row = await cursor.fetchone()

                if row:
                    return {
                        "server_id": row[0],
                        "status": row[1],
                        "current_streams": row[2],
                        "max_streams": row[3],
                        "last_heartbeat": row[4],
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting orchestrator state for {instance_id}: {e}")
            return None

    async def _get_instance_state_from_worker(self, instance_id: str) -> Optional[Dict]:
        """Get instance state from worker (simulated for now)."""
        # In a real implementation, this would query the worker directly
        # For now, we'll simulate based on database state
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT COUNT(*) FROM stream_assignments 
                    WHERE server_id = ? AND status = 'active'
                """,
                    (instance_id,),
                )
                stream_count = (await cursor.fetchone())[0]

                return {
                    "server_id": instance_id,
                    "active_streams": stream_count,
                    "last_seen": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.error(f"Error getting worker state for {instance_id}: {e}")
            return None

    async def _force_reregister_instance(
        self, instance_id: str, worker_state: Dict
    ) -> RecoveryResult:
        """Force re-registration of worker instance in orchestrator."""
        try:
            async with self.db_manager.get_connection() as conn:
                # Register instance with default values
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO instances 
                    (server_id, ip, port, max_streams, current_streams, status, last_heartbeat)
                    VALUES (?, '0.0.0.0', 0, 10, ?, 'active', ?)
                """,
                    (
                        instance_id,
                        worker_state.get("active_streams", 0),
                        datetime.now().isoformat(),
                    ),
                )

                await conn.commit()

                return RecoveryResult(
                    action_taken=RecoveryAction.FORCE_REGISTER,
                    success=True,
                    details=f"Force re-registered instance {instance_id}",
                    affected_instances=[instance_id],
                )
        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.FORCE_REGISTER,
                success=False,
                details=f"Failed to force re-register {instance_id}: {e}",
                affected_instances=[instance_id],
            )

    async def _cleanup_orphaned_instance(
        self, instance_id: str, orchestrator_state: Dict
    ) -> RecoveryResult:
        """Clean up orphaned instance from orchestrator."""
        try:
            async with self.db_manager.get_connection() as conn:
                # Remove instance
                await conn.execute(
                    "DELETE FROM instances WHERE server_id = ?", (instance_id,)
                )

                # Reassign its streams
                cursor = await conn.execute(
                    """
                    SELECT stream_id FROM stream_assignments 
                    WHERE server_id = ? AND status = 'active'
                """,
                    (instance_id,),
                )
                orphaned_streams = [row[0] for row in await cursor.fetchall()]

                # Mark streams as unassigned for rebalancing
                await conn.execute(
                    """
                    UPDATE stream_assignments 
                    SET status = 'unassigned' 
                    WHERE server_id = ?
                """,
                    (instance_id,),
                )

                await conn.commit()

                return RecoveryResult(
                    action_taken=RecoveryAction.REMOVE,
                    success=True,
                    details=f"Cleaned up orphaned instance {instance_id}, marked {len(orphaned_streams)} streams for reassignment",
                    affected_instances=[instance_id],
                    affected_streams=orphaned_streams,
                )
        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.REMOVE,
                success=False,
                details=f"Failed to cleanup orphaned instance {instance_id}: {e}",
                affected_instances=[instance_id],
            )

    async def _sync_instance_differences(
        self, instance_id: str, orchestrator_state: Dict, worker_state: Dict
    ) -> RecoveryResult:
        """Sync differences between orchestrator and worker state."""
        try:
            differences = []

            # Check stream count differences
            orchestrator_streams = orchestrator_state.get("current_streams", 0)
            worker_streams = worker_state.get("active_streams", 0)

            if orchestrator_streams != worker_streams:
                differences.append(
                    f"Stream count mismatch: orchestrator={orchestrator_streams}, worker={worker_streams}"
                )

                # Update orchestrator to match worker reality
                async with self.db_manager.get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE instances 
                        SET current_streams = ?
                        WHERE server_id = ?
                    """,
                        (worker_streams, instance_id),
                    )
                    await conn.commit()

            return RecoveryResult(
                action_taken=RecoveryAction.SYNC,
                success=True,
                details=f"Synced differences for {instance_id}: {'; '.join(differences) if differences else 'No differences found'}",
                affected_instances=[instance_id],
            )

        except Exception as e:
            return RecoveryResult(
                action_taken=RecoveryAction.SYNC,
                success=False,
                details=f"Failed to sync instance {instance_id}: {e}",
                affected_instances=[instance_id],
            )


class ConsistencyMonitor:
    """
    Continuous monitoring service for system consistency.
    Runs periodic checks and triggers auto-recovery when needed.
    """

    def __init__(
        self, consistency_checker: ConsistencyChecker, check_interval: int = 300
    ):
        self.consistency_checker = consistency_checker
        self.check_interval = check_interval  # seconds
        self.monitoring = False
        self.last_check = None

    async def start_monitoring(self):
        """Start continuous consistency monitoring."""
        self.monitoring = True
        logger.info(
            f"Starting consistency monitoring with {self.check_interval}s interval"
        )

        while self.monitoring:
            try:
                await self._perform_check_cycle()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    def stop_monitoring(self):
        """Stop consistency monitoring."""
        self.monitoring = False
        logger.info("Consistency monitoring stopped")

    async def _perform_check_cycle(self):
        """Perform a complete consistency check and recovery cycle."""
        logger.debug("Performing consistency check cycle")

        # Run consistency check
        report = await self.consistency_checker.verify_stream_assignments()
        self.last_check = report

        # Auto-recover if issues found and not too many recent attempts
        if not report.is_healthy and len(report.stream_issues) > 0:
            logger.warning(
                f"Consistency issues detected: {len(report.stream_issues)} issues, score: {report.consistency_score:.2f}"
            )

            # Attempt auto-recovery for non-critical issues
            non_critical_issues = [
                issue for issue in report.stream_issues if issue.severity != "critical"
            ]
            if non_critical_issues:
                recovery_results = (
                    await self.consistency_checker.auto_recover_inconsistencies(report)
                )
                successful_recoveries = len([r for r in recovery_results if r.success])
                logger.info(
                    f"Auto-recovery completed: {successful_recoveries}/{len(recovery_results)} successful"
                )
        else:
            logger.debug(
                f"System consistency healthy: score {report.consistency_score:.2f}"
            )

    def get_last_report(self) -> Optional[ConsistencyReport]:
        """Get the last consistency report."""
        return self.last_check

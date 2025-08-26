"""
Test suite for the Consistency Verification and Auto-Recovery System

Tests all aspects of consistency checking, conflict resolution, and auto-recovery
to ensure requirements 3.1, 3.2, 3.3, 3.4 are properly implemented.
"""

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from consistency_checker import (ConsistencyChecker, ConsistencyMonitor,
                                 ConsistencyReport, ConsistencyStatus,
                                 InstanceStateIssue, RecoveryAction,
                                 RecoveryResult, StreamAssignmentIssue)


class MockDatabaseManager:
    """Mock database manager for testing."""
    
    def __init__(self):
        self.db_path = None
        self.connection = None
        
    async def setup_test_db(self):
        """Set up test database with sample data."""
        # Create temporary database
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        self.connection = sqlite3.connect(self.db_path)
        
        # Create tables
        self.connection.execute("""
            CREATE TABLE instances (
                server_id TEXT PRIMARY KEY,
                ip TEXT,
                port INTEGER,
                max_streams INTEGER,
                current_streams INTEGER,
                status TEXT,
                last_heartbeat TEXT
            )
        """)
        
        self.connection.execute("""
            CREATE TABLE stream_assignments (
                stream_id INTEGER,
                server_id TEXT,
                status TEXT,
                assigned_at TEXT,
                PRIMARY KEY (stream_id, server_id)
            )
        """)
        
        # Insert test data
        now = datetime.now().isoformat()
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        
        # Active instances
        self.connection.execute("""
            INSERT INTO instances VALUES 
            ('worker1', '192.168.1.1', 8001, 10, 5, 'active', ?),
            ('worker2', '192.168.1.2', 8002, 10, 3, 'active', ?),
            ('worker3', '192.168.1.3', 8003, 10, 0, 'inactive', ?)
        """, (now, now, old_time))
        
        # Stream assignments
        self.connection.execute("""
            INSERT INTO stream_assignments VALUES 
            (1, 'worker1', 'active', ?),
            (2, 'worker1', 'active', ?),
            (3, 'worker2', 'active', ?),
            (4, 'worker2', 'active', ?),
            (5, 'worker1', 'active', ?),
            (6, 'nonexistent_worker', 'active', ?)
        """, (now, now, now, now, now, now))
        
        self.connection.commit()
    
    async def get_connection(self):
        """Return async context manager for database connection."""
        return AsyncConnection(self.connection)
    
    async def cleanup(self):
        """Clean up test database."""
        if self.connection:
            self.connection.close()
        if self.db_path and os.path.exists(self.db_path):
            os.unlink(self.db_path)


class AsyncConnection:
    """Async wrapper for sqlite connection."""
    
    def __init__(self, connection):
        self.connection = connection
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def execute(self, query, params=()):
        cursor = self.connection.execute(query, params)
        return AsyncCursor(cursor)
    
    async def commit(self):
        self.connection.commit()


class AsyncCursor:
    """Async wrapper for sqlite cursor."""
    
    def __init__(self, cursor):
        self.cursor = cursor
    
    async def fetchall(self):
        return self.cursor.fetchall()
    
    async def fetchone(self):
        return self.cursor.fetchone()


@pytest.fixture
async def db_manager():
    """Fixture providing a test database manager."""
    manager = MockDatabaseManager()
    await manager.setup_test_db()
    yield manager
    await manager.cleanup()


@pytest.fixture
def consistency_checker(event_loop):
    """Fixture providing a consistency checker with test database."""
    async def _create_checker():
        manager = MockDatabaseManager()
        await manager.setup_test_db()
        checker = ConsistencyChecker(manager)
        return checker, manager
    
    checker, manager = event_loop.run_until_complete(_create_checker())
    yield checker
    event_loop.run_until_complete(manager.cleanup())


class TestConsistencyChecker:
    """Test cases for ConsistencyChecker class."""
    
    @pytest.mark.asyncio
    async def test_verify_stream_assignments_basic(self, consistency_checker):
        """Test basic stream assignment verification."""
        report = await consistency_checker.verify_stream_assignments()
        
        assert isinstance(report, ConsistencyReport)
        assert report.total_streams_checked > 0
        assert report.total_instances_checked >= 2
        assert len(report.stream_issues) > 0  # Should detect orphaned stream
        assert 0.0 <= report.consistency_score <= 1.0
    
    @pytest.mark.asyncio
    async def test_detect_orphaned_streams(self, consistency_checker):
        """Test detection of orphaned streams (Requirement 3.1, 3.3)."""
        orphaned_streams = await consistency_checker.detect_orphaned_streams()
        
        # Should detect stream 6 assigned to nonexistent_worker
        orphaned_issues = [issue for issue in orphaned_streams 
                          if issue.issue_type == ConsistencyStatus.ORPHANED]
        
        assert len(orphaned_issues) > 0
        assert any(issue.stream_id == 6 for issue in orphaned_issues)
        assert any(issue.orchestrator_assignment == 'nonexistent_worker' for issue in orphaned_issues)
    
    @pytest.mark.asyncio
    async def test_resolve_orphaned_stream_conflict(self, consistency_checker):
        """Test resolution of orphaned stream conflicts (Requirement 3.2, 3.3)."""
        # Create orphaned stream issue
        orphaned_issue = StreamAssignmentIssue(
            stream_id=6,
            issue_type=ConsistencyStatus.ORPHANED,
            orchestrator_assignment='nonexistent_worker',
            worker_assignments=[],
            severity="high"
        )
        
        results = await consistency_checker.resolve_conflicts([orphaned_issue])
        
        assert len(results) == 1
        result = results[0]
        assert result.action_taken == RecoveryAction.REASSIGN
        assert 6 in result.affected_streams
    
    @pytest.mark.asyncio
    async def test_synchronize_instance_state(self, consistency_checker):
        """Test instance state synchronization (Requirement 3.1, 3.2, 3.4)."""
        # Test syncing existing instance
        result = await consistency_checker.synchronize_instance_state('worker1')
        
        assert isinstance(result, RecoveryResult)
        assert result.action_taken == RecoveryAction.SYNC
        assert 'worker1' in result.affected_instances
    
    @pytest.mark.asyncio
    async def test_synchronize_nonexistent_instance(self, consistency_checker):
        """Test syncing nonexistent instance."""
        result = await consistency_checker.synchronize_instance_state('nonexistent')
        
        assert isinstance(result, RecoveryResult)
        assert not result.success
        assert 'not found' in result.details.lower()
    
    @pytest.mark.asyncio
    async def test_auto_recover_inconsistencies(self, consistency_checker):
        """Test automatic recovery from inconsistencies (Requirement 3.2, 3.4)."""
        # First get a report with issues
        report = await consistency_checker.verify_stream_assignments()
        
        if len(report.stream_issues) > 0:
            results = await consistency_checker.auto_recover_inconsistencies(report)
            
            assert isinstance(results, list)
            assert len(results) > 0
            
            # Check that recovery was attempted
            for result in results:
                assert isinstance(result, RecoveryResult)
                assert result.action_taken in [
                    RecoveryAction.REASSIGN, 
                    RecoveryAction.RESOLVE_CONFLICT,
                    RecoveryAction.SYNC,
                    RecoveryAction.REMOVE
                ]
    
    @pytest.mark.asyncio
    async def test_duplicate_assignment_detection(self, consistency_checker):
        """Test detection of duplicate stream assignments."""
        # Modify the mock to simulate duplicate assignments
        async with consistency_checker.db_manager.get_connection() as conn:
            # Add duplicate assignment
            await conn.execute("""
                INSERT INTO stream_assignments VALUES (1, 'worker2', 'active', ?)
            """, (datetime.now().isoformat(),))
            await conn.commit()
        
        report = await consistency_checker.verify_stream_assignments()
        
        # Should detect duplicate assignment for stream 1
        duplicate_issues = [issue for issue in report.stream_issues 
                           if issue.issue_type == ConsistencyStatus.DUPLICATE]
        
        assert len(duplicate_issues) > 0
        assert any(issue.stream_id == 1 for issue in duplicate_issues)
    
    @pytest.mark.asyncio
    async def test_resolve_duplicate_assignment(self, consistency_checker):
        """Test resolution of duplicate assignments (Requirement 3.3)."""
        # Create duplicate assignment issue
        duplicate_issue = StreamAssignmentIssue(
            stream_id=1,
            issue_type=ConsistencyStatus.DUPLICATE,
            orchestrator_assignment='worker1',
            worker_assignments=['worker1', 'worker2'],
            severity="critical"
        )
        
        results = await consistency_checker.resolve_conflicts([duplicate_issue])
        
        assert len(results) == 1
        result = results[0]
        assert result.action_taken == RecoveryAction.RESOLVE_CONFLICT
        assert 1 in result.affected_streams
    
    @pytest.mark.asyncio
    async def test_consistency_score_calculation(self, consistency_checker):
        """Test consistency score calculation."""
        report = await consistency_checker.verify_stream_assignments()
        
        # Score should be between 0 and 1
        assert 0.0 <= report.consistency_score <= 1.0
        
        # If there are issues, score should be less than 1
        if len(report.stream_issues) > 0:
            assert report.consistency_score < 1.0
    
    @pytest.mark.asyncio
    async def test_stale_heartbeat_detection(self, consistency_checker):
        """Test detection of instances with stale heartbeats."""
        report = await consistency_checker.verify_stream_assignments()
        
        # Should detect worker3 with old heartbeat
        stale_instances = [issue for issue in report.instance_issues 
                          if 'stale heartbeat' in issue.description]
        
        assert len(stale_instances) > 0
        assert any(issue.instance_id == 'worker3' for issue in stale_instances)
    
    @pytest.mark.asyncio
    async def test_recovery_attempt_limiting(self, consistency_checker):
        """Test that recovery attempts are limited to prevent infinite loops."""
        # Create an issue
        issue = StreamAssignmentIssue(
            stream_id=999,
            issue_type=ConsistencyStatus.ORPHANED,
            severity="medium"
        )
        
        # Simulate multiple recovery attempts
        issue_key = f"{issue.stream_id}_{issue.issue_type.value}"
        consistency_checker.recovery_attempts[issue_key] = 3  # Max attempts
        
        # Should not attempt recovery
        should_attempt = consistency_checker._should_attempt_recovery(issue)
        assert not should_attempt
    
    @pytest.mark.asyncio
    async def test_critical_issue_always_recoverable(self, consistency_checker):
        """Test that critical issues are always attempted for recovery."""
        issue = StreamAssignmentIssue(
            stream_id=999,
            issue_type=ConsistencyStatus.DUPLICATE,
            severity="critical"
        )
        
        # Even with previous attempts, critical issues should be recoverable
        issue_key = f"{issue.stream_id}_{issue.issue_type.value}"
        consistency_checker.recovery_attempts[issue_key] = 2
        
        should_attempt = consistency_checker._should_attempt_recovery(issue)
        assert should_attempt


class TestConsistencyMonitor:
    """Test cases for ConsistencyMonitor class."""
    
    @pytest.mark.asyncio
    async def test_monitor_initialization(self, consistency_checker):
        """Test monitor initialization."""
        monitor = ConsistencyMonitor(consistency_checker, check_interval=60)
        
        assert monitor.consistency_checker == consistency_checker
        assert monitor.check_interval == 60
        assert not monitor.monitoring
        assert monitor.last_check is None
    
    @pytest.mark.asyncio
    async def test_single_check_cycle(self, consistency_checker):
        """Test a single monitoring check cycle."""
        monitor = ConsistencyMonitor(consistency_checker, check_interval=60)
        
        # Perform single check cycle
        await monitor._perform_check_cycle()
        
        # Should have a report now
        assert monitor.last_check is not None
        assert isinstance(monitor.last_check, ConsistencyReport)
    
    @pytest.mark.asyncio
    async def test_get_last_report(self, consistency_checker):
        """Test getting the last consistency report."""
        monitor = ConsistencyMonitor(consistency_checker)
        
        # Initially no report
        assert monitor.get_last_report() is None
        
        # After check cycle, should have report
        await monitor._perform_check_cycle()
        report = monitor.get_last_report()
        
        assert report is not None
        assert isinstance(report, ConsistencyReport)


class TestIntegrationScenarios:
    """Integration test scenarios for complete consistency workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_consistency_workflow(self, consistency_checker):
        """Test complete workflow from detection to recovery (All Requirements)."""
        # Step 1: Detect issues
        initial_report = await consistency_checker.verify_stream_assignments()
        initial_issues = len(initial_report.stream_issues)
        
        if initial_issues > 0:
            # Step 2: Attempt auto-recovery
            recovery_results = await consistency_checker.auto_recover_inconsistencies(initial_report)
            
            # Step 3: Verify recovery
            post_recovery_report = await consistency_checker.verify_stream_assignments()
            
            # Should have fewer issues or better consistency score
            assert (len(post_recovery_report.stream_issues) <= initial_issues or
                   post_recovery_report.consistency_score >= initial_report.consistency_score)
    
    @pytest.mark.asyncio
    async def test_orphaned_stream_complete_recovery(self, db_manager):
        """Test complete recovery of orphaned stream scenario."""
        checker = ConsistencyChecker(db_manager)
        
        # Add orphaned stream
        async with db_manager.get_connection() as conn:
            await conn.execute("""
                INSERT INTO stream_assignments VALUES (999, 'dead_worker', 'active', ?)
            """, (datetime.now().isoformat(),))
            await conn.commit()
        
        # Detect and recover
        report = await checker.verify_stream_assignments()
        orphaned_issues = [issue for issue in report.stream_issues 
                          if issue.stream_id == 999 and issue.issue_type == ConsistencyStatus.ORPHANED]
        
        assert len(orphaned_issues) > 0
        
        # Recover
        recovery_results = await checker.resolve_conflicts(orphaned_issues)
        
        # Verify recovery
        assert len(recovery_results) > 0
        assert any(result.success for result in recovery_results)
    
    @pytest.mark.asyncio
    async def test_instance_failure_recovery(self, db_manager):
        """Test recovery from instance failure scenario."""
        checker = ConsistencyChecker(db_manager)
        
        # Simulate instance failure by marking as inactive with old heartbeat
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        async with db_manager.get_connection() as conn:
            await conn.execute("""
                UPDATE instances 
                SET status = 'inactive', last_heartbeat = ?
                WHERE server_id = 'worker2'
            """, (old_time,))
            await conn.commit()
        
        # Sync instance state
        result = await checker.synchronize_instance_state('worker2')
        
        # Should handle the failed instance
        assert isinstance(result, RecoveryResult)
        assert 'worker2' in result.affected_instances


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
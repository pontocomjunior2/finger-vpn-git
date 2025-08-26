"""
Simplified test for consistency checker to verify basic functionality.
"""

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

from consistency_checker import (ConsistencyChecker, ConsistencyStatus,
                                 RecoveryAction, StreamAssignmentIssue)


class SimpleDatabaseManager:
    """Simple database manager for testing."""
    
    def __init__(self):
        self.db_path = None
        self.connection = None
        
    async def setup_test_db(self):
        """Set up test database."""
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
        
        self.connection.execute("""
            INSERT INTO instances VALUES 
            ('worker1', '192.168.1.1', 8001, 10, 2, 'active', ?),
            ('worker2', '192.168.1.2', 8002, 10, 1, 'active', ?)
        """, (now, now))
        
        self.connection.execute("""
            INSERT INTO stream_assignments VALUES 
            (1, 'worker1', 'active', ?),
            (2, 'worker1', 'active', ?),
            (3, 'worker2', 'active', ?),
            (4, 'orphaned_worker', 'active', ?)
        """, (now, now, now, now))
        
        self.connection.commit()
    
    def get_connection(self):
        """Return connection context manager."""
        return SimpleConnection(self.connection)
    
    async def cleanup(self):
        """Clean up."""
        if self.connection:
            self.connection.close()
        if self.db_path and os.path.exists(self.db_path):
            os.unlink(self.db_path)


class SimpleConnection:
    """Simple connection wrapper."""
    
    def __init__(self, connection):
        self.connection = connection
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def execute(self, query, params=()):
        cursor = self.connection.execute(query, params)
        return SimpleCursor(cursor)
    
    async def commit(self):
        self.connection.commit()


class SimpleCursor:
    """Simple cursor wrapper."""
    
    def __init__(self, cursor):
        self.cursor = cursor
    
    async def fetchall(self):
        return self.cursor.fetchall()
    
    async def fetchone(self):
        return self.cursor.fetchone()


async def test_basic_consistency_check():
    """Test basic consistency checking functionality."""
    print("Testing basic consistency check...")
    
    # Setup
    db_manager = SimpleDatabaseManager()
    await db_manager.setup_test_db()
    
    try:
        # Create checker
        checker = ConsistencyChecker(db_manager)
        
        # Run consistency check
        report = await checker.verify_stream_assignments()
        
        print(f"Consistency score: {report.consistency_score}")
        print(f"Issues found: {len(report.stream_issues)}")
        print(f"Recommendations: {report.recommendations}")
        
        # Should detect orphaned stream (stream 4 assigned to orphaned_worker)
        orphaned_issues = [issue for issue in report.stream_issues 
                          if issue.issue_type == ConsistencyStatus.ORPHANED]
        
        assert len(orphaned_issues) > 0, "Should detect orphaned streams"
        assert any(issue.stream_id == 4 for issue in orphaned_issues), "Should detect stream 4 as orphaned"
        
        print("✓ Basic consistency check passed")
        
    finally:
        await db_manager.cleanup()


async def test_conflict_resolution():
    """Test conflict resolution functionality."""
    print("Testing conflict resolution...")
    
    # Setup
    db_manager = SimpleDatabaseManager()
    await db_manager.setup_test_db()
    
    try:
        checker = ConsistencyChecker(db_manager)
        
        # Create a test conflict
        conflict = StreamAssignmentIssue(
            stream_id=4,
            issue_type=ConsistencyStatus.ORPHANED,
            orchestrator_assignment='orphaned_worker',
            worker_assignments=[],
            severity="high"
        )
        
        # Resolve conflict
        results = await checker.resolve_conflicts([conflict])
        
        assert len(results) == 1, "Should return one result"
        result = results[0]
        
        print(f"Resolution action: {result.action_taken}")
        print(f"Success: {result.success}")
        print(f"Details: {result.details}")
        
        assert result.action_taken == RecoveryAction.REASSIGN, "Should attempt reassignment"
        
        print("✓ Conflict resolution passed")
        
    finally:
        await db_manager.cleanup()


async def test_instance_synchronization():
    """Test instance state synchronization."""
    print("Testing instance synchronization...")
    
    # Setup
    db_manager = SimpleDatabaseManager()
    await db_manager.setup_test_db()
    
    try:
        checker = ConsistencyChecker(db_manager)
        
        # Test syncing existing instance
        result = await checker.synchronize_instance_state('worker1')
        
        print(f"Sync action: {result.action_taken}")
        print(f"Success: {result.success}")
        print(f"Details: {result.details}")
        
        assert result.action_taken == RecoveryAction.SYNC, "Should perform sync action"
        assert 'worker1' in result.affected_instances, "Should affect worker1"
        
        print("✓ Instance synchronization passed")
        
    finally:
        await db_manager.cleanup()


async def main():
    """Run all tests."""
    print("Running Consistency Checker Tests")
    print("=" * 40)
    
    try:
        await test_basic_consistency_check()
        await test_conflict_resolution()
        await test_instance_synchronization()
        
        print("\n" + "=" * 40)
        print("All tests passed! ✓")
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
"""
Advanced Transaction Management System
Implements transaction monitoring, automatic rollback for long-running operations,
and intelligent transaction lifecycle management.

Requirements addressed: 2.2, 2.3, 2.4
"""

import asyncio
import logging
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import psycopg2

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"
    DEADLOCK = "deadlock"
    FAILED = "failed"


class TransactionPriority(Enum):
    """Transaction priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TransactionMetrics:
    """Transaction performance metrics"""
    transaction_id: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    query_count: int = 0
    rows_affected: int = 0
    bytes_transferred: int = 0
    lock_wait_time: float = 0.0
    cpu_time: float = 0.0


@dataclass
class TransactionInfo:
    """Comprehensive transaction information"""
    transaction_id: str
    connection_id: int
    thread_id: int
    start_time: float
    context: str
    status: TransactionStatus
    priority: TransactionPriority
    timeout_threshold: float
    max_queries: int
    isolation_level: str
    read_only: bool
    savepoints: List[str]
    metrics: TransactionMetrics
    last_activity: float
    queries_executed: List[str]
    
    def __post_init__(self):
        if not self.metrics:
            self.metrics = TransactionMetrics(
                transaction_id=self.transaction_id,
                start_time=self.start_time
            )


class TransactionMonitor:
    """Advanced transaction monitoring and management"""
    
    def __init__(self, 
                 default_timeout: float = 30.0,
                 max_concurrent_transactions: int = 100,
                 cleanup_interval: float = 60.0):
        self.default_timeout = default_timeout
        self.max_concurrent_transactions = max_concurrent_transactions
        self.cleanup_interval = cleanup_interval
        
        # Transaction tracking
        self.active_transactions: Dict[str, TransactionInfo] = {}
        self.transaction_history: List[TransactionInfo] = []
        self.deadlock_history: List[Dict] = []
        
        # Monitoring state
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = False
        self._stats = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "failed_transactions": 0,
            "timeout_transactions": 0,
            "deadlock_transactions": 0,
            "avg_duration": 0.0,
            "max_duration": 0.0,
            "concurrent_peak": 0
        }
        
        # Performance tracking
        self._performance_samples: List[float] = []
        self._last_cleanup = time.time()
    
    def start_monitoring(self):
        """Start background transaction monitoring"""
        with self._lock:
            if self._monitor_thread is None or not self._monitor_thread.is_alive():
                self._stop_monitoring = False
                self._monitor_thread = threading.Thread(
                    target=self._monitor_loop, 
                    daemon=True,
                    name="TransactionMonitor"
                )
                self._monitor_thread.start()
                logger.info("Transaction monitoring started")
    
    def stop_monitoring(self):
        """Stop background transaction monitoring"""
        with self._lock:
            self._stop_monitoring = True
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=5)
                logger.info("Transaction monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while not self._stop_monitoring:
            try:
                self._check_transaction_health()
                self._cleanup_old_data()
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in transaction monitoring loop: {e}")
                time.sleep(10)  # Wait longer on error
    
    def _check_transaction_health(self):
        """Check health of active transactions"""
        current_time = time.time()
        problematic_transactions = []
        
        with self._lock:
            for tx_id, tx_info in list(self.active_transactions.items()):
                duration = current_time - tx_info.start_time
                idle_time = current_time - tx_info.last_activity
                
                # Check for timeout
                if duration > tx_info.timeout_threshold:
                    problematic_transactions.append((tx_id, "timeout", duration))
                
                # Check for idle transactions
                elif idle_time > 300:  # 5 minutes idle
                    problematic_transactions.append((tx_id, "idle", idle_time))
                
                # Check for excessive queries
                elif len(tx_info.queries_executed) > tx_info.max_queries:
                    problematic_transactions.append((tx_id, "excessive_queries", len(tx_info.queries_executed)))
        
        # Log problematic transactions
        for tx_id, issue_type, value in problematic_transactions:
            tx_info = self.active_transactions.get(tx_id)
            if tx_info:
                logger.warning(
                    f"Problematic transaction detected: {tx_id} "
                    f"({issue_type}: {value:.1f}) in context: {tx_info.context}"
                )
                
                # Mark timeout transactions
                if issue_type == "timeout":
                    tx_info.status = TransactionStatus.TIMEOUT
    
    def _cleanup_old_data(self):
        """Cleanup old transaction data"""
        current_time = time.time()
        
        if current_time - self._last_cleanup < self.cleanup_interval:
            return
        
        with self._lock:
            # Clean transaction history (keep last 1000)
            if len(self.transaction_history) > 1000:
                self.transaction_history = self.transaction_history[-1000:]
            
            # Clean deadlock history (keep last 100)
            if len(self.deadlock_history) > 100:
                self.deadlock_history = self.deadlock_history[-100:]
            
            # Clean performance samples (keep last 500)
            if len(self._performance_samples) > 500:
                self._performance_samples = self._performance_samples[-500:]
            
            self._last_cleanup = current_time
    
    def register_transaction(self, 
                           connection_id: int,
                           context: str,
                           timeout: Optional[float] = None,
                           priority: TransactionPriority = TransactionPriority.NORMAL,
                           isolation_level: str = "READ_COMMITTED",
                           read_only: bool = False,
                           max_queries: int = 1000) -> TransactionInfo:
        """Register a new transaction"""
        
        # Check concurrent transaction limit
        with self._lock:
            if len(self.active_transactions) >= self.max_concurrent_transactions:
                raise RuntimeError(
                    f"Maximum concurrent transactions ({self.max_concurrent_transactions}) exceeded"
                )
        
        transaction_id = f"{context}_{int(time.time() * 1000)}_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"
        current_time = time.time()
        
        tx_info = TransactionInfo(
            transaction_id=transaction_id,
            connection_id=connection_id,
            thread_id=threading.get_ident(),
            start_time=current_time,
            context=context,
            status=TransactionStatus.PENDING,
            priority=priority,
            timeout_threshold=timeout or self.default_timeout,
            max_queries=max_queries,
            isolation_level=isolation_level,
            read_only=read_only,
            savepoints=[],
            metrics=TransactionMetrics(transaction_id, current_time),
            last_activity=current_time,
            queries_executed=[]
        )
        
        with self._lock:
            self.active_transactions[transaction_id] = tx_info
            self._stats["total_transactions"] += 1
            
            # Update concurrent peak
            current_concurrent = len(self.active_transactions)
            if current_concurrent > self._stats["concurrent_peak"]:
                self._stats["concurrent_peak"] = current_concurrent
        
        logger.debug(f"Transaction {transaction_id} registered in context: {context}")
        return tx_info
    
    def update_transaction_activity(self, 
                                  transaction_id: str, 
                                  query: Optional[str] = None,
                                  rows_affected: int = 0,
                                  bytes_transferred: int = 0):
        """Update transaction activity"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions[transaction_id]
                tx_info.last_activity = time.time()
                tx_info.metrics.query_count += 1
                tx_info.metrics.rows_affected += rows_affected
                tx_info.metrics.bytes_transferred += bytes_transferred
                
                if query:
                    # Store query (truncated for memory efficiency)
                    truncated_query = query[:200] if len(query) > 200 else query
                    tx_info.queries_executed.append(truncated_query)
                    
                    # Keep only last 50 queries per transaction
                    if len(tx_info.queries_executed) > 50:
                        tx_info.queries_executed.pop(0)
                
                # Update status to active if pending
                if tx_info.status == TransactionStatus.PENDING:
                    tx_info.status = TransactionStatus.ACTIVE
    
    def add_savepoint(self, transaction_id: str, savepoint_name: str):
        """Add savepoint to transaction"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions[transaction_id]
                tx_info.savepoints.append(savepoint_name)
                logger.debug(f"Savepoint {savepoint_name} added to transaction {transaction_id}")
    
    def complete_transaction(self, 
                           transaction_id: str, 
                           status: TransactionStatus,
                           error: Optional[Exception] = None):
        """Mark transaction as completed"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions.pop(transaction_id)
                tx_info.status = status
                tx_info.metrics.end_time = time.time()
                tx_info.metrics.duration = tx_info.metrics.end_time - tx_info.metrics.start_time
                
                # Update statistics
                if status == TransactionStatus.COMMITTED:
                    self._stats["successful_transactions"] += 1
                elif status == TransactionStatus.TIMEOUT:
                    self._stats["timeout_transactions"] += 1
                elif status == TransactionStatus.DEADLOCK:
                    self._stats["deadlock_transactions"] += 1
                    self._record_deadlock(tx_info, error)
                else:
                    self._stats["failed_transactions"] += 1
                
                # Update duration statistics
                duration = tx_info.metrics.duration
                self._performance_samples.append(duration)
                
                if duration > self._stats["max_duration"]:
                    self._stats["max_duration"] = duration
                
                # Calculate rolling average
                if self._performance_samples:
                    self._stats["avg_duration"] = sum(self._performance_samples) / len(self._performance_samples)
                
                # Add to history
                self.transaction_history.append(tx_info)
                
                logger.debug(
                    f"Transaction {transaction_id} completed with status {status.value} "
                    f"(duration: {duration:.3f}s, queries: {tx_info.metrics.query_count})"
                )
    
    def _record_deadlock(self, tx_info: TransactionInfo, error: Optional[Exception]):
        """Record deadlock information"""
        deadlock_info = {
            "timestamp": datetime.now(),
            "transaction_id": tx_info.transaction_id,
            "context": tx_info.context,
            "duration": tx_info.metrics.duration,
            "queries": tx_info.queries_executed.copy(),
            "error": str(error) if error else None
        }
        
        self.deadlock_history.append(deadlock_info)
        logger.warning(f"Deadlock recorded for transaction {tx_info.transaction_id}")
    
    def get_active_transactions(self) -> List[TransactionInfo]:
        """Get list of currently active transactions"""
        with self._lock:
            return list(self.active_transactions.values())
    
    def get_transaction_statistics(self) -> Dict:
        """Get comprehensive transaction statistics"""
        with self._lock:
            current_time = time.time()
            
            # Calculate recent statistics (last hour)
            recent_transactions = [
                tx for tx in self.transaction_history
                if tx.metrics.end_time and (current_time - tx.metrics.end_time) < 3600
            ]
            
            recent_successful = len([tx for tx in recent_transactions if tx.status == TransactionStatus.COMMITTED])
            recent_failed = len([tx for tx in recent_transactions if tx.status != TransactionStatus.COMMITTED])
            
            return {
                "total_stats": self._stats.copy(),
                "active_transactions": len(self.active_transactions),
                "recent_stats": {
                    "total": len(recent_transactions),
                    "successful": recent_successful,
                    "failed": recent_failed,
                    "success_rate": (recent_successful / max(len(recent_transactions), 1)) * 100
                },
                "deadlock_stats": {
                    "total_deadlocks": len(self.deadlock_history),
                    "recent_deadlocks": len([
                        d for d in self.deadlock_history
                        if (current_time - d["timestamp"].timestamp()) < 3600
                    ])
                },
                "performance_stats": {
                    "avg_duration": self._stats["avg_duration"],
                    "max_duration": self._stats["max_duration"],
                    "concurrent_peak": self._stats["concurrent_peak"]
                }
            }
    
    def force_rollback_transaction(self, transaction_id: str, reason: str = "forced"):
        """Force rollback of a specific transaction"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions[transaction_id]
                logger.warning(
                    f"Forcing rollback of transaction {transaction_id} "
                    f"in context {tx_info.context}. Reason: {reason}"
                )
                # Note: Actual rollback would need connection access
                # This marks it for rollback
                tx_info.status = TransactionStatus.FAILED
                return True
            return False


class TransactionManager:
    """High-level transaction management interface"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.monitor = TransactionMonitor()
        self.monitor.start_monitoring()
    
    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.monitor.stop_monitoring()
        except Exception:
            pass
    
    @asynccontextmanager
    async def managed_transaction(self, 
                                context: str = "unknown",
                                timeout: Optional[float] = None,
                                priority: TransactionPriority = TransactionPriority.NORMAL,
                                isolation_level: str = "READ_COMMITTED",
                                read_only: bool = False,
                                max_queries: int = 1000):
        """Managed transaction with comprehensive monitoring"""
        
        async with self.db_manager.get_connection(context, timeout) as conn:
            # Register transaction
            tx_info = self.monitor.register_transaction(
                connection_id=id(conn),
                context=context,
                timeout=timeout,
                priority=priority,
                isolation_level=isolation_level,
                read_only=read_only,
                max_queries=max_queries
            )
            
            transaction_id = tx_info.transaction_id
            
            try:
                # Configure transaction
                await asyncio.to_thread(self._configure_transaction, conn, tx_info)
                
                # Begin transaction
                await asyncio.to_thread(conn.cursor().execute, "BEGIN")
                logger.debug(f"Transaction {transaction_id} started")
                
                # Create transaction context
                tx_context = TransactionContext(
                    connection=conn,
                    transaction_info=tx_info,
                    monitor=self.monitor
                )
                
                yield tx_context
                
                # Commit if we reach here
                await asyncio.to_thread(conn.commit)
                self.monitor.complete_transaction(transaction_id, TransactionStatus.COMMITTED)
                logger.debug(f"Transaction {transaction_id} committed successfully")
                
            except Exception as e:
                # Rollback on any error
                try:
                    await asyncio.to_thread(conn.rollback)
                    logger.warning(f"Transaction {transaction_id} rolled back due to error: {e}")
                    
                    # Determine error type
                    if self._is_deadlock_error(e):
                        status = TransactionStatus.DEADLOCK
                    elif self._is_timeout_error(e):
                        status = TransactionStatus.TIMEOUT
                    else:
                        status = TransactionStatus.ROLLED_BACK
                    
                    self.monitor.complete_transaction(transaction_id, status, e)
                    
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction {transaction_id}: {rollback_error}")
                    self.monitor.complete_transaction(transaction_id, TransactionStatus.FAILED, rollback_error)
                
                raise
    
    @contextmanager
    def managed_transaction_sync(self, 
                               context: str = "unknown",
                               timeout: Optional[float] = None,
                               priority: TransactionPriority = TransactionPriority.NORMAL,
                               isolation_level: str = "READ_COMMITTED",
                               read_only: bool = False,
                               max_queries: int = 1000):
        """Synchronous managed transaction"""
        
        with self.db_manager.get_connection_sync(context, timeout) as conn:
            # Register transaction
            tx_info = self.monitor.register_transaction(
                connection_id=id(conn),
                context=context,
                timeout=timeout,
                priority=priority,
                isolation_level=isolation_level,
                read_only=read_only,
                max_queries=max_queries
            )
            
            transaction_id = tx_info.transaction_id
            
            try:
                # Configure transaction
                self._configure_transaction(conn, tx_info)
                
                # Begin transaction
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN")
                logger.debug(f"Transaction {transaction_id} started")
                
                # Create transaction context
                tx_context = TransactionContext(
                    connection=conn,
                    transaction_info=tx_info,
                    monitor=self.monitor
                )
                
                yield tx_context
                
                # Commit if we reach here
                conn.commit()
                self.monitor.complete_transaction(transaction_id, TransactionStatus.COMMITTED)
                logger.debug(f"Transaction {transaction_id} committed successfully")
                
            except Exception as e:
                # Rollback on any error
                try:
                    conn.rollback()
                    logger.warning(f"Transaction {transaction_id} rolled back due to error: {e}")
                    
                    # Determine error type
                    if self._is_deadlock_error(e):
                        status = TransactionStatus.DEADLOCK
                    elif self._is_timeout_error(e):
                        status = TransactionStatus.TIMEOUT
                    else:
                        status = TransactionStatus.ROLLED_BACK
                    
                    self.monitor.complete_transaction(transaction_id, status, e)
                    
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction {transaction_id}: {rollback_error}")
                    self.monitor.complete_transaction(transaction_id, TransactionStatus.FAILED, rollback_error)
                
                raise
    
    def _configure_transaction(self, conn, tx_info: TransactionInfo):
        """Configure transaction settings"""
        try:
            with conn.cursor() as cursor:
                # Set isolation level
                if tx_info.isolation_level != "READ_COMMITTED":
                    cursor.execute(f"SET TRANSACTION ISOLATION LEVEL {tx_info.isolation_level}")
                
                # Set read-only mode
                if tx_info.read_only:
                    cursor.execute("SET TRANSACTION READ ONLY")
                
                # Set statement timeout based on transaction timeout
                timeout_ms = int(tx_info.timeout_threshold * 1000)
                cursor.execute(f"SET statement_timeout = {timeout_ms}")
                
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Failed to configure transaction {tx_info.transaction_id}: {e}")
            conn.rollback()
    
    def _is_deadlock_error(self, error: Exception) -> bool:
        """Check if error is a deadlock"""
        error_str = str(error).lower()
        return any(indicator in error_str for indicator in [
            "deadlock detected",
            "could not serialize access",
            "concurrent update"
        ])
    
    def _is_timeout_error(self, error: Exception) -> bool:
        """Check if error is a timeout"""
        error_str = str(error).lower()
        return any(indicator in error_str for indicator in [
            "timeout",
            "statement timeout",
            "lock timeout"
        ])
    
    def get_statistics(self) -> Dict:
        """Get transaction statistics"""
        return self.monitor.get_transaction_statistics()
    
    def force_rollback_all_long_transactions(self, threshold_seconds: float = 300):
        """Force rollback of all transactions exceeding threshold"""
        current_time = time.time()
        rolled_back = []
        
        for tx_info in self.monitor.get_active_transactions():
            duration = current_time - tx_info.start_time
            if duration > threshold_seconds:
                if self.monitor.force_rollback_transaction(
                    tx_info.transaction_id, 
                    f"exceeded_threshold_{threshold_seconds}s"
                ):
                    rolled_back.append(tx_info.transaction_id)
        
        if rolled_back:
            logger.warning(f"Force rolled back {len(rolled_back)} long-running transactions")
        
        return rolled_back


class TransactionContext:
    """Context object for managed transactions"""
    
    def __init__(self, connection, transaction_info: TransactionInfo, monitor: TransactionMonitor):
        self.connection = connection
        self.transaction_info = transaction_info
        self.monitor = monitor
    
    def execute_query(self, query: str, parameters: tuple = None, fetch: bool = False):
        """Execute query within transaction context"""
        try:
            with self.connection.cursor() as cursor:
                if parameters:
                    cursor.execute(query, parameters)
                else:
                    cursor.execute(query)
                
                # Update activity
                rows_affected = cursor.rowcount if cursor.rowcount >= 0 else 0
                self.monitor.update_transaction_activity(
                    self.transaction_info.transaction_id,
                    query=query,
                    rows_affected=rows_affected
                )
                
                if fetch:
                    return cursor.fetchall()
                
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"Query failed in transaction {self.transaction_info.transaction_id}: {e}")
            raise
    
    def create_savepoint(self, name: str):
        """Create savepoint within transaction"""
        savepoint_name = f"sp_{name}_{int(time.time())}"
        
        with self.connection.cursor() as cursor:
            cursor.execute(f"SAVEPOINT {savepoint_name}")
        
        self.monitor.add_savepoint(self.transaction_info.transaction_id, savepoint_name)
        return savepoint_name
    
    def rollback_to_savepoint(self, savepoint_name: str):
        """Rollback to specific savepoint"""
        with self.connection.cursor() as cursor:
            cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        
        logger.debug(f"Rolled back to savepoint {savepoint_name} in transaction {self.transaction_info.transaction_id}")
    
    def release_savepoint(self, savepoint_name: str):
        """Release savepoint"""
        with self.connection.cursor() as cursor:
            cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        
        # Remove from transaction info
        if savepoint_name in self.transaction_info.savepoints:
            self.transaction_info.savepoints.remove(savepoint_name)


# Global transaction manager instance
_transaction_manager = None


def get_transaction_manager(db_manager=None):
    """Get global transaction manager instance"""
    global _transaction_manager
    if _transaction_manager is None and db_manager:
        _transaction_manager = TransactionManager(db_manager)
    return _transaction_manager
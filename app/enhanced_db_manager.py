"""
Enhanced Database Connection Manager
Implements optimized connection pool with intelligent timeouts, deadlock prevention,
comprehensive error handling, and transaction monitoring.

Requirements addressed: 2.1, 2.2, 2.3, 2.4, 5.1
"""

import asyncio
import logging
import os
import random
import threading
import time
import traceback
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv
from psycopg2 import DatabaseError, InterfaceError, OperationalError

# Load environment variables
load_dotenv(dotenv_path=".env")

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Transaction status enumeration"""
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    TIMEOUT = "timeout"
    DEADLOCK = "deadlock"


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TransactionInfo:
    """Transaction tracking information"""
    transaction_id: str
    start_time: float
    connection_id: int
    context: str
    status: TransactionStatus
    query_count: int = 0
    last_query_time: Optional[float] = None
    timeout_threshold: float = 30.0  # 30 seconds default


@dataclass
class ConnectionMetrics:
    """Connection performance metrics"""
    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    avg_connection_time: float = 0.0
    max_connection_time: float = 0.0
    deadlock_count: int = 0
    timeout_count: int = 0
    retry_count: int = 0


@dataclass
class ErrorPattern:
    """Error pattern tracking"""
    error_type: str
    count: int
    first_occurrence: datetime
    last_occurrence: datetime
    severity: ErrorSeverity
    contexts: List[str]


class DeadlockDetector:
    """Detects and handles database deadlocks"""
    
    def __init__(self):
        self.deadlock_history: List[Dict] = []
        self.deadlock_patterns: Dict[str, int] = {}
        self._lock = threading.Lock()
    
    def is_deadlock_error(self, error: Exception) -> bool:
        """Check if error is a deadlock"""
        error_str = str(error).lower()
        deadlock_indicators = [
            "deadlock detected",
            "lock timeout",
            "could not serialize access",
            "concurrent update"
        ]
        return any(indicator in error_str for indicator in deadlock_indicators)
    
    def record_deadlock(self, error: Exception, context: str, query: str = None):
        """Record deadlock occurrence"""
        with self._lock:
            deadlock_info = {
                "timestamp": datetime.now(),
                "error": str(error),
                "context": context,
                "query": query[:200] if query else None  # Truncate long queries
            }
            
            self.deadlock_history.append(deadlock_info)
            
            # Keep only last 100 deadlocks
            if len(self.deadlock_history) > 100:
                self.deadlock_history.pop(0)
            
            # Track patterns
            error_key = str(error)[:100]  # Use first 100 chars as key
            self.deadlock_patterns[error_key] = self.deadlock_patterns.get(error_key, 0) + 1
            
            logger.warning(f"Deadlock detected in {context}: {error}")
    
    def get_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with jitter to avoid thundering herd"""
        base_delay = 0.1 * (2 ** attempt)  # Exponential backoff
        jitter = random.uniform(0, 0.1)  # Add randomness
        return min(base_delay + jitter, 5.0)  # Cap at 5 seconds


class TransactionMonitor:
    """Monitors and manages long-running transactions"""
    
    def __init__(self, timeout_threshold: float = 30.0):
        self.active_transactions: Dict[str, TransactionInfo] = {}
        self.timeout_threshold = timeout_threshold
        self.transaction_history: List[TransactionInfo] = []
        self._lock = threading.Lock()
        self._monitor_task = None
        self._stop_monitoring = False
    
    def start_monitoring(self):
        """Start background transaction monitoring"""
        if self._monitor_task is None:
            self._stop_monitoring = False
            self._monitor_task = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_task.start()
            logger.info("Transaction monitoring started")
    
    def stop_monitoring(self):
        """Stop background transaction monitoring"""
        self._stop_monitoring = True
        if self._monitor_task:
            self._monitor_task.join(timeout=5)
            self._monitor_task = None
            logger.info("Transaction monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while not self._stop_monitoring:
            try:
                self._check_long_transactions()
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in transaction monitoring: {e}")
    
    def register_transaction(self, transaction_id: str, connection_id: int, 
                           context: str, timeout_threshold: float = None) -> TransactionInfo:
        """Register a new transaction"""
        with self._lock:
            tx_info = TransactionInfo(
                transaction_id=transaction_id,
                start_time=time.time(),
                connection_id=connection_id,
                context=context,
                status=TransactionStatus.ACTIVE,
                timeout_threshold=timeout_threshold or self.timeout_threshold
            )
            
            self.active_transactions[transaction_id] = tx_info
            return tx_info
    
    def update_transaction(self, transaction_id: str, query_executed: bool = False):
        """Update transaction activity"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions[transaction_id]
                if query_executed:
                    tx_info.query_count += 1
                    tx_info.last_query_time = time.time()
    
    def complete_transaction(self, transaction_id: str, status: TransactionStatus):
        """Mark transaction as completed"""
        with self._lock:
            if transaction_id in self.active_transactions:
                tx_info = self.active_transactions.pop(transaction_id)
                tx_info.status = status
                
                # Add to history
                self.transaction_history.append(tx_info)
                
                # Keep only last 1000 transactions in history
                if len(self.transaction_history) > 1000:
                    self.transaction_history.pop(0)
    
    def _check_long_transactions(self):
        """Check for long-running transactions"""
        current_time = time.time()
        long_transactions = []
        
        with self._lock:
            for tx_id, tx_info in list(self.active_transactions.items()):
                duration = current_time - tx_info.start_time
                
                if duration > tx_info.timeout_threshold:
                    long_transactions.append((tx_id, tx_info, duration))
        
        # Log warnings for long transactions
        for tx_id, tx_info, duration in long_transactions:
            logger.warning(
                f"Long-running transaction detected: {tx_id} "
                f"({duration:.1f}s) in context: {tx_info.context}"
            )
            
            # If transaction is extremely long (2x threshold), mark for timeout
            if duration > tx_info.timeout_threshold * 2:
                logger.error(
                    f"Transaction {tx_id} exceeded timeout threshold "
                    f"({duration:.1f}s > {tx_info.timeout_threshold * 2:.1f}s)"
                )
                # Note: Actual transaction cancellation would require connection access
    
    def get_active_transactions(self) -> List[TransactionInfo]:
        """Get list of currently active transactions"""
        with self._lock:
            return list(self.active_transactions.values())


class EnhancedDatabaseManager:
    """Enhanced database connection manager with intelligent features"""
    
    def __init__(self, minconn: int = 3, maxconn: int = 15):
        self.minconn = minconn
        self.maxconn = maxconn
        self.pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        
        # Enhanced components
        self.deadlock_detector = DeadlockDetector()
        self.transaction_monitor = TransactionMonitor()
        self.metrics = ConnectionMetrics()
        self.error_patterns: Dict[str, ErrorPattern] = {}
        
        # Configuration
        self.max_retries = 3
        self.base_retry_delay = 0.1
        self.connection_timeout = 30
        self.query_timeout = 30
        
        # Thread safety
        self._lock = threading.Lock()
        self._connection_tracking: Dict[int, Dict] = {}
        
        # Initialize
        self._create_pool()
        self.transaction_monitor.start_monitoring()
    
    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.transaction_monitor.stop_monitoring()
            if self.pool:
                self.pool.closeall()
        except Exception:
            pass
    
    def _create_pool(self):
        """Create optimized connection pool"""
        for attempt in range(self.max_retries):
            try:
                db_config = {
                    "host": os.getenv("POSTGRES_HOST"),
                    "user": os.getenv("POSTGRES_USER"),
                    "password": os.getenv("POSTGRES_PASSWORD"),
                    "database": os.getenv("POSTGRES_DB"),
                    "port": os.getenv("POSTGRES_PORT", "5432"),
                    "connect_timeout": self.connection_timeout,
                    "options": (
                        f"-c statement_timeout={self.query_timeout * 1000} "
                        f"-c lock_timeout=10000 "
                        f"-c idle_in_transaction_session_timeout={self.connection_timeout * 1000}"
                    ),
                    "application_name": f'enhanced_fingerv7_{os.getenv("SERVER_ID", "1")}',
                }
                
                # Validate required configurations
                required_configs = ["host", "user", "password", "database"]
                missing_configs = [key for key in required_configs if not db_config[key]]
                
                if missing_configs:
                    raise ValueError(f"Missing database configurations: {missing_configs}")
                
                # Create pool with enhanced settings
                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self.minconn,
                    maxconn=self.maxconn,
                    **db_config
                )
                
                logger.info(f"Enhanced database pool created successfully (attempt {attempt + 1})")
                return
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to create database pool after {self.max_retries} attempts: {e}")
                    raise
                
                delay = self.base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(f"Pool creation attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
                time.sleep(delay)
    
    def _configure_connection(self, conn):
        """Configure connection with optimized settings"""
        try:
            with conn.cursor() as cursor:
                # Set timeouts and limits
                cursor.execute(f"SET statement_timeout = '{self.query_timeout * 1000}'")
                cursor.execute("SET lock_timeout = '10000'")  # 10 seconds
                cursor.execute(f"SET idle_in_transaction_session_timeout = '{self.connection_timeout * 1000}'")
                
                # Optimize for our workload
                cursor.execute("SET synchronous_commit = 'local'")  # Faster commits
                cursor.execute("SET wal_buffers = '16MB'")
                cursor.execute("SET checkpoint_completion_target = 0.9")
                
                # Set application name for monitoring
                cursor.execute(f"SET application_name = 'enhanced_fingerv7_{os.getenv('SERVER_ID', '1')}'")
                
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Failed to configure connection: {e}")
            conn.rollback()
    
    def _test_connection(self, conn):
        """Test connection validity"""
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as e:
            raise OperationalError(f"Connection test failed: {e}")
    
    def _record_error(self, error: Exception, context: str):
        """Record and analyze error patterns"""
        error_type = type(error).__name__
        error_str = str(error)
        
        # Determine severity
        severity = ErrorSeverity.LOW
        if isinstance(error, (OperationalError, InterfaceError)):
            severity = ErrorSeverity.HIGH
        elif "deadlock" in error_str.lower() or "timeout" in error_str.lower():
            severity = ErrorSeverity.CRITICAL
        
        # Update error patterns
        pattern_key = f"{error_type}:{error_str[:100]}"
        
        if pattern_key in self.error_patterns:
            pattern = self.error_patterns[pattern_key]
            pattern.count += 1
            pattern.last_occurrence = datetime.now()
            if context not in pattern.contexts:
                pattern.contexts.append(context)
        else:
            self.error_patterns[pattern_key] = ErrorPattern(
                error_type=error_type,
                count=1,
                first_occurrence=datetime.now(),
                last_occurrence=datetime.now(),
                severity=severity,
                contexts=[context]
            )
        
        # Update metrics
        self.metrics.failed_connections += 1
        
        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.error(f"Critical database error in {context}: {error}")
        elif severity == ErrorSeverity.HIGH:
            logger.warning(f"High severity database error in {context}: {error}")
        else:
            logger.debug(f"Database error in {context}: {error}") 
   
    @asynccontextmanager
    async def get_connection(self, context: str = "unknown", timeout: float = None):
        """Enhanced async connection manager with comprehensive error handling"""
        conn = None
        start_time = time.time()
        connection_timeout = timeout or self.connection_timeout
        
        for attempt in range(self.max_retries):
            try:
                # Check if pool needs recreation
                if self.pool is None or self.pool.closed:
                    logger.warning("Pool closed or not initialized. Recreating...")
                    self._create_pool()
                
                # Get connection with timeout
                conn = await asyncio.wait_for(
                    asyncio.to_thread(self.pool.getconn),
                    timeout=connection_timeout
                )
                
                if conn:
                    # Configure and test connection
                    await asyncio.to_thread(self._configure_connection, conn)
                    await asyncio.to_thread(self._test_connection, conn)
                    
                    # Track connection
                    conn_id = id(conn)
                    with self._lock:
                        self._connection_tracking[conn_id] = {
                            "acquired_at": time.time(),
                            "context": context,
                            "thread_id": threading.get_ident()
                        }
                    
                    # Update metrics
                    connection_time = time.time() - start_time
                    self.metrics.total_connections += 1
                    self.metrics.active_connections += 1
                    self.metrics.avg_connection_time = (
                        (self.metrics.avg_connection_time * (self.metrics.total_connections - 1) + connection_time) /
                        self.metrics.total_connections
                    )
                    self.metrics.max_connection_time = max(self.metrics.max_connection_time, connection_time)
                    
                    try:
                        yield conn
                    finally:
                        # Cleanup connection tracking
                        with self._lock:
                            if conn_id in self._connection_tracking:
                                del self._connection_tracking[conn_id]
                        
                        self.metrics.active_connections -= 1
                        
                        # Return connection to pool
                        try:
                            if conn and not conn.closed:
                                await asyncio.to_thread(self.pool.putconn, conn)
                            else:
                                logger.warning(f"Connection already closed in context: {context}")
                        except Exception as e:
                            logger.error(f"Error returning connection to pool: {e}")
                    
                    return
                else:
                    raise OperationalError("Failed to obtain connection from pool")
            
            except asyncio.TimeoutError:
                error = OperationalError(f"Connection timeout after {connection_timeout}s")
                self._record_error(error, context)
                
                if attempt == self.max_retries - 1:
                    raise error
                
                delay = self.deadlock_detector.get_retry_delay(attempt)
                logger.warning(f"Connection timeout in {context}, retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
            
            except Exception as e:
                self._record_error(e, context)
                
                # Handle deadlocks specially
                if self.deadlock_detector.is_deadlock_error(e):
                    self.deadlock_detector.record_deadlock(e, context)
                    self.metrics.deadlock_count += 1
                
                if conn:
                    try:
                        await asyncio.to_thread(conn.close)
                    except:
                        pass
                    conn = None
                
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to get connection after {self.max_retries} attempts in {context}: {e}")
                    raise
                
                delay = self.deadlock_detector.get_retry_delay(attempt)
                logger.warning(f"Connection attempt {attempt + 1} failed in {context}, retrying in {delay:.2f}s: {e}")
                await asyncio.sleep(delay)
                self.metrics.retry_count += 1
    
    @contextmanager
    def get_connection_sync(self, context: str = "unknown", timeout: float = None):
        """Enhanced sync connection manager"""
        conn = None
        start_time = time.time()
        connection_timeout = timeout or self.connection_timeout
        
        for attempt in range(self.max_retries):
            try:
                # Check if timeout exceeded
                if time.time() - start_time > connection_timeout:
                    raise OperationalError(f"Connection timeout after {connection_timeout}s")
                
                # Check if pool needs recreation
                if self.pool is None or self.pool.closed:
                    logger.warning("Pool closed or not initialized. Recreating...")
                    self._create_pool()
                
                conn = self.pool.getconn()
                
                if conn:
                    # Configure and test connection
                    self._configure_connection(conn)
                    self._test_connection(conn)
                    
                    # Track connection
                    conn_id = id(conn)
                    with self._lock:
                        self._connection_tracking[conn_id] = {
                            "acquired_at": time.time(),
                            "context": context,
                            "thread_id": threading.get_ident()
                        }
                    
                    # Update metrics
                    connection_time = time.time() - start_time
                    self.metrics.total_connections += 1
                    self.metrics.active_connections += 1
                    self.metrics.avg_connection_time = (
                        (self.metrics.avg_connection_time * (self.metrics.total_connections - 1) + connection_time) /
                        self.metrics.total_connections
                    )
                    self.metrics.max_connection_time = max(self.metrics.max_connection_time, connection_time)
                    
                    try:
                        yield conn
                    finally:
                        # Cleanup connection tracking
                        with self._lock:
                            if conn_id in self._connection_tracking:
                                del self._connection_tracking[conn_id]
                        
                        self.metrics.active_connections -= 1
                        
                        # Return connection to pool
                        try:
                            if conn and not conn.closed:
                                self.pool.putconn(conn)
                            else:
                                logger.warning(f"Connection already closed in context: {context}")
                        except Exception as e:
                            logger.error(f"Error returning connection to pool: {e}")
                    
                    return
                else:
                    raise OperationalError("Failed to obtain connection from pool")
            
            except Exception as e:
                self._record_error(e, context)
                
                # Handle deadlocks specially
                if self.deadlock_detector.is_deadlock_error(e):
                    self.deadlock_detector.record_deadlock(e, context)
                    self.metrics.deadlock_count += 1
                
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None
                
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to get connection after {self.max_retries} attempts in {context}: {e}")
                    raise
                
                delay = self.deadlock_detector.get_retry_delay(attempt)
                remaining_time = connection_timeout - (time.time() - start_time)
                
                if delay >= remaining_time:
                    delay = max(0.1, remaining_time - 0.1)
                
                logger.warning(f"Connection attempt {attempt + 1} failed in {context}, retrying in {delay:.2f}s: {e}")
                time.sleep(delay)
                self.metrics.retry_count += 1
    
    @asynccontextmanager
    async def get_transaction(self, context: str = "unknown", timeout: float = None):
        """Enhanced transaction manager with monitoring and auto-rollback"""
        transaction_id = f"{context}_{int(time.time() * 1000)}_{threading.get_ident()}"
        
        async with self.get_connection(context, timeout) as conn:
            # Register transaction
            tx_info = self.transaction_monitor.register_transaction(
                transaction_id, id(conn), context, timeout
            )
            
            try:
                # Begin transaction
                await asyncio.to_thread(conn.cursor().execute, "BEGIN")
                logger.debug(f"Transaction {transaction_id} started in {context}")
                
                yield conn, transaction_id
                
                # Commit if we reach here
                await asyncio.to_thread(conn.commit)
                self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.COMMITTED)
                logger.debug(f"Transaction {transaction_id} committed successfully")
                
            except Exception as e:
                # Rollback on any error
                try:
                    await asyncio.to_thread(conn.rollback)
                    logger.warning(f"Transaction {transaction_id} rolled back due to error: {e}")
                    
                    if self.deadlock_detector.is_deadlock_error(e):
                        self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.DEADLOCK)
                    else:
                        self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.ROLLED_BACK)
                        
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction {transaction_id}: {rollback_error}")
                
                raise
    
    @contextmanager
    def get_transaction_sync(self, context: str = "unknown", timeout: float = None):
        """Enhanced sync transaction manager"""
        transaction_id = f"{context}_{int(time.time() * 1000)}_{threading.get_ident()}"
        
        with self.get_connection_sync(context, timeout) as conn:
            # Register transaction
            tx_info = self.transaction_monitor.register_transaction(
                transaction_id, id(conn), context, timeout
            )
            
            try:
                # Begin transaction
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN")
                logger.debug(f"Transaction {transaction_id} started in {context}")
                
                yield conn, transaction_id
                
                # Commit if we reach here
                conn.commit()
                self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.COMMITTED)
                logger.debug(f"Transaction {transaction_id} committed successfully")
                
            except Exception as e:
                # Rollback on any error
                try:
                    conn.rollback()
                    logger.warning(f"Transaction {transaction_id} rolled back due to error: {e}")
                    
                    if self.deadlock_detector.is_deadlock_error(e):
                        self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.DEADLOCK)
                    else:
                        self.transaction_monitor.complete_transaction(transaction_id, TransactionStatus.ROLLED_BACK)
                        
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction {transaction_id}: {rollback_error}")
                
                raise
    
    async def execute_with_retry(self, operation: Callable, context: str = "unknown", 
                               max_retries: int = None) -> Any:
        """Execute database operation with intelligent retry logic"""
        max_retries = max_retries or self.max_retries
        
        for attempt in range(max_retries):
            try:
                return await operation()
            
            except Exception as e:
                self._record_error(e, context)
                
                # Check if error is retryable
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error in {context}: {e}")
                    raise
                
                if attempt == max_retries - 1:
                    logger.error(f"Operation failed after {max_retries} attempts in {context}: {e}")
                    raise
                
                # Handle deadlocks with special retry logic
                if self.deadlock_detector.is_deadlock_error(e):
                    self.deadlock_detector.record_deadlock(e, context)
                    delay = self.deadlock_detector.get_retry_delay(attempt)
                else:
                    delay = self.base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                
                logger.warning(f"Operation attempt {attempt + 1} failed in {context}, retrying in {delay:.2f}s: {e}")
                await asyncio.sleep(delay)
                self.metrics.retry_count += 1
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable"""
        error_str = str(error).lower()
        
        # Retryable errors
        retryable_patterns = [
            "deadlock detected",
            "lock timeout",
            "connection reset",
            "connection timed out",
            "server closed the connection",
            "could not serialize access",
            "concurrent update"
        ]
        
        # Non-retryable errors
        non_retryable_patterns = [
            "syntax error",
            "column does not exist",
            "table does not exist",
            "permission denied",
            "authentication failed"
        ]
        
        # Check non-retryable first
        if any(pattern in error_str for pattern in non_retryable_patterns):
            return False
        
        # Check retryable
        if any(pattern in error_str for pattern in retryable_patterns):
            return True
        
        # Default: retry operational errors, not programming errors
        return isinstance(error, (OperationalError, InterfaceError))
    
    def get_health_status(self) -> Dict:
        """Get comprehensive health status of the database manager"""
        active_transactions = self.transaction_monitor.get_active_transactions()
        
        return {
            "pool_status": {
                "is_closed": self.pool.closed if self.pool else True,
                "min_connections": self.minconn,
                "max_connections": self.maxconn,
                "active_connections": self.metrics.active_connections
            },
            "metrics": {
                "total_connections": self.metrics.total_connections,
                "failed_connections": self.metrics.failed_connections,
                "success_rate": (
                    (self.metrics.total_connections - self.metrics.failed_connections) /
                    max(self.metrics.total_connections, 1) * 100
                ),
                "avg_connection_time": self.metrics.avg_connection_time,
                "max_connection_time": self.metrics.max_connection_time,
                "deadlock_count": self.metrics.deadlock_count,
                "timeout_count": self.metrics.timeout_count,
                "retry_count": self.metrics.retry_count
            },
            "transactions": {
                "active_count": len(active_transactions),
                "active_transactions": [
                    {
                        "id": tx.transaction_id,
                        "context": tx.context,
                        "duration": time.time() - tx.start_time,
                        "query_count": tx.query_count
                    }
                    for tx in active_transactions
                ]
            },
            "error_patterns": {
                pattern_key: {
                    "error_type": pattern.error_type,
                    "count": pattern.count,
                    "severity": pattern.severity.value,
                    "contexts": pattern.contexts[:5]  # Limit to 5 contexts
                }
                for pattern_key, pattern in list(self.error_patterns.items())[:10]  # Top 10 patterns
            }
        }
    
    def recreate_pool(self):
        """Recreate the connection pool"""
        try:
            if self.pool:
                self.pool.closeall()
        except Exception as e:
            logger.error(f"Error closing existing pool: {e}")
        
        time.sleep(1)  # Brief pause before recreation
        self._create_pool()
        logger.info("Database pool recreated successfully")


# Global instance
_enhanced_db_manager = None


def get_enhanced_db_manager() -> EnhancedDatabaseManager:
    """Get global enhanced database manager instance"""
    global _enhanced_db_manager
    if _enhanced_db_manager is None:
        _enhanced_db_manager = EnhancedDatabaseManager()
    return _enhanced_db_manager


# Compatibility functions for existing code
async def get_enhanced_connection(context: str = "unknown"):
    """Get enhanced database connection (async)"""
    return get_enhanced_db_manager().get_connection(context)


def get_enhanced_connection_sync(context: str = "unknown"):
    """Get enhanced database connection (sync)"""
    return get_enhanced_db_manager().get_connection_sync(context)


async def get_enhanced_transaction(context: str = "unknown"):
    """Get enhanced database transaction (async)"""
    return get_enhanced_db_manager().get_transaction(context)


def get_enhanced_transaction_sync(context: str = "unknown"):
    """Get enhanced database transaction (sync)"""
    return get_enhanced_db_manager().get_transaction_sync(context)
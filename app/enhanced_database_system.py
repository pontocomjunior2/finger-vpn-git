"""
Enhanced Database System Integration
Integrates all enhanced database components into a unified system.

This module provides a single interface for:
- Enhanced connection management with intelligent pooling
- Comprehensive error handling and retry logic
- Transaction monitoring and automatic rollback
- Performance metrics and health monitoring

Requirements addressed: 2.1, 2.2, 2.3, 2.4, 5.1
"""

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from database_error_handler import (DatabaseErrorHandler, ErrorContext,
                                    get_database_error_handler)
from enhanced_db_manager import (EnhancedDatabaseManager,
                                 get_enhanced_db_manager)
from transaction_manager import (TransactionManager, TransactionPriority,
                                 get_transaction_manager)

logger = logging.getLogger(__name__)


class SystemHealthStatus(Enum):
    """Overall system health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILED = "failed"


@dataclass
class SystemHealth:
    """System health information"""
    status: SystemHealthStatus
    score: float  # 0-100
    issues: List[str]
    recommendations: List[str]
    metrics: Dict[str, Any]


class EnhancedDatabaseSystem:
    """Unified enhanced database system"""
    
    def __init__(self, 
                 minconn: int = 3, 
                 maxconn: int = 15,
                 enable_monitoring: bool = True):
        
        # Initialize core components
        self.db_manager = EnhancedDatabaseManager(minconn, maxconn)
        self.error_handler = get_database_error_handler()
        self.transaction_manager = get_transaction_manager(self.db_manager)
        
        # System configuration
        self.enable_monitoring = enable_monitoring
        self._health_check_interval = 60  # seconds
        self._last_health_check = 0
        self._cached_health = None
        
        # Performance thresholds
        self.performance_thresholds = {
            "connection_time_warning": 5.0,  # seconds
            "connection_time_critical": 10.0,
            "error_rate_warning": 5.0,  # percent
            "error_rate_critical": 15.0,
            "active_transactions_warning": 50,
            "active_transactions_critical": 80,
            "deadlock_rate_warning": 1.0,  # per hour
            "deadlock_rate_critical": 5.0
        }
        
        logger.info("Enhanced Database System initialized")
    
    @asynccontextmanager
    async def get_connection(self, context: str = "unknown", timeout: float = None):
        """Get enhanced database connection with comprehensive error handling"""
        operation_start = time.time()
        
        async def connection_operation():
            async with self.db_manager.get_connection(context, timeout) as conn:
                return conn
        
        try:
            async with self.db_manager.get_connection(context, timeout) as conn:
                yield conn
        except Exception as e:
            # Create error context
            error_context = ErrorContext(
                operation="get_connection",
                query=None,
                parameters=None,
                connection_id=None,
                transaction_id=None,
                attempt_number=1,
                start_time=operation_start,
                stack_trace=str(e)
            )
            
            # Handle error through error handler
            await self.error_handler.handle_error_async(
                e, error_context, connection_operation
            )
    
    @contextmanager
    def get_connection_sync(self, context: str = "unknown", timeout: float = None):
        """Get enhanced database connection synchronously"""
        operation_start = time.time()
        
        def connection_operation():
            with self.db_manager.get_connection_sync(context, timeout) as conn:
                return conn
        
        try:
            with self.db_manager.get_connection_sync(context, timeout) as conn:
                yield conn
        except Exception as e:
            # Create error context
            error_context = ErrorContext(
                operation="get_connection_sync",
                query=None,
                parameters=None,
                connection_id=None,
                transaction_id=None,
                attempt_number=1,
                start_time=operation_start,
                stack_trace=str(e)
            )
            
            # Handle error through error handler
            self.error_handler.handle_error_sync(
                e, error_context, connection_operation
            )
    
    @asynccontextmanager
    async def get_transaction(self, 
                            context: str = "unknown",
                            timeout: Optional[float] = None,
                            priority: TransactionPriority = TransactionPriority.NORMAL,
                            isolation_level: str = "READ_COMMITTED",
                            read_only: bool = False,
                            max_queries: int = 1000):
        """Get managed transaction with comprehensive monitoring"""
        async with self.transaction_manager.managed_transaction(
            context=context,
            timeout=timeout,
            priority=priority,
            isolation_level=isolation_level,
            read_only=read_only,
            max_queries=max_queries
        ) as tx_context:
            yield tx_context
    
    @contextmanager
    def get_transaction_sync(self, 
                           context: str = "unknown",
                           timeout: Optional[float] = None,
                           priority: TransactionPriority = TransactionPriority.NORMAL,
                           isolation_level: str = "READ_COMMITTED",
                           read_only: bool = False,
                           max_queries: int = 1000):
        """Get managed transaction synchronously"""
        with self.transaction_manager.managed_transaction_sync(
            context=context,
            timeout=timeout,
            priority=priority,
            isolation_level=isolation_level,
            read_only=read_only,
            max_queries=max_queries
        ) as tx_context:
            yield tx_context
    
    async def execute_with_retry(self, 
                               operation: Callable,
                               context: str = "unknown",
                               max_retries: int = 3) -> Any:
        """Execute operation with intelligent retry logic"""
        return await self.db_manager.execute_with_retry(operation, context, max_retries)
    
    def get_system_health(self, force_refresh: bool = False) -> SystemHealth:
        """Get comprehensive system health status"""
        current_time = time.time()
        
        # Use cached health if recent and not forcing refresh
        if (not force_refresh and 
            self._cached_health and 
            (current_time - self._last_health_check) < self._health_check_interval):
            return self._cached_health
        
        # Gather health data from all components
        db_health = self.db_manager.get_health_status()
        error_stats = self.error_handler.get_error_statistics()
        tx_stats = self.transaction_manager.get_statistics()
        
        # Calculate health score and identify issues
        health_score = 100.0
        issues = []
        recommendations = []
        
        # Check connection performance
        avg_conn_time = db_health["metrics"]["avg_connection_time"]
        if avg_conn_time > self.performance_thresholds["connection_time_critical"]:
            health_score -= 30
            issues.append(f"Critical connection time: {avg_conn_time:.2f}s")
            recommendations.append("Consider increasing connection pool size or optimizing database")
        elif avg_conn_time > self.performance_thresholds["connection_time_warning"]:
            health_score -= 15
            issues.append(f"High connection time: {avg_conn_time:.2f}s")
            recommendations.append("Monitor database performance and connection pool usage")
        
        # Check error rates
        error_rate = 100 - db_health["metrics"]["success_rate"]
        if error_rate > self.performance_thresholds["error_rate_critical"]:
            health_score -= 40
            issues.append(f"Critical error rate: {error_rate:.1f}%")
            recommendations.append("Investigate database connectivity and query issues")
        elif error_rate > self.performance_thresholds["error_rate_warning"]:
            health_score -= 20
            issues.append(f"High error rate: {error_rate:.1f}%")
            recommendations.append("Review recent errors and optimize problematic queries")
        
        # Check active transactions
        active_tx = tx_stats["active_transactions"]
        if active_tx > self.performance_thresholds["active_transactions_critical"]:
            health_score -= 25
            issues.append(f"Critical number of active transactions: {active_tx}")
            recommendations.append("Review long-running transactions and optimize query performance")
        elif active_tx > self.performance_thresholds["active_transactions_warning"]:
            health_score -= 10
            issues.append(f"High number of active transactions: {active_tx}")
            recommendations.append("Monitor transaction duration and consider optimization")
        
        # Check deadlock rates
        recent_deadlocks = tx_stats["deadlock_stats"]["recent_deadlocks"]
        if recent_deadlocks > self.performance_thresholds["deadlock_rate_critical"]:
            health_score -= 35
            issues.append(f"Critical deadlock rate: {recent_deadlocks}/hour")
            recommendations.append("Review transaction logic and implement deadlock prevention strategies")
        elif recent_deadlocks > self.performance_thresholds["deadlock_rate_warning"]:
            health_score -= 15
            issues.append(f"High deadlock rate: {recent_deadlocks}/hour")
            recommendations.append("Monitor concurrent operations and optimize transaction ordering")
        
        # Check pool status
        if db_health["pool_status"]["is_closed"]:
            health_score -= 50
            issues.append("Database pool is closed")
            recommendations.append("Restart database connection pool")
        
        # Determine overall status
        if health_score >= 90:
            status = SystemHealthStatus.HEALTHY
        elif health_score >= 70:
            status = SystemHealthStatus.WARNING
        elif health_score >= 40:
            status = SystemHealthStatus.CRITICAL
        else:
            status = SystemHealthStatus.FAILED
        
        # Create health object
        health = SystemHealth(
            status=status,
            score=max(0, health_score),
            issues=issues,
            recommendations=recommendations,
            metrics={
                "database": db_health,
                "errors": error_stats,
                "transactions": tx_stats,
                "timestamp": current_time
            }
        )
        
        # Cache result
        self._cached_health = health
        self._last_health_check = current_time
        
        return health
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        health = self.get_system_health()
        
        return {
            "health_score": health.score,
            "health_status": health.status.value,
            "connection_metrics": health.metrics["database"]["metrics"],
            "transaction_metrics": health.metrics["transactions"],
            "error_metrics": health.metrics["errors"],
            "recommendations": health.recommendations,
            "timestamp": time.time()
        }
    
    def optimize_performance(self) -> Dict[str, Any]:
        """Perform automatic performance optimizations"""
        optimizations = []
        
        health = self.get_system_health(force_refresh=True)
        
        # Force rollback long-running transactions
        if health.metrics["transactions"]["active_transactions"] > 20:
            rolled_back = self.transaction_manager.force_rollback_all_long_transactions(300)
            if rolled_back:
                optimizations.append(f"Rolled back {len(rolled_back)} long-running transactions")
        
        # Recreate pool if too many errors
        if health.metrics["database"]["metrics"]["success_rate"] < 80:
            try:
                self.db_manager.recreate_pool()
                optimizations.append("Recreated database connection pool")
            except Exception as e:
                optimizations.append(f"Failed to recreate pool: {e}")
        
        return {
            "optimizations_performed": optimizations,
            "health_before": health.score,
            "health_after": self.get_system_health(force_refresh=True).score
        }
    
    def emergency_recovery(self) -> Dict[str, Any]:
        """Perform emergency recovery procedures"""
        recovery_actions = []
        
        try:
            # Stop transaction monitoring temporarily
            self.transaction_manager.monitor.stop_monitoring()
            recovery_actions.append("Stopped transaction monitoring")
            
            # Force rollback all active transactions
            rolled_back = self.transaction_manager.force_rollback_all_long_transactions(0)
            recovery_actions.append(f"Force rolled back {len(rolled_back)} transactions")
            
            # Recreate database pool
            self.db_manager.recreate_pool()
            recovery_actions.append("Recreated database connection pool")
            
            # Restart transaction monitoring
            self.transaction_manager.monitor.start_monitoring()
            recovery_actions.append("Restarted transaction monitoring")
            
            # Clear error history
            self.error_handler.error_history.clear()
            recovery_actions.append("Cleared error history")
            
            return {
                "success": True,
                "actions_performed": recovery_actions,
                "health_after_recovery": self.get_system_health(force_refresh=True).score
            }
            
        except Exception as e:
            recovery_actions.append(f"Recovery failed: {e}")
            return {
                "success": False,
                "actions_performed": recovery_actions,
                "error": str(e)
            }
    
    def get_diagnostic_report(self) -> Dict[str, Any]:
        """Generate comprehensive diagnostic report"""
        health = self.get_system_health(force_refresh=True)
        
        return {
            "system_health": {
                "status": health.status.value,
                "score": health.score,
                "issues": health.issues,
                "recommendations": health.recommendations
            },
            "detailed_metrics": health.metrics,
            "performance_thresholds": self.performance_thresholds,
            "configuration": {
                "min_connections": self.db_manager.minconn,
                "max_connections": self.db_manager.maxconn,
                "monitoring_enabled": self.enable_monitoring,
                "health_check_interval": self._health_check_interval
            },
            "component_status": {
                "database_manager": "active",
                "error_handler": "active",
                "transaction_manager": "active"
            }
        }


# Global enhanced database system instance
_enhanced_db_system = None
_system_lock = threading.Lock()


def get_enhanced_database_system(minconn: int = 3, maxconn: int = 15) -> EnhancedDatabaseSystem:
    """Get global enhanced database system instance"""
    global _enhanced_db_system
    
    with _system_lock:
        if _enhanced_db_system is None:
            _enhanced_db_system = EnhancedDatabaseSystem(minconn, maxconn)
    
    return _enhanced_db_system


# Convenience functions for common operations
async def get_enhanced_connection(context: str = "unknown", timeout: float = None):
    """Get enhanced database connection (async)"""
    system = get_enhanced_database_system()
    return system.get_connection(context, timeout)


def get_enhanced_connection_sync(context: str = "unknown", timeout: float = None):
    """Get enhanced database connection (sync)"""
    system = get_enhanced_database_system()
    return system.get_connection_sync(context, timeout)


async def get_enhanced_transaction(context: str = "unknown", **kwargs):
    """Get enhanced database transaction (async)"""
    system = get_enhanced_database_system()
    return system.get_transaction(context, **kwargs)


def get_enhanced_transaction_sync(context: str = "unknown", **kwargs):
    """Get enhanced database transaction (sync)"""
    system = get_enhanced_database_system()
    return system.get_transaction_sync(context, **kwargs)


def get_system_health():
    """Get system health status"""
    system = get_enhanced_database_system()
    return system.get_system_health()


def get_performance_metrics():
    """Get performance metrics"""
    system = get_enhanced_database_system()
    return system.get_performance_metrics()


def perform_emergency_recovery():
    """Perform emergency recovery"""
    system = get_enhanced_database_system()
    return system.emergency_recovery()
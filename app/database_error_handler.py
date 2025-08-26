"""
Comprehensive Database Error Handling Module
Implements advanced error handling strategies, retry logic, and recovery mechanisms.

Requirements addressed: 2.1, 2.2, 2.3, 2.4, 5.1
"""

import asyncio
import logging
import random
import threading
import time
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import psycopg2
from psycopg2 import (DatabaseError, DataError, IntegrityError, InterfaceError,
                      OperationalError, ProgrammingError)

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Database error categories"""
    CONNECTION = "connection"
    DEADLOCK = "deadlock"
    TIMEOUT = "timeout"
    CONSTRAINT = "constraint"
    SYNTAX = "syntax"
    PERMISSION = "permission"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Error recovery strategies"""
    RETRY = "retry"
    RECONNECT = "reconnect"
    FALLBACK = "fallback"
    ABORT = "abort"
    ESCALATE = "escalate"


@dataclass
class ErrorContext:
    """Context information for error handling"""
    operation: str
    query: Optional[str]
    parameters: Optional[tuple]
    connection_id: Optional[int]
    transaction_id: Optional[str]
    attempt_number: int
    start_time: float
    stack_trace: str


@dataclass
class RecoveryAction:
    """Recovery action to be taken"""
    strategy: RecoveryStrategy
    delay: float
    max_attempts: int
    fallback_operation: Optional[Callable]
    escalation_threshold: int


class DatabaseErrorAnalyzer:
    """Analyzes database errors and determines appropriate recovery strategies"""
    
    def __init__(self):
        self.error_patterns = self._initialize_error_patterns()
        self.recovery_strategies = self._initialize_recovery_strategies()
    
    def _initialize_error_patterns(self) -> Dict[ErrorCategory, List[str]]:
        """Initialize error pattern matching"""
        return {
            ErrorCategory.CONNECTION: [
                "connection refused",
                "connection timed out",
                "connection reset",
                "server closed the connection",
                "no connection to the server",
                "connection lost",
                "broken pipe",
                "network is unreachable"
            ],
            ErrorCategory.DEADLOCK: [
                "deadlock detected",
                "could not serialize access",
                "concurrent update",
                "tuple concurrently updated"
            ],
            ErrorCategory.TIMEOUT: [
                "timeout",
                "lock timeout",
                "statement timeout",
                "idle in transaction session timeout",
                "query timeout"
            ],
            ErrorCategory.CONSTRAINT: [
                "unique constraint",
                "foreign key constraint",
                "check constraint",
                "not null constraint",
                "exclusion constraint"
            ],
            ErrorCategory.SYNTAX: [
                "syntax error",
                "column does not exist",
                "table does not exist",
                "function does not exist",
                "operator does not exist"
            ],
            ErrorCategory.PERMISSION: [
                "permission denied",
                "authentication failed",
                "access denied",
                "insufficient privilege"
            ],
            ErrorCategory.RESOURCE: [
                "out of memory",
                "disk full",
                "too many connections",
                "too many clients already",
                "connection limit exceeded"
            ]
        }
    
    def _initialize_recovery_strategies(self) -> Dict[ErrorCategory, RecoveryAction]:
        """Initialize recovery strategies for each error category"""
        return {
            ErrorCategory.CONNECTION: RecoveryAction(
                strategy=RecoveryStrategy.RECONNECT,
                delay=1.0,
                max_attempts=5,
                fallback_operation=None,
                escalation_threshold=3
            ),
            ErrorCategory.DEADLOCK: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay=0.1,
                max_attempts=5,
                fallback_operation=None,
                escalation_threshold=10
            ),
            ErrorCategory.TIMEOUT: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay=2.0,
                max_attempts=3,
                fallback_operation=None,
                escalation_threshold=5
            ),
            ErrorCategory.CONSTRAINT: RecoveryAction(
                strategy=RecoveryStrategy.ABORT,
                delay=0.0,
                max_attempts=1,
                fallback_operation=None,
                escalation_threshold=1
            ),
            ErrorCategory.SYNTAX: RecoveryAction(
                strategy=RecoveryStrategy.ABORT,
                delay=0.0,
                max_attempts=1,
                fallback_operation=None,
                escalation_threshold=1
            ),
            ErrorCategory.PERMISSION: RecoveryAction(
                strategy=RecoveryStrategy.ESCALATE,
                delay=0.0,
                max_attempts=1,
                fallback_operation=None,
                escalation_threshold=1
            ),
            ErrorCategory.RESOURCE: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay=5.0,
                max_attempts=3,
                fallback_operation=None,
                escalation_threshold=2
            )
        }
    
    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize database error"""
        error_str = str(error).lower()
        
        for category, patterns in self.error_patterns.items():
            if any(pattern in error_str for pattern in patterns):
                return category
        
        # Categorize by exception type if pattern matching fails
        if isinstance(error, OperationalError):
            return ErrorCategory.CONNECTION
        elif isinstance(error, IntegrityError):
            return ErrorCategory.CONSTRAINT
        elif isinstance(error, ProgrammingError):
            return ErrorCategory.SYNTAX
        elif isinstance(error, DataError):
            return ErrorCategory.SYNTAX
        
        return ErrorCategory.UNKNOWN
    
    def get_recovery_action(self, error: Exception, context: ErrorContext) -> RecoveryAction:
        """Get appropriate recovery action for error"""
        category = self.categorize_error(error)
        base_action = self.recovery_strategies.get(category, self.recovery_strategies[ErrorCategory.UNKNOWN])
        
        # Customize action based on context
        action = RecoveryAction(
            strategy=base_action.strategy,
            delay=base_action.delay,
            max_attempts=base_action.max_attempts,
            fallback_operation=base_action.fallback_operation,
            escalation_threshold=base_action.escalation_threshold
        )
        
        # Adjust based on attempt number
        if context.attempt_number > 1:
            # Increase delay with exponential backoff
            action.delay = min(action.delay * (2 ** (context.attempt_number - 1)), 30.0)
            
            # Add jitter to prevent thundering herd
            action.delay += random.uniform(0, action.delay * 0.1)
        
        # Escalate if too many attempts
        if context.attempt_number >= action.escalation_threshold:
            action.strategy = RecoveryStrategy.ESCALATE
        
        return action


class CircuitBreaker:
    """Circuit breaker pattern for database operations"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()
    
    def call(self, operation: Callable) -> Any:
        """Execute operation with circuit breaker protection"""
        with self._lock:
            if self.state == "open":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "half-open"
                    logger.info("Circuit breaker transitioning to half-open state")
                else:
                    raise Exception("Circuit breaker is open - operation blocked")
            
            try:
                result = operation()
                
                if self.state == "half-open":
                    self.state = "closed"
                    self.failure_count = 0
                    logger.info("Circuit breaker closed - operations restored")
                
                return result
                
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "open"
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
                raise
    
    def get_state(self) -> Dict:
        """Get current circuit breaker state"""
        with self._lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_time": self.last_failure_time,
                "recovery_timeout": self.recovery_timeout
            }


class DatabaseErrorHandler:
    """Comprehensive database error handler"""
    
    def __init__(self):
        self.analyzer = DatabaseErrorAnalyzer()
        self.circuit_breaker = CircuitBreaker()
        self.error_history: List[ErrorContext] = []
        self.recovery_stats: Dict[str, int] = {
            "total_errors": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "escalations": 0
        }
        self._lock = threading.Lock()
    
    async def handle_error_async(self, error: Exception, context: ErrorContext, 
                                operation: Callable) -> Any:
        """Handle database error asynchronously"""
        return await self._handle_error_internal(error, context, operation, is_async=True)
    
    def handle_error_sync(self, error: Exception, context: ErrorContext, 
                         operation: Callable) -> Any:
        """Handle database error synchronously"""
        return self._handle_error_internal(error, context, operation, is_async=False)
    
    async def _handle_error_internal(self, error: Exception, context: ErrorContext, 
                                   operation: Callable, is_async: bool = True) -> Any:
        """Internal error handling logic"""
        with self._lock:
            self.recovery_stats["total_errors"] += 1
            self.error_history.append(context)
            
            # Keep only last 1000 errors
            if len(self.error_history) > 1000:
                self.error_history.pop(0)
        
        # Log error details
        logger.error(
            f"Database error in {context.operation} (attempt {context.attempt_number}): {error}\n"
            f"Query: {context.query}\n"
            f"Stack trace: {context.stack_trace}"
        )
        
        # Get recovery action
        recovery_action = self.analyzer.get_recovery_action(error, context)
        
        # Execute recovery strategy
        try:
            if recovery_action.strategy == RecoveryStrategy.RETRY:
                return await self._execute_retry(error, context, operation, recovery_action, is_async)
            
            elif recovery_action.strategy == RecoveryStrategy.RECONNECT:
                return await self._execute_reconnect(error, context, operation, recovery_action, is_async)
            
            elif recovery_action.strategy == RecoveryStrategy.FALLBACK:
                return await self._execute_fallback(error, context, operation, recovery_action, is_async)
            
            elif recovery_action.strategy == RecoveryStrategy.ESCALATE:
                return await self._execute_escalation(error, context, operation, recovery_action, is_async)
            
            else:  # ABORT
                return await self._execute_abort(error, context, operation, recovery_action, is_async)
        
        except Exception as recovery_error:
            with self._lock:
                self.recovery_stats["failed_recoveries"] += 1
            
            logger.error(f"Recovery failed for {context.operation}: {recovery_error}")
            raise recovery_error
    
    async def _execute_retry(self, error: Exception, context: ErrorContext, 
                           operation: Callable, action: RecoveryAction, is_async: bool) -> Any:
        """Execute retry recovery strategy"""
        if context.attempt_number >= action.max_attempts:
            logger.error(f"Max retry attempts ({action.max_attempts}) exceeded for {context.operation}")
            raise error
        
        logger.info(f"Retrying {context.operation} in {action.delay:.2f}s (attempt {context.attempt_number + 1})")
        
        if is_async:
            await asyncio.sleep(action.delay)
            result = await operation()
        else:
            time.sleep(action.delay)
            result = operation()
        
        with self._lock:
            self.recovery_stats["successful_recoveries"] += 1
        
        return result
    
    async def _execute_reconnect(self, error: Exception, context: ErrorContext, 
                               operation: Callable, action: RecoveryAction, is_async: bool) -> Any:
        """Execute reconnect recovery strategy"""
        logger.info(f"Attempting reconnection for {context.operation}")
        
        # Force pool recreation (this would need to be implemented in the calling code)
        # For now, we'll treat it as a retry with longer delay
        return await self._execute_retry(error, context, operation, action, is_async)
    
    async def _execute_fallback(self, error: Exception, context: ErrorContext, 
                              operation: Callable, action: RecoveryAction, is_async: bool) -> Any:
        """Execute fallback recovery strategy"""
        if action.fallback_operation:
            logger.info(f"Executing fallback operation for {context.operation}")
            
            if is_async:
                result = await action.fallback_operation()
            else:
                result = action.fallback_operation()
            
            with self._lock:
                self.recovery_stats["successful_recoveries"] += 1
            
            return result
        else:
            logger.error(f"No fallback operation defined for {context.operation}")
            raise error
    
    async def _execute_escalation(self, error: Exception, context: ErrorContext, 
                                operation: Callable, action: RecoveryAction, is_async: bool) -> Any:
        """Execute escalation recovery strategy"""
        with self._lock:
            self.recovery_stats["escalations"] += 1
        
        logger.critical(
            f"Escalating error for {context.operation}: {error}\n"
            f"Context: {context}\n"
            f"This requires immediate attention!"
        )
        
        # In a real system, this would trigger alerts, notifications, etc.
        raise error
    
    async def _execute_abort(self, error: Exception, context: ErrorContext, 
                           operation: Callable, action: RecoveryAction, is_async: bool) -> Any:
        """Execute abort recovery strategy"""
        logger.error(f"Aborting operation {context.operation} due to unrecoverable error: {error}")
        raise error
    
    def get_error_statistics(self) -> Dict:
        """Get comprehensive error statistics"""
        with self._lock:
            recent_errors = [
                ctx for ctx in self.error_history 
                if time.time() - ctx.start_time < 3600  # Last hour
            ]
            
            error_categories = {}
            for ctx in recent_errors:
                # This would need the actual error to categorize
                # For now, we'll use the operation as a proxy
                category = ctx.operation
                error_categories[category] = error_categories.get(category, 0) + 1
            
            return {
                "recovery_stats": self.recovery_stats.copy(),
                "circuit_breaker": self.circuit_breaker.get_state(),
                "recent_errors": {
                    "total": len(recent_errors),
                    "by_category": error_categories
                },
                "error_rate": {
                    "last_hour": len(recent_errors),
                    "last_24_hours": len([
                        ctx for ctx in self.error_history 
                        if time.time() - ctx.start_time < 86400
                    ])
                }
            }


# Global error handler instance
_error_handler = None


def get_database_error_handler() -> DatabaseErrorHandler:
    """Get global database error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = DatabaseErrorHandler()
    return _error_handler


# Decorator for automatic error handling
def with_database_error_handling(operation_name: str = None):
    """Decorator to automatically handle database errors"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            context = ErrorContext(
                operation=operation_name or func.__name__,
                query=kwargs.get('query'),
                parameters=kwargs.get('parameters'),
                connection_id=None,
                transaction_id=None,
                attempt_number=1,
                start_time=time.time(),
                stack_trace=traceback.format_stack()
            )
            
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                handler = get_database_error_handler()
                return await handler.handle_error_async(e, context, lambda: func(*args, **kwargs))
        
        def sync_wrapper(*args, **kwargs):
            context = ErrorContext(
                operation=operation_name or func.__name__,
                query=kwargs.get('query'),
                parameters=kwargs.get('parameters'),
                connection_id=None,
                transaction_id=None,
                attempt_number=1,
                start_time=time.time(),
                stack_trace=traceback.format_stack()
            )
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handler = get_database_error_handler()
                return handler.handle_error_sync(e, context, lambda: func(*args, **kwargs))
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
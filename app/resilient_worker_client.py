#!/usr/bin/env python3
"""
Resilient Worker Client with Circuit Breaker and Retry Logic

This module provides a resilient client for worker instances to communicate
with the orchestrator, implementing circuit breaker patterns, exponential backoff,
and local operation mode for enhanced reliability.

Author: Sistema de Fingerprinting
Date: 2024
"""

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service is back


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: int = 60  # Seconds to wait before trying again
    success_threshold: int = 3  # Successes needed to close circuit
    timeout: int = 30  # Request timeout in seconds


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_attempts: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff base
    jitter: bool = True  # Add random jitter to delays


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    total_requests: int = 0
    total_failures: int = 0
    state_changes: List[Dict[str, Any]] = field(default_factory=list)


class CircuitBreaker:
    """Circuit breaker implementation for resilient communication."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            self.stats.total_requests += 1
            
            # Check if circuit should be opened
            if self._should_open_circuit():
                self._open_circuit()
            
            # Check if circuit should transition to half-open
            if self._should_try_half_open():
                self._half_open_circuit()
            
            # Fail fast if circuit is open
            if self.stats.state == CircuitState.OPEN:
                raise CircuitBreakerOpenError("Circuit breaker is open")
        
        try:
            # Execute the function
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
            
        except Exception as e:
            await self._record_failure()
            raise
    
    def _should_open_circuit(self) -> bool:
        """Check if circuit should be opened."""
        return (
            self.stats.state == CircuitState.CLOSED and
            self.stats.failure_count >= self.config.failure_threshold
        )
    
    def _should_try_half_open(self) -> bool:
        """Check if circuit should try half-open state."""
        if self.stats.state != CircuitState.OPEN:
            return False
        
        if not self.stats.last_failure_time:
            return False
        
        time_since_failure = datetime.now() - self.stats.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    def _open_circuit(self) -> None:
        """Open the circuit."""
        if self.stats.state != CircuitState.OPEN:
            self._record_state_change(CircuitState.OPEN)
            self.stats.state = CircuitState.OPEN
            logger.warning("Circuit breaker opened due to failures")
    
    def _half_open_circuit(self) -> None:
        """Set circuit to half-open state."""
        if self.stats.state != CircuitState.HALF_OPEN:
            self._record_state_change(CircuitState.HALF_OPEN)
            self.stats.state = CircuitState.HALF_OPEN
            self.stats.success_count = 0
            logger.info("Circuit breaker half-opened, testing service")
    
    def _close_circuit(self) -> None:
        """Close the circuit."""
        if self.stats.state != CircuitState.CLOSED:
            self._record_state_change(CircuitState.CLOSED)
            self.stats.state = CircuitState.CLOSED
            self.stats.failure_count = 0
            logger.info("Circuit breaker closed, service recovered")
    
    async def _record_success(self) -> None:
        """Record a successful operation."""
        async with self._lock:
            self.stats.success_count += 1
            self.stats.last_success_time = datetime.now()
            
            # Close circuit if enough successes in half-open state
            if (self.stats.state == CircuitState.HALF_OPEN and 
                self.stats.success_count >= self.config.success_threshold):
                self._close_circuit()
    
    async def _record_failure(self) -> None:
        """Record a failed operation."""
        async with self._lock:
            self.stats.failure_count += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = datetime.now()
            
            # Reset success count on failure
            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.success_count = 0
    
    def _record_state_change(self, new_state: CircuitState) -> None:
        """Record a state change for monitoring."""
        change = {
            'timestamp': datetime.now().isoformat(),
            'from_state': self.stats.state.value,
            'to_state': new_state.value,
            'failure_count': self.stats.failure_count,
            'total_requests': self.stats.total_requests
        }
        self.stats.state_changes.append(change)
        
        # Keep only last 50 state changes
        if len(self.stats.state_changes) > 50:
            self.stats.state_changes = self.stats.state_changes[-50:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            'state': self.stats.state.value,
            'failure_count': self.stats.failure_count,
            'success_count': self.stats.success_count,
            'total_requests': self.stats.total_requests,
            'total_failures': self.stats.total_failures,
            'last_failure_time': self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None,
            'last_success_time': self.stats.last_success_time.isoformat() if self.stats.last_success_time else None,
            'recent_state_changes': self.stats.state_changes[-10:]  # Last 10 changes
        }


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class RetryHandler:
    """Handles exponential backoff retry logic."""
    
    def __init__(self, config: RetryConfig):
        self.config = config
    
    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry."""
        last_exception = None
        
        for attempt in range(self.config.max_attempts):
            try:
                return await func(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                
                if attempt == self.config.max_attempts - 1:
                    # Last attempt, don't wait
                    break
                
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
        
        # All attempts failed
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff."""
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            # Add random jitter (±25%)
            jitter = delay * 0.25 * (2 * random.random() - 1)
            delay += jitter
        
        return max(0, delay)


@dataclass
class LocalOperationState:
    """State for local operation mode."""
    is_active: bool = False
    assigned_streams: List[int] = field(default_factory=list)
    last_orchestrator_contact: Optional[datetime] = None
    local_mode_start: Optional[datetime] = None
    processed_streams: Dict[int, datetime] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'is_active': self.is_active,
            'assigned_streams': self.assigned_streams,
            'last_orchestrator_contact': self.last_orchestrator_contact.isoformat() if self.last_orchestrator_contact else None,
            'local_mode_start': self.local_mode_start.isoformat() if self.local_mode_start else None,
            'processed_streams': {
                str(k): v.isoformat() for k, v in self.processed_streams.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LocalOperationState':
        """Create from dictionary."""
        state = cls()
        state.is_active = data.get('is_active', False)
        state.assigned_streams = data.get('assigned_streams', [])
        
        if data.get('last_orchestrator_contact'):
            state.last_orchestrator_contact = datetime.fromisoformat(data['last_orchestrator_contact'])
        
        if data.get('local_mode_start'):
            state.local_mode_start = datetime.fromisoformat(data['local_mode_start'])
        
        processed = data.get('processed_streams', {})
        state.processed_streams = {
            int(k): datetime.fromisoformat(v) for k, v in processed.items()
        }
        
        return state


class ResilientWorkerClient:
    """Resilient worker client with circuit breaker and retry logic."""
    
    def __init__(
        self,
        orchestrator_url: str,
        server_id: str,
        max_streams: int = 20,
        circuit_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.server_id = server_id
        self.max_streams = max_streams
        
        # Initialize circuit breaker and retry handler
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = CircuitBreaker(self.circuit_config)
        self.retry_handler = RetryHandler(self.retry_config)
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Local operation state
        self.local_state = LocalOperationState()
        self.local_state_file = f"local_state_{server_id}.json"
        
        # Load local state if exists
        self._load_local_state()
        
        # Orchestrator availability tracking
        self.orchestrator_available = True
        self.last_health_check = datetime.now()
        self.health_check_interval = 30  # seconds
        
        # Registration status for compatibility with fingerv7.py
        self.is_registered = False
        
        # Metrics
        self.metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'circuit_breaker_trips': 0,
            'local_mode_activations': 0,
            'retry_attempts': 0
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.circuit_config.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    def _load_local_state(self) -> None:
        """Load local operation state from file."""
        try:
            if os.path.exists(self.local_state_file):
                with open(self.local_state_file, 'r') as f:
                    data = json.load(f)
                    self.local_state = LocalOperationState.from_dict(data)
                    logger.info(f"Loaded local state: {len(self.local_state.assigned_streams)} streams")
        except Exception as e:
            logger.warning(f"Failed to load local state: {e}")
            self.local_state = LocalOperationState()
    
    def _save_local_state(self) -> None:
        """Save local operation state to file."""
        try:
            with open(self.local_state_file, 'w') as f:
                json.dump(self.local_state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save local state: {e}")
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request with circuit breaker protection."""
        async def _request():
            url = f"{self.orchestrator_url}{endpoint}"
            session = await self._get_session()
            
            async with session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=error_text
                    )
        
        # Execute with circuit breaker and retry
        try:
            self.metrics['total_requests'] += 1
            result = await self.circuit_breaker.call(
                self.retry_handler.execute_with_retry, _request
            )
            self.metrics['successful_requests'] += 1
            self._record_orchestrator_contact()
            return result
            
        except CircuitBreakerOpenError:
            self.metrics['circuit_breaker_trips'] += 1
            self._activate_local_mode()
            raise
        except Exception as e:
            self.metrics['failed_requests'] += 1
            logger.error(f"Request failed after retries: {e}")
            self._activate_local_mode()
            raise
    
    def _record_orchestrator_contact(self) -> None:
        """Record successful contact with orchestrator."""
        self.local_state.last_orchestrator_contact = datetime.now()
        self.orchestrator_available = True
        
        # Deactivate local mode if it was active
        if self.local_state.is_active:
            logger.info("Orchestrator reconnected, deactivating local mode")
            self.local_state.is_active = False
            self.local_state.local_mode_start = None
            self._save_local_state()
    
    def _activate_local_mode(self) -> None:
        """Activate local operation mode."""
        if not self.local_state.is_active:
            logger.warning("Activating local operation mode - orchestrator unreachable")
            self.local_state.is_active = True
            self.local_state.local_mode_start = datetime.now()
            self.metrics['local_mode_activations'] += 1
            self.orchestrator_available = False
            self._save_local_state()
    
    async def register(self) -> bool:
        """Register with orchestrator."""
        if self.local_state.is_active:
            logger.info("In local mode, skipping registration")
            return False
        
        try:
            data = {
                "server_id": self.server_id,
                "ip": self._get_local_ip(),
                "port": int(os.getenv('LOCAL_PORT', 8000)),
                "max_streams": self.max_streams
            }
            
            response = await self._make_request("POST", "/register", data)
            
            if response.get("status") == "registered":
                logger.info(f"Successfully registered with orchestrator")
                self.is_registered = True
                return True
            else:
                logger.error(f"Registration failed: {response}")
                self.is_registered = False
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            self.is_registered = False
            return False
    
    async def send_heartbeat(self) -> bool:
        """Send heartbeat to orchestrator."""
        if self.local_state.is_active:
            logger.debug("In local mode, skipping heartbeat")
            return False
        
        try:
            data = {
                "server_id": self.server_id,
                "current_streams": len(self.local_state.assigned_streams),
                "status": "active"
            }
            
            response = await self._make_request("POST", "/heartbeat", data)
            
            if response.get("status") == "heartbeat_updated":
                logger.debug("Heartbeat sent successfully")
                return True
            else:
                logger.error(f"Heartbeat failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return False
    
    async def request_streams(self, requested_count: Optional[int] = None) -> List[int]:
        """Request streams from orchestrator."""
        if self.local_state.is_active:
            logger.info("In local mode, using cached streams")
            return self.local_state.assigned_streams.copy()
        
        if requested_count is None:
            requested_count = self.max_streams - len(self.local_state.assigned_streams)
        
        try:
            data = {
                "server_id": self.server_id,
                "requested_count": requested_count
            }
            
            response = await self._make_request("POST", "/streams/assign", data)
            
            if response.get("status") == "assigned":
                new_streams = response.get("assigned_streams", [])
                self.local_state.assigned_streams.extend(new_streams)
                self._save_local_state()
                
                logger.info(f"Received {len(new_streams)} streams: {new_streams}")
                return new_streams
                
            elif response.get("status") in ["no_capacity", "no_streams"]:
                logger.info(f"No streams assigned: {response.get('message')}")
                return []
                
            else:
                logger.error(f"Unexpected response: {response}")
                return []
                
        except Exception as e:
            logger.error(f"Stream request error: {e}")
            return []
    
    async def release_streams(self, stream_ids: List[int]) -> bool:
        """Release streams."""
        if self.local_state.is_active:
            logger.info("In local mode, releasing streams locally")
            for stream_id in stream_ids:
                if stream_id in self.local_state.assigned_streams:
                    self.local_state.assigned_streams.remove(stream_id)
            self._save_local_state()
            return True
        
        if not stream_ids:
            return True
        
        try:
            data = {
                "server_id": self.server_id,
                "stream_ids": stream_ids
            }
            
            response = await self._make_request("POST", "/streams/release", data)
            
            if response.get("status") == "released":
                released_streams = response.get("released_streams", [])
                
                for stream_id in released_streams:
                    if stream_id in self.local_state.assigned_streams:
                        self.local_state.assigned_streams.remove(stream_id)
                
                self._save_local_state()
                logger.info(f"Released {len(released_streams)} streams")
                return True
                
            else:
                logger.error(f"Stream release failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Stream release error: {e}")
            return False
    
    def can_process_stream(self, stream_id: int) -> bool:
        """Check if stream can be processed in local mode."""
        if not self.local_state.is_active:
            return stream_id in self.local_state.assigned_streams
        
        # In local mode, can process assigned streams
        return stream_id in self.local_state.assigned_streams
    
    def record_stream_processing(self, stream_id: int) -> None:
        """Record that a stream was processed."""
        self.local_state.processed_streams[stream_id] = datetime.now()
        
        # Clean old entries (keep last 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        self.local_state.processed_streams = {
            k: v for k, v in self.local_state.processed_streams.items()
            if v > cutoff
        }
        
        self._save_local_state()
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        now = datetime.now()
        
        # Check if we need to test orchestrator availability
        if (now - self.last_health_check).total_seconds() >= self.health_check_interval:
            self.last_health_check = now
            
            try:
                response = await self._make_request("GET", "/health")
                orchestrator_healthy = response.get("status") == "healthy"
            except Exception:
                orchestrator_healthy = False
            
            self.orchestrator_available = orchestrator_healthy
        
        return {
            'server_id': self.server_id,
            'orchestrator_available': self.orchestrator_available,
            'local_mode_active': self.local_state.is_active,
            'assigned_streams': len(self.local_state.assigned_streams),
            'circuit_breaker_state': self.circuit_breaker.stats.state.value,
            'last_orchestrator_contact': self.local_state.last_orchestrator_contact.isoformat() if self.local_state.last_orchestrator_contact else None,
            'metrics': self.metrics.copy()
        }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed status information."""
        return {
            'client_info': {
                'server_id': self.server_id,
                'orchestrator_url': self.orchestrator_url,
                'max_streams': self.max_streams
            },
            'local_state': self.local_state.to_dict(),
            'circuit_breaker': self.circuit_breaker.get_stats(),
            'orchestrator_status': {
                'available': self.orchestrator_available,
                'last_health_check': self.last_health_check.isoformat()
            },
            'metrics': self.metrics.copy(),
            'configuration': {
                'circuit_breaker': {
                    'failure_threshold': self.circuit_config.failure_threshold,
                    'recovery_timeout': self.circuit_config.recovery_timeout,
                    'success_threshold': self.circuit_config.success_threshold,
                    'timeout': self.circuit_config.timeout
                },
                'retry': {
                    'max_attempts': self.retry_config.max_attempts,
                    'base_delay': self.retry_config.base_delay,
                    'max_delay': self.retry_config.max_delay,
                    'exponential_base': self.retry_config.exponential_base,
                    'jitter': self.retry_config.jitter
                }
            }
        }
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    async def shutdown(self) -> None:
        """Shutdown client gracefully."""
        logger.info(f"Shutting down resilient worker client for {self.server_id}")
        
        # Try to release all streams if orchestrator is available
        if not self.local_state.is_active and self.local_state.assigned_streams:
            try:
                await self.release_streams(self.local_state.assigned_streams.copy())
            except Exception as e:
                logger.warning(f"Failed to release streams during shutdown: {e}")
        
        # Save final state
        self._save_local_state()
        
        # Close HTTP session
        if self.session and not self.session.closed:
            await self.session.close()
        
        logger.info("Resilient worker client shutdown complete")


def create_resilient_worker_client(
    orchestrator_url: str,
    server_id: str,
    max_streams: int = 20,
    circuit_failure_threshold: int = 5,
    circuit_recovery_timeout: int = 60,
    retry_max_attempts: int = 3,
    retry_base_delay: float = 1.0
) -> ResilientWorkerClient:
    """
    Factory function to create a resilient worker client with custom configuration.
    
    Args:
        orchestrator_url: URL of the orchestrator service
        server_id: Unique identifier for this worker instance
        max_streams: Maximum number of streams this worker can handle
        circuit_failure_threshold: Number of failures before opening circuit
        circuit_recovery_timeout: Seconds to wait before testing recovery
        retry_max_attempts: Maximum retry attempts
        retry_base_delay: Base delay for exponential backoff
    
    Returns:
        Configured ResilientWorkerClient instance
    """
    circuit_config = CircuitBreakerConfig(
        failure_threshold=circuit_failure_threshold,
        recovery_timeout=circuit_recovery_timeout,
        success_threshold=3,
        timeout=30
    )
    
    retry_config = RetryConfig(
        max_attempts=retry_max_attempts,
        base_delay=retry_base_delay,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True
    )
    
    return ResilientWorkerClient(
        orchestrator_url=orchestrator_url,
        server_id=server_id,
        max_streams=max_streams,
        circuit_config=circuit_config,
        retry_config=retry_config
    )
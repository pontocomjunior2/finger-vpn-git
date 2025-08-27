#!/usr/bin/env python3
"""
Orquestrador Central para Distribuição de Streams

Este serviço gerencia a distribuição de streams entre múltiplas instâncias
do sistema de fingerprinting, eliminando duplicidades e garantindo
balanceamento de carga adequado.

Autor: Sistema de Fingerprinting
Data: 2025
"""

import asyncio
import logging
import os
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras
import redis
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

# Import diagnostic logging functionality
from diagnostic_logger import diagnostic_logger, environment_validator, diagnostic_functions

# Configuração de logging (deve vir antes de qualquer uso do logger)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Set initial phase for diagnostic logging
diagnostic_logger.set_phase("MODULE_INITIALIZATION")

# =============================================================================
# OPTIONAL MODULE LOADING WITH GRACEFUL DEGRADATION
# =============================================================================

def load_optional_modules():
    """
    Load optional modules with graceful degradation and detailed logging.
    
    Returns:
        dict: Dictionary containing module availability flags and loaded modules
        
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    modules = {
        'psutil': {'available': False, 'module': None, 'error': None},
        'enhanced_orchestrator': {'available': False, 'module': None, 'error': None},
        'resilient_orchestrator': {'available': False, 'module': None, 'error': None}
    }
    
    # Load psutil for system metrics
    try:
        import psutil
        modules['psutil']['available'] = True
        modules['psutil']['module'] = psutil
        logger.info("psutil loaded successfully - system metrics available")
    except ImportError as e:
        modules['psutil']['error'] = str(e)
        logger.warning(f"psutil not available: {e}. System metrics will be disabled.")
    except Exception as e:
        modules['psutil']['error'] = str(e)
        logger.error(f"Unexpected error loading psutil: {e}")
    
    # Load enhanced orchestrator for smart load balancing
    try:
        from enhanced_orchestrator import EnhancedStreamOrchestrator
        from load_balancer_config import create_load_balance_config
        from smart_load_balancer import LoadBalanceConfig, RebalanceReason
        
        modules['enhanced_orchestrator']['available'] = True
        modules['enhanced_orchestrator']['module'] = {
            'EnhancedStreamOrchestrator': EnhancedStreamOrchestrator,
            'create_load_balance_config': create_load_balance_config,
            'LoadBalanceConfig': LoadBalanceConfig,
            'RebalanceReason': RebalanceReason
        }
        logger.info("Enhanced orchestrator loaded successfully - smart load balancing available")
        
    except ImportError as e:
        modules['enhanced_orchestrator']['error'] = str(e)
        logger.warning(f"Enhanced orchestrator not available: {e}. Using basic load balancing.")
    except Exception as e:
        modules['enhanced_orchestrator']['error'] = str(e)
        logger.error(f"Unexpected error loading enhanced orchestrator: {e}")
    
    # Load resilient orchestrator for enhanced failure handling
    try:
        from resilient_orchestrator import (
            FailureRecoveryConfig, 
            HeartbeatConfig,
            ResilientOrchestrator,
            SystemHealthStatus
        )
        
        modules['resilient_orchestrator']['available'] = True
        modules['resilient_orchestrator']['module'] = {
            'FailureRecoveryConfig': FailureRecoveryConfig,
            'HeartbeatConfig': HeartbeatConfig,
            'ResilientOrchestrator': ResilientOrchestrator,
            'SystemHealthStatus': SystemHealthStatus
        }
        logger.info("Resilient orchestrator loaded successfully - enhanced failure handling available")
        
    except ImportError as e:
        modules['resilient_orchestrator']['error'] = str(e)
        logger.warning(f"Resilient orchestrator not available: {e}. Using basic failure handling.")
    except Exception as e:
        modules['resilient_orchestrator']['error'] = str(e)
        logger.error(f"Unexpected error loading resilient orchestrator: {e}")
    
    # Log summary of loaded modules
    available_modules = [name for name, info in modules.items() if info['available']]
    unavailable_modules = [name for name, info in modules.items() if not info['available']]
    
    logger.info(f"Optional modules loaded: {available_modules}")
    if unavailable_modules:
        logger.warning(f"Optional modules not available: {unavailable_modules}")
        logger.info("System will continue with basic functionality for missing modules")
    
    return modules

# Load optional modules with graceful degradation
OPTIONAL_MODULES = load_optional_modules()

# Set compatibility flags for backward compatibility
HAS_PSUTIL = OPTIONAL_MODULES['psutil']['available']
HAS_SMART_BALANCER = OPTIONAL_MODULES['enhanced_orchestrator']['available'] 
HAS_RESILIENT_ORCHESTRATOR = OPTIONAL_MODULES['resilient_orchestrator']['available']

# Extract modules for direct access (with None fallback)
psutil = OPTIONAL_MODULES['psutil']['module'] if HAS_PSUTIL else None

if HAS_SMART_BALANCER:
    enhanced_modules = OPTIONAL_MODULES['enhanced_orchestrator']['module']
    EnhancedStreamOrchestrator = enhanced_modules['EnhancedStreamOrchestrator']
    create_load_balance_config = enhanced_modules['create_load_balance_config']
    LoadBalanceConfig = enhanced_modules['LoadBalanceConfig']
    RebalanceReason = enhanced_modules['RebalanceReason']
else:
    EnhancedStreamOrchestrator = None
    create_load_balance_config = None
    LoadBalanceConfig = None
    RebalanceReason = None

if HAS_RESILIENT_ORCHESTRATOR:
    resilient_modules = OPTIONAL_MODULES['resilient_orchestrator']['module']
    FailureRecoveryConfig = resilient_modules['FailureRecoveryConfig']
    HeartbeatConfig = resilient_modules['HeartbeatConfig']
    ResilientOrchestrator = resilient_modules['ResilientOrchestrator']
    SystemHealthStatus = resilient_modules['SystemHealthStatus']
else:
    FailureRecoveryConfig = None
    HeartbeatConfig = None
    ResilientOrchestrator = None
    SystemHealthStatus = None

# Carregar variáveis de ambiente
# Primeiro tenta carregar do .env da raiz do projeto
root_env_file = Path(__file__).parent.parent / ".env"
app_env_file = Path(__file__).parent / ".env"

if root_env_file.exists():
    load_dotenv(root_env_file)
    print(f"Orquestrador: Variáveis carregadas de {root_env_file}")
elif app_env_file.exists():
    load_dotenv(app_env_file)
    print(f"Orquestrador: Variáveis carregadas de {app_env_file}")
else:
    print("Orquestrador: Nenhum arquivo .env encontrado")

# Mapear variáveis POSTGRES_* para DB_* se necessário
if os.getenv("POSTGRES_HOST") and not os.getenv("DB_HOST"):
    os.environ["DB_HOST"] = os.getenv("POSTGRES_HOST")
if os.getenv("POSTGRES_DB") and not os.getenv("DB_NAME"):
    os.environ["DB_NAME"] = os.getenv("POSTGRES_DB")
if os.getenv("POSTGRES_USER") and not os.getenv("DB_USER"):
    os.environ["DB_USER"] = os.getenv("POSTGRES_USER")
if os.getenv("POSTGRES_PASSWORD") and not os.getenv("DB_PASSWORD"):
    os.environ["DB_PASSWORD"] = os.getenv("POSTGRES_PASSWORD")
if os.getenv("POSTGRES_PORT") and not os.getenv("DB_PORT"):
    os.environ["DB_PORT"] = os.getenv("POSTGRES_PORT")

# Configuração de logging já foi feita acima

# Configurações do banco de dados
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "radio_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "port": int(os.getenv("DB_PORT", 5432)),
}

# Configurações do orquestrador
MAX_STREAMS_PER_INSTANCE = int(os.getenv("MAX_STREAMS_PER_INSTANCE", 20))
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", 300))  # 5 minutos
REBALANCE_INTERVAL = int(os.getenv("REBALANCE_INTERVAL", 60))  # 1 minuto

# Service startup configuration
POSTGRES_STARTUP_TIMEOUT = int(os.getenv("POSTGRES_STARTUP_TIMEOUT", 60))
REDIS_STARTUP_TIMEOUT = int(os.getenv("REDIS_STARTUP_TIMEOUT", 30))
DB_MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", 3))
DB_RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", 1.0))


# =============================================================================
# SERVICE STARTUP VERIFICATION FUNCTIONS
# =============================================================================

def wait_for_postgres(host: str = "localhost", port: int = 5432, timeout: int = POSTGRES_STARTUP_TIMEOUT) -> bool:
    """
    Wait for PostgreSQL to be ready with timeout and retry logic.
    
    Args:
        host: PostgreSQL host
        port: PostgreSQL port
        timeout: Maximum time to wait in seconds
        
    Returns:
        bool: True if PostgreSQL is ready, False if timeout
        
    Requirements: 1.1, 1.2, 3.1, 4.1, 4.2
    """
    diagnostic_logger.set_phase("POSTGRES_STARTUP")
    diagnostic_logger.step(f"Waiting for PostgreSQL at {host}:{port} (timeout: {timeout}s)")
    
    start_time = time.time()
    retry_delay = 1.0
    max_retry_delay = 8.0
    attempt_count = 0
    
    while time.time() - start_time < timeout:
        attempt_count += 1
        elapsed = time.time() - start_time
        
        diagnostic_logger.info(f"PostgreSQL readiness check attempt #{attempt_count} (elapsed: {elapsed:.1f}s)", 
                              context={"host": host, "port": port, "attempt": attempt_count})
        
        try:
            # Try to connect using pg_isready command first (more reliable)
            result = subprocess.run(
                ["pg_isready", "-h", host, "-p", str(port)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                diagnostic_logger.success(f"PostgreSQL is ready at {host}:{port} (verified with pg_isready)", 
                                        context={"method": "pg_isready", "attempts": attempt_count, "elapsed": elapsed})
                return True
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to direct connection test
            try:
                # Test basic connection without authentication
                test_conn = psycopg2.connect(
                    host=host,
                    port=port,
                    database="postgres",  # Default database
                    user="postgres",      # Default user
                    password="",          # No password for initial test
                    connect_timeout=3
                )
                test_conn.close()
                diagnostic_logger.success(f"PostgreSQL is ready at {host}:{port} (direct connection)", 
                                        context={"method": "direct_connection", "attempts": attempt_count, "elapsed": elapsed})
                return True
                
            except psycopg2.OperationalError as e:
                # Check if it's an authentication error (means server is up)
                if "authentication failed" in str(e).lower() or "password authentication failed" in str(e).lower():
                    diagnostic_logger.success(f"PostgreSQL is ready at {host}:{port} (authentication required)", 
                                            context={"method": "auth_check", "attempts": attempt_count, "elapsed": elapsed})
                    return True
                    
                # Server not ready yet - log specific error for diagnostics
                diagnostic_logger.warning(f"PostgreSQL connection attempt failed: {str(e)[:100]}...", 
                                        context={"error_type": "OperationalError", "attempt": attempt_count})
            except Exception as e:
                # Any other error means server not ready
                diagnostic_logger.warning(f"PostgreSQL connection attempt failed: {str(e)[:100]}...", 
                                        context={"error_type": type(e).__name__, "attempt": attempt_count})
        
        remaining = timeout - elapsed
        
        if remaining <= 0:
            break
            
        # Exponential backoff with jitter
        actual_delay = min(retry_delay, remaining)
        diagnostic_logger.info(f"PostgreSQL not ready, retrying in {actual_delay:.1f}s (remaining: {remaining:.1f}s)", 
                              context={"retry_delay": actual_delay, "remaining_time": remaining})
        time.sleep(actual_delay)
        
        # Increase delay for next iteration
        retry_delay = min(retry_delay * 1.5, max_retry_delay)
    
    diagnostic_logger.error(f"PostgreSQL not ready after {timeout}s timeout at {host}:{port}", 
                           context={"total_attempts": attempt_count, "timeout": timeout, "host": host, "port": port},
                           suggested_solution="Check PostgreSQL service status, increase timeout, or verify network connectivity")
    return False


def wait_for_redis(host: str = "localhost", port: int = 6379, timeout: int = REDIS_STARTUP_TIMEOUT) -> bool:
    """
    Wait for Redis to be ready with ping verification.
    
    Args:
        host: Redis host
        port: Redis port  
        timeout: Maximum time to wait in seconds
        
    Returns:
        bool: True if Redis is ready, False if timeout
        
    Requirements: 1.2, 3.2, 4.1, 4.2
    """
    diagnostic_logger.set_phase("REDIS_STARTUP")
    diagnostic_logger.step(f"Waiting for Redis at {host}:{port} (timeout: {timeout}s)")
    
    start_time = time.time()
    retry_delay = 0.5
    max_retry_delay = 4.0
    attempt_count = 0
    
    while time.time() - start_time < timeout:
        attempt_count += 1
        elapsed = time.time() - start_time
        
        diagnostic_logger.info(f"Redis readiness check attempt #{attempt_count} (elapsed: {elapsed:.1f}s)", 
                              context={"host": host, "port": port, "attempt": attempt_count})
        
        try:
            # Create Redis client with short timeout
            redis_client = redis.Redis(
                host=host,
                port=port,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=False
            )
            
            # Test with ping command
            response = redis_client.ping()
            
            if response:
                diagnostic_logger.success(f"Redis is ready at {host}:{port} (ping successful)", 
                                        context={"method": "ping", "attempts": attempt_count, "elapsed": elapsed})
                redis_client.close()
                return True
                
        except redis.ConnectionError as e:
            # Connection failed, server not ready
            diagnostic_logger.warning(f"Redis connection failed: {str(e)[:100]}...", 
                                    context={"error_type": "ConnectionError", "attempt": attempt_count})
        except redis.TimeoutError as e:
            # Timeout, server might be overloaded
            diagnostic_logger.warning(f"Redis timeout: {str(e)[:100]}...", 
                                    context={"error_type": "TimeoutError", "attempt": attempt_count})
        except Exception as e:
            # Any other error
            diagnostic_logger.warning(f"Redis connection error: {str(e)[:100]}...", 
                                    context={"error_type": type(e).__name__, "attempt": attempt_count})
        
        remaining = timeout - elapsed
        
        if remaining <= 0:
            break
            
        # Exponential backoff
        actual_delay = min(retry_delay, remaining)
        diagnostic_logger.info(f"Redis not ready, retrying in {actual_delay:.1f}s (remaining: {remaining:.1f}s)", 
                              context={"retry_delay": actual_delay, "remaining_time": remaining})
        time.sleep(actual_delay)
        
        # Increase delay for next iteration
        retry_delay = min(retry_delay * 1.5, max_retry_delay)
    
    diagnostic_logger.error(f"Redis not ready after {timeout}s timeout at {host}:{port}", 
                           context={"total_attempts": attempt_count, "timeout": timeout, "host": host, "port": port},
                           suggested_solution="Check Redis service status, increase timeout, or verify network connectivity")
    return False


def setup_database(db_config: dict, max_retries: int = DB_MAX_RETRIES) -> bool:
    """
    Setup database with proper error handling and retry logic.
    
    Args:
        db_config: Database configuration dictionary
        max_retries: Maximum number of retry attempts
        
    Returns:
        bool: True if setup successful, False otherwise
        
    Requirements: 1.1, 2.1, 2.2, 2.3, 4.1, 4.2
    """
    diagnostic_logger.set_phase("DATABASE_SETUP")
    diagnostic_logger.step("Setting up database connection and tables")
    
    retry_delay = DB_RETRY_DELAY
    
    for attempt in range(max_retries):
        conn = None
        cursor = None
        
        try:
            # Test basic connectivity first
            diagnostic_logger.info(f"Database setup attempt {attempt + 1}/{max_retries}", 
                                  context={"attempt": attempt + 1, "max_retries": max_retries, "config": {
                                      "host": db_config["host"], "port": db_config["port"], 
                                      "database": db_config["database"], "user": db_config["user"]
                                  }})
            
            # Try to connect with provided configuration
            conn = psycopg2.connect(**db_config)
            conn.autocommit = True
            
            # Test the connection with a simple query
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            
            if result and result[0] == 1:
                diagnostic_logger.success("Database connection successful", 
                                        context={"attempt": attempt + 1, "database": db_config["database"]})
                return True
            else:
                diagnostic_logger.warning("Database connection test failed - unexpected result", 
                                        context={"result": result})
                
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            
            if "authentication failed" in error_msg:
                diagnostic_logger.error(f"Database authentication failed: {e}", 
                                      context={"user": db_config["user"], "host": db_config["host"]},
                                      exception=e,
                                      suggested_solution="Verify DB_USER and DB_PASSWORD environment variables")
                return False  # Don't retry authentication errors
            elif "database" in error_msg and "does not exist" in error_msg:
                diagnostic_logger.warning(f"Target database does not exist, attempting to create: {e}", 
                                        context={"database": db_config["database"]})
                # Try to connect to default postgres database to create the target database
                try:
                    default_config = db_config.copy()
                    default_config["database"] = "postgres"
                    
                    default_conn = psycopg2.connect(**default_config)
                    default_conn.autocommit = True
                    default_cursor = default_conn.cursor()
                    
                    # Create database if it doesn't exist
                    default_cursor.execute(f"CREATE DATABASE {db_config['database']}")
                    diagnostic_logger.success(f"Created database: {db_config['database']}")
                    
                    default_cursor.close()
                    default_conn.close()
                    
                    # Now try original connection again
                    continue
                    
                except Exception as create_error:
                    diagnostic_logger.error(f"Could not create database: {create_error}", 
                                          exception=create_error,
                                          suggested_solution="Check database creation permissions or create database manually")
            else:
                diagnostic_logger.warning(f"Database connection failed (attempt {attempt + 1}): {e}", 
                                        context={"error_type": "OperationalError", "attempt": attempt + 1},
                                        exception=e)
                
        except psycopg2.DatabaseError as e:
            diagnostic_logger.error(f"Database error during setup (attempt {attempt + 1}): {e}", 
                                   context={"error_type": "DatabaseError", "attempt": attempt + 1},
                                   exception=e,
                                   suggested_solution="Check database server health and configuration")
            
        except Exception as e:
            diagnostic_logger.error(f"Unexpected error during database setup (attempt {attempt + 1}): {e}", 
                                   context={"error_type": type(e).__name__, "attempt": attempt + 1},
                                   exception=e,
                                   suggested_solution="Check database connectivity and system resources")
            
        finally:
            # Safe cleanup with enhanced error handling
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as cursor_error:
                    diagnostic_logger.warning(f"Error closing cursor: {cursor_error}", 
                                            context={"cleanup_error": "cursor"})
            if conn is not None:
                try:
                    conn.close()
                except Exception as conn_error:
                    diagnostic_logger.warning(f"Error closing connection: {conn_error}", 
                                            context={"cleanup_error": "connection"})
        
        # Wait before retry (except on last attempt)
        if attempt < max_retries - 1:
            diagnostic_logger.info(f"Retrying database setup in {retry_delay:.1f}s...", 
                                  context={"retry_delay": retry_delay, "next_attempt": attempt + 2})
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
    
    diagnostic_logger.error(f"Database setup failed after {max_retries} attempts", 
                           context={"max_retries": max_retries, "final_retry_delay": retry_delay},
                           suggested_solution="Check database service status, verify configuration, or increase DB_MAX_RETRIES")
    return False


def _get_application_components_status(orchestrator) -> dict:
    """
    Get status of application components including optional modules.
    
    Args:
        orchestrator: StreamOrchestrator instance
        
    Returns:
        dict: Status of each application component
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    components = {}
    
    # Check enhanced orchestrator
    components["enhanced_orchestrator"] = {
        "name": "Enhanced Orchestrator (Smart Load Balancing)",
        "status": "available" if orchestrator.enhanced_orchestrator else "unavailable",
        "details": {
            "module_loaded": HAS_SMART_BALANCER,
            "instance_initialized": orchestrator.enhanced_orchestrator is not None,
            "functionality": "Smart load balancing and advanced stream management"
        }
    }
    
    if not orchestrator.enhanced_orchestrator and HAS_SMART_BALANCER:
        components["enhanced_orchestrator"]["error"] = "Module loaded but instance not initialized"
    elif not HAS_SMART_BALANCER:
        error_info = OPTIONAL_MODULES.get('enhanced_orchestrator', {}).get('error')
        components["enhanced_orchestrator"]["error"] = error_info or "Module not available"
    
    # Check resilient orchestrator
    components["resilient_orchestrator"] = {
        "name": "Resilient Orchestrator (Enhanced Failure Handling)",
        "status": "available" if orchestrator.resilient_orchestrator else "unavailable",
        "details": {
            "module_loaded": HAS_RESILIENT_ORCHESTRATOR,
            "instance_initialized": orchestrator.resilient_orchestrator is not None,
            "functionality": "Enhanced failure detection and recovery"
        }
    }
    
    if not orchestrator.resilient_orchestrator and HAS_RESILIENT_ORCHESTRATOR:
        components["resilient_orchestrator"]["error"] = "Module loaded but instance not initialized"
    elif not HAS_RESILIENT_ORCHESTRATOR:
        error_info = OPTIONAL_MODULES.get('resilient_orchestrator', {}).get('error')
        components["resilient_orchestrator"]["error"] = error_info or "Module not available"
    
    # Check psutil for system metrics
    components["system_metrics"] = {
        "name": "System Metrics (psutil)",
        "status": "available" if HAS_PSUTIL else "unavailable",
        "details": {
            "module_loaded": HAS_PSUTIL,
            "functionality": "CPU, memory, and disk usage monitoring"
        }
    }
    
    if not HAS_PSUTIL:
        error_info = OPTIONAL_MODULES.get('psutil', {}).get('error')
        components["system_metrics"]["error"] = error_info or "Module not available"
    
    return components


def _validate_configuration() -> dict:
    """
    Validate system configuration and environment variables.
    
    Returns:
        dict: Configuration validation results
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    validation = {
        "status": "valid",
        "issues": [],
        "environment_variables": {},
        "database_config": {},
        "timeouts": {}
    }
    
    # Check required environment variables
    required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    for var in required_vars:
        value = os.getenv(var)
        if value:
            validation["environment_variables"][var] = "set"
        else:
            validation["environment_variables"][var] = "missing"
            validation["issues"].append(f"Environment variable {var} is not set")
    
    # Check database configuration
    validation["database_config"] = {
        "host": DB_CONFIG["host"],
        "port": DB_CONFIG["port"],
        "database": DB_CONFIG["database"],
        "user": DB_CONFIG["user"],
        "password_set": bool(DB_CONFIG["password"])
    }
    
    # Check timeout configurations
    validation["timeouts"] = {
        "postgres_startup_timeout": POSTGRES_STARTUP_TIMEOUT,
        "redis_startup_timeout": REDIS_STARTUP_TIMEOUT,
        "heartbeat_timeout": HEARTBEAT_TIMEOUT,
        "db_max_retries": DB_MAX_RETRIES,
        "db_retry_delay": DB_RETRY_DELAY
    }
    
    # Validate timeout values
    if POSTGRES_STARTUP_TIMEOUT < 30:
        validation["issues"].append("PostgreSQL startup timeout is very low (< 30s)")
    if REDIS_STARTUP_TIMEOUT < 10:
        validation["issues"].append("Redis startup timeout is very low (< 10s)")
    if HEARTBEAT_TIMEOUT < 60:
        validation["issues"].append("Heartbeat timeout is very low (< 60s)")
    
    # Set overall status
    if validation["issues"]:
        validation["status"] = "issues_found"
    
    return validation


def _get_system_warnings() -> List[str]:
    """
    Get current system warnings and potential issues.
    
    Returns:
        List[str]: List of warning messages
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    warnings = []
    
    # Check optional modules
    if not HAS_SMART_BALANCER:
        warnings.append("Enhanced orchestrator not available - using basic load balancing")
    
    if not HAS_RESILIENT_ORCHESTRATOR:
        warnings.append("Resilient orchestrator not available - using basic failure handling")
    
    if not HAS_PSUTIL:
        warnings.append("System metrics not available - psutil module not loaded")
    
    # Check system resources if psutil is available
    if HAS_PSUTIL and psutil:
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                warnings.append(f"High memory usage detected: {memory.percent:.1f}%")
            
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > 90:
                warnings.append(f"High disk usage detected: {disk_percent:.1f}%")
                
        except Exception:
            pass
    
    # Check configuration warnings
    if not os.getenv("DB_PASSWORD"):
        warnings.append("Database password not set - using empty password")
    
    return warnings


def _get_system_recommendations(service_status: dict, app_components: dict) -> List[str]:
    """
    Get system recommendations based on current status.
    
    Args:
        service_status: Service status from verify_services
        app_components: Application components status
        
    Returns:
        List[str]: List of recommendation messages
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    recommendations = []
    
    # Service-based recommendations
    if service_status["overall_status"] != "ready":
        recommendations.append("Ensure all required services (PostgreSQL, Redis) are running and accessible")
    
    # Component-based recommendations
    unavailable_components = [
        name for name, info in app_components.items() 
        if info.get("status") == "unavailable"
    ]
    
    if "enhanced_orchestrator" in unavailable_components:
        recommendations.append("Consider installing enhanced orchestrator for smart load balancing capabilities")
    
    if "resilient_orchestrator" in unavailable_components:
        recommendations.append("Consider installing resilient orchestrator for enhanced failure handling")
    
    if "system_metrics" in unavailable_components:
        recommendations.append("Install psutil package for system metrics monitoring")
    
    # Performance recommendations
    if HAS_PSUTIL and psutil:
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 80:
                recommendations.append("Consider increasing available memory or optimizing memory usage")
            
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > 80:
                recommendations.append("High CPU usage detected - consider scaling or optimization")
                
        except Exception:
            pass
    
    # Configuration recommendations
    if HEARTBEAT_TIMEOUT < 300:
        recommendations.append("Consider increasing heartbeat timeout for better stability in slow networks")
    
    if DB_MAX_RETRIES < 3:
        recommendations.append("Consider increasing database retry attempts for better resilience")
    
    return recommendations


def _get_system_metrics() -> Optional[dict]:
    """
    Get current system metrics if psutil is available.
    
    Returns:
        dict: System metrics or None if not available
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    if not HAS_PSUTIL or not psutil:
        return None
    
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        
        # Get disk usage for root partition
        disk = psutil.disk_usage('/')
        
        # Get load average (Unix-like systems only)
        load_avg = None
        try:
            load_avg = list(psutil.getloadavg())
        except (AttributeError, OSError):
            # Not available on Windows
            pass
        
        # Get uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory": {
                "percent": round(memory.percent, 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2)
            },
            "disk": {
                "percent": round((disk.used / disk.total) * 100, 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2)
            },
            "load_average": load_avg,
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_human": str(timedelta(seconds=int(uptime_seconds)))
        }
        
    except Exception as e:
        logger.warning(f"Failed to get system metrics: {e}")
        return {
            "error": str(e),
            "message": "System metrics collection failed"
        }


def validate_startup_environment() -> dict:
    """
    Validate startup environment with comprehensive diagnostics and reporting.
    
    Returns:
        dict: Comprehensive validation report
        
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    diagnostic_logger.set_phase("STARTUP_VALIDATION")
    diagnostic_logger.step("Starting comprehensive startup environment validation")
    
    # Perform environment validation
    env_validation = environment_validator.validate_all()
    
    # Generate diagnostic report
    diagnostic_report = diagnostic_functions.generate_comprehensive_report(
        DB_CONFIG, 
        os.getenv("REDIS_HOST", "localhost"), 
        int(os.getenv("REDIS_PORT", 6379))
    )
    
    # Combine results
    validation_report = {
        "timestamp": datetime.now().isoformat(),
        "validation_type": "startup_environment",
        "environment_validation": env_validation,
        "service_diagnostics": diagnostic_report,
        "overall_status": "UNKNOWN",
        "critical_issues": [],
        "warnings": [],
        "recommendations": []
    }
    
    # Analyze combined results
    critical_issues = []
    warnings = []
    recommendations = []
    
    # Check environment validation
    if env_validation["overall_status"] == "FAILED":
        critical_issues.extend(env_validation["issues"])
        recommendations.extend(env_validation["recommendations"])
    elif env_validation["overall_status"] == "WARNING":
        warnings.extend(env_validation["warnings"])
        recommendations.extend(env_validation["recommendations"])
    
    # Check service diagnostics
    if diagnostic_report["overall_status"] in ["ALL_ISSUES", "MIXED"]:
        for service_name, service_data in diagnostic_report["services"].items():
            if service_data["status"] != "HEALTHY":
                for issue in service_data["issues_found"]:
                    critical_issues.append(f"{service_name}: {issue['error']}")
        recommendations.extend(diagnostic_report["recommendations"])
    
    # Set overall status
    if critical_issues:
        validation_report["overall_status"] = "CRITICAL_ISSUES"
    elif warnings:
        validation_report["overall_status"] = "WARNINGS"
    else:
        validation_report["overall_status"] = "HEALTHY"
    
    validation_report["critical_issues"] = critical_issues
    validation_report["warnings"] = warnings
    validation_report["recommendations"] = list(set(recommendations))  # Remove duplicates
    
    # Log results
    if validation_report["overall_status"] == "CRITICAL_ISSUES":
        diagnostic_logger.error("Startup environment validation found critical issues", 
                               context={"critical_issues_count": len(critical_issues)},
                               suggested_solution="Address critical issues before proceeding")
    elif validation_report["overall_status"] == "WARNINGS":
        diagnostic_logger.warning("Startup environment validation completed with warnings", 
                                 context={"warnings_count": len(warnings)})
    else:
        diagnostic_logger.success("Startup environment validation passed successfully")
    
    return validation_report


def verify_services(db_config: dict, redis_host: str = "localhost", redis_port: int = 6379) -> dict:
    """
    Perform comprehensive checks of all required services.
    
    Args:
        db_config: Database configuration dictionary
        redis_host: Redis host
        redis_port: Redis port
        
    Returns:
        dict: Service status report with detailed information
        
    Requirements: 3.1, 3.2, 3.3, 4.3
    """
    diagnostic_logger.set_phase("SERVICE_VERIFICATION")
    diagnostic_logger.step("Performing comprehensive service verification")
    
    status_report = {
        "overall_status": "unknown",
        "services": {},
        "timestamp": datetime.now().isoformat(),
        "errors": [],
        "verification_details": {
            "total_services": 2,
            "services_checked": 0,
            "services_ready": 0,
            "services_failed": 0
        }
    }
    
    # Check PostgreSQL
    diagnostic_logger.info("Starting PostgreSQL service verification", 
                          context={"host": db_config["host"], "port": db_config["port"], "database": db_config["database"]})
    
    postgres_status = {
        "name": "PostgreSQL",
        "status": "checking",
        "details": {},
        "error": None
    }
    
    try:
        # Test PostgreSQL connectivity
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Get PostgreSQL version
        cursor.execute("SELECT version()")
        version_info = cursor.fetchone()[0]
        postgres_status["details"]["version"] = version_info
        
        # Test basic operations
        cursor.execute("SELECT current_timestamp")
        current_time = cursor.fetchone()[0]
        postgres_status["details"]["current_time"] = str(current_time)
        
        # Check if we can create tables (test permissions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS service_verification_test (
                id SERIAL PRIMARY KEY,
                test_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert test data
        cursor.execute("INSERT INTO service_verification_test DEFAULT VALUES RETURNING id")
        test_id = cursor.fetchone()[0]
        
        # Clean up test data
        cursor.execute("DELETE FROM service_verification_test WHERE id = %s", (test_id,))
        cursor.execute("DROP TABLE service_verification_test")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        postgres_status["status"] = "ready"
        postgres_status["details"]["operations_test"] = "passed"
        status_report["verification_details"]["services_ready"] += 1
        
        diagnostic_logger.success("PostgreSQL service verification passed", 
                                 context={"version": version_info.split()[1] if len(version_info.split()) > 1 else "unknown",
                                         "operations_test": "passed"})
        
    except Exception as e:
        postgres_status["status"] = "error"
        postgres_status["error"] = str(e)
        status_report["errors"].append(f"PostgreSQL: {e}")
        status_report["verification_details"]["services_failed"] += 1
        
        diagnostic_logger.error("PostgreSQL service verification failed", 
                               context={"database": db_config["database"], "host": db_config["host"]},
                               exception=e,
                               suggested_solution="Check PostgreSQL service status and database connectivity")
    
    status_report["services"]["postgresql"] = postgres_status
    status_report["verification_details"]["services_checked"] += 1
    
    # Check Redis
    diagnostic_logger.info("Starting Redis service verification", 
                          context={"host": redis_host, "port": redis_port})
    
    redis_status = {
        "name": "Redis",
        "status": "checking", 
        "details": {},
        "error": None
    }
    
    try:
        # Test Redis connectivity
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        # Test ping
        ping_response = redis_client.ping()
        redis_status["details"]["ping"] = str(ping_response)
        
        # Get Redis info
        redis_info = redis_client.info()
        redis_status["details"]["version"] = redis_info.get("redis_version", "unknown")
        redis_status["details"]["uptime_seconds"] = redis_info.get("uptime_in_seconds", 0)
        redis_status["details"]["connected_clients"] = redis_info.get("connected_clients", 0)
        redis_status["details"]["used_memory_human"] = redis_info.get("used_memory_human", "unknown")
        
        # Test basic operations
        test_key = "service_verification_test"
        redis_client.set(test_key, "test_value", ex=10)  # Expire in 10 seconds
        test_value = redis_client.get(test_key)
        redis_client.delete(test_key)
        
        if test_value == b"test_value":
            redis_status["details"]["operations_test"] = "passed"
        else:
            redis_status["details"]["operations_test"] = "failed"
            diagnostic_logger.warning("Redis operations test returned unexpected result", 
                                     context={"expected": "test_value", "actual": str(test_value)})
            
        redis_client.close()
        redis_status["status"] = "ready"
        status_report["verification_details"]["services_ready"] += 1
        
        diagnostic_logger.success("Redis service verification passed", 
                                 context={"version": redis_status["details"]["version"],
                                         "uptime_seconds": redis_status["details"]["uptime_seconds"],
                                         "operations_test": redis_status["details"]["operations_test"]})
        
    except Exception as e:
        redis_status["status"] = "error"
        redis_status["error"] = str(e)
        status_report["errors"].append(f"Redis: {e}")
        status_report["verification_details"]["services_failed"] += 1
        
        diagnostic_logger.error("Redis service verification failed", 
                               context={"host": redis_host, "port": redis_port},
                               exception=e,
                               suggested_solution="Check Redis service status and connectivity")
    
    status_report["services"]["redis"] = redis_status
    status_report["verification_details"]["services_checked"] += 1
    
    # Determine overall status
    all_services_ready = all(
        service["status"] == "ready" 
        for service in status_report["services"].values()
    )
    
    if all_services_ready:
        status_report["overall_status"] = "ready"
        diagnostic_logger.success("All services verified successfully", 
                                 context={
                                     "services_ready": status_report["verification_details"]["services_ready"],
                                     "total_services": status_report["verification_details"]["total_services"]
                                 })
    else:
        status_report["overall_status"] = "error"
        diagnostic_logger.error("Service verification failed - not all services are ready", 
                               context={
                                   "services_ready": status_report["verification_details"]["services_ready"],
                                   "services_failed": status_report["verification_details"]["services_failed"],
                                   "total_services": status_report["verification_details"]["total_services"],
                                   "errors": status_report["errors"]
                               },
                               suggested_solution="Check failed services and resolve connectivity issues")
    
    return status_report


# Modelos Pydantic
class InstanceRegistration(BaseModel):
    server_id: str
    ip: str
    port: int
    max_streams: int = MAX_STREAMS_PER_INSTANCE


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_free_gb: float
    disk_total_gb: float
    load_average: Optional[List[float]] = None
    uptime_seconds: Optional[float] = None


class HeartbeatRequest(BaseModel):
    server_id: str
    current_streams: int
    status: str = "active"
    system_metrics: Optional[SystemMetrics] = None


class StreamRequest(BaseModel):
    server_id: str
    requested_count: int = MAX_STREAMS_PER_INSTANCE


class StreamRelease(BaseModel):
    server_id: str
    stream_ids: List[int]


class DiagnosticRequest(BaseModel):
    server_id: str
    local_streams: List[int]  # Lista de stream IDs que a instância acredita ter
    local_stream_count: int


# Função de ciclo de vida da aplicação
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação FastAPI com monitoramento resiliente."""
    # Startup
    logger.info("Iniciando orquestrador com monitoramento resiliente...")
    
    # Verify services before starting orchestrator
    logger.info("Verificando serviços antes de inicializar o orquestrador...")
    service_status = verify_services(DB_CONFIG)
    
    if service_status["overall_status"] != "ready":
        logger.error("Falha na verificação de serviços durante inicialização")
        logger.error(f"Erros: {service_status['errors']}")
        raise RuntimeError("Services not ready for orchestrator startup")
    
    logger.info("Todos os serviços verificados com sucesso")
    
    orchestrator = StreamOrchestrator()
    orchestrator.create_tables()

    # Iniciar tarefas em background usando as funções independentes
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    failover_task_handle = asyncio.create_task(failover_monitor_task())
    
    # Start resilient monitoring if available
    if orchestrator.resilient_orchestrator:
        await orchestrator.resilient_orchestrator.start_monitoring()
        logger.info("Resilient monitoring started")

    # Armazenar referência do orquestrador no app
    app.state.orchestrator = orchestrator

    try:
        yield
    finally:
        # Shutdown
        logger.info("Encerrando orquestrador...")
        
        # Stop resilient monitoring
        if orchestrator.resilient_orchestrator:
            await orchestrator.resilient_orchestrator.stop_monitoring()
            logger.info("Resilient monitoring stopped")
        
        cleanup_task_handle.cancel()
        failover_task_handle.cancel()

        try:
            await cleanup_task_handle
        except asyncio.CancelledError:
            pass

        try:
            await failover_task_handle
        except asyncio.CancelledError:
            pass


# Aplicação FastAPI
app = FastAPI(
    title="Stream Orchestrator",
    description="Orquestrador central para distribuição de streams",
    version="1.0.0",
    lifespan=lifespan,
)


class StreamOrchestrator:
    """Classe principal do orquestrador de streams."""

    def __init__(self):
        self.db_config = DB_CONFIG
        self.active_instances: Dict[str, dict] = {}
        self.stream_assignments: Dict[int, str] = {}  # stream_id -> server_id
        
        # Initialize enhanced orchestrator for smart load balancing with graceful degradation
        self.enhanced_orchestrator = self._initialize_enhanced_orchestrator()
        
        # Initialize resilient orchestrator for enhanced failure handling with graceful degradation
        self.resilient_orchestrator = self._initialize_resilient_orchestrator()

    def _initialize_enhanced_orchestrator(self):
        """
        Initialize enhanced orchestrator with graceful degradation.
        
        Returns:
            EnhancedStreamOrchestrator instance or None if not available
            
        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        if not HAS_SMART_BALANCER:
            logger.info("Enhanced orchestrator not available - using basic load balancing")
            return None
            
        try:
            # Verify all required components are available
            if not all([EnhancedStreamOrchestrator, create_load_balance_config]):
                logger.warning("Enhanced orchestrator components missing - falling back to basic mode")
                return None
            
            # Create configuration from environment variables
            config = create_load_balance_config()
            enhanced_orch = EnhancedStreamOrchestrator(self.db_config, config)
            
            logger.info("Enhanced orchestrator initialized successfully - smart load balancing enabled")
            return enhanced_orch
            
        except Exception as e:
            logger.error(f"Failed to initialize enhanced orchestrator: {e}")
            logger.warning("Falling back to basic load balancing due to initialization failure")
            return None

    def _initialize_resilient_orchestrator(self):
        """
        Initialize resilient orchestrator with graceful degradation.
        
        Returns:
            ResilientOrchestrator instance or None if not available
            
        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        if not HAS_RESILIENT_ORCHESTRATOR:
            logger.info("Resilient orchestrator not available - using basic failure handling")
            return None
            
        try:
            # Verify all required components are available
            if not all([ResilientOrchestrator, HeartbeatConfig, FailureRecoveryConfig]):
                logger.warning("Resilient orchestrator components missing - falling back to basic mode")
                return None
            
            # Create heartbeat and recovery configurations from environment
            heartbeat_config = HeartbeatConfig(
                timeout_seconds=int(os.getenv("HEARTBEAT_TIMEOUT", 300)),
                warning_threshold_seconds=int(os.getenv("HEARTBEAT_WARNING_THRESHOLD", 120)),
                max_missed_heartbeats=int(os.getenv("MAX_MISSED_HEARTBEATS", 3)),
                check_interval_seconds=int(os.getenv("HEARTBEAT_CHECK_INTERVAL", 30)),
                emergency_threshold_seconds=int(os.getenv("EMERGENCY_THRESHOLD", 600))
            )
            
            recovery_config = FailureRecoveryConfig(
                max_retry_attempts=int(os.getenv("MAX_RETRY_ATTEMPTS", 3)),
                retry_delay_seconds=int(os.getenv("RETRY_DELAY_SECONDS", 5)),
                exponential_backoff=os.getenv("EXPONENTIAL_BACKOFF", "true").lower() == "true",
                circuit_breaker_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", 5)),
                circuit_breaker_timeout_seconds=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", 60)),
                emergency_recovery_enabled=os.getenv("EMERGENCY_RECOVERY_ENABLED", "true").lower() == "true"
            )
            
            resilient_orch = ResilientOrchestrator(
                self.db_config, heartbeat_config, recovery_config
            )
            
            logger.info("Resilient orchestrator initialized successfully - enhanced failure handling enabled")
            return resilient_orch
            
        except Exception as e:
            logger.error(f"Failed to initialize resilient orchestrator: {e}")
            logger.warning("Falling back to basic failure handling due to initialization failure")
            return None

    def get_optional_modules_status(self):
        """
        Get status information about optional modules.
        
        Returns:
            dict: Detailed status of all optional modules
            
        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        status = {
            "timestamp": datetime.now().isoformat(),
            "modules": {},
            "functionality": {
                "basic_orchestration": True,
                "smart_load_balancing": HAS_SMART_BALANCER and self.enhanced_orchestrator is not None,
                "enhanced_failure_handling": HAS_RESILIENT_ORCHESTRATOR and self.resilient_orchestrator is not None,
                "system_metrics": HAS_PSUTIL
            }
        }
        
        # Add detailed module information
        for module_name, module_info in OPTIONAL_MODULES.items():
            status["modules"][module_name] = {
                "available": module_info['available'],
                "error": module_info['error'],
                "initialized": False
            }
            
            # Check if module is actually initialized and working
            if module_name == "enhanced_orchestrator" and self.enhanced_orchestrator:
                status["modules"][module_name]["initialized"] = True
            elif module_name == "resilient_orchestrator" and self.resilient_orchestrator:
                status["modules"][module_name]["initialized"] = True
            elif module_name == "psutil" and module_info['available']:
                status["modules"][module_name]["initialized"] = True
        
        return status

    def get_db_connection(self):
        """Obtém conexão com o banco de dados com tratamento robusto de erros."""
        # Use resilient orchestrator connection if available
        if self.resilient_orchestrator:
            try:
                return self.resilient_orchestrator.get_db_connection()
            except Exception as e:
                logger.warning(f"Resilient connection failed, falling back to basic: {e}")
        
        # Fallback to basic connection with retry logic
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                conn = psycopg2.connect(**self.db_config)
                conn.autocommit = True
                return conn
            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to database after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error connecting to database: {e}")
                raise

    def create_tables(self):
        """Cria as tabelas necessárias para o orquestrador."""
        # First verify database connectivity using the new setup function
        if not setup_database(self.db_config):
            logger.error("Database setup verification failed")
            return False
            
        conn = None
        cursor = None
        
        try:
            # Get database connection with proper error handling
            try:
                conn = self.get_db_connection()
            except Exception as conn_error:
                logger.error(f"Falha ao conectar ao banco de dados: {conn_error}")
                return False
            
            # Initialize cursor with proper error handling
            try:
                cursor = conn.cursor()
            except Exception as cursor_error:
                logger.error(f"Falha ao criar cursor: {cursor_error}")
                return False

            # Tabela de instâncias registradas
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_instances (
                    id SERIAL PRIMARY KEY,
                    server_id VARCHAR(50) UNIQUE NOT NULL,
                    ip VARCHAR(45) NOT NULL,
                    port INTEGER NOT NULL,
                    max_streams INTEGER DEFAULT 20,
                    current_streams INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'active',
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Criar índices para a tabela de instâncias
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_server_id ON orchestrator_instances(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_status ON orchestrator_instances(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_heartbeat ON orchestrator_instances(last_heartbeat)"
            )

            # Tabela de atribuições de streams
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_stream_assignments (
                    id SERIAL PRIMARY KEY,
                    stream_id INTEGER NOT NULL,
                    server_id VARCHAR(50) NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active',
                    UNIQUE(stream_id)
                )
            """
            )

            # Criar índices para a tabela de atribuições
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_server_id ON orchestrator_stream_assignments(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_stream_id ON orchestrator_stream_assignments(stream_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_status ON orchestrator_stream_assignments(status)"
            )

            # Tabela de métricas de sistema das instâncias
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_instance_metrics (
                    id SERIAL PRIMARY KEY,
                    server_id VARCHAR(50) NOT NULL,
                    cpu_percent FLOAT,
                    memory_percent FLOAT,
                    memory_used_gb FLOAT,
                    memory_total_gb FLOAT,
                    disk_percent FLOAT,
                    disk_free_gb FLOAT,
                    disk_total_gb FLOAT,
                    load_average_1m FLOAT,
                    load_average_5m FLOAT,
                    load_average_15m FLOAT,
                    uptime_seconds FLOAT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (server_id) REFERENCES orchestrator_instances(server_id) ON DELETE CASCADE
                )
            """
            )

            # Criar índices para a tabela de métricas
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_server_id ON orchestrator_instance_metrics(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_recorded_at ON orchestrator_instance_metrics(recorded_at)"
            )

            # Tabela de histórico de rebalanceamentos
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_rebalance_history (
                    id SERIAL PRIMARY KEY,
                    rebalance_type VARCHAR(50) NOT NULL,
                    streams_moved INTEGER DEFAULT 0,
                    instances_affected INTEGER DEFAULT 0,
                    reason TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()
            logger.info("Tabelas do orquestrador criadas com sucesso")
            return True

        except psycopg2.DatabaseError as db_error:
            logger.error(f"Erro de banco de dados ao criar tabelas: {db_error}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            return False
        except psycopg2.OperationalError as op_error:
            logger.error(f"Erro operacional do banco ao criar tabelas: {op_error}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao criar tabelas: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            return False
        finally:
            # Safe resource cleanup - only close if initialized and not None
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as cursor_error:
                    logger.error(f"Erro ao fechar cursor: {cursor_error}")
            if conn is not None:
                try:
                    conn.close()
                except Exception as conn_error:
                    logger.error(f"Erro ao fechar conexão: {conn_error}")

    def get_available_streams(self) -> List[int]:
        """Obtém lista de streams disponíveis do banco de dados."""
        conn = None
        cursor = None
        
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Buscar todos os streams disponíveis
            cursor.execute(
                """
                SELECT DISTINCT id 
                FROM streams 
                ORDER BY id
            """
            )

            all_streams = [row[0] for row in cursor.fetchall()]

            # Buscar streams já atribuídos
            cursor.execute(
                """
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE status = 'active'
            """
            )

            assigned_streams = set(row[0] for row in cursor.fetchall())

            # Retornar streams não atribuídos
            available_streams = [s for s in all_streams if s not in assigned_streams]

            logger.info(
                f"Streams disponíveis: {len(available_streams)}, Total: {len(all_streams)}"
            )
            return available_streams

        except Exception as e:
            logger.error(f"Erro ao buscar streams disponíveis: {e}")
            return []
        finally:
            # Safe resource cleanup
            if cursor:
                try:
                    cursor.close()
                except Exception as cursor_error:
                    logger.error(f"Erro ao fechar cursor: {cursor_error}")
            if conn:
                try:
                    conn.close()
                except Exception as conn_error:
                    logger.error(f"Erro ao fechar conexão: {conn_error}")

    def register_instance(self, registration: InstanceRegistration) -> dict:
        """Registra uma nova instância no orquestrador."""
        conn = None
        cursor = None
        
        try:
            # Get database connection with proper error handling
            try:
                conn = self.get_db_connection()
            except Exception as conn_error:
                logger.error(f"Falha ao conectar ao banco de dados para registrar instância {registration.server_id}: {conn_error}")
                raise HTTPException(
                    status_code=500, detail=f"Erro de conexão com banco de dados: {conn_error}"
                )
            
            # Initialize cursor with proper error handling
            try:
                cursor = conn.cursor()
            except Exception as cursor_error:
                logger.error(f"Falha ao criar cursor para registrar instância {registration.server_id}: {cursor_error}")
                raise HTTPException(
                    status_code=500, detail=f"Erro ao criar cursor: {cursor_error}"
                )
            # Verificar se é uma re-registração (instância já existe)
            cursor.execute(
                """
                SELECT server_id, current_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s
            """,
                (registration.server_id,),
            )

            existing_instance = cursor.fetchone()
            is_reregistration = existing_instance is not None

            # Inserir ou atualizar instância
            cursor.execute(
                """
                INSERT INTO orchestrator_instances 
                (server_id, ip, port, max_streams, current_streams, status, last_heartbeat)
                VALUES (%s, %s, %s, %s, 0, 'active', CURRENT_TIMESTAMP)
                ON CONFLICT (server_id) 
                DO UPDATE SET 
                    ip = EXCLUDED.ip,
                    port = EXCLUDED.port,
                    max_streams = EXCLUDED.max_streams,
                    current_streams = 0,
                    status = 'active',
                    last_heartbeat = CURRENT_TIMESTAMP
                RETURNING id
            """,
                (
                    registration.server_id,
                    registration.ip,
                    registration.port,
                    registration.max_streams,
                ),
            )

            instance_id = cursor.fetchone()[0]

            # Se é uma re-registração, liberar streams órfãos imediatamente
            if is_reregistration:
                logger.info(
                    f"Re-registração detectada para instância {registration.server_id}, liberando streams órfãos"
                )

                # Liberar todos os streams atribuídos à instância anterior
                cursor.execute(
                    """
                    DELETE FROM orchestrator_stream_assignments 
                    WHERE server_id = %s
                """,
                    (registration.server_id,),
                )

                released_count = cursor.rowcount
                if released_count > 0:
                    logger.info(
                        f"Liberados {released_count} streams órfãos da instância {registration.server_id}"
                    )

                    # Forçar reatribuição imediata dos streams liberados
                    try:
                        self._immediate_stream_rebalance(cursor, registration.server_id)
                    except Exception as e:
                        logger.warning(f"Erro na reatribuição imediata de streams: {e}")

            # Commit das alterações
            conn.commit()

            # Atualizar cache local
            self.active_instances[registration.server_id] = {
                "id": instance_id,
                "ip": registration.ip,
                "port": registration.port,
                "max_streams": registration.max_streams,
                "current_streams": 0,
                "status": "active",
                "last_heartbeat": datetime.now(),
            }

            # Verificar se deve fazer rebalanceamento automático
            should_rebalance = False

            if not is_reregistration:
                # Nova instância - verificar se há necessidade de rebalanceamento
                cursor.execute(
                    """
                    SELECT COUNT(*) as total_instances,
                           SUM(max_streams) as total_capacity,
                           (
                               SELECT COUNT(*) 
                               FROM orchestrator_stream_assignments 
                               WHERE status = 'active'
                           ) as total_assigned_streams
                    FROM orchestrator_instances 
                    WHERE status = 'active' 
                      AND last_heartbeat > NOW() - INTERVAL '1 minute'
                """
                )

                stats = cursor.fetchone()
                total_instances = stats[0]
                total_capacity = stats[1] or 0
                total_assigned_streams = stats[2] or 0

                # Rebalancear se:
                # 1. Há mais de uma instância ativa
                # 2. Há streams atribuídos
                # 3. A nova capacidade permite melhor distribuição
                if total_instances > 1 and total_assigned_streams > 0:
                    # Calcular se o rebalanceamento seria benéfico
                    # (diferença significativa na distribuição atual)
                    cursor.execute(
                        """
                        SELECT 
                            server_id,
                            current_streams,
                            max_streams
                        FROM orchestrator_instances 
                        WHERE status = 'active' 
                          AND last_heartbeat > NOW() - INTERVAL '1 minute'
                          AND server_id != %s
                        ORDER BY current_streams DESC
                    """,
                        (registration.server_id,),
                    )

                    other_instances = cursor.fetchall()

                    if other_instances:
                        max_load = max(inst[1] for inst in other_instances)
                        avg_load = total_assigned_streams / total_instances

                        # Rebalancear se a diferença for significativa (> 20% da média)
                        if max_load > avg_load * 1.2:
                            should_rebalance = True
                            logger.info(
                                f"Rebalanceamento automático ativado: carga máxima {max_load} > 20% da média {avg_load:.1f}"
                            )

            if is_reregistration:
                logger.info(
                    f"Instância {registration.server_id} re-registrada com sucesso (streams órfãos liberados)"
                )
            else:
                logger.info(
                    f"Instância {registration.server_id} registrada com sucesso"
                )

                # Executar rebalanceamento automático se necessário
                if should_rebalance:
                    try:
                        logger.info(
                            f"Iniciando rebalanceamento automático devido ao registro da nova instância {registration.server_id}"
                        )

                        # Fechar conexão atual antes do rebalanceamento
                        cursor.close()
                        conn.close()

                        # Executar rebalanceamento completo
                        self.rebalance_all_streams()

                        # Registrar histórico do rebalanceamento
                        conn = self.get_db_connection()
                        cursor = conn.cursor()

                        cursor.execute(
                            """
                            INSERT INTO orchestrator_rebalance_history 
                            (rebalance_type, reason, executed_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                        """,
                            (
                                "automatic",
                                f"Nova instância registrada: {registration.server_id}",
                            ),
                        )

                        conn.commit()

                        logger.info(
                            f"Rebalanceamento automático concluído para nova instância {registration.server_id}"
                        )

                    except Exception as e:
                        logger.error(f"Erro no rebalanceamento automático: {e}")
                        # Continuar mesmo se o rebalanceamento falhar

            return {
                "status": "registered",
                "server_id": registration.server_id,
                "max_streams": registration.max_streams,
                "reregistration": is_reregistration,
                "auto_rebalanced": should_rebalance,
            }

        except psycopg2.DatabaseError as db_error:
            logger.error(f"Erro de banco de dados ao registrar instância {registration.server_id}: {db_error}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro de banco de dados: {db_error}"
            )
        except psycopg2.OperationalError as op_error:
            logger.error(f"Erro operacional do banco ao registrar instância {registration.server_id}: {op_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro operacional do banco: {op_error}"
            )
        except HTTPException:
            # Re-raise HTTP exceptions without modification
            raise
        except Exception as e:
            logger.error(f"Erro inesperado ao registrar instância {registration.server_id}: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro inesperado ao registrar instância: {e}"
            )
        finally:
            # Safe resource cleanup - only close if initialized and not None
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as cursor_error:
                    logger.error(f"Erro ao fechar cursor: {cursor_error}")
            if conn is not None:
                try:
                    conn.close()
                except Exception as conn_error:
                    logger.error(f"Erro ao fechar conexão: {conn_error}")

    def update_heartbeat(self, heartbeat: HeartbeatRequest) -> dict:
        """Atualiza o heartbeat de uma instância."""
        conn = None
        cursor = None
        
        try:
            # Get database connection with proper error handling
            try:
                conn = self.get_db_connection()
            except Exception as conn_error:
                logger.error(f"Falha ao conectar ao banco de dados para heartbeat de {heartbeat.server_id}: {conn_error}")
                raise HTTPException(
                    status_code=500, detail=f"Erro de conexão com banco de dados: {conn_error}"
                )
            
            # Initialize cursor with proper error handling
            try:
                cursor = conn.cursor()
            except Exception as cursor_error:
                logger.error(f"Falha ao criar cursor para heartbeat de {heartbeat.server_id}: {cursor_error}")
                raise HTTPException(
                    status_code=500, detail=f"Erro ao criar cursor: {cursor_error}"
                )

            # Update heartbeat in resilient orchestrator if available
            if self.resilient_orchestrator:
                self.resilient_orchestrator.instance_heartbeats[heartbeat.server_id] = datetime.now()
                
                # If instance was previously failed, attempt recovery
                if heartbeat.server_id in self.resilient_orchestrator.failed_instances:
                    logger.info(f"Received heartbeat from previously failed instance {heartbeat.server_id}")
                    # The resilient orchestrator will handle recovery in its monitoring loop
            
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET last_heartbeat = CURRENT_TIMESTAMP,
                    current_streams = %s,
                    status = %s
                WHERE server_id = %s
                RETURNING id
            """,
                (heartbeat.current_streams, heartbeat.status, heartbeat.server_id),
            )

            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Instância não encontrada")

            instance_id = result[0]

            # Armazenar métricas de sistema se fornecidas
            if heartbeat.system_metrics:
                metrics = heartbeat.system_metrics
                
                # Extrair valores de load average da lista
                load_avg_1m = load_avg_5m = load_avg_15m = None
                if metrics.load_average and len(metrics.load_average) >= 3:
                    load_avg_1m = metrics.load_average[0]
                    load_avg_5m = metrics.load_average[1]
                    load_avg_15m = metrics.load_average[2]
                
                cursor.execute(
                    """
                    INSERT INTO orchestrator_instance_metrics 
                    (server_id, cpu_percent, memory_percent, memory_used_gb,
                     memory_total_gb, disk_percent, disk_free_gb, disk_total_gb,
                     load_average_1m, load_average_5m, load_average_15m, 
                     uptime_seconds, recorded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                    (
                        heartbeat.server_id,
                        metrics.cpu_percent,
                        metrics.memory_percent,
                        metrics.memory_used_gb,
                        metrics.memory_total_gb,
                        metrics.disk_percent,
                        metrics.disk_free_gb,
                        metrics.disk_total_gb,
                        load_avg_1m,
                        load_avg_5m,
                        load_avg_15m,
                        metrics.uptime_seconds,
                    ),
                )
                logger.debug(f"Métricas de sistema armazenadas para {heartbeat.server_id}")

            conn.commit()

            # Atualizar cache local
            if heartbeat.server_id in self.active_instances:
                self.active_instances[heartbeat.server_id].update(
                    {
                        "current_streams": heartbeat.current_streams,
                        "status": heartbeat.status,
                        "last_heartbeat": datetime.now(),
                    }
                )

            return {"status": "heartbeat_updated"}

        except psycopg2.DatabaseError as db_error:
            logger.error(f"Erro de banco de dados ao atualizar heartbeat de {heartbeat.server_id}: {db_error}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro de banco de dados: {db_error}"
            )
        except psycopg2.OperationalError as op_error:
            logger.error(f"Erro operacional do banco ao atualizar heartbeat de {heartbeat.server_id}: {op_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro operacional do banco: {op_error}"
            )
        except HTTPException:
            # Re-raise HTTP exceptions without modification
            raise
        except Exception as e:
            logger.error(f"Erro inesperado ao atualizar heartbeat de {heartbeat.server_id}: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Erro ao fazer rollback: {rollback_error}")
            raise HTTPException(
                status_code=500, detail=f"Erro inesperado ao atualizar heartbeat: {e}"
            )
        finally:
            # Safe resource cleanup - only close if initialized and not None
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as cursor_error:
                    logger.error(f"Erro ao fechar cursor: {cursor_error}")
            if conn is not None:
                try:
                    conn.close()
                except Exception as conn_error:
                    logger.error(f"Erro ao fechar conexão: {conn_error}")

    def assign_streams(self, request: StreamRequest) -> dict:
        """Atribui streams para uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Verificar se instância existe e está ativa
            cursor.execute(
                """
                SELECT current_streams, max_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
            """,
                (request.server_id,),
            )

            instance_data = cursor.fetchone()
            if not instance_data:
                raise HTTPException(
                    status_code=404, detail="Instância não encontrada ou inativa"
                )

            current_streams, max_streams = instance_data
            available_slots = max_streams - current_streams

            if available_slots <= 0:
                return {
                    "status": "no_capacity",
                    "assigned_streams": [],
                    "message": "Instância já está na capacidade máxima",
                }

            # Buscar streams disponíveis
            available_streams = self.get_available_streams()
            streams_to_assign = min(
                available_slots, request.requested_count, len(available_streams)
            )

            if streams_to_assign == 0:
                return {
                    "status": "no_streams",
                    "assigned_streams": [],
                    "message": "Nenhum stream disponível para atribuição",
                }

            # Atribuir streams
            assigned_streams = available_streams[:streams_to_assign]

            for stream_id in assigned_streams:
                cursor.execute(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, status)
                    VALUES (%s, %s, 'active')
                """,
                    (stream_id, request.server_id),
                )

            # Atualizar contador de streams da instância
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = current_streams + %s
                WHERE server_id = %s
            """,
                (len(assigned_streams), request.server_id),
            )

            # Commit da transação
            conn.commit()

            logger.info(
                f"Atribuídos {len(assigned_streams)} streams para {request.server_id}"
            )

            return {
                "status": "assigned",
                "assigned_streams": assigned_streams,
                "count": len(assigned_streams),
            }

        except Exception as e:
            logger.error(f"Erro ao atribuir streams para {request.server_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Erro ao atribuir streams: {e}"
            )
        finally:
            cursor.close()
            conn.close()

    def release_streams(self, release: StreamRelease) -> dict:
        """Libera streams de uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            if not release.stream_ids:
                return {"status": "no_streams_to_release"}

            # Remover atribuições
            cursor.execute(
                """
                DELETE FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND stream_id = ANY(%s)
                RETURNING stream_id
            """,
                (release.server_id, release.stream_ids),
            )

            released_streams = [row[0] for row in cursor.fetchall()]

            # Atualizar contador de streams da instância
            if released_streams:
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET current_streams = GREATEST(0, current_streams - %s)
                    WHERE server_id = %s
                """,
                    (len(released_streams), release.server_id),
                )

            # Commit da transação
            conn.commit()

            logger.info(
                f"Liberados {len(released_streams)} streams de {release.server_id}"
            )

            return {
                "status": "released",
                "released_streams": released_streams,
                "count": len(released_streams),
            }

        except Exception as e:
            logger.error(f"Erro ao liberar streams de {release.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao liberar streams: {e}")
        finally:
            cursor.close()
            conn.close()

    def _immediate_stream_rebalance(self, cursor, reregistered_server_id: str):
        """Força reatribuição imediata de streams para instância re-registrada."""
        # Buscar streams não atribuídos
        cursor.execute(
            """
            SELECT id FROM streams 
            WHERE id NOT IN (
                SELECT stream_id FROM orchestrator_stream_assignments WHERE status = 'active'
            )
            LIMIT 50
        """
        )

        available_streams = cursor.fetchall()

        if available_streams:
            # Buscar capacidade da instância re-registrada
            cursor.execute(
                """
                SELECT max_streams, current_streams
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
            """,
                (reregistered_server_id,),
            )

            instance_info = cursor.fetchone()

            if instance_info:
                max_streams, current_streams = instance_info
                available_capacity = max_streams - current_streams
                streams_to_assign = min(len(available_streams), available_capacity)

                if streams_to_assign > 0:
                    assigned_count = 0
                    for i, (stream_id,) in enumerate(
                        available_streams[:streams_to_assign]
                    ):
                        cursor.execute(
                            """
                            INSERT INTO orchestrator_stream_assignments (stream_id, server_id, assigned_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                        """,
                            (stream_id, reregistered_server_id),
                        )
                        assigned_count += 1

                    # Atualizar contador da instância
                    cursor.execute(
                        """
                        UPDATE orchestrator_instances 
                        SET current_streams = current_streams + %s
                        WHERE server_id = %s
                    """,
                        (assigned_count, reregistered_server_id),
                    )

                    logger.info(
                        f"Reatribuídos {assigned_count} streams imediatamente para instância re-registrada {reregistered_server_id}"
                    )

    def handle_orphaned_streams(self):
        """Detecta e reatribui streams órfãos automaticamente de forma mais agressiva."""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Encontrar streams órfãos (atribuídos a instâncias inativas)
            cursor.execute(
                """
                SELECT DISTINCT osa.stream_id 
                FROM orchestrator_stream_assignments osa
                JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
                WHERE oi.status = 'inactive' 
                   OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes'
            """
            )

            orphaned_streams = [row["stream_id"] for row in cursor.fetchall()]

            if orphaned_streams:
                logger.warning(
                    f"Detectados {len(orphaned_streams)} streams órfãos: {orphaned_streams}"
                )

                # Liberar streams órfãos
                cursor.execute(
                    """
                    DELETE FROM orchestrator_stream_assignments osa
                    USING orchestrator_instances oi
                    WHERE osa.server_id = oi.server_id
                    AND (oi.status = 'inactive' OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes')
                """
                )

                # Atualizar contadores das instâncias que perderam streams
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET current_streams = (
                        SELECT COUNT(*) 
                        FROM orchestrator_stream_assignments 
                        WHERE server_id = orchestrator_instances.server_id
                    )
                    WHERE server_id IN (
                        SELECT DISTINCT oi.server_id 
                        FROM orchestrator_instances oi
                        WHERE oi.status = 'inactive' 
                           OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes'
                    )
                """
                )

                # Reatribuir todos os streams órfãos de uma vez usando distribuição otimizada
                if orphaned_streams:
                    self._redistribute_orphaned_streams_optimized(
                        cursor, orphaned_streams
                    )

                logger.info(
                    f"Failover automático concluído para {len(orphaned_streams)} streams"
                )

        except Exception as e:
            logger.error(f"Erro no failover automático: {e}")
        finally:
            cursor.close()
            conn.close()

    def _redistribute_orphaned_streams_optimized(self, cursor, orphaned_streams: list):
        """Redistribui streams órfãos de forma otimizada para balanceamento de carga."""
        try:
            # Buscar todas as instâncias ativas com suas capacidades e cargas atuais
            cursor.execute(
                """
                SELECT 
                    oi.server_id,
                    oi.max_streams,
                    COALESCE(COUNT(osa.stream_id), 0) as current_load,
                    (oi.max_streams - COALESCE(COUNT(osa.stream_id), 0)) as available_capacity
                FROM orchestrator_instances oi
                LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id
                WHERE oi.status = 'active' 
                  AND oi.last_heartbeat > NOW() - INTERVAL '1 minute'
                GROUP BY oi.server_id, oi.max_streams
                HAVING (oi.max_streams - COALESCE(COUNT(osa.stream_id), 0)) > 0
                ORDER BY current_load ASC, available_capacity DESC
            """
            )

            available_instances = cursor.fetchall()

            if not available_instances:
                logger.error(
                    "Nenhuma instância ativa com capacidade disponível para reatribuir streams órfãos"
                )
                return

            # Distribuir streams órfãos de forma balanceada
            assignments = []
            instance_index = 0

            for stream_id in orphaned_streams:
                # Encontrar a próxima instância com capacidade disponível
                attempts = 0
                while attempts < len(available_instances):
                    instance = available_instances[instance_index]

                    if instance["available_capacity"] > 0:
                        assignments.append((stream_id, instance["server_id"]))
                        # Reduzir capacidade disponível temporariamente para balanceamento
                        available_instances[instance_index] = {
                            **instance,
                            "available_capacity": instance["available_capacity"] - 1,
                            "current_load": instance["current_load"] + 1,
                        }
                        break

                    instance_index = (instance_index + 1) % len(available_instances)
                    attempts += 1

                if attempts >= len(available_instances):
                    logger.warning(
                        f"Não foi possível encontrar capacidade para stream {stream_id}"
                    )
                    break

                # Avançar para próxima instância para distribuição round-robin
                instance_index = (instance_index + 1) % len(available_instances)

            # Executar todas as atribuições em lote
            if assignments:
                cursor.executemany(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, assigned_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                """,
                    assignments,
                )

                # Atualizar contadores das instâncias
                for stream_id, server_id in assignments:
                    cursor.execute(
                        """
                        UPDATE orchestrator_instances 
                        SET current_streams = current_streams + 1
                        WHERE server_id = %s
                    """,
                        (server_id,),
                    )

                logger.info(
                    f"Reatribuídos {len(assignments)} streams órfãos para {len(set(a[1] for a in assignments))} instâncias"
                )

                # Log detalhado das atribuições
                for stream_id, server_id in assignments:
                    logger.debug(
                        f"Stream órfão {stream_id} reatribuído para instância {server_id}"
                    )

        except Exception as e:
            logger.error(f"Erro na redistribuição otimizada de streams órfãos: {e}")
            raise

    def rebalance_all_streams(self):
        """Rebalanceia todos os streams de forma igualitária entre todas as instâncias ativas."""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Buscar todas as instâncias ativas com suas cargas atuais
            cursor.execute(
                """
                SELECT 
                    oi.server_id, 
                    oi.max_streams,
                    COALESCE(COUNT(osa.stream_id), 0) as current_streams
                FROM orchestrator_instances oi
                LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id AND osa.status = 'active'
                WHERE oi.status = 'active' 
                  AND oi.last_heartbeat > NOW() - INTERVAL '1 minute'
                GROUP BY oi.server_id, oi.max_streams
                ORDER BY oi.server_id
            """
            )

            active_instances = cursor.fetchall()

            if not active_instances:
                logger.warning(
                    "Nenhuma instância ativa encontrada para rebalanceamento"
                )
                return

            # Calcular estatísticas atuais
            total_capacity = sum(instance["max_streams"] for instance in active_instances)
            total_streams = sum(instance["current_streams"] for instance in active_instances)
            
            if total_streams == 0:
                logger.info("Nenhum stream atribuído encontrado")
                return

            if total_streams > total_capacity:
                logger.error(
                    f"Número de streams ({total_streams}) excede capacidade total ({total_capacity})"
                )
                return

            # Calcular distribuição ideal baseada na capacidade proporcional
            target_distribution = {}
            remaining_streams = total_streams
            
            # Primeira passada: distribuição proporcional
            for instance in active_instances:
                server_id = instance["server_id"]
                max_streams = instance["max_streams"]
                
                # Calcular proporção baseada na capacidade
                proportion = max_streams / total_capacity
                ideal_count = int(total_streams * proportion)
                
                # Garantir que não exceda a capacidade da instância
                target_count = min(ideal_count, max_streams, remaining_streams)
                target_distribution[server_id] = target_count
                remaining_streams -= target_count
            
            # Segunda passada: distribuir streams restantes
            if remaining_streams > 0:
                # Ordenar instâncias por capacidade disponível
                available_instances = [
                    (server_id, instance["max_streams"] - target_distribution[server_id])
                    for instance in active_instances
                    for server_id in [instance["server_id"]]
                    if target_distribution[server_id] < instance["max_streams"]
                ]
                available_instances.sort(key=lambda x: x[1], reverse=True)
                
                for server_id, available_capacity in available_instances:
                    if remaining_streams <= 0:
                        break
                    
                    additional = min(remaining_streams, available_capacity)
                    target_distribution[server_id] += additional
                    remaining_streams -= additional

            logger.info(f"Distribuição alvo calculada: {target_distribution}")
            
            # Verificar se rebalanceamento é necessário
            current_distribution = {instance["server_id"]: instance["current_streams"] for instance in active_instances}
            
            # Calcular diferença
            needs_rebalancing = False
            for server_id in target_distribution:
                current = current_distribution.get(server_id, 0)
                target = target_distribution[server_id]
                if abs(current - target) > 1:  # Tolerância de 1 stream
                    needs_rebalancing = True
                    break
            
            if not needs_rebalancing:
                logger.info("Sistema já está balanceado, rebalanceamento desnecessário")
                return

            # Buscar todos os streams atribuídos
            cursor.execute(
                """
                SELECT stream_id, server_id
                FROM orchestrator_stream_assignments
                WHERE status = 'active'
                ORDER BY assigned_at ASC
            """
            )

            current_assignments = cursor.fetchall()
            
            # Implementar rebalanceamento incremental
            # 1. Identificar instâncias que precisam liberar streams
            streams_to_move = []
            
            for instance in active_instances:
                server_id = instance["server_id"]
                current = current_distribution[server_id]
                target = target_distribution[server_id]
                
                if current > target:
                    # Esta instância precisa liberar streams
                    excess = current - target
                    
                    # Buscar streams desta instância para mover
                    instance_streams = [
                        assignment["stream_id"] for assignment in current_assignments
                        if assignment["server_id"] == server_id
                    ][:excess]
                    
                    streams_to_move.extend(instance_streams)
            
            # 2. Reatribuir streams para instâncias que precisam de mais
            if streams_to_move:
                # Primeiro, liberar os streams que serão movidos
                cursor.execute(
                    "DELETE FROM orchestrator_stream_assignments WHERE stream_id = ANY(%s)",
                    (streams_to_move,)
                )
                
                # Redistribuir para instâncias que precisam
                new_assignments = []
                stream_index = 0
                
                for instance in active_instances:
                    server_id = instance["server_id"]
                    current = current_distribution[server_id]
                    target = target_distribution[server_id]
                    
                    if current < target:
                        # Esta instância precisa receber streams
                        needed = target - current
                        
                        for _ in range(needed):
                            if stream_index < len(streams_to_move):
                                stream_id = streams_to_move[stream_index]
                                new_assignments.append((stream_id, server_id))
                                stream_index += 1
                
                # Executar novas atribuições
                if new_assignments:
                    cursor.executemany(
                        """
                        INSERT INTO orchestrator_stream_assignments 
                        (stream_id, server_id, assigned_at, status)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
                    """,
                        new_assignments,
                    )
                    
                    logger.info(f"Movidos {len(new_assignments)} streams durante rebalanceamento")

            # Atualizar contadores das instâncias
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = (
                    SELECT COUNT(*) 
                    FROM orchestrator_stream_assignments 
                    WHERE server_id = orchestrator_instances.server_id 
                      AND status = 'active'
                )
                WHERE status = 'active'
            """
            )
            
            conn.commit()

            # Log da nova distribuição
            cursor.execute(
                """
                SELECT 
                    oi.server_id,
                    oi.current_streams,
                    oi.max_streams
                FROM orchestrator_instances oi
                WHERE oi.status = 'active'
                ORDER BY oi.server_id
            """
            )

            final_distribution = cursor.fetchall()
            logger.info(f"Rebalanceamento concluído. Nova distribuição:")
            for dist in final_distribution:
                logger.info(
                    f"  {dist['server_id']}: {dist['current_streams']}/{dist['max_streams']} streams"
                )

        except Exception as e:
            logger.error(f"Erro no rebalanceamento completo: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    async def cleanup_inactive_instances(self):
        """Remove instâncias inativas e reatribui seus streams."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Primeiro, executar failover automático
            self.handle_orphaned_streams()

            # Buscar instâncias inativas
            timeout_threshold = datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT)

            cursor.execute(
                """
                SELECT server_id, current_streams
                FROM orchestrator_instances 
                WHERE last_heartbeat < %s AND status = 'active'
            """,
                (timeout_threshold,),
            )

            inactive_instances = cursor.fetchall()

            for server_id, current_streams in inactive_instances:
                logger.warning(
                    f"Instância {server_id} inativa, liberando {current_streams} streams"
                )

                # Marcar instância como inativa
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET status = 'inactive', current_streams = 0
                    WHERE server_id = %s
                """,
                    (server_id,),
                )

                # Remover do cache local
                if server_id in self.active_instances:
                    del self.active_instances[server_id]

                logger.info(f"Instância {server_id} marcada como inativa")

            if inactive_instances:
                logger.info(
                    f"Limpeza concluída: {len(inactive_instances)} instâncias inativas removidas"
                )

        except Exception as e:
            logger.error(f"Erro durante limpeza de instâncias inativas: {e}")
        finally:
            cursor.close()
            conn.close()

    def get_orchestrator_status(self) -> dict:
        """Retorna status atual do orquestrador."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Estatísticas de instâncias
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_instances,
                    COUNT(*) FILTER (WHERE status = 'active') as active_instances,
                    COALESCE(SUM(current_streams), 0) as total_assigned_streams,
                    COALESCE(SUM(max_streams), 0) as total_capacity
                FROM orchestrator_instances
            """
            )

            instance_stats = cursor.fetchone()

            # Estatísticas de streams
            cursor.execute(
                """
                SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE status = 'active'
            """
            )

            assigned_streams = cursor.fetchone()[0]

            # Streams disponíveis
            available_streams = len(self.get_available_streams())

            return {
                "orchestrator_status": "active",
                "instances": {
                    "total": instance_stats[0],
                    "active": instance_stats[1],
                    "total_capacity": instance_stats[3],
                    "current_load": instance_stats[2],
                },
                "streams": {
                    "assigned": assigned_streams,
                    "available": available_streams,
                    "total": assigned_streams + available_streams,
                },
                "load_percentage": round(
                    (instance_stats[2] / max(instance_stats[3], 1)) * 100, 2
                ),
            }

        except Exception as e:
            logger.error(f"Erro ao obter status do orquestrador: {e}")
            return {"orchestrator_status": "error", "error": str(e)}
        finally:
            cursor.close()
            conn.close()

    def smart_rebalance(self, reason: str = "manual") -> dict:
        """
        Perform intelligent rebalancing using smart load balancer.
        
        Args:
            reason: Reason for rebalancing (manual, new_instance, instance_failure, etc.)
            
        Returns:
            Dictionary with rebalancing results
        """
        if not self.enhanced_orchestrator:
            logger.warning("Smart load balancer not available, falling back to basic rebalancing")
            try:
                self.rebalance_all_streams()
                return {
                    "status": "completed",
                    "method": "basic",
                    "message": "Basic rebalancing completed successfully"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "method": "basic",
                    "error": str(e)
                }
        
        try:
            # Map string reason to enum
            reason_mapping = {
                "manual": RebalanceReason.MANUAL,
                "new_instance": RebalanceReason.NEW_INSTANCE,
                "instance_failure": RebalanceReason.INSTANCE_FAILURE,
                "load_imbalance": RebalanceReason.LOAD_IMBALANCE,
                "performance_degradation": RebalanceReason.PERFORMANCE_DEGRADATION
            }
            
            rebalance_reason = reason_mapping.get(reason, RebalanceReason.MANUAL)
            
            # Execute smart rebalancing
            result = self.enhanced_orchestrator.intelligent_rebalance(rebalance_reason)
            
            return {
                "status": "completed" if result.success else "error",
                "method": "smart",
                "reason": result.reason.value,
                "streams_moved": result.streams_moved,
                "instances_affected": result.instances_affected,
                "execution_time_ms": result.execution_time_ms,
                "migrations": len(result.migrations),
                "error": result.error_message
            }
            
        except Exception as e:
            logger.error(f"Error in smart rebalancing: {e}")
            return {
                "status": "error",
                "method": "smart",
                "error": str(e)
            }

    def check_load_balance(self) -> dict:
        """
        Check current load balance status and detect imbalances.
        
        Returns:
            Dictionary with load balance analysis
        """
        if not self.enhanced_orchestrator:
            return {
                "status": "unavailable",
                "message": "Smart load balancer not available"
            }
        
        try:
            consistency_report = self.enhanced_orchestrator.verify_system_consistency()
            return {
                "status": "success",
                "consistent": consistency_report["consistent"],
                "needs_rebalancing": consistency_report.get("needs_rebalancing", False),
                "reason": consistency_report.get("reason", ""),
                "statistics": consistency_report.get("statistics", {}),
                "instances": consistency_report.get("instances", [])
            }
            
        except Exception as e:
            logger.error(f"Error checking load balance: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def handle_instance_failure_smart(self, server_id: str) -> dict:
        """
        Handle instance failure using smart load balancing.
        
        Args:
            server_id: ID of the failed server
            
        Returns:
            Dictionary with failure handling results
        """
        if not self.enhanced_orchestrator:
            logger.warning("Smart load balancer not available, using basic failure handling")
            try:
                self.handle_orphaned_streams()
                return {
                    "status": "completed",
                    "method": "basic",
                    "message": f"Basic failure handling completed for {server_id}"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "method": "basic",
                    "error": str(e)
                }
        
        try:
            result = self.enhanced_orchestrator.handle_instance_failure(server_id)
            
            return {
                "status": "completed" if result.success else "error",
                "method": "smart",
                "server_id": server_id,
                "streams_redistributed": result.streams_moved,
                "instances_affected": result.instances_affected,
                "execution_time_ms": result.execution_time_ms,
                "error": result.error_message
            }
            
        except Exception as e:
            logger.error(f"Error in smart failure handling: {e}")
            return {
                "status": "error",
                "method": "smart",
                "error": str(e)
            }

    def get_load_balancer_stats(self) -> dict:
        """Get load balancer statistics and performance metrics"""
        if not self.enhanced_orchestrator:
            return {
                "status": "unavailable",
                "message": "Smart load balancer not available"
            }
        
        try:
            stats = self.enhanced_orchestrator.get_load_balancer_statistics()
            return {
                "status": "success",
                "statistics": stats
            }
        except Exception as e:
            logger.error(f"Error getting load balancer stats: {e}")
            return {
                "status": "error",
                "error": str(e)
            }


# Instância global do orquestrador
orchestrator = StreamOrchestrator()

# Endpoints da API


@app.post("/register")
async def register_instance(registration: InstanceRegistration):
    """Registra uma nova instância."""
    return orchestrator.register_instance(registration)


@app.post("/heartbeat")
async def heartbeat(heartbeat_req: HeartbeatRequest):
    """Atualiza heartbeat de uma instância."""
    return orchestrator.update_heartbeat(heartbeat_req)


@app.post("/streams/assign")
async def assign_streams(request: StreamRequest):
    """Atribui streams para uma instância."""
    return orchestrator.assign_streams(request)


@app.post("/streams/release")
async def release_streams(release: StreamRelease):
    """Libera streams de uma instância."""
    return orchestrator.release_streams(release)


@app.get("/health")
async def health_check():
    """
    Enhanced health check endpoint with detailed service status.
    
    Provides comprehensive health information including:
    - PostgreSQL connectivity and operations
    - Redis connectivity and operations  
    - Application components status
    - Optional modules status
    - System metrics (if available)
    
    Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
    """
    try:
        # Get orchestrator instance from app state
        orchestrator = app.state.orchestrator
        
        # Perform comprehensive service verification
        service_status = verify_services(
            orchestrator.db_config,
            redis_host="localhost",
            redis_port=6379
        )
        
        # Get application component status
        app_components = _get_application_components_status(orchestrator)
        
        # Get system metrics if available
        system_metrics = _get_system_metrics()
        
        # Combine all status information
        health_data = {
            "status": "healthy" if service_status["overall_status"] == "ready" else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "services": service_status["services"],
            "application_components": app_components,
            "details": {
                "database_connected": service_status["services"].get("postgresql", {}).get("status") == "ready",
                "redis_connected": service_status["services"].get("redis", {}).get("status") == "ready",
                "all_services_ready": service_status["overall_status"] == "ready",
                "optional_modules_loaded": len([c for c in app_components.values() if c.get("status") == "available"]),
                "total_optional_modules": len(app_components)
            }
        }
        
        # Add system metrics if available
        if system_metrics:
            health_data["system_metrics"] = system_metrics
        
        # Add errors if any
        if service_status["errors"]:
            health_data["errors"] = service_status["errors"]
        
        # Determine HTTP status code based on service status
        if service_status["overall_status"] == "ready":
            return health_data
        else:
            # Return 503 Service Unavailable if any service is not ready
            raise HTTPException(
                status_code=503,
                detail=health_data
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Health check failed with unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "error_type": type(e).__name__,
                "details": {
                    "database_connected": False,
                    "redis_connected": False,
                    "all_services_ready": False
                },
                "suggestion": "Check service logs for detailed error information and ensure all required services are running"
            }
        )


@app.get("/modules/status")
async def get_modules_status():
    """
    Get status of optional modules and available functionality.
    
    Returns detailed information about which optional modules are loaded
    and what functionality is available.
    
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    try:
        # Get orchestrator instance from app state
        orchestrator = app.state.orchestrator
        
        # Get module status information
        module_status = orchestrator.get_optional_modules_status()
        
        return {
            "status": "success",
            "timestamp": module_status["timestamp"],
            "modules": module_status["modules"],
            "functionality": module_status["functionality"],
            "summary": {
                "total_modules": len(module_status["modules"]),
                "available_modules": sum(1 for m in module_status["modules"].values() if m["available"]),
                "initialized_modules": sum(1 for m in module_status["modules"].values() if m["initialized"]),
                "degraded_functionality": not all(module_status["functionality"].values())
            }
        }
        
    except Exception as e:
        logger.error(f"Module status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "message": "Failed to retrieve module status information"
            }
        )


@app.get("/ready")
async def readiness_check():
    """
    Startup readiness probe separate from liveness probe.
    
    This endpoint performs quick connectivity checks to determine if the application
    is ready to serve traffic. It uses shorter timeouts than the full health check
    to provide faster responses for container orchestration systems.
    
    Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
    """
    try:
        # Get orchestrator instance from app state
        orchestrator = app.state.orchestrator
        
        logger.info("Performing readiness check with quick connectivity tests")
        
        # Quick readiness check - just verify basic connectivity
        postgres_ready = wait_for_postgres(
            host=orchestrator.db_config["host"],
            port=orchestrator.db_config["port"],
            timeout=5  # Short timeout for readiness probe
        )
        
        redis_ready = wait_for_redis(
            host="localhost",
            port=6379,
            timeout=3  # Short timeout for readiness probe
        )
        
        # Check if orchestrator is properly initialized
        orchestrator_ready = hasattr(orchestrator, 'db_config') and orchestrator.db_config is not None
        
        readiness_data = {
            "status": "ready" if (postgres_ready and redis_ready and orchestrator_ready) else "not_ready",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "postgresql": "ready" if postgres_ready else "not_ready",
                "redis": "ready" if redis_ready else "not_ready",
                "orchestrator": "ready" if orchestrator_ready else "not_ready"
            },
            "details": {
                "check_type": "readiness_probe",
                "timeout_used": "short (3-5s per service)",
                "purpose": "Container orchestration readiness verification"
            }
        }
        
        if postgres_ready and redis_ready and orchestrator_ready:
            logger.info("Readiness check passed - all core services ready")
            return readiness_data
        else:
            logger.warning(f"Readiness check failed - Services status: PostgreSQL={postgres_ready}, Redis={redis_ready}, Orchestrator={orchestrator_ready}")
            raise HTTPException(
                status_code=503,
                detail=readiness_data
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Readiness check failed with unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "error_type": type(e).__name__,
                "details": {
                    "check_type": "readiness_probe",
                    "suggestion": "Check if PostgreSQL and Redis services are running and accessible"
                }
            }
        )


@app.get("/status")
async def get_status():
    """Retorna status do orquestrador."""
    return app.state.orchestrator.get_orchestrator_status()


@app.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check endpoint with comprehensive application status.
    
    Provides in-depth information about:
    - All service components and their detailed status
    - Application internal state and statistics
    - Performance metrics and resource usage
    - Configuration validation
    - Diagnostic information for troubleshooting
    
    Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
    """
    try:
        # Get orchestrator instance from app state
        orchestrator = app.state.orchestrator
        
        logger.info("Performing detailed health check with comprehensive diagnostics")
        
        # Get comprehensive service status
        service_status = verify_services(
            orchestrator.db_config,
            redis_host="localhost", 
            redis_port=6379
        )
        
        # Get application components status
        app_components = _get_application_components_status(orchestrator)
        
        # Get system metrics
        system_metrics = _get_system_metrics()
        
        # Get orchestrator internal status
        orchestrator_status = orchestrator.get_orchestrator_status()
        
        # Get configuration validation
        config_validation = _validate_configuration()
        
        # Compile detailed health report
        detailed_health = {
            "status": "healthy" if service_status["overall_status"] == "ready" else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "check_type": "detailed_health_check",
            "services": service_status["services"],
            "application_components": app_components,
            "orchestrator_internal": {
                "active_instances": len(orchestrator_status.get("instances", [])),
                "total_streams": orchestrator_status.get("total_streams", 0),
                "stream_assignments": len(orchestrator.stream_assignments),
                "functionality_available": {
                    "basic_orchestration": True,
                    "smart_load_balancing": orchestrator.enhanced_orchestrator is not None,
                    "enhanced_failure_handling": orchestrator.resilient_orchestrator is not None,
                    "system_monitoring": HAS_PSUTIL
                }
            },
            "configuration": config_validation,
            "performance": {
                "system_metrics": system_metrics,
                "service_response_times": service_status.get("response_times", {}),
                "last_check_duration": "< 1s"
            },
            "diagnostics": {
                "errors": service_status.get("errors", []),
                "warnings": _get_system_warnings(),
                "recommendations": _get_system_recommendations(service_status, app_components)
            }
        }
        
        # Determine overall health status
        if service_status["overall_status"] == "ready":
            logger.info("Detailed health check passed - all systems operational")
            return detailed_health
        else:
            logger.warning("Detailed health check failed - some systems not ready")
            raise HTTPException(
                status_code=503,
                detail=detailed_health
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Detailed health check failed with unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "check_type": "detailed_health_check",
                "error": str(e),
                "error_type": type(e).__name__,
                "diagnostics": {
                    "suggestion": "Check application logs for detailed error information",
                    "common_causes": [
                        "Database connection issues",
                        "Redis connectivity problems", 
                        "Application initialization failures",
                        "Resource constraints"
                    ]
                }
            }
        )


@app.get("/instances")
async def get_instances():
    """Lista todas as instâncias registradas."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, registered_at, last_heartbeat
            FROM orchestrator_instances 
            ORDER BY registered_at DESC
        """
        )

        instances = cursor.fetchall()
        return {"instances": [dict(instance) for instance in instances]}

    except Exception as e:
        logger.error(f"Erro ao listar instâncias: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar instâncias: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/instances/{server_id}")
async def get_instance(server_id: str):
    """Retorna informações detalhadas de uma instância específica."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Obter informações da instância
        cursor.execute(
            """
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, registered_at, last_heartbeat
            FROM orchestrator_instances 
            WHERE server_id = %s
        """,
            (server_id,),
        )

        instance = cursor.fetchone()
        if not instance:
            raise HTTPException(
                status_code=404, detail=f"Instância {server_id} não encontrada"
            )

        # Obter streams atribuídos
        cursor.execute(
            """
            SELECT stream_id FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
            ORDER BY stream_id
        """,
            (server_id,),
        )

        assigned_streams = [row["stream_id"] for row in cursor.fetchall()]

        # Preparar resposta
        instance_data = dict(instance)
        instance_data["assigned_streams"] = assigned_streams

        return {"status": "success", "data": instance_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter instância {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter instância: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/streams/assignments")
async def get_stream_assignments():
    """Lista todas as atribuições de streams."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT osa.stream_id, osa.server_id, osa.assigned_at, osa.status,
                   oi.ip, oi.port
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
            ORDER BY osa.assigned_at DESC
        """
        )

        assignments = cursor.fetchall()
        return {"assignments": [dict(assignment) for assignment in assignments]}

    except Exception as e:
        logger.error(f"Erro ao listar atribuições: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar atribuições: {e}")
    finally:
        cursor.close()
        conn.close()


@app.post("/diagnostic")
async def diagnostic_check(request: DiagnosticRequest):
    """Endpoint de diagnóstico para comparar estado local com o orquestrador."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Obter streams atribuídos pelo orquestrador para esta instância
        cursor.execute(
            """
            SELECT stream_id FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
            ORDER BY stream_id
        """,
            (request.server_id,),
        )

        orchestrator_streams = [row["stream_id"] for row in cursor.fetchall()]

        # Obter informações da instância
        cursor.execute(
            """
            SELECT current_streams, max_streams, status, last_heartbeat
            FROM orchestrator_instances 
            WHERE server_id = %s
        """,
            (request.server_id,),
        )

        instance_info = cursor.fetchone()
        if not instance_info:
            raise HTTPException(
                status_code=404, detail=f"Instância {request.server_id} não encontrada"
            )

        # Comparar estados
        local_streams_set = set(request.local_streams)
        orchestrator_streams_set = set(orchestrator_streams)

        # Identificar inconsistências
        streams_only_local = local_streams_set - orchestrator_streams_set
        streams_only_orchestrator = orchestrator_streams_set - local_streams_set
        streams_in_sync = local_streams_set & orchestrator_streams_set

        # Verificar contagens
        count_mismatch = request.local_stream_count != len(orchestrator_streams)
        orchestrator_count_mismatch = instance_info["current_streams"] != len(
            orchestrator_streams
        )

        # Determinar status de sincronização
        is_synchronized = (
            len(streams_only_local) == 0
            and len(streams_only_orchestrator) == 0
            and not count_mismatch
            and not orchestrator_count_mismatch
        )

        # Calcular tempo desde último heartbeat
        last_heartbeat = instance_info["last_heartbeat"]
        heartbeat_age_seconds = None
        if last_heartbeat:
            heartbeat_age_seconds = (datetime.now() - last_heartbeat).total_seconds()

        result = {
            "server_id": request.server_id,
            "timestamp": datetime.now().isoformat(),
            "is_synchronized": is_synchronized,
            "synchronization_status": "OK" if is_synchronized else "INCONSISTENT",
            "local_state": {
                "stream_count": request.local_stream_count,
                "streams": sorted(request.local_streams),
            },
            "orchestrator_state": {
                "stream_count": len(orchestrator_streams),
                "streams": sorted(orchestrator_streams),
                "instance_current_streams": instance_info["current_streams"],
            },
            "inconsistencies": {
                "streams_only_in_local": sorted(list(streams_only_local)),
                "streams_only_in_orchestrator": sorted(list(streams_only_orchestrator)),
                "count_mismatch": count_mismatch,
                "orchestrator_count_mismatch": orchestrator_count_mismatch,
            },
            "streams_in_sync": sorted(list(streams_in_sync)),
            "instance_info": {
                "status": instance_info["status"],
                "max_streams": instance_info["max_streams"],
                "last_heartbeat": (
                    last_heartbeat.isoformat() if last_heartbeat else None
                ),
                "heartbeat_age_seconds": heartbeat_age_seconds,
            },
            "recommendations": [],
        }

        # Adicionar recomendações baseadas nas inconsistências
        if streams_only_local:
            result["recommendations"].append(
                f"Instância tem {len(streams_only_local)} streams não reconhecidos pelo orquestrador"
            )

        if streams_only_orchestrator:
            result["recommendations"].append(
                f"Orquestrador tem {len(streams_only_orchestrator)} streams não processados pela instância"
            )

        if count_mismatch:
            result["recommendations"].append(
                "Contagem local de streams não confere com orquestrador"
            )

        if orchestrator_count_mismatch:
            result["recommendations"].append(
                "Contagem do orquestrador não confere com assignments ativos"
            )

        if heartbeat_age_seconds and heartbeat_age_seconds > 120:
            result["recommendations"].append(
                f"Último heartbeat há {heartbeat_age_seconds:.0f} segundos - possível problema de conectividade"
            )

        if not is_synchronized:
            result["recommendations"].append(
                "Recomenda-se executar reload_streams_dynamic ou verificação de consistência"
            )

        logger.info(
            f"Diagnóstico para {request.server_id}: {'SINCRONIZADO' if is_synchronized else 'INCONSISTENTE'}"
        )

        return result

    except Exception as e:
        logger.error(f"Erro no diagnóstico para {request.server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no diagnóstico: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/instances/{server_id}/metrics")
async def get_instance_metrics(server_id: str, hours: int = 24):
    """Obtém métricas de performance de uma instância específica."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Verificar se a instância existe
        cursor.execute(
            "SELECT id FROM orchestrator_instances WHERE server_id = %s",
            (server_id,)
        )
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Instância não encontrada")

        # Obter métricas das últimas N horas
        cursor.execute(
            """
            SELECT 
                cpu_percent,
                memory_percent,
                disk_percent,
                load_average_1m,
                load_average_5m,
                load_average_15m,
                uptime_seconds,
                recorded_at
            FROM orchestrator_instance_metrics 
            WHERE server_id = %s 
              AND recorded_at > NOW() - INTERVAL '%s hours'
            ORDER BY recorded_at DESC
            """,
            (server_id, hours)
        )

        metrics = cursor.fetchall()
        return {
            "server_id": server_id,
            "metrics": [dict(metric) for metric in metrics],
            "count": len(metrics)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter métricas para {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter métricas: {e}")
    finally:
        cursor.close()
        conn.close()


# Smart Load Balancing Endpoints

@app.post("/rebalance/smart")
async def smart_rebalance_endpoint(reason: str = "manual"):
    """
    Trigger intelligent rebalancing using smart load balancer.
    
    Args:
        reason: Reason for rebalancing (manual, new_instance, instance_failure, load_imbalance, performance_degradation)
    """
    try:
        result = orchestrator.smart_rebalance(reason)
        return result
    except Exception as e:
        logger.error(f"Error in smart rebalance endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Smart rebalancing failed: {e}")


@app.get("/rebalance/check")
async def check_load_balance_endpoint():
    """Check current load balance status and detect imbalances."""
    try:
        result = orchestrator.check_load_balance()
        return result
    except Exception as e:
        logger.error(f"Error checking load balance: {e}")
        raise HTTPException(status_code=500, detail=f"Load balance check failed: {e}")


@app.post("/instances/{server_id}/failure")
async def handle_instance_failure_endpoint(server_id: str):
    """Handle instance failure using smart load balancing."""
    try:
        result = orchestrator.handle_instance_failure_smart(server_id)
        return result
    except Exception as e:
        logger.error(f"Error handling instance failure: {e}")
        raise HTTPException(status_code=500, detail=f"Instance failure handling failed: {e}")


@app.get("/rebalance/stats")
async def get_load_balancer_stats_endpoint():
    """Get load balancer statistics and performance metrics."""
    try:
        result = orchestrator.get_load_balancer_stats()
        return result
    except Exception as e:
        logger.error(f"Error getting load balancer stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get load balancer stats: {e}")


# Resilient Orchestrator Endpoints

@app.get("/resilience/status")
async def get_resilience_status():
    """Get comprehensive resilience and health status."""
    if not orchestrator.resilient_orchestrator:
        raise HTTPException(status_code=503, detail="Resilient orchestrator not available")
    
    try:
        status = orchestrator.resilient_orchestrator.get_resilience_status()
        return status
    except Exception as e:
        logger.error(f"Error getting resilience status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get resilience status: {e}")


@app.post("/resilience/recovery/{server_id}")
async def force_instance_recovery(server_id: str):
    """Force recovery attempt for a specific failed instance."""
    if not orchestrator.resilient_orchestrator:
        raise HTTPException(status_code=503, detail="Resilient orchestrator not available")
    
    try:
        result = await orchestrator.resilient_orchestrator.force_instance_recovery(server_id)
        return result
    except Exception as e:
        logger.error(f"Error forcing instance recovery: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to force instance recovery: {e}")


@app.post("/resilience/emergency/{server_id}")
async def trigger_emergency_recovery(server_id: str, reason: str = "Manual trigger"):
    """Manually trigger emergency recovery for an instance."""
    if not orchestrator.resilient_orchestrator:
        raise HTTPException(status_code=503, detail="Resilient orchestrator not available")
    
    try:
        result = await orchestrator.resilient_orchestrator.trigger_emergency_recovery(server_id, reason)
        return result
    except Exception as e:
        logger.error(f"Error triggering emergency recovery: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger emergency recovery: {e}")


@app.get("/resilience/health")
async def get_system_health():
    """Get current system health status."""
    if not orchestrator.resilient_orchestrator:
        return {"status": "basic", "message": "Resilient orchestrator not available"}
    
    try:
        status = orchestrator.resilient_orchestrator.get_resilience_status()
        return {
            "system_health": status["system_health"],
            "last_health_check": status["last_health_check"],
            "active_instances": status["active_instances"],
            "failed_instances": status["failed_instances"],
            "critical_failures": status["critical_failures"]
        }
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system health: {e}")


@app.post("/rebalance/basic")
async def basic_rebalance_endpoint():
    """Trigger basic rebalancing (fallback method)."""
    try:
        orchestrator.rebalance_all_streams()
        return {
            "status": "completed",
            "method": "basic",
            "message": "Basic rebalancing completed successfully"
        }
    except Exception as e:
        logger.error(f"Error in basic rebalance: {e}")
        raise HTTPException(status_code=500, detail=f"Basic rebalancing failed: {e}")


# Background Tasks for Smart Load Balancing

async def smart_rebalance_monitor_task():
    """Background task to monitor and trigger automatic rebalancing."""
    while True:
        try:
            if orchestrator.enhanced_orchestrator:
                # Check if rebalancing is needed
                result = orchestrator.check_load_balance()
                
                if result.get("status") == "success" and result.get("needs_rebalancing"):
                    logger.info(f"Automatic rebalancing triggered: {result.get('reason')}")
                    
                    # Trigger automatic rebalancing
                    rebalance_result = orchestrator.smart_rebalance("load_imbalance")
                    
                    if rebalance_result.get("status") == "completed":
                        logger.info(
                            f"Automatic rebalancing completed: "
                            f"{rebalance_result.get('streams_moved', 0)} streams moved"
                        )
                    else:
                        logger.error(f"Automatic rebalancing failed: {rebalance_result.get('error')}")
            
            # Wait before next check (configurable interval)
            await asyncio.sleep(int(os.getenv("SMART_REBALANCE_INTERVAL", "300")))  # 5 minutes default
            
        except Exception as e:
            logger.error(f"Error in smart rebalance monitor: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error


# Update lifespan to include smart rebalance monitor and resilient monitoring
@asynccontextmanager
async def enhanced_lifespan(app: FastAPI):
    """Enhanced lifespan manager with smart rebalancing and resilient monitoring."""
    # Startup
    logger.info("Starting enhanced orchestrator with resilient monitoring...")
    orchestrator.create_tables()

    # Start background tasks
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    failover_task_handle = asyncio.create_task(failover_monitor_task())
    smart_rebalance_task_handle = asyncio.create_task(smart_rebalance_monitor_task())
    
    # Start resilient monitoring if available
    if orchestrator.resilient_orchestrator:
        await orchestrator.resilient_orchestrator.start_monitoring()
        logger.info("Resilient monitoring started")

    # Store orchestrator reference
    app.state.orchestrator = orchestrator

    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down enhanced orchestrator...")
        
        # Stop resilient monitoring
        if orchestrator.resilient_orchestrator:
            await orchestrator.resilient_orchestrator.stop_monitoring()
            logger.info("Resilient monitoring stopped")
        
        cleanup_task_handle.cancel()
        failover_task_handle.cancel()
        smart_rebalance_task_handle.cancel()

        for task in [cleanup_task_handle, failover_task_handle, smart_rebalance_task_handle]:
            try:
                await task
            except asyncio.CancelledError:
                pass


# Replace the original lifespan with enhanced version
app.router.lifespan_context = enhanced_lifespan


async def cleanup_task():
    """Tarefa de limpeza que executa periodicamente."""
    while True:
        try:
            await orchestrator.cleanup_inactive_instances()
            await asyncio.sleep(REBALANCE_INTERVAL)
        except Exception as e:
            logger.error(f"Erro na tarefa de limpeza: {e}")
            await asyncio.sleep(30)  # Aguardar menos tempo em caso de erro


async def failover_monitor_task():
    """Tarefa de monitoramento de failover que executa mais frequentemente."""
    while True:
        try:
            # Executar verificação de failover a cada 10 segundos para maior responsividade
            orchestrator.handle_orphaned_streams()
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Erro na tarefa de failover: {e}")
            await asyncio.sleep(5)  # Aguardar menos tempo em caso de erro


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ORCHESTRATOR_PORT", 8001))
    host = os.getenv("ORCHESTRATOR_HOST", "0.0.0.0")

    logger.info(f"Iniciando orquestrador em {host}:{port}")

    uvicorn.run(app, host=host, port=port, log_level="info")

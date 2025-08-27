#!/usr/bin/env python3
"""
Comprehensive Error Logging and Diagnostics Module

This module provides structured logging with timestamps, detailed error messages
with context and suggested solutions, diagnostic functions for troubleshooting
common issues, and environment variable validation and reporting.

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import psycopg2
import redis


class StructuredLogger:
    """
    Enhanced structured logger with timestamps and context for all startup phases.
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    def __init__(self, name: str = "diagnostic", log_level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Clear existing handlers to avoid conflicts
        self.logger.handlers.clear()
        
        # Create structured formatter that handles missing phase gracefully
        class PhaseFormatter(logging.Formatter):
            def format(self, record):
                if not hasattr(record, 'phase'):
                    record.phase = 'GENERAL'
                return super().format(record)
        
        formatter = PhaseFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(phase)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler for persistent logging
        # Use absolute path or relative to current file location
        current_dir = Path(__file__).parent
        log_dir = current_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(log_dir / "orchestrator_diagnostic.log")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        self.current_phase = "INITIALIZATION"
    
    def set_phase(self, phase: str):
        """Set the current startup phase for context."""
        self.current_phase = phase
    
    def _log_with_context(self, level: str, message: str, context: Optional[Dict] = None, 
                         exception: Optional[Exception] = None, suggested_solution: Optional[str] = None):
        """Log message with structured context and optional exception details."""
        
        # Create extra context for formatter
        extra = {"phase": self.current_phase}
        
        # Build structured message
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": self.current_phase,
            "message": message,
            "level": level
        }
        
        if context:
            log_data["context"] = context
        
        if exception:
            log_data["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exc()
            }
        
        if suggested_solution:
            log_data["suggested_solution"] = suggested_solution
        
        # Log the message
        log_method = getattr(self.logger, level.lower())
        log_method(message, extra=extra)
        
        # Also log structured data to file for analysis
        structured_log_file = Path("/app/logs/orchestrator_structured.jsonl")
        structured_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(structured_log_file, "a") as f:
            f.write(json.dumps(log_data) + "\n")
    
    def info(self, message: str, context: Optional[Dict] = None):
        """Log info message with context."""
        self._log_with_context("INFO", message, context)
    
    def warning(self, message: str, context: Optional[Dict] = None, suggested_solution: Optional[str] = None):
        """Log warning message with context and optional solution."""
        self._log_with_context("WARNING", message, context, suggested_solution=suggested_solution)
    
    def error(self, message: str, context: Optional[Dict] = None, exception: Optional[Exception] = None, 
              suggested_solution: Optional[str] = None):
        """Log error message with context, exception details, and suggested solution."""
        self._log_with_context("ERROR", message, context, exception, suggested_solution)
    
    def critical(self, message: str, context: Optional[Dict] = None, exception: Optional[Exception] = None, 
                 suggested_solution: Optional[str] = None):
        """Log critical message with context, exception details, and suggested solution."""
        self._log_with_context("CRITICAL", message, context, exception, suggested_solution)
    
    def success(self, message: str, context: Optional[Dict] = None):
        """Log success message with context."""
        self._log_with_context("INFO", f"SUCCESS: {message}", context)
    
    def step(self, message: str, context: Optional[Dict] = None):
        """Log step message with context."""
        self._log_with_context("INFO", f"STEP: {message}", context)


class EnvironmentValidator:
    """
    Environment variable validation and reporting functionality.
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
        self.validation_results = {}
    
    def validate_all(self) -> Dict[str, Any]:
        """
        Perform comprehensive environment validation.
        
        Returns:
            Dict containing validation results with detailed reporting
        """
        self.logger.set_phase("ENVIRONMENT_VALIDATION")
        self.logger.step("Starting comprehensive environment validation")
        
        validation_report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "UNKNOWN",
            "categories": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Validate database configuration
        db_validation = self._validate_database_config()
        validation_report["categories"]["database"] = db_validation
        
        # Validate Redis configuration
        redis_validation = self._validate_redis_config()
        validation_report["categories"]["redis"] = redis_validation
        
        # Validate orchestrator configuration
        orchestrator_validation = self._validate_orchestrator_config()
        validation_report["categories"]["orchestrator"] = orchestrator_validation
        
        # Validate timeout configurations
        timeout_validation = self._validate_timeout_config()
        validation_report["categories"]["timeouts"] = timeout_validation
        
        # Validate system paths and permissions
        system_validation = self._validate_system_config()
        validation_report["categories"]["system"] = system_validation
        
        # Aggregate results
        all_categories = [db_validation, redis_validation, orchestrator_validation, 
                         timeout_validation, system_validation]
        
        total_issues = sum(len(cat.get("issues", [])) for cat in all_categories)
        total_warnings = sum(len(cat.get("warnings", [])) for cat in all_categories)
        
        # Collect all issues and warnings
        for category in all_categories:
            validation_report["issues"].extend(category.get("issues", []))
            validation_report["warnings"].extend(category.get("warnings", []))
            validation_report["recommendations"].extend(category.get("recommendations", []))
        
        # Determine overall status
        if total_issues > 0:
            validation_report["overall_status"] = "FAILED"
            self.logger.error(f"Environment validation failed with {total_issues} issues")
        elif total_warnings > 0:
            validation_report["overall_status"] = "WARNING"
            self.logger.warning(f"Environment validation completed with {total_warnings} warnings")
        else:
            validation_report["overall_status"] = "PASSED"
            self.logger.success("Environment validation passed successfully")
        
        self.validation_results = validation_report
        return validation_report
    
    def _validate_database_config(self) -> Dict[str, Any]:
        """Validate database configuration variables."""
        result = {
            "name": "Database Configuration",
            "status": "UNKNOWN",
            "variables": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Required database variables
        required_vars = {
            "DB_HOST": {"default": "localhost", "description": "Database host"},
            "DB_PORT": {"default": "5432", "description": "Database port", "type": "int"},
            "DB_NAME": {"default": "radio_db", "description": "Database name"},
            "DB_USER": {"default": "postgres", "description": "Database user"},
            "DB_PASSWORD": {"default": "", "description": "Database password", "sensitive": True}
        }
        
        for var_name, var_info in required_vars.items():
            value = os.getenv(var_name)
            var_result = {
                "value": value if not var_info.get("sensitive") else ("***" if value else None),
                "is_set": value is not None,
                "is_empty": not bool(value),
                "default": var_info["default"],
                "description": var_info["description"]
            }
            
            if not value:
                if var_name == "DB_PASSWORD":
                    result["warnings"].append(f"{var_name} is not set - using empty password")
                    result["recommendations"].append(f"Set {var_name} for secure database access")
                else:
                    result["issues"].append(f"{var_name} is not set")
            elif var_info.get("type") == "int":
                try:
                    int(value)
                    var_result["parsed_value"] = int(value)
                except ValueError:
                    result["issues"].append(f"{var_name} is not a valid integer: {value}")
            
            result["variables"][var_name] = var_result
        
        # Validate port range
        db_port = os.getenv("DB_PORT", "5432")
        try:
            port_num = int(db_port)
            if not (1 <= port_num <= 65535):
                result["issues"].append(f"DB_PORT {port_num} is outside valid range (1-65535)")
        except ValueError:
            pass  # Already handled above
        
        # Set status
        if result["issues"]:
            result["status"] = "FAILED"
        elif result["warnings"]:
            result["status"] = "WARNING"
        else:
            result["status"] = "PASSED"
        
        return result
    
    def _validate_redis_config(self) -> Dict[str, Any]:
        """Validate Redis configuration variables."""
        result = {
            "name": "Redis Configuration",
            "status": "UNKNOWN",
            "variables": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Redis configuration variables
        redis_vars = {
            "REDIS_HOST": {"default": "localhost", "description": "Redis host"},
            "REDIS_PORT": {"default": "6379", "description": "Redis port", "type": "int"},
            "REDIS_PASSWORD": {"default": "", "description": "Redis password", "sensitive": True, "optional": True}
        }
        
        for var_name, var_info in redis_vars.items():
            value = os.getenv(var_name)
            var_result = {
                "value": value if not var_info.get("sensitive") else ("***" if value else None),
                "is_set": value is not None,
                "is_empty": not bool(value),
                "default": var_info["default"],
                "description": var_info["description"],
                "optional": var_info.get("optional", False)
            }
            
            if not value and not var_info.get("optional"):
                result["warnings"].append(f"{var_name} is not set - using default: {var_info['default']}")
            elif value and var_info.get("type") == "int":
                try:
                    int(value)
                    var_result["parsed_value"] = int(value)
                except ValueError:
                    result["issues"].append(f"{var_name} is not a valid integer: {value}")
            
            result["variables"][var_name] = var_result
        
        # Validate Redis port range
        redis_port = os.getenv("REDIS_PORT", "6379")
        try:
            port_num = int(redis_port)
            if not (1 <= port_num <= 65535):
                result["issues"].append(f"REDIS_PORT {port_num} is outside valid range (1-65535)")
        except ValueError:
            pass
        
        # Set status
        if result["issues"]:
            result["status"] = "FAILED"
        elif result["warnings"]:
            result["status"] = "WARNING"
        else:
            result["status"] = "PASSED"
        
        return result
    
    def _validate_orchestrator_config(self) -> Dict[str, Any]:
        """Validate orchestrator-specific configuration variables."""
        result = {
            "name": "Orchestrator Configuration",
            "status": "UNKNOWN",
            "variables": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Orchestrator configuration variables
        orchestrator_vars = {
            "MAX_STREAMS_PER_INSTANCE": {"default": "20", "description": "Maximum streams per instance", "type": "int"},
            "HEARTBEAT_TIMEOUT": {"default": "300", "description": "Heartbeat timeout in seconds", "type": "int"},
            "REBALANCE_INTERVAL": {"default": "60", "description": "Rebalance interval in seconds", "type": "int"},
            "LOG_LEVEL": {"default": "INFO", "description": "Logging level", "valid_values": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}
        }
        
        for var_name, var_info in orchestrator_vars.items():
            value = os.getenv(var_name)
            var_result = {
                "value": value,
                "is_set": value is not None,
                "default": var_info["default"],
                "description": var_info["description"]
            }
            
            if not value:
                result["warnings"].append(f"{var_name} is not set - using default: {var_info['default']}")
                value = var_info["default"]  # Use default for validation
            
            # Type validation
            if var_info.get("type") == "int":
                try:
                    parsed_value = int(value)
                    var_result["parsed_value"] = parsed_value
                    
                    # Range validation for specific variables
                    if var_name == "MAX_STREAMS_PER_INSTANCE" and parsed_value <= 0:
                        result["issues"].append(f"{var_name} must be positive, got: {parsed_value}")
                    elif var_name == "HEARTBEAT_TIMEOUT" and parsed_value < 30:
                        result["warnings"].append(f"{var_name} is very low ({parsed_value}s), consider increasing for stability")
                    elif var_name == "REBALANCE_INTERVAL" and parsed_value < 10:
                        result["warnings"].append(f"{var_name} is very low ({parsed_value}s), may cause excessive rebalancing")
                        
                except ValueError:
                    result["issues"].append(f"{var_name} is not a valid integer: {value}")
            
            # Valid values validation
            if var_info.get("valid_values") and value not in var_info["valid_values"]:
                result["issues"].append(f"{var_name} has invalid value '{value}', valid values: {var_info['valid_values']}")
            
            result["variables"][var_name] = var_result
        
        # Set status
        if result["issues"]:
            result["status"] = "FAILED"
        elif result["warnings"]:
            result["status"] = "WARNING"
        else:
            result["status"] = "PASSED"
        
        return result
    
    def _validate_timeout_config(self) -> Dict[str, Any]:
        """Validate timeout configuration variables."""
        result = {
            "name": "Timeout Configuration",
            "status": "UNKNOWN",
            "variables": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Timeout configuration variables
        timeout_vars = {
            "POSTGRES_STARTUP_TIMEOUT": {"default": "60", "description": "PostgreSQL startup timeout", "type": "int", "min": 30},
            "REDIS_STARTUP_TIMEOUT": {"default": "30", "description": "Redis startup timeout", "type": "int", "min": 10},
            "APP_STARTUP_TIMEOUT": {"default": "120", "description": "Application startup timeout", "type": "int", "min": 60},
            "DB_MAX_RETRIES": {"default": "3", "description": "Database connection max retries", "type": "int", "min": 1},
            "DB_RETRY_DELAY": {"default": "1.0", "description": "Database retry delay in seconds", "type": "float", "min": 0.1}
        }
        
        for var_name, var_info in timeout_vars.items():
            value = os.getenv(var_name)
            var_result = {
                "value": value,
                "is_set": value is not None,
                "default": var_info["default"],
                "description": var_info["description"]
            }
            
            if not value:
                result["warnings"].append(f"{var_name} is not set - using default: {var_info['default']}")
                value = var_info["default"]
            
            # Type validation
            try:
                if var_info.get("type") == "int":
                    parsed_value = int(value)
                elif var_info.get("type") == "float":
                    parsed_value = float(value)
                else:
                    parsed_value = value
                
                var_result["parsed_value"] = parsed_value
                
                # Range validation
                min_value = var_info.get("min")
                if min_value is not None and parsed_value < min_value:
                    result["warnings"].append(f"{var_name} is below recommended minimum ({min_value}): {parsed_value}")
                    result["recommendations"].append(f"Consider increasing {var_name} to at least {min_value} for better reliability")
                
            except (ValueError, TypeError):
                result["issues"].append(f"{var_name} is not a valid {var_info.get('type', 'value')}: {value}")
            
            result["variables"][var_name] = var_result
        
        # Set status
        if result["issues"]:
            result["status"] = "FAILED"
        elif result["warnings"]:
            result["status"] = "WARNING"
        else:
            result["status"] = "PASSED"
        
        return result
    
    def _validate_system_config(self) -> Dict[str, Any]:
        """Validate system paths and permissions."""
        result = {
            "name": "System Configuration",
            "status": "UNKNOWN",
            "paths": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        # Important system paths
        system_paths = {
            "/app": {"description": "Application directory", "required": True, "writable": False},
            "/app/logs": {"description": "Log directory", "required": False, "writable": True, "create_if_missing": True},
            "/var/lib/postgresql/data": {"description": "PostgreSQL data directory", "required": False, "writable": True},
            "/tmp": {"description": "Temporary directory", "required": True, "writable": True}
        }
        
        for path_str, path_info in system_paths.items():
            path = Path(path_str)
            path_result = {
                "path": str(path),
                "exists": path.exists(),
                "is_directory": path.is_dir() if path.exists() else None,
                "is_writable": None,
                "description": path_info["description"],
                "required": path_info["required"]
            }
            
            if path.exists():
                try:
                    # Test writability
                    if path_info.get("writable"):
                        test_file = path / ".write_test"
                        test_file.touch()
                        test_file.unlink()
                        path_result["is_writable"] = True
                except (PermissionError, OSError):
                    path_result["is_writable"] = False
                    if path_info.get("writable"):
                        result["issues"].append(f"Path {path_str} is not writable")
            else:
                if path_info["required"]:
                    result["issues"].append(f"Required path {path_str} does not exist")
                elif path_info.get("create_if_missing"):
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        path_result["exists"] = True
                        path_result["is_directory"] = True
                        result["warnings"].append(f"Created missing directory: {path_str}")
                    except (PermissionError, OSError) as e:
                        result["issues"].append(f"Cannot create directory {path_str}: {e}")
            
            result["paths"][path_str] = path_result
        
        # Set status
        if result["issues"]:
            result["status"] = "FAILED"
        elif result["warnings"]:
            result["status"] = "WARNING"
        else:
            result["status"] = "PASSED"
        
        return result


class DiagnosticFunctions:
    """
    Diagnostic functions for troubleshooting common issues.
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
    
    def diagnose_database_connectivity(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Diagnose database connectivity issues with detailed analysis.
        
        Args:
            db_config: Database configuration dictionary
            
        Returns:
            Dict containing diagnostic results and recommendations
        """
        self.logger.set_phase("DATABASE_DIAGNOSTICS")
        self.logger.step("Starting database connectivity diagnostics")
        
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "service": "PostgreSQL",
            "status": "UNKNOWN",
            "tests": {},
            "issues_found": [],
            "recommendations": []
        }
        
        # Test 1: Basic connectivity
        connectivity_test = self._test_database_connectivity(db_config)
        diagnosis["tests"]["connectivity"] = connectivity_test
        
        # Test 2: Authentication
        auth_test = self._test_database_authentication(db_config)
        diagnosis["tests"]["authentication"] = auth_test
        
        # Test 3: Database existence
        db_test = self._test_database_existence(db_config)
        diagnosis["tests"]["database_existence"] = db_test
        
        # Test 4: Basic operations
        operations_test = self._test_database_operations(db_config)
        diagnosis["tests"]["operations"] = operations_test
        
        # Analyze results and provide recommendations
        self._analyze_database_results(diagnosis)
        
        return diagnosis
    
    def _test_database_connectivity(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test basic database connectivity."""
        test_result = {
            "name": "Basic Connectivity",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            # Try to connect without specifying database
            basic_config = db_config.copy()
            basic_config["database"] = "postgres"  # Default database
            
            conn = psycopg2.connect(**basic_config, connect_timeout=5)
            conn.close()
            
            test_result["status"] = "PASSED"
            test_result["details"]["message"] = "Successfully connected to PostgreSQL server"
            self.logger.success("Database connectivity test passed")
            
        except psycopg2.OperationalError as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            
            # Analyze specific error types
            error_msg = str(e).lower()
            if "connection refused" in error_msg:
                test_result["details"]["likely_cause"] = "PostgreSQL server is not running or not accepting connections"
                test_result["details"]["suggestion"] = "Check if PostgreSQL service is started and listening on the correct port"
            elif "timeout" in error_msg:
                test_result["details"]["likely_cause"] = "Network connectivity issues or server overload"
                test_result["details"]["suggestion"] = "Check network connectivity and server performance"
            elif "host" in error_msg and "unknown" in error_msg:
                test_result["details"]["likely_cause"] = "Invalid hostname or DNS resolution failure"
                test_result["details"]["suggestion"] = "Verify DB_HOST setting and DNS configuration"
            else:
                test_result["details"]["likely_cause"] = "Unknown connectivity issue"
                test_result["details"]["suggestion"] = "Check PostgreSQL logs for more details"
            
            self.logger.error("Database connectivity test failed", 
                            context={"error": str(e)}, 
                            suggested_solution=test_result["details"]["suggestion"])
        
        except Exception as e:
            test_result["status"] = "ERROR"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Unexpected error during connectivity test"
            self.logger.error("Unexpected error in connectivity test", exception=e)
        
        return test_result
    
    def _test_database_authentication(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test database authentication."""
        test_result = {
            "name": "Authentication",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            conn = psycopg2.connect(**db_config, connect_timeout=5)
            conn.close()
            
            test_result["status"] = "PASSED"
            test_result["details"]["message"] = f"Successfully authenticated as user '{db_config['user']}'"
            self.logger.success("Database authentication test passed")
            
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            
            if "authentication failed" in error_msg or "password authentication failed" in error_msg:
                test_result["status"] = "FAILED"
                test_result["error"] = str(e)
                test_result["details"]["likely_cause"] = "Invalid username or password"
                test_result["details"]["suggestion"] = "Verify DB_USER and DB_PASSWORD environment variables"
                
                self.logger.error("Database authentication failed", 
                                context={"user": db_config["user"]},
                                suggested_solution="Check DB_USER and DB_PASSWORD settings")
            else:
                # Connectivity issue, not authentication
                test_result["status"] = "SKIPPED"
                test_result["details"]["message"] = "Skipped due to connectivity issues"
        
        except Exception as e:
            test_result["status"] = "ERROR"
            test_result["error"] = str(e)
            self.logger.error("Unexpected error in authentication test", exception=e)
        
        return test_result
    
    def _test_database_existence(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test if target database exists."""
        test_result = {
            "name": "Database Existence",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            conn = psycopg2.connect(**db_config, connect_timeout=5)
            conn.close()
            
            test_result["status"] = "PASSED"
            test_result["details"]["message"] = f"Database '{db_config['database']}' exists and is accessible"
            self.logger.success("Database existence test passed")
            
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            
            if "database" in error_msg and "does not exist" in error_msg:
                test_result["status"] = "FAILED"
                test_result["error"] = str(e)
                test_result["details"]["likely_cause"] = f"Database '{db_config['database']}' does not exist"
                test_result["details"]["suggestion"] = "Create the database or check DB_NAME environment variable"
                
                self.logger.error("Target database does not exist", 
                                context={"database": db_config["database"]},
                                suggested_solution="Create database or verify DB_NAME setting")
            else:
                test_result["status"] = "SKIPPED"
                test_result["details"]["message"] = "Skipped due to connectivity or authentication issues"
        
        except Exception as e:
            test_result["status"] = "ERROR"
            test_result["error"] = str(e)
            self.logger.error("Unexpected error in database existence test", exception=e)
        
        return test_result
    
    def _test_database_operations(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test basic database operations."""
        test_result = {
            "name": "Basic Operations",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            conn = psycopg2.connect(**db_config, connect_timeout=5)
            cursor = conn.cursor()
            
            # Test SELECT operation
            cursor.execute("SELECT current_timestamp, version()")
            result = cursor.fetchone()
            
            test_result["status"] = "PASSED"
            test_result["details"]["timestamp"] = str(result[0])
            test_result["details"]["version"] = result[1]
            test_result["details"]["message"] = "Basic database operations successful"
            
            cursor.close()
            conn.close()
            
            self.logger.success("Database operations test passed")
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Database operational issues"
            test_result["details"]["suggestion"] = "Check database health and permissions"
            
            self.logger.error("Database operations test failed", 
                            exception=e,
                            suggested_solution="Check database health and user permissions")
        
        return test_result
    
    def _analyze_database_results(self, diagnosis: Dict[str, Any]):
        """Analyze database diagnostic results and provide recommendations."""
        tests = diagnosis["tests"]
        
        # Determine overall status
        if all(test["status"] == "PASSED" for test in tests.values()):
            diagnosis["status"] = "HEALTHY"
        elif any(test["status"] == "FAILED" for test in tests.values()):
            diagnosis["status"] = "ISSUES_FOUND"
        else:
            diagnosis["status"] = "PARTIAL"
        
        # Collect issues and recommendations
        for test_name, test_result in tests.items():
            if test_result["status"] == "FAILED":
                diagnosis["issues_found"].append({
                    "test": test_name,
                    "error": test_result["error"],
                    "cause": test_result["details"].get("likely_cause"),
                    "suggestion": test_result["details"].get("suggestion")
                })
                
                if test_result["details"].get("suggestion"):
                    diagnosis["recommendations"].append(test_result["details"]["suggestion"])
        
        # Add general recommendations based on patterns
        if not diagnosis["recommendations"]:
            if diagnosis["status"] == "HEALTHY":
                diagnosis["recommendations"].append("Database connectivity is healthy - no action needed")
            else:
                diagnosis["recommendations"].append("Check PostgreSQL service status and configuration")
    
    def diagnose_redis_connectivity(self, redis_host: str = "localhost", redis_port: int = 6379) -> Dict[str, Any]:
        """
        Diagnose Redis connectivity issues with detailed analysis.
        
        Args:
            redis_host: Redis host
            redis_port: Redis port
            
        Returns:
            Dict containing diagnostic results and recommendations
        """
        self.logger.set_phase("REDIS_DIAGNOSTICS")
        self.logger.step("Starting Redis connectivity diagnostics")
        
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "service": "Redis",
            "status": "UNKNOWN",
            "tests": {},
            "issues_found": [],
            "recommendations": []
        }
        
        # Test 1: Basic connectivity
        connectivity_test = self._test_redis_connectivity(redis_host, redis_port)
        diagnosis["tests"]["connectivity"] = connectivity_test
        
        # Test 2: Redis operations
        operations_test = self._test_redis_operations(redis_host, redis_port)
        diagnosis["tests"]["operations"] = operations_test
        
        # Test 3: Redis info
        info_test = self._test_redis_info(redis_host, redis_port)
        diagnosis["tests"]["info"] = info_test
        
        # Analyze results
        self._analyze_redis_results(diagnosis)
        
        return diagnosis
    
    def _test_redis_connectivity(self, host: str, port: int) -> Dict[str, Any]:
        """Test basic Redis connectivity."""
        test_result = {
            "name": "Basic Connectivity",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            redis_client = redis.Redis(
                host=host,
                port=port,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=False
            )
            
            # Test ping
            response = redis_client.ping()
            
            if response:
                test_result["status"] = "PASSED"
                test_result["details"]["message"] = "Successfully connected to Redis server"
                self.logger.success("Redis connectivity test passed")
            else:
                test_result["status"] = "FAILED"
                test_result["details"]["message"] = "Redis ping returned False"
            
            redis_client.close()
            
        except redis.ConnectionError as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Redis server is not running or not accepting connections"
            test_result["details"]["suggestion"] = "Check if Redis service is started and listening on the correct port"
            
            self.logger.error("Redis connectivity test failed", 
                            context={"host": host, "port": port, "error": str(e)},
                            suggested_solution="Check Redis service status and configuration")
        
        except redis.TimeoutError as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Redis server is responding slowly or overloaded"
            test_result["details"]["suggestion"] = "Check Redis performance and server load"
        
        except Exception as e:
            test_result["status"] = "ERROR"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Unexpected error during Redis connectivity test"
            self.logger.error("Unexpected error in Redis connectivity test", exception=e)
        
        return test_result
    
    def _test_redis_operations(self, host: str, port: int) -> Dict[str, Any]:
        """Test basic Redis operations."""
        test_result = {
            "name": "Basic Operations",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            redis_client = redis.Redis(host=host, port=port, socket_timeout=5)
            
            # Test SET and GET operations
            test_key = f"diagnostic_test_{datetime.now().timestamp()}"
            test_value = "diagnostic_value"
            
            redis_client.set(test_key, test_value, ex=60)  # Expire in 60 seconds
            retrieved_value = redis_client.get(test_key)
            redis_client.delete(test_key)  # Cleanup
            
            if retrieved_value and retrieved_value.decode() == test_value:
                test_result["status"] = "PASSED"
                test_result["details"]["message"] = "Basic Redis operations successful"
                self.logger.success("Redis operations test passed")
            else:
                test_result["status"] = "FAILED"
                test_result["details"]["message"] = "Redis operations returned unexpected results"
            
            redis_client.close()
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Redis operational issues"
            test_result["details"]["suggestion"] = "Check Redis health and permissions"
            
            self.logger.error("Redis operations test failed", 
                            exception=e,
                            suggested_solution="Check Redis health and configuration")
        
        return test_result
    
    def _test_redis_info(self, host: str, port: int) -> Dict[str, Any]:
        """Test Redis info command."""
        test_result = {
            "name": "Redis Info",
            "status": "UNKNOWN",
            "details": {},
            "error": None
        }
        
        try:
            redis_client = redis.Redis(host=host, port=port, socket_timeout=5)
            
            info = redis_client.info()
            
            test_result["status"] = "PASSED"
            test_result["details"]["redis_version"] = info.get("redis_version", "unknown")
            test_result["details"]["used_memory_human"] = info.get("used_memory_human", "unknown")
            test_result["details"]["connected_clients"] = info.get("connected_clients", "unknown")
            test_result["details"]["uptime_in_seconds"] = info.get("uptime_in_seconds", "unknown")
            
            self.logger.success("Redis info test passed", 
                              context={"version": test_result["details"]["redis_version"]})
            
            redis_client.close()
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["details"]["likely_cause"] = "Cannot retrieve Redis information"
            
            self.logger.error("Redis info test failed", exception=e)
        
        return test_result
    
    def _analyze_redis_results(self, diagnosis: Dict[str, Any]):
        """Analyze Redis diagnostic results and provide recommendations."""
        tests = diagnosis["tests"]
        
        # Determine overall status
        if all(test["status"] == "PASSED" for test in tests.values()):
            diagnosis["status"] = "HEALTHY"
        elif any(test["status"] == "FAILED" for test in tests.values()):
            diagnosis["status"] = "ISSUES_FOUND"
        else:
            diagnosis["status"] = "PARTIAL"
        
        # Collect issues and recommendations
        for test_name, test_result in tests.items():
            if test_result["status"] == "FAILED":
                diagnosis["issues_found"].append({
                    "test": test_name,
                    "error": test_result["error"],
                    "cause": test_result["details"].get("likely_cause"),
                    "suggestion": test_result["details"].get("suggestion")
                })
                
                if test_result["details"].get("suggestion"):
                    diagnosis["recommendations"].append(test_result["details"]["suggestion"])
        
        # Add general recommendations
        if not diagnosis["recommendations"]:
            if diagnosis["status"] == "HEALTHY":
                diagnosis["recommendations"].append("Redis connectivity is healthy - no action needed")
            else:
                diagnosis["recommendations"].append("Check Redis service status and configuration")
    
    def generate_comprehensive_report(self, db_config: Dict[str, Any], 
                                    redis_host: str = "localhost", 
                                    redis_port: int = 6379) -> Dict[str, Any]:
        """
        Generate a comprehensive diagnostic report for all services.
        
        Args:
            db_config: Database configuration
            redis_host: Redis host
            redis_port: Redis port
            
        Returns:
            Dict containing comprehensive diagnostic report
        """
        self.logger.set_phase("COMPREHENSIVE_DIAGNOSTICS")
        self.logger.step("Generating comprehensive diagnostic report")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "report_type": "comprehensive_diagnostics",
            "overall_status": "UNKNOWN",
            "services": {},
            "summary": {
                "total_services": 0,
                "healthy_services": 0,
                "services_with_issues": 0,
                "total_issues": 0,
                "total_recommendations": 0
            },
            "recommendations": []
        }
        
        # Database diagnostics
        db_diagnosis = self.diagnose_database_connectivity(db_config)
        report["services"]["database"] = db_diagnosis
        
        # Redis diagnostics
        redis_diagnosis = self.diagnose_redis_connectivity(redis_host, redis_port)
        report["services"]["redis"] = redis_diagnosis
        
        # Calculate summary
        services = [db_diagnosis, redis_diagnosis]
        report["summary"]["total_services"] = len(services)
        
        for service in services:
            if service["status"] == "HEALTHY":
                report["summary"]["healthy_services"] += 1
            else:
                report["summary"]["services_with_issues"] += 1
            
            report["summary"]["total_issues"] += len(service["issues_found"])
            report["recommendations"].extend(service["recommendations"])
        
        report["summary"]["total_recommendations"] = len(report["recommendations"])
        
        # Determine overall status
        if report["summary"]["services_with_issues"] == 0:
            report["overall_status"] = "ALL_HEALTHY"
        elif report["summary"]["healthy_services"] == 0:
            report["overall_status"] = "ALL_ISSUES"
        else:
            report["overall_status"] = "MIXED"
        
        self.logger.info(f"Comprehensive diagnostic report completed", 
                        context={
                            "overall_status": report["overall_status"],
                            "healthy_services": report["summary"]["healthy_services"],
                            "services_with_issues": report["summary"]["services_with_issues"]
                        })
        
        return report


# Global instances for easy access
diagnostic_logger = StructuredLogger()
environment_validator = EnvironmentValidator(diagnostic_logger)
diagnostic_functions = DiagnosticFunctions(diagnostic_logger)
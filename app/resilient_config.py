#!/usr/bin/env python3
"""
Configuration management for Resilient Orchestrator

This module provides configuration utilities for the resilient orchestrator,
including environment variable parsing and validation.
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResilientConfig:
    """Complete configuration for resilient orchestrator"""

    # Heartbeat monitoring
    heartbeat_timeout_seconds: int = 300  # 5 minutes
    heartbeat_warning_threshold_seconds: int = 120  # 2 minutes
    heartbeat_check_interval_seconds: int = 30
    emergency_threshold_seconds: int = 600  # 10 minutes
    max_missed_heartbeats: int = 3

    # Failure recovery
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5
    exponential_backoff: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    emergency_recovery_enabled: bool = True

    # System health monitoring
    health_check_interval_seconds: int = 60
    failure_recovery_interval_seconds: int = 120
    critical_failure_retention_hours: int = 24

    # Performance thresholds
    max_instance_failure_rate: float = 0.1  # 10% failure rate threshold
    min_active_instance_ratio: float = 0.5  # 50% minimum active instances
    max_capacity_utilization: float = 0.9  # 90% maximum capacity utilization


def load_resilient_config() -> ResilientConfig:
    """
    Load resilient orchestrator configuration from environment variables.

    Returns:
        ResilientConfig object with values from environment or defaults
    """
    try:
        config = ResilientConfig(
            # Heartbeat monitoring configuration
            heartbeat_timeout_seconds=int(os.getenv("HEARTBEAT_TIMEOUT", "300")),
            heartbeat_warning_threshold_seconds=int(
                os.getenv("HEARTBEAT_WARNING_THRESHOLD", "120")
            ),
            heartbeat_check_interval_seconds=int(
                os.getenv("HEARTBEAT_CHECK_INTERVAL", "30")
            ),
            emergency_threshold_seconds=int(os.getenv("EMERGENCY_THRESHOLD", "600")),
            max_missed_heartbeats=int(os.getenv("MAX_MISSED_HEARTBEATS", "3")),
            # Failure recovery configuration
            max_retry_attempts=int(os.getenv("MAX_RETRY_ATTEMPTS", "3")),
            retry_delay_seconds=int(os.getenv("RETRY_DELAY_SECONDS", "5")),
            exponential_backoff=os.getenv("EXPONENTIAL_BACKOFF", "true").lower()
            == "true",
            circuit_breaker_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
            circuit_breaker_timeout_seconds=int(
                os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60")
            ),
            emergency_recovery_enabled=os.getenv(
                "EMERGENCY_RECOVERY_ENABLED", "true"
            ).lower()
            == "true",
            # System health monitoring configuration
            health_check_interval_seconds=int(os.getenv("HEALTH_CHECK_INTERVAL", "60")),
            failure_recovery_interval_seconds=int(
                os.getenv("FAILURE_RECOVERY_INTERVAL", "120")
            ),
            critical_failure_retention_hours=int(
                os.getenv("CRITICAL_FAILURE_RETENTION_HOURS", "24")
            ),
            # Performance thresholds
            max_instance_failure_rate=float(
                os.getenv("MAX_INSTANCE_FAILURE_RATE", "0.1")
            ),
            min_active_instance_ratio=float(
                os.getenv("MIN_ACTIVE_INSTANCE_RATIO", "0.5")
            ),
            max_capacity_utilization=float(
                os.getenv("MAX_CAPACITY_UTILIZATION", "0.9")
            ),
        )

        # Validate configuration
        validate_resilient_config(config)

        logger.info("Resilient orchestrator configuration loaded successfully")
        return config

    except Exception as e:
        logger.error(f"Error loading resilient configuration: {e}")
        logger.info("Using default resilient configuration")
        return ResilientConfig()


def validate_resilient_config(config: ResilientConfig) -> bool:
    """
    Validate resilient orchestrator configuration.

    Args:
        config: ResilientConfig object to validate

    Returns:
        True if configuration is valid, False otherwise
    """
    errors = []

    # Validate heartbeat configuration
    if config.heartbeat_timeout_seconds <= 0:
        errors.append("heartbeat_timeout_seconds must be positive")

    if config.heartbeat_warning_threshold_seconds >= config.heartbeat_timeout_seconds:
        errors.append(
            "heartbeat_warning_threshold_seconds must be less than heartbeat_timeout_seconds"
        )

    if config.heartbeat_check_interval_seconds <= 0:
        errors.append("heartbeat_check_interval_seconds must be positive")

    if config.emergency_threshold_seconds <= config.heartbeat_timeout_seconds:
        errors.append(
            "emergency_threshold_seconds must be greater than heartbeat_timeout_seconds"
        )

    # Validate failure recovery configuration
    if config.max_retry_attempts < 0:
        errors.append("max_retry_attempts must be non-negative")

    if config.retry_delay_seconds <= 0:
        errors.append("retry_delay_seconds must be positive")

    if config.circuit_breaker_threshold <= 0:
        errors.append("circuit_breaker_threshold must be positive")

    if config.circuit_breaker_timeout_seconds <= 0:
        errors.append("circuit_breaker_timeout_seconds must be positive")

    # Validate performance thresholds
    if not (0.0 <= config.max_instance_failure_rate <= 1.0):
        errors.append("max_instance_failure_rate must be between 0.0 and 1.0")

    if not (0.0 <= config.min_active_instance_ratio <= 1.0):
        errors.append("min_active_instance_ratio must be between 0.0 and 1.0")

    if not (0.0 <= config.max_capacity_utilization <= 1.0):
        errors.append("max_capacity_utilization must be between 0.0 and 1.0")

    # Validate monitoring intervals
    if config.health_check_interval_seconds <= 0:
        errors.append("health_check_interval_seconds must be positive")

    if config.failure_recovery_interval_seconds <= 0:
        errors.append("failure_recovery_interval_seconds must be positive")

    if config.critical_failure_retention_hours <= 0:
        errors.append("critical_failure_retention_hours must be positive")

    if errors:
        logger.error(f"Resilient configuration validation errors: {errors}")
        return False

    logger.info("Resilient configuration validation passed")
    return True


def get_environment_config_summary() -> Dict:
    """
    Get summary of current environment configuration for resilient orchestrator.

    Returns:
        Dictionary with current environment variable values
    """
    return {
        "heartbeat": {
            "HEARTBEAT_TIMEOUT": os.getenv("HEARTBEAT_TIMEOUT", "300"),
            "HEARTBEAT_WARNING_THRESHOLD": os.getenv(
                "HEARTBEAT_WARNING_THRESHOLD", "120"
            ),
            "HEARTBEAT_CHECK_INTERVAL": os.getenv("HEARTBEAT_CHECK_INTERVAL", "30"),
            "EMERGENCY_THRESHOLD": os.getenv("EMERGENCY_THRESHOLD", "600"),
            "MAX_MISSED_HEARTBEATS": os.getenv("MAX_MISSED_HEARTBEATS", "3"),
        },
        "recovery": {
            "MAX_RETRY_ATTEMPTS": os.getenv("MAX_RETRY_ATTEMPTS", "3"),
            "RETRY_DELAY_SECONDS": os.getenv("RETRY_DELAY_SECONDS", "5"),
            "EXPONENTIAL_BACKOFF": os.getenv("EXPONENTIAL_BACKOFF", "true"),
            "CIRCUIT_BREAKER_THRESHOLD": os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"),
            "CIRCUIT_BREAKER_TIMEOUT": os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"),
            "EMERGENCY_RECOVERY_ENABLED": os.getenv(
                "EMERGENCY_RECOVERY_ENABLED", "true"
            ),
        },
        "monitoring": {
            "HEALTH_CHECK_INTERVAL": os.getenv("HEALTH_CHECK_INTERVAL", "60"),
            "FAILURE_RECOVERY_INTERVAL": os.getenv("FAILURE_RECOVERY_INTERVAL", "120"),
            "CRITICAL_FAILURE_RETENTION_HOURS": os.getenv(
                "CRITICAL_FAILURE_RETENTION_HOURS", "24"
            ),
        },
        "thresholds": {
            "MAX_INSTANCE_FAILURE_RATE": os.getenv("MAX_INSTANCE_FAILURE_RATE", "0.1"),
            "MIN_ACTIVE_INSTANCE_RATIO": os.getenv("MIN_ACTIVE_INSTANCE_RATIO", "0.5"),
            "MAX_CAPACITY_UTILIZATION": os.getenv("MAX_CAPACITY_UTILIZATION", "0.9"),
        },
    }


def create_sample_env_file(filename: str = ".env.resilient") -> bool:
    """
    Create a sample environment file with resilient orchestrator configuration.

    Args:
        filename: Name of the environment file to create

    Returns:
        True if file was created successfully, False otherwise
    """
    try:
        sample_config = """# Resilient Orchestrator Configuration

# Heartbeat Monitoring
HEARTBEAT_TIMEOUT=300
HEARTBEAT_WARNING_THRESHOLD=120
HEARTBEAT_CHECK_INTERVAL=30
EMERGENCY_THRESHOLD=600
MAX_MISSED_HEARTBEATS=3

# Failure Recovery
MAX_RETRY_ATTEMPTS=3
RETRY_DELAY_SECONDS=5
EXPONENTIAL_BACKOFF=true
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60
EMERGENCY_RECOVERY_ENABLED=true

# System Health Monitoring
HEALTH_CHECK_INTERVAL=60
FAILURE_RECOVERY_INTERVAL=120
CRITICAL_FAILURE_RETENTION_HOURS=24

# Performance Thresholds
MAX_INSTANCE_FAILURE_RATE=0.1
MIN_ACTIVE_INSTANCE_RATIO=0.5
MAX_CAPACITY_UTILIZATION=0.9
"""

        with open(filename, "w") as f:
            f.write(sample_config)

        logger.info(f"Sample resilient configuration file created: {filename}")
        return True

    except Exception as e:
        logger.error(f"Error creating sample configuration file: {e}")
        return False


if __name__ == "__main__":
    # Test configuration loading
    config = load_resilient_config()
    print("Loaded configuration:")
    print(f"  Heartbeat timeout: {config.heartbeat_timeout_seconds}s")
    print(f"  Emergency threshold: {config.emergency_threshold_seconds}s")
    print(f"  Max retry attempts: {config.max_retry_attempts}")
    print(f"  Circuit breaker threshold: {config.circuit_breaker_threshold}")
    print(f"  Emergency recovery enabled: {config.emergency_recovery_enabled}")

    # Create sample environment file
    create_sample_env_file()

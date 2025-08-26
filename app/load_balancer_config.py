"""
Configuration for Smart Load Balancer
Provides configurable settings for load balancing algorithm
"""

import os
from typing import Optional

from smart_load_balancer import LoadBalanceConfig


def create_load_balance_config() -> LoadBalanceConfig:
    """
    Create load balance configuration from environment variables.
    
    Returns:
        LoadBalanceConfig with settings from environment or defaults
    """
    config = LoadBalanceConfig()
    
    # Thresholds
    config.imbalance_threshold = float(os.getenv("LOAD_IMBALANCE_THRESHOLD", "0.20"))
    config.max_stream_difference = int(os.getenv("MAX_STREAM_DIFFERENCE", "2"))
    config.performance_threshold = float(os.getenv("PERFORMANCE_THRESHOLD", "0.3"))
    
    # Migration settings
    config.max_migrations_per_cycle = int(os.getenv("MAX_MIGRATIONS_PER_CYCLE", "10"))
    config.migration_batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "3"))
    config.migration_delay_seconds = int(os.getenv("MIGRATION_DELAY_SECONDS", "5"))
    
    # Safety limits
    config.min_instances_for_rebalance = int(os.getenv("MIN_INSTANCES_FOR_REBALANCE", "2"))
    config.max_load_factor = float(os.getenv("MAX_LOAD_FACTOR", "0.9"))
    config.emergency_threshold = float(os.getenv("EMERGENCY_THRESHOLD", "0.95"))
    
    return config


def get_rebalance_intervals() -> dict:
    """Get rebalancing interval configurations"""
    return {
        "smart_rebalance_interval": int(os.getenv("SMART_REBALANCE_INTERVAL", "300")),  # 5 minutes
        "consistency_check_interval": int(os.getenv("CONSISTENCY_CHECK_INTERVAL", "180")),  # 3 minutes
        "performance_monitor_interval": int(os.getenv("PERFORMANCE_MONITOR_INTERVAL", "60")),  # 1 minute
        "min_rebalance_interval": int(os.getenv("MIN_REBALANCE_INTERVAL", "60"))  # 1 minute minimum
    }


def validate_config(config: LoadBalanceConfig) -> bool:
    """
    Validate load balance configuration.
    
    Args:
        config: LoadBalanceConfig to validate
        
    Returns:
        True if configuration is valid, False otherwise
    """
    if config.imbalance_threshold <= 0 or config.imbalance_threshold > 1.0:
        return False
    
    if config.max_stream_difference < 1:
        return False
    
    if config.performance_threshold <= 0 or config.performance_threshold > 1.0:
        return False
    
    if config.max_migrations_per_cycle < 1:
        return False
    
    if config.migration_batch_size < 1:
        return False
    
    if config.migration_delay_seconds < 0:
        return False
    
    if config.min_instances_for_rebalance < 2:
        return False
    
    if config.max_load_factor <= 0 or config.max_load_factor > 1.0:
        return False
    
    if config.emergency_threshold <= config.max_load_factor or config.emergency_threshold > 1.0:
        return False
    
    return True


# Default configuration values for documentation
DEFAULT_CONFIG = {
    "LOAD_IMBALANCE_THRESHOLD": "0.20",  # 20% difference triggers rebalancing
    "MAX_STREAM_DIFFERENCE": "2",        # Max difference in stream count from average
    "PERFORMANCE_THRESHOLD": "0.3",      # Minimum performance score (0.0-1.0)
    "MAX_MIGRATIONS_PER_CYCLE": "10",    # Maximum migrations per rebalancing cycle
    "MIGRATION_BATCH_SIZE": "3",         # Streams to migrate in each batch
    "MIGRATION_DELAY_SECONDS": "5",      # Delay between migration batches
    "MIN_INSTANCES_FOR_REBALANCE": "2",  # Minimum instances required for rebalancing
    "MAX_LOAD_FACTOR": "0.9",            # Don't assign to instances above 90% capacity
    "EMERGENCY_THRESHOLD": "0.95",       # Emergency rebalancing at 95% capacity
    "SMART_REBALANCE_INTERVAL": "300",   # Auto-rebalancing check interval (seconds)
    "CONSISTENCY_CHECK_INTERVAL": "180", # Consistency check interval (seconds)
    "PERFORMANCE_MONITOR_INTERVAL": "60", # Performance monitoring interval (seconds)
    "MIN_REBALANCE_INTERVAL": "60"       # Minimum time between rebalancing operations
}
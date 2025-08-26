#!/usr/bin/env python3
"""
Resilient Database Operations with Retry Logic

This module provides database operations with exponential backoff retry logic,
connection management, and error handling for enhanced reliability.

Author: Sistema de Fingerprinting
Date: 2024
"""

import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.errors
from db_pool import get_db_pool

logger = logging.getLogger(__name__)


@dataclass
class DatabaseRetryConfig:
    """Configuration for database retry logic."""
    max_attempts: int = 3
    base_delay: float = 0.5  # Base delay in seconds
    max_delay: float = 30.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff base
    jitter: bool = True  # Add random jitter to delays
    
    # Specific timeouts
    connection_timeout: int = 30  # Connection timeout in seconds
    query_timeout: int = 60  # Query timeout in seconds
    
    # Retryable error types
    retryable_errors: Tuple[type, ...] = (
        psycopg2.OperationalError
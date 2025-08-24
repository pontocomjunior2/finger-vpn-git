#!/usr/bin/env python3
"""
Shim module for tests expecting a Windows-specific fingerv7 interface.
Provides small wrappers around functions/constants from fingerv7.py
so tests like test_implementation.py can import and mock them.

All functions follow async signatures expected by the tests, wrapping
synchronous implementations from fingerv7 when necessary.
"""
from __future__ import annotations

import os
from typing import Optional

# Import core functions and values from the main implementation
from fingerv7 import (
    consistent_hash,
    acquire_stream_lock as _acquire_stream_lock,
    release_stream_lock as _release_stream_lock,
    get_assigned_server as _get_assigned_server,
    SERVER_ID as _BASE_SERVER_ID,
    TOTAL_SERVERS as _BASE_TOTAL_SERVERS,
)


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


# Expose mutable constants that tests can override
SERVER_ID: int = _to_int(os.getenv("SERVER_ID", _BASE_SERVER_ID), 1)
TOTAL_SERVERS: int = _to_int(os.getenv("TOTAL_SERVERS", _BASE_TOTAL_SERVERS), 1)


def should_process_stream(
    stream_id: str, server_id: Optional[int] = None, total_servers: Optional[int] = None
) -> bool:
    """Return True if the given stream_id should be processed by server_id.

    Uses consistent hashing so exactly one server is selected among total_servers.
    Defaults to module-level SERVER_ID and TOTAL_SERVERS if not provided.
    """
    sid = _to_int(server_id if server_id is not None else SERVER_ID, SERVER_ID)
    buckets = _to_int(
        total_servers if total_servers is not None else TOTAL_SERVERS, TOTAL_SERVERS
    )
    if buckets <= 0:
        return False
    try:
        return (consistent_hash(str(stream_id), buckets) + 1) == sid
    except Exception:
        return False


async def acquire_stream_lock(stream_id: str, server_id: int, timeout: int = 30) -> bool:
    """Async wrapper around fingerv7.acquire_stream_lock (sync).

    The base implementation expects timeout in minutes; we just use its default.
    """
    # Convert to string to stay compatible with DB layer expectations
    return _acquire_stream_lock(str(stream_id), str(server_id))


async def release_stream_lock(stream_id: str, server_id: int) -> bool:
    """Async wrapper around fingerv7.release_stream_lock (sync)."""
    return _release_stream_lock(str(stream_id), str(server_id))


async def check_stream_ownership(stream_id: str, server_id: int) -> bool:
    """Check if the provided server_id is the owner/assignee of stream_id.

    Attempts DB-backed ownership via get_assigned_server, with a fallback
    to consistent hashing when necessary.
    """
    try:
        assigned = _get_assigned_server(str(stream_id))
        return _to_int(assigned, -1) == _to_int(server_id, -2)
    except Exception:
        # Fallback to consistent hash when DB lookup fails
        return should_process_stream(stream_id, server_id, TOTAL_SERVERS)


__all__ = [
    "should_process_stream",
    "acquire_stream_lock",
    "release_stream_lock",
    "check_stream_ownership",
    "SERVER_ID",
    "TOTAL_SERVERS",
]
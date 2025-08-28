# Ensure local modules in this folder are importable as top-level modules in tests
# This helps with `from orchestrator_client import ...` and similar imports
# regardless of how pytest sets the rootdir or Python path.
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Optionally, load .env if present to mimic runtime environment
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(dotenv_path=HERE / ".env")
except Exception:
    pass

import pytest
import json

@pytest.fixture(scope="session")
def postgres_config():
    """Pytest fixture for the database configuration."""
    config_str = os.getenv(
        "POSTGRES_CONFIG",
        '{"host": "localhost", "port": 5432, "user": "postgres", "password": "password", "dbname": "test_db"}',
    )
    return json.loads(config_str)

@pytest.fixture(scope="session")
def smart_load_balancer():
    """Pytest fixture for the SmartLoadBalancer."""
    # This avoids importing the class at collection time
    from smart_load_balancer import SmartLoadBalancer
    return SmartLoadBalancer

#!/usr/bin/env python3
"""
Simple Startup Validation Script

A lightweight script to quickly validate that the orchestrator startup
sequence is working correctly. This can be used for quick checks during
development or as part of CI/CD pipelines.

Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4
"""

import os
import sys
import time
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

def check_environment_variables():
    """Check that required environment variables are set."""
    print("Checking environment variables...")
    
    required_vars = [
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "REDIS_HOST", "REDIS_PORT"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"X Missing environment variables: {missing_vars}")
        return False
    
    print("+ All required environment variables are set")
    return True

def test_postgres_connection():
    """Test PostgreSQL connection."""
    print("Testing PostgreSQL connection...")
    
    try:
        import psycopg2
        
        config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME", "orchestrator"),
            "user": os.getenv("DB_USER", "orchestrator_user"),
            "password": os.getenv("DB_PASSWORD", "orchestrator_pass")
        }
        
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result and result[0] == 1:
            print("+ PostgreSQL connection successful")
            return True
        else:
            print("X PostgreSQL connection test failed")
            return False
            
    except Exception as e:
        print(f"X PostgreSQL connection failed: {e}")
        return False

def test_redis_connection():
    """Test Redis connection."""
    print("Testing Redis connection...")
    
    try:
        import redis
        
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            socket_connect_timeout=5
        )
        
        # Test ping
        ping_result = redis_client.ping()
        
        # Test set/get
        test_key = f"startup_validation_{int(time.time())}"
        redis_client.set(test_key, "test_value", ex=60)
        retrieved = redis_client.get(test_key)
        redis_client.delete(test_key)
        redis_client.close()
        
        if ping_result and retrieved and retrieved.decode() == "test_value":
            print("+ Redis connection and functionality test successful")
            return True
        else:
            print("X Redis functionality test failed")
            return False
            
    except Exception as e:
        print(f"X Redis connection failed: {e}")
        return False

def test_orchestrator_functions():
    """Test orchestrator module functions."""
    print("Testing orchestrator module functions...")
    
    try:
        from orchestrator import wait_for_postgres, wait_for_redis, setup_database
        
        # Test wait_for_postgres
        postgres_result = wait_for_postgres(
            os.getenv("DB_HOST", "localhost"),
            int(os.getenv("DB_PORT", 5432)),
            timeout=10
        )
        
        if not postgres_result:
            print("X wait_for_postgres failed")
            return False
        
        # Test wait_for_redis
        redis_result = wait_for_redis(
            os.getenv("REDIS_HOST", "localhost"),
            int(os.getenv("REDIS_PORT", 6379)),
            timeout=10
        )
        
        if not redis_result:
            print("X wait_for_redis failed")
            return False
        
        print("+ Orchestrator functions test successful")
        return True
        
    except Exception as e:
        print(f"X Orchestrator functions test failed: {e}")
        return False

def test_health_endpoint():
    """Test health endpoint if application is running."""
    print("Testing health endpoint...")
    
    try:
        import requests
        
        app_host = os.getenv("APP_HOST", "localhost")
        app_port = os.getenv("APP_PORT", "8000")
        health_url = f"http://{app_host}:{app_port}/health"
        
        response = requests.get(health_url, timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            if "status" in health_data and "services" in health_data:
                print("+ Health endpoint test successful")
                print(f"  Status: {health_data.get('status')}")
                print(f"  Services: {len(health_data.get('services', {}))}")
                return True
            else:
                print("X Health endpoint returned invalid format")
                return False
        else:
            print(f"X Health endpoint returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("! Health endpoint not accessible (application may not be running)")
        return None  # Not a failure, just not running
    except Exception as e:
        print(f"X Health endpoint test failed: {e}")
        return False

def main():
    """Run simple startup validation."""
    print("=" * 60)
    print("ORCHESTRATOR STARTUP VALIDATION (SIMPLE)")
    print("=" * 60)
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Environment Variables", check_environment_variables),
        ("PostgreSQL Connection", test_postgres_connection),
        ("Redis Connection", test_redis_connection),
        ("Orchestrator Functions", test_orchestrator_functions),
        ("Health Endpoint", test_health_endpoint)
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            result = test_func()
            if result is True:
                passed += 1
            elif result is False:
                failed += 1
            else:  # None means skipped
                skipped += 1
        except Exception as e:
            print(f"X {test_name} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")
    print()
    
    if failed == 0:
        print("+ ALL TESTS PASSED! Orchestrator startup validation successful.")
        print("\nThe orchestrator is ready for use:")
        print("  - PostgreSQL is accessible and functional")
        print("  - Redis is accessible and functional")
        print("  - Orchestrator functions are working")
        if skipped == 0:
            print("  - Health endpoint is responding correctly")
        print()
        return True
    else:
        print(f"X {failed} TEST(S) FAILED! Please review the issues above.")
        print("\nCommon solutions:")
        print("  - Ensure PostgreSQL and Redis services are running")
        print("  - Check environment variables are properly set")
        print("  - Verify network connectivity and credentials")
        print("  - Review service logs for detailed error information")
        print()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
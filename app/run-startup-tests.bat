@echo off
REM Startup Validation Test Runner for Windows
REM This script runs the orchestrator startup validation tests

echo ===============================================================================
echo ORCHESTRATOR STARTUP VALIDATION TEST RUNNER
echo ===============================================================================
echo Started at: %date% %time%
echo.

REM Set default environment variables if not set
if not defined DB_HOST set DB_HOST=localhost
if not defined DB_PORT set DB_PORT=5432
if not defined DB_NAME set DB_NAME=orchestrator
if not defined DB_USER set DB_USER=orchestrator_user
if not defined DB_PASSWORD set DB_PASSWORD=orchestrator_pass
if not defined REDIS_HOST set REDIS_HOST=localhost
if not defined REDIS_PORT set REDIS_PORT=6379
if not defined APP_HOST set APP_HOST=localhost
if not defined APP_PORT set APP_PORT=8000

echo Configuration:
echo   Database: %DB_USER%@%DB_HOST%:%DB_PORT%/%DB_NAME%
echo   Redis: %REDIS_HOST%:%REDIS_PORT%
echo   Application: %APP_HOST%:%APP_PORT%
echo.

REM Change to script directory
cd /d "%~dp0"

REM Run Python test suite
echo Running Python startup validation tests...
python test_startup_validation.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===============================================================================
    echo STARTUP VALIDATION TESTS COMPLETED SUCCESSFULLY
    echo ===============================================================================
    echo All tests passed! The orchestrator startup sequence is working correctly.
    exit /b 0
) else (
    echo.
    echo ===============================================================================
    echo STARTUP VALIDATION TESTS FAILED
    echo ===============================================================================
    echo Some tests failed. Please review the output above for details.
    exit /b 1
)
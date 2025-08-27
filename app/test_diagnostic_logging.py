#!/usr/bin/env python3
"""
Test script for comprehensive error logging and diagnostics functionality.

This script tests all the diagnostic logging features implemented in task 6:
- Structured logging with timestamps
- Detailed error messages with context and suggested solutions
- Diagnostic functions for troubleshooting common issues
- Environment variable validation and reporting

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Add app directory to path
sys.path.append(str(Path(__file__).parent))

from diagnostic_logger import diagnostic_logger, environment_validator, diagnostic_functions
from orchestrator import DB_CONFIG, validate_startup_environment, verify_services


def test_structured_logging():
    """Test structured logging functionality."""
    print("\n" + "="*60)
    print("TESTING STRUCTURED LOGGING")
    print("="*60)
    
    diagnostic_logger.set_phase("TESTING")
    
    # Test different log levels with context
    diagnostic_logger.info("Testing info logging", context={"test_type": "info", "component": "logger"})
    
    diagnostic_logger.warning("Testing warning logging", 
                             context={"test_type": "warning", "severity": "medium"},
                             suggested_solution="This is a test warning - no action needed")
    
    # Test error logging with exception
    try:
        raise ValueError("This is a test exception")
    except Exception as e:
        diagnostic_logger.error("Testing error logging with exception", 
                               context={"test_type": "error", "component": "exception_handler"},
                               exception=e,
                               suggested_solution="This is a test error - no action needed")
    
    diagnostic_logger.success("Structured logging test completed")
    diagnostic_logger.step("Moving to next test phase")
    
    print("✓ Structured logging test completed")


def test_environment_validation():
    """Test environment variable validation."""
    print("\n" + "="*60)
    print("TESTING ENVIRONMENT VALIDATION")
    print("="*60)
    
    # Run comprehensive environment validation
    validation_result = environment_validator.validate_all()
    
    print(f"Overall Status: {validation_result['overall_status']}")
    print(f"Categories Checked: {len(validation_result['categories'])}")
    print(f"Total Issues: {len(validation_result['issues'])}")
    print(f"Total Warnings: {len(validation_result['warnings'])}")
    print(f"Total Recommendations: {len(validation_result['recommendations'])}")
    
    # Display category results
    for category_name, category_data in validation_result['categories'].items():
        print(f"\n{category_name.upper()}: {category_data['status']}")
        if category_data.get('issues'):
            for issue in category_data['issues']:
                print(f"  ❌ {issue}")
        if category_data.get('warnings'):
            for warning in category_data['warnings']:
                print(f"  ⚠️  {warning}")
    
    # Display recommendations
    if validation_result['recommendations']:
        print("\nRECOMMENDATIONS:")
        for rec in validation_result['recommendations']:
            print(f"  💡 {rec}")
    
    print("✓ Environment validation test completed")
    return validation_result


def test_database_diagnostics():
    """Test database diagnostic functions."""
    print("\n" + "="*60)
    print("TESTING DATABASE DIAGNOSTICS")
    print("="*60)
    
    # Run database diagnostics
    db_diagnosis = diagnostic_functions.diagnose_database_connectivity(DB_CONFIG)
    
    print(f"Database Status: {db_diagnosis['status']}")
    print(f"Tests Performed: {len(db_diagnosis['tests'])}")
    print(f"Issues Found: {len(db_diagnosis['issues_found'])}")
    
    # Display test results
    for test_name, test_result in db_diagnosis['tests'].items():
        status_icon = "✓" if test_result['status'] == "PASSED" else "❌" if test_result['status'] == "FAILED" else "⏭️"
        print(f"  {status_icon} {test_result['name']}: {test_result['status']}")
        
        if test_result['status'] == "FAILED" and test_result.get('error'):
            print(f"    Error: {test_result['error']}")
            if test_result['details'].get('suggestion'):
                print(f"    Suggestion: {test_result['details']['suggestion']}")
    
    # Display recommendations
    if db_diagnosis['recommendations']:
        print("\nDATABASE RECOMMENDATIONS:")
        for rec in db_diagnosis['recommendations']:
            print(f"  💡 {rec}")
    
    print("✓ Database diagnostics test completed")
    return db_diagnosis


def test_redis_diagnostics():
    """Test Redis diagnostic functions."""
    print("\n" + "="*60)
    print("TESTING REDIS DIAGNOSTICS")
    print("="*60)
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    # Run Redis diagnostics
    redis_diagnosis = diagnostic_functions.diagnose_redis_connectivity(redis_host, redis_port)
    
    print(f"Redis Status: {redis_diagnosis['status']}")
    print(f"Tests Performed: {len(redis_diagnosis['tests'])}")
    print(f"Issues Found: {len(redis_diagnosis['issues_found'])}")
    
    # Display test results
    for test_name, test_result in redis_diagnosis['tests'].items():
        status_icon = "✓" if test_result['status'] == "PASSED" else "❌" if test_result['status'] == "FAILED" else "⏭️"
        print(f"  {status_icon} {test_result['name']}: {test_result['status']}")
        
        if test_result['status'] == "FAILED" and test_result.get('error'):
            print(f"    Error: {test_result['error']}")
            if test_result['details'].get('suggestion'):
                print(f"    Suggestion: {test_result['details']['suggestion']}")
    
    # Display recommendations
    if redis_diagnosis['recommendations']:
        print("\nREDIS RECOMMENDATIONS:")
        for rec in redis_diagnosis['recommendations']:
            print(f"  💡 {rec}")
    
    print("✓ Redis diagnostics test completed")
    return redis_diagnosis


def test_comprehensive_report():
    """Test comprehensive diagnostic report generation."""
    print("\n" + "="*60)
    print("TESTING COMPREHENSIVE DIAGNOSTIC REPORT")
    print("="*60)
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    # Generate comprehensive report
    report = diagnostic_functions.generate_comprehensive_report(DB_CONFIG, redis_host, redis_port)
    
    print(f"Overall Status: {report['overall_status']}")
    print(f"Total Services: {report['summary']['total_services']}")
    print(f"Healthy Services: {report['summary']['healthy_services']}")
    print(f"Services with Issues: {report['summary']['services_with_issues']}")
    print(f"Total Issues: {report['summary']['total_issues']}")
    print(f"Total Recommendations: {report['summary']['total_recommendations']}")
    
    # Display service status
    for service_name, service_data in report['services'].items():
        status_icon = "✓" if service_data['status'] == "HEALTHY" else "❌"
        print(f"  {status_icon} {service_name.upper()}: {service_data['status']}")
    
    print("✓ Comprehensive diagnostic report test completed")
    return report


def test_startup_validation():
    """Test startup environment validation."""
    print("\n" + "="*60)
    print("TESTING STARTUP ENVIRONMENT VALIDATION")
    print("="*60)
    
    # Run startup validation
    validation_report = validate_startup_environment()
    
    print(f"Overall Status: {validation_report['overall_status']}")
    print(f"Critical Issues: {len(validation_report['critical_issues'])}")
    print(f"Warnings: {len(validation_report['warnings'])}")
    print(f"Recommendations: {len(validation_report['recommendations'])}")
    
    # Display critical issues
    if validation_report['critical_issues']:
        print("\nCRITICAL ISSUES:")
        for issue in validation_report['critical_issues']:
            print(f"  ❌ {issue}")
    
    # Display warnings
    if validation_report['warnings']:
        print("\nWARNINGS:")
        for warning in validation_report['warnings']:
            print(f"  ⚠️  {warning}")
    
    print("✓ Startup environment validation test completed")
    return validation_report


def test_enhanced_service_verification():
    """Test enhanced service verification with diagnostic logging."""
    print("\n" + "="*60)
    print("TESTING ENHANCED SERVICE VERIFICATION")
    print("="*60)
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    # Run service verification
    service_status = verify_services(DB_CONFIG, redis_host, redis_port)
    
    print(f"Overall Status: {service_status['overall_status']}")
    print(f"Services Checked: {service_status['verification_details']['services_checked']}")
    print(f"Services Ready: {service_status['verification_details']['services_ready']}")
    print(f"Services Failed: {service_status['verification_details']['services_failed']}")
    
    # Display service details
    for service_name, service_data in service_status['services'].items():
        status_icon = "✓" if service_data['status'] == "ready" else "❌"
        print(f"  {status_icon} {service_data['name']}: {service_data['status']}")
        
        if service_data.get('details'):
            for key, value in service_data['details'].items():
                if key != 'version':  # Don't show full version string
                    print(f"    {key}: {value}")
    
    # Display errors
    if service_status['errors']:
        print("\nERRORS:")
        for error in service_status['errors']:
            print(f"  ❌ {error}")
    
    print("✓ Enhanced service verification test completed")
    return service_status


def save_test_results(results: dict):
    """Save test results to file for analysis."""
    results_file = Path("/app/logs/diagnostic_test_results.json")
    results_file.parent.mkdir(exist_ok=True)
    
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Test results saved to: {results_file}")


def main():
    """Run all diagnostic logging tests."""
    print("🔍 COMPREHENSIVE ERROR LOGGING AND DIAGNOSTICS TEST SUITE")
    print("=" * 80)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "test_results": {}
    }
    
    try:
        # Test 1: Structured Logging
        test_structured_logging()
        results["test_results"]["structured_logging"] = "PASSED"
        
        # Test 2: Environment Validation
        env_validation = test_environment_validation()
        results["test_results"]["environment_validation"] = {
            "status": "PASSED",
            "overall_status": env_validation["overall_status"],
            "issues_count": len(env_validation["issues"]),
            "warnings_count": len(env_validation["warnings"])
        }
        
        # Test 3: Database Diagnostics
        db_diagnosis = test_database_diagnostics()
        results["test_results"]["database_diagnostics"] = {
            "status": "PASSED",
            "db_status": db_diagnosis["status"],
            "issues_count": len(db_diagnosis["issues_found"])
        }
        
        # Test 4: Redis Diagnostics
        redis_diagnosis = test_redis_diagnostics()
        results["test_results"]["redis_diagnostics"] = {
            "status": "PASSED",
            "redis_status": redis_diagnosis["status"],
            "issues_count": len(redis_diagnosis["issues_found"])
        }
        
        # Test 5: Comprehensive Report
        comprehensive_report = test_comprehensive_report()
        results["test_results"]["comprehensive_report"] = {
            "status": "PASSED",
            "overall_status": comprehensive_report["overall_status"],
            "healthy_services": comprehensive_report["summary"]["healthy_services"],
            "total_services": comprehensive_report["summary"]["total_services"]
        }
        
        # Test 6: Startup Validation
        startup_validation = test_startup_validation()
        results["test_results"]["startup_validation"] = {
            "status": "PASSED",
            "overall_status": startup_validation["overall_status"],
            "critical_issues": len(startup_validation["critical_issues"]),
            "warnings": len(startup_validation["warnings"])
        }
        
        # Test 7: Enhanced Service Verification
        service_verification = test_enhanced_service_verification()
        results["test_results"]["service_verification"] = {
            "status": "PASSED",
            "overall_status": service_verification["overall_status"],
            "services_ready": service_verification["verification_details"]["services_ready"],
            "services_failed": service_verification["verification_details"]["services_failed"]
        }
        
        # Save results
        save_test_results(results)
        
        print("\n" + "="*80)
        print("🎉 ALL DIAGNOSTIC LOGGING TESTS COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        # Summary
        total_tests = len(results["test_results"])
        passed_tests = sum(1 for test in results["test_results"].values() 
                          if (test == "PASSED" or (isinstance(test, dict) and test.get("status") == "PASSED")))
        
        print(f"📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        
        # Check log files
        log_files = [
            "/app/logs/orchestrator_diagnostic.log",
            "/app/logs/orchestrator_structured.jsonl"
        ]
        
        print("\n📁 LOG FILES CREATED:")
        for log_file in log_files:
            if Path(log_file).exists():
                size = Path(log_file).stat().st_size
                print(f"  ✓ {log_file} ({size} bytes)")
            else:
                print(f"  ❌ {log_file} (not found)")
        
        return 0
        
    except Exception as e:
        diagnostic_logger.error("Test suite failed with exception", 
                               exception=e,
                               suggested_solution="Check test setup and dependencies")
        print(f"\n❌ TEST SUITE FAILED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
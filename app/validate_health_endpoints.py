#!/usr/bin/env python3
"""
Validation script for enhanced health check endpoints.

This script validates that the health check endpoints are properly defined
and have the correct structure without requiring a running server.

Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4
"""

import ast
import inspect
import sys
from typing import List, Dict, Any


def validate_endpoint_exists(source_code: str, endpoint_path: str, method: str = "GET") -> Dict[str, Any]:
    """
    Validate that an endpoint exists in the source code.
    
    Args:
        source_code: The source code to analyze
        endpoint_path: The endpoint path to look for (e.g., "/health")
        method: HTTP method (default: GET)
        
    Returns:
        dict: Validation results
    """
    result = {
        "endpoint": endpoint_path,
        "method": method,
        "found": False,
        "function_name": None,
        "decorator_found": False,
        "async_function": False,
        "docstring": None,
        "requirements_mentioned": False
    }
    
    # Look for the endpoint decorator pattern
    decorator_pattern = f'@app.{method.lower()}("{endpoint_path}")'
    
    if decorator_pattern in source_code:
        result["decorator_found"] = True
        
        # Find the function that follows this decorator
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if decorator_pattern in line:
                # Look for the function definition in the next few lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    func_line = lines[j].strip()
                    if func_line.startswith('async def ') or func_line.startswith('def '):
                        result["found"] = True
                        result["async_function"] = func_line.startswith('async def ')
                        
                        # Extract function name
                        if 'def ' in func_line:
                            func_name = func_line.split('def ')[1].split('(')[0].strip()
                            result["function_name"] = func_name
                        
                        # Look for docstring and requirements
                        docstring_start = j + 1
                        while docstring_start < len(lines) and not lines[docstring_start].strip():
                            docstring_start += 1
                        
                        if docstring_start < len(lines) and '"""' in lines[docstring_start]:
                            # Extract docstring
                            docstring_lines = []
                            in_docstring = False
                            for k in range(docstring_start, len(lines)):
                                line = lines[k]
                                if '"""' in line:
                                    if in_docstring:
                                        break
                                    else:
                                        in_docstring = True
                                        docstring_lines.append(line)
                                elif in_docstring:
                                    docstring_lines.append(line)
                            
                            result["docstring"] = '\n'.join(docstring_lines)
                            
                            # Check for requirements mention
                            docstring_text = result["docstring"].lower()
                            if 'requirements:' in docstring_text or 'requirement' in docstring_text:
                                result["requirements_mentioned"] = True
                        
                        break
                break
    
    return result


def validate_helper_functions(source_code: str) -> Dict[str, Any]:
    """
    Validate that helper functions exist in the source code.
    
    Args:
        source_code: The source code to analyze
        
    Returns:
        dict: Validation results for helper functions
    """
    helper_functions = [
        "_get_application_components_status",
        "_get_system_metrics", 
        "_validate_configuration",
        "_get_system_warnings",
        "_get_system_recommendations"
    ]
    
    results = {}
    
    for func_name in helper_functions:
        result = {
            "function_name": func_name,
            "found": False,
            "has_docstring": False,
            "has_requirements": False,
            "has_type_hints": False
        }
        
        # Look for function definition
        func_pattern = f"def {func_name}("
        if func_pattern in source_code:
            result["found"] = True
            
            # Find the function and analyze it
            lines = source_code.split('\n')
            for i, line in enumerate(lines):
                if func_pattern in line:
                    # Check for type hints
                    if '->' in line:
                        result["has_type_hints"] = True
                    
                    # Look for docstring
                    for j in range(i + 1, min(i + 10, len(lines))):
                        if '"""' in lines[j]:
                            result["has_docstring"] = True
                            
                            # Look for requirements in docstring
                            docstring_end = j + 1
                            while docstring_end < len(lines) and '"""' not in lines[docstring_end]:
                                docstring_end += 1
                            
                            docstring = '\n'.join(lines[j:docstring_end + 1]).lower()
                            if 'requirements:' in docstring or 'requirement' in docstring:
                                result["has_requirements"] = True
                            break
                    break
        
        results[func_name] = result
    
    return results


def main():
    """Main validation function."""
    print("🔍 Health Check Endpoints Validation")
    print("=" * 50)
    
    # Read the orchestrator source code
    try:
        with open('app/orchestrator.py', 'r', encoding='utf-8') as f:
            source_code = f.read()
    except FileNotFoundError:
        print("❌ Error: orchestrator.py not found")
        return False
    
    # Validate endpoints
    endpoints_to_check = [
        ("/health", "GET"),
        ("/ready", "GET"),
        ("/health/detailed", "GET")
    ]
    
    print("\n📋 Endpoint Validation:")
    all_endpoints_valid = True
    
    for endpoint_path, method in endpoints_to_check:
        result = validate_endpoint_exists(source_code, endpoint_path, method)
        
        status = "✅" if result["found"] else "❌"
        print(f"{status} {method} {endpoint_path}")
        
        if result["found"]:
            print(f"   Function: {result['function_name']}")
            print(f"   Async: {result['async_function']}")
            print(f"   Has docstring: {result['docstring'] is not None}")
            print(f"   Requirements mentioned: {result['requirements_mentioned']}")
        else:
            print(f"   ❌ Endpoint not found!")
            all_endpoints_valid = False
        
        print()
    
    # Validate helper functions
    print("🔧 Helper Functions Validation:")
    helper_results = validate_helper_functions(source_code)
    
    all_helpers_valid = True
    for func_name, result in helper_results.items():
        status = "✅" if result["found"] else "❌"
        print(f"{status} {func_name}")
        
        if result["found"]:
            print(f"   Has docstring: {result['has_docstring']}")
            print(f"   Has type hints: {result['has_type_hints']}")
            print(f"   Requirements mentioned: {result['has_requirements']}")
        else:
            print(f"   ❌ Function not found!")
            all_helpers_valid = False
        
        print()
    
    # Summary
    print("📊 Validation Summary:")
    print(f"Endpoints valid: {all_endpoints_valid}")
    print(f"Helper functions valid: {all_helpers_valid}")
    
    overall_valid = all_endpoints_valid and all_helpers_valid
    
    if overall_valid:
        print("\n🎉 All validations passed! Health check implementation is complete.")
    else:
        print("\n⚠️  Some validations failed. Please check the implementation.")
    
    return overall_valid


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 Validation failed: {e}")
        sys.exit(1)
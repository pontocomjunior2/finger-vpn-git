#!/usr/bin/env python3
"""
Task 10 Completion Validation

This script validates that Task 10 (Integrate all components and perform end-to-end testing)
has been completed successfully by testing all integration requirements.

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration_system import (EndToEndTestSuite, IntegratedOrchestrator,
                                IntegrationStatus)

logger = logging.getLogger(__name__)


class Task10Validator:
    """Validates completion of Task 10 requirements"""
    
    def __init__(self):
        self.validation_results = []
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'orchestrator'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
    
    async def validate_component_wiring(self) -> Dict[str, Any]:
        """Validate that all enhanced components are properly wired together"""
        logger.info("Validating component wiring...")
        
        result = {
            'test_name': 'Component Wiring',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            orchestrator = IntegratedOrchestrator(self.db_config)
            
            # Initialize components
            init_success = await orchestrator.initialize_components()
            result['details']['initialization_success'] = init_success
            
            if not init_success:
                result['success'] = False
                result['errors'].append("Component initialization failed")
                return result
            
            # Check that all required components are wired
            required_components = [
                'db_manager', 'error_handler', 'enhanced_orchestrator',
                'resilient_orchestrator', 'consistency_checker',
                'monitoring_system', 'diagnostic_api'
            ]
            
            for component_name in required_components:
                component = getattr(orchestrator, component_name, None)
                if component is None:
                    result['success'] = False
                    result['errors'].append(f"Component {component_name} not wired")
                else:
                    result['details'][f'{component_name}_wired'] = True
            
            # Check component health
            healthy_count = sum(orchestrator.component_health.values())
            total_count = len(orchestrator.component_health)
            
            result['details']['healthy_components'] = healthy_count
            result['details']['total_components'] = total_count
            
            if healthy_count < total_count:
                result['success'] = False
                result['errors'].append(f"Only {healthy_count}/{total_count} components are healthy")
            
            logger.info(f"Component wiring validation: {'PASSED' if result['success'] else 'FAILED'}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(f"Component wiring validation failed: {str(e)}")
            logger.error(f"Component wiring validation error: {e}")
        
        return result
    
    async def validate_end_to_end_operations(self) -> Dict[str, Any]:
        """Validate end-to-end operations work correctly"""
        logger.info("Validating end-to-end operations...")
        
        result = {
            'test_name': 'End-to-End Operations',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            orchestrator = IntegratedOrchestrator(self.db_config)
            
            # Start system
            start_success = await orchestrator.start_system()
            result['details']['system_startup'] = start_success
            
            if not start_success:
                result['success'] = False
                result['errors'].append("System startup failed")
                return result
            
            # Test instance registration
            reg_result = await orchestrator.register_instance(
                'validation-worker-1', '127.0.0.1', 8001, 20
            )
            result['details']['instance_registration'] = reg_result['status'] == 'success'
            
            if reg_result['status'] != 'success':
                result['success'] = False
                result['errors'].append(f"Instance registration failed: {reg_result.get('error')}")
            
            # Test heartbeat processing
            heartbeat_data = {
                'current_streams': 5,
                'cpu_percent': 45.0,
                'memory_percent': 60.0
            }
            
            hb_result = await orchestrator.process_heartbeat('validation-worker-1', heartbeat_data)
            result['details']['heartbeat_processing'] = hb_result['status'] == 'success'
            
            if hb_result['status'] != 'success':
                result['success'] = False
                result['errors'].append(f"Heartbeat processing failed: {hb_result.get('error')}")
            
            # Test stream assignment
            assign_result = await orchestrator.assign_streams('validation-worker-1', 3)
            result['details']['stream_assignment'] = assign_result['status'] == 'success'
            
            if assign_result['status'] != 'success':
                result['success'] = False
                result['errors'].append(f"Stream assignment failed: {assign_result.get('error')}")
            
            # Test system status
            status = await orchestrator.get_system_status()
            result['details']['system_status'] = 'status' in status
            result['details']['active_instances'] = status.get('active_instances', 0)
            
            logger.info(f"End-to-end operations validation: {'PASSED' if result['success'] else 'FAILED'}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(f"End-to-end operations validation failed: {str(e)}")
            logger.error(f"End-to-end operations validation error: {e}")
        finally:
            if orchestrator:
                await orchestrator.stop_system()
        
        return result
    
    async def validate_failure_simulation(self) -> Dict[str, Any]:
        """Validate failure simulation and recovery"""
        logger.info("Validating failure simulation...")
        
        result = {
            'test_name': 'Failure Simulation',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            orchestrator = IntegratedOrchestrator(self.db_config)
            await orchestrator.start_system()
            
            # Register instances
            await orchestrator.register_instance('fail-worker-1', '127.0.0.1', 8001, 20)
            await orchestrator.register_instance('fail-worker-2', '127.0.0.1', 8002, 20)
            
            # Assign streams to first instance
            await orchestrator.assign_streams('fail-worker-1', 5)
            
            # Simulate instance failure
            failure_result = await orchestrator.handle_instance_failure('fail-worker-1')
            result['details']['failure_handling'] = failure_result['status'] == 'success'
            result['details']['recovery_performed'] = failure_result.get('recovery_performed', False)
            
            if failure_result['status'] != 'success':
                result['success'] = False
                result['errors'].append(f"Failure handling failed: {failure_result.get('error')}")
            
            logger.info(f"Failure simulation validation: {'PASSED' if result['success'] else 'FAILED'}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(f"Failure simulation validation failed: {str(e)}")
            logger.error(f"Failure simulation validation error: {e}")
        finally:
            if orchestrator:
                await orchestrator.stop_system()
        
        return result
    
    async def validate_performance_requirements(self) -> Dict[str, Any]:
        """Validate basic performance requirements"""
        logger.info("Validating performance requirements...")
        
        result = {
            'test_name': 'Performance Requirements',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            orchestrator = IntegratedOrchestrator(self.db_config)
            await orchestrator.start_system()
            
            # Test registration performance
            import time
            
            registration_times = []
            for i in range(5):
                start_time = time.time()
                reg_result = await orchestrator.register_instance(
                    f'perf-worker-{i}', '127.0.0.1', 8000 + i, 20
                )
                reg_time = time.time() - start_time
                registration_times.append(reg_time)
                
                if reg_result['status'] != 'success':
                    result['success'] = False
                    result['errors'].append(f"Registration {i} failed")
            
            avg_reg_time = sum(registration_times) / len(registration_times)
            max_reg_time = max(registration_times)
            
            result['details']['avg_registration_time_ms'] = avg_reg_time * 1000
            result['details']['max_registration_time_ms'] = max_reg_time * 1000
            
            # Performance thresholds
            max_allowed_time = 2.0  # 2 seconds
            
            if max_reg_time > max_allowed_time:
                result['success'] = False
                result['errors'].append(f"Registration time {max_reg_time:.3f}s exceeds {max_allowed_time}s")
            
            # Test heartbeat performance
            heartbeat_times = []
            for i in range(5):
                start_time = time.time()
                hb_result = await orchestrator.process_heartbeat(
                    f'perf-worker-{i}', {'current_streams': 5}
                )
                hb_time = time.time() - start_time
                heartbeat_times.append(hb_time)
            
            avg_hb_time = sum(heartbeat_times) / len(heartbeat_times)
            result['details']['avg_heartbeat_time_ms'] = avg_hb_time * 1000
            
            max_hb_time = 1.0  # 1 second
            if avg_hb_time > max_hb_time:
                result['success'] = False
                result['errors'].append(f"Heartbeat time {avg_hb_time:.3f}s exceeds {max_hb_time}s")
            
            logger.info(f"Performance requirements validation: {'PASSED' if result['success'] else 'FAILED'}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(f"Performance requirements validation failed: {str(e)}")
            logger.error(f"Performance requirements validation error: {e}")
        finally:
            if orchestrator:
                await orchestrator.stop_system()
        
        return result
    
    async def validate_end_to_end_test_suite(self) -> Dict[str, Any]:
        """Validate that the end-to-end test suite works"""
        logger.info("Validating end-to-end test suite...")
        
        result = {
            'test_name': 'End-to-End Test Suite',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            orchestrator = IntegratedOrchestrator(self.db_config)
            await orchestrator.start_system()
            
            # Create test suite
            test_suite = EndToEndTestSuite(orchestrator)
            
            # Run a subset of tests
            test_scenarios = [
                test_suite._test_normal_operation,
                test_suite._test_instance_failure
            ]
            
            test_results = []
            for test_func in test_scenarios:
                try:
                    test_result = await test_func()
                    test_results.append(test_result)
                    result['details'][f'{test_func.__name__}_success'] = test_result.success
                    
                    if not test_result.success:
                        result['success'] = False
                        result['errors'].append(f"{test_func.__name__} failed: {test_result.error_message}")
                        
                except Exception as e:
                    result['success'] = False
                    result['errors'].append(f"{test_func.__name__} crashed: {str(e)}")
            
            result['details']['tests_executed'] = len(test_results)
            result['details']['tests_passed'] = sum(1 for tr in test_results if tr.success)
            
            logger.info(f"End-to-end test suite validation: {'PASSED' if result['success'] else 'FAILED'}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(f"End-to-end test suite validation failed: {str(e)}")
            logger.error(f"End-to-end test suite validation error: {e}")
        finally:
            if orchestrator:
                await orchestrator.stop_system()
        
        return result
    
    async def run_task_10_validation(self) -> Dict[str, Any]:
        """Run complete Task 10 validation"""
        logger.info("Starting Task 10 completion validation")
        logger.info("=" * 60)
        
        # Run all validations
        validations = [
            await self.validate_component_wiring(),
            await self.validate_end_to_end_operations(),
            await self.validate_failure_simulation(),
            await self.validate_performance_requirements(),
            await self.validate_end_to_end_test_suite()
        ]
        
        # Calculate results
        total_validations = len(validations)
        passed_validations = sum(1 for v in validations if v['success'])
        failed_validations = total_validations - passed_validations
        
        # Generate report
        validation_report = {
            'task': 'Task 10: Integrate all components and perform end-to-end testing',
            'summary': {
                'total_validations': total_validations,
                'passed_validations': passed_validations,
                'failed_validations': failed_validations,
                'success_rate': passed_validations / total_validations if total_validations > 0 else 0,
                'overall_success': failed_validations == 0
            },
            'validations': validations,
            'requirements_validated': [
                'Wire together all enhanced components with proper error handling',
                'Perform comprehensive end-to-end testing with failure simulation',
                'Validate system performance under various load conditions'
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        return validation_report


async def main():
    """Main validation function"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Task 10 Completion Validation")
    logger.info("Validating: Integrate all components and perform end-to-end testing")
    
    # Create validator
    validator = Task10Validator()
    
    try:
        # Run validation
        validation_report = await validator.run_task_10_validation()
        
        # Save report
        report_filename = f"task_10_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(validation_report, f, indent=2)
        
        logger.info(f"Validation report saved to {report_filename}")
        
        # Log summary
        logger.info("=" * 60)
        logger.info("TASK 10 VALIDATION SUMMARY")
        logger.info("=" * 60)
        
        summary = validation_report['summary']
        logger.info(f"Total validations: {summary['total_validations']}")
        logger.info(f"Passed: {summary['passed_validations']}")
        logger.info(f"Failed: {summary['failed_validations']}")
        logger.info(f"Success rate: {summary['success_rate']:.2%}")
        
        if summary['overall_success']:
            logger.info("✓ TASK 10 COMPLETED SUCCESSFULLY")
            logger.info("All components are integrated and end-to-end testing is working")
        else:
            logger.error("✗ TASK 10 VALIDATION FAILED")
            logger.error("Some requirements are not met:")
            
            for validation in validation_report['validations']:
                if not validation['success']:
                    logger.error(f"  - {validation['test_name']}: {', '.join(validation['errors'])}")
        
        # Return appropriate exit code
        return 0 if summary['overall_success'] else 1
        
    except Exception as e:
        logger.error(f"Task 10 validation failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
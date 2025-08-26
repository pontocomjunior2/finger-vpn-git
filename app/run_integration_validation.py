#!/usr/bin/env python3
"""
Integration Validation Runner

This script runs comprehensive validation of the integrated orchestrator system
to ensure all components are properly wired together and functioning correctly.

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from integration_system import (EndToEndTestSuite, IntegratedOrchestrator,
                                IntegrationStatus)

logger = logging.getLogger(__name__)


class IntegrationValidator:
    """Comprehensive integration validation system"""
    
    def __init__(self):
        self.validation_results = []
        self.start_time = datetime.now()
    
    async def validate_component_integration(self, orchestrator: IntegratedOrchestrator) -> Dict[str, Any]:
        """Validate that all components are properly integrated"""
        logger.info("Validating component integration...")
        
        validation_result = {
            'test_name': 'Component Integration',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            # Check component initialization
            required_components = [
                'db_manager', 'error_handler', 'enhanced_orchestrator',
                'resilient_orchestrator', 'consistency_checker',
                'monitoring_system', 'diagnostic_api'
            ]
            
            for component_name in required_components:
                component = getattr(orchestrator, component_name, None)
                if component is None:
                    validation_result['success'] = False
                    validation_result['errors'].append(f"Component {component_name} not initialized")
                else:
                    validation_result['details'][f'{component_name}_initialized'] = True
            
            # Check component health
            healthy_components = sum(orchestrator.component_health.values())
            total_components = len(orchestrator.component_health)
            
            validation_result['details']['healthy_components'] = healthy_components
            validation_result['details']['total_components'] = total_components
            validation_result['details']['health_ratio'] = healthy_components / total_components if total_components > 0 else 0
            
            if healthy_components < total_components:
                validation_result['success'] = False
                validation_result['errors'].append(f"Only {healthy_components}/{total_components} components are healthy")
            
            logger.info(f"Component integration validation: {'PASSED' if validation_result['success'] else 'FAILED'}")
            
        except Exception as e:
            validation_result['success'] = False
            validation_result['errors'].append(f"Component integration validation failed: {str(e)}")
            logger.error(f"Component integration validation error: {e}")
        
        return validation_result
    
    async def validate_system_startup(self, db_config: Dict[str, str]) -> Dict[str, Any]:
        """Validate system startup and shutdown process"""
        logger.info("Validating system startup and shutdown...")
        
        validation_result = {
            'test_name': 'System Startup/Shutdown',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            # Test system startup
            orchestrator = IntegratedOrchestrator(db_config)
            
            startup_start = time.time()
            startup_success = await orchestrator.start_system()
            startup_time = time.time() - startup_start
            
            validation_result['details']['startup_success'] = startup_success
            validation_result['details']['startup_time_seconds'] = startup_time
            validation_result['details']['final_status'] = orchestrator.status.value
            
            if not startup_success:
                validation_result['success'] = False
                validation_result['errors'].append("System startup failed")
            
            if orchestrator.status != IntegrationStatus.RUNNING:
                validation_result['success'] = False
                validation_result['errors'].append(f"System status is {orchestrator.status.value}, expected RUNNING")
            
            # Check background tasks
            validation_result['details']['background_tasks_count'] = len(orchestrator.background_tasks)
            
            if len(orchestrator.background_tasks) == 0:
                validation_result['success'] = False
                validation_result['errors'].append("No background tasks started")
            
            # Test system shutdown
            shutdown_start = time.time()
            shutdown_success = await orchestrator.stop_system()
            shutdown_time = time.time() - shutdown_start
            
            validation_result['details']['shutdown_success'] = shutdown_success
            validation_result['details']['shutdown_time_seconds'] = shutdown_time
            validation_result['details']['final_shutdown_status'] = orchestrator.status.value
            
            if not shutdown_success:
                validation_result['success'] = False
                validation_result['errors'].append("System shutdown failed")
            
            logger.info(f"System startup/shutdown validation: {'PASSED' if validation_result['success'] else 'FAILED'}")
            
        except Exception as e:
            validation_result['success'] = False
            validation_result['errors'].append(f"System startup/shutdown validation failed: {str(e)}")
            logger.error(f"System startup/shutdown validation error: {e}")
        finally:
            if orchestrator:
                try:
                    await orchestrator.stop_system()
                except:
                    pass
        
        return validation_result
    
    async def validate_end_to_end_operations(self, db_config: Dict[str, str]) -> Dict[str, Any]:
        """Validate end-to-end operations"""
        logger.info("Validating end-to-end operations...")
        
        validation_result = {
            'test_name': 'End-to-End Operations',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            # Start system
            orchestrator = IntegratedOrchestrator(db_config)
            await orchestrator.start_system()
            
            # Test instance registration
            registration_result = await orchestrator.register_instance(
                'validation-worker-1', '127.0.0.1', 8001, 20
            )
            
            validation_result['details']['instance_registration'] = registration_result['status'] == 'success'
            
            if registration_result['status'] != 'success':
                validation_result['success'] = False
                validation_result['errors'].append(f"Instance registration failed: {registration_result.get('error')}")
            
            # Test heartbeat processing
            heartbeat_data = {
                'current_streams': 5,
                'cpu_percent': 45.0,
                'memory_percent': 60.0,
                'response_time_ms': 150.0
            }
            
            heartbeat_result = await orchestrator.process_heartbeat('validation-worker-1', heartbeat_data)
            
            validation_result['details']['heartbeat_processing'] = heartbeat_result['status'] == 'success'
            
            if heartbeat_result['status'] != 'success':
                validation_result['success'] = False
                validation_result['errors'].append(f"Heartbeat processing failed: {heartbeat_result.get('error')}")
            
            # Test stream assignment
            assignment_result = await orchestrator.assign_streams('validation-worker-1', 5)
            
            validation_result['details']['stream_assignment'] = assignment_result['status'] == 'success'
            
            if assignment_result['status'] != 'success':
                validation_result['success'] = False
                validation_result['errors'].append(f"Stream assignment failed: {assignment_result.get('error')}")
            
            # Test system status
            status = await orchestrator.get_system_status()
            
            validation_result['details']['system_status_available'] = 'status' in status
            validation_result['details']['active_instances'] = status.get('active_instances', 0)
            validation_result['details']['total_streams'] = status.get('total_streams', 0)
            
            logger.info(f"End-to-end operations validation: {'PASSED' if validation_result['success'] else 'FAILED'}")
            
        except Exception as e:
            validation_result['success'] = False
            validation_result['errors'].append(f"End-to-end operations validation failed: {str(e)}")
            logger.error(f"End-to-end operations validation error: {e}")
        finally:
            if orchestrator:
                try:
                    await orchestrator.stop_system()
                except:
                    pass
        
        return validation_result
    
    async def validate_failure_scenarios(self, db_config: Dict[str, str]) -> Dict[str, Any]:
        """Validate failure scenario handling"""
        logger.info("Validating failure scenario handling...")
        
        validation_result = {
            'test_name': 'Failure Scenarios',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            # Start system
            orchestrator = IntegratedOrchestrator(db_config)
            await orchestrator.start_system()
            
            # Register instances
            await orchestrator.register_instance('failure-worker-1', '127.0.0.1', 8001, 20)
            await orchestrator.register_instance('failure-worker-2', '127.0.0.1', 8002, 20)
            
            # Assign streams
            await orchestrator.assign_streams('failure-worker-1', 5)
            
            # Test instance failure handling
            failure_result = await orchestrator.handle_instance_failure('failure-worker-1')
            
            validation_result['details']['failure_handling'] = failure_result['status'] == 'success'
            validation_result['details']['recovery_performed'] = failure_result.get('recovery_performed', False)
            
            if failure_result['status'] != 'success':
                validation_result['success'] = False
                validation_result['errors'].append(f"Instance failure handling failed: {failure_result.get('error')}")
            
            logger.info(f"Failure scenarios validation: {'PASSED' if validation_result['success'] else 'FAILED'}")
            
        except Exception as e:
            validation_result['success'] = False
            validation_result['errors'].append(f"Failure scenarios validation failed: {str(e)}")
            logger.error(f"Failure scenarios validation error: {e}")
        finally:
            if orchestrator:
                try:
                    await orchestrator.stop_system()
                except:
                    pass
        
        return validation_result
    
    async def validate_performance_requirements(self, db_config: Dict[str, str]) -> Dict[str, Any]:
        """Validate performance requirements"""
        logger.info("Validating performance requirements...")
        
        validation_result = {
            'test_name': 'Performance Requirements',
            'success': True,
            'details': {},
            'errors': []
        }
        
        orchestrator = None
        
        try:
            # Start system
            orchestrator = IntegratedOrchestrator(db_config)
            await orchestrator.start_system()
            
            # Test registration performance
            registration_times = []
            for i in range(10):
                start_time = time.time()
                result = await orchestrator.register_instance(
                    f'perf-worker-{i}', '127.0.0.1', 8000 + i, 20
                )
                registration_time = time.time() - start_time
                registration_times.append(registration_time)
                
                if result['status'] != 'success':
                    validation_result['success'] = False
                    validation_result['errors'].append(f"Registration failed for worker {i}")
            
            avg_registration_time = sum(registration_times) / len(registration_times)
            max_registration_time = max(registration_times)
            
            validation_result['details']['avg_registration_time'] = avg_registration_time
            validation_result['details']['max_registration_time'] = max_registration_time
            
            # Performance requirements (configurable)
            max_allowed_registration_time = float(os.getenv('MAX_REGISTRATION_TIME', '2.0'))
            
            if max_registration_time > max_allowed_registration_time:
                validation_result['success'] = False
                validation_result['errors'].append(
                    f"Registration time {max_registration_time:.3f}s exceeds limit {max_allowed_registration_time}s"
                )
            
            # Test heartbeat performance
            heartbeat_times = []
            for i in range(10):
                start_time = time.time()
                result = await orchestrator.process_heartbeat(
                    f'perf-worker-{i}', {'current_streams': 5}
                )
                heartbeat_time = time.time() - start_time
                heartbeat_times.append(heartbeat_time)
            
            avg_heartbeat_time = sum(heartbeat_times) / len(heartbeat_times)
            validation_result['details']['avg_heartbeat_time'] = avg_heartbeat_time
            
            max_allowed_heartbeat_time = float(os.getenv('MAX_HEARTBEAT_TIME', '1.0'))
            
            if avg_heartbeat_time > max_allowed_heartbeat_time:
                validation_result['success'] = False
                validation_result['errors'].append(
                    f"Average heartbeat time {avg_heartbeat_time:.3f}s exceeds limit {max_allowed_heartbeat_time}s"
                )
            
            logger.info(f"Performance requirements validation: {'PASSED' if validation_result['success'] else 'FAILED'}")
            
        except Exception as e:
            validation_result['success'] = False
            validation_result['errors'].append(f"Performance requirements validation failed: {str(e)}")
            logger.error(f"Performance requirements validation error: {e}")
        finally:
            if orchestrator:
                try:
                    await orchestrator.stop_system()
                except:
                    pass
        
        return validation_result
    
    async def run_comprehensive_validation(self, db_config: Dict[str, str]) -> Dict[str, Any]:
        """Run comprehensive validation of the integrated system"""
        logger.info("Starting comprehensive integration validation")
        
        # Run all validation tests
        validations = [
            await self.validate_system_startup(db_config),
            await self.validate_end_to_end_operations(db_config),
            await self.validate_failure_scenarios(db_config),
            await self.validate_performance_requirements(db_config)
        ]
        
        # Component integration validation requires a running system
        orchestrator = IntegratedOrchestrator(db_config)
        try:
            await orchestrator.start_system()
            component_validation = await self.validate_component_integration(orchestrator)
            validations.append(component_validation)
        finally:
            await orchestrator.stop_system()
        
        # Generate comprehensive report
        total_tests = len(validations)
        passed_tests = sum(1 for v in validations if v['success'])
        failed_tests = total_tests - passed_tests
        
        validation_report = {
            'summary': {
                'total_validations': total_tests,
                'passed_validations': passed_tests,
                'failed_validations': failed_tests,
                'success_rate': passed_tests / total_tests if total_tests > 0 else 0,
                'validation_duration_seconds': (datetime.now() - self.start_time).total_seconds()
            },
            'validations': validations,
            'timestamp': datetime.now().isoformat(),
            'overall_success': failed_tests == 0
        }
        
        return validation_report


async def main():
    """Main validation function"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'orchestrator'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    logger.info("Starting integration validation")
    logger.info(f"Database config: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    # Create validator
    validator = IntegrationValidator()
    
    try:
        # Run comprehensive validation
        validation_report = await validator.run_comprehensive_validation(db_config)
        
        # Save validation report
        report_filename = f"integration_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(validation_report, f, indent=2)
        
        logger.info(f"Validation report saved to {report_filename}")
        
        # Log summary
        summary = validation_report['summary']
        logger.info("Integration validation completed:")
        logger.info(f"  Total validations: {summary['total_validations']}")
        logger.info(f"  Passed: {summary['passed_validations']}")
        logger.info(f"  Failed: {summary['failed_validations']}")
        logger.info(f"  Success rate: {summary['success_rate']:.2%}")
        logger.info(f"  Duration: {summary['validation_duration_seconds']:.2f}s")
        
        # Log failed validations
        if summary['failed_validations'] > 0:
            logger.error("Failed validations:")
            for validation in validation_report['validations']:
                if not validation['success']:
                    logger.error(f"  - {validation['test_name']}: {', '.join(validation['errors'])}")
        
        # Run end-to-end test suite
        logger.info("Running end-to-end test suite...")
        
        orchestrator = IntegratedOrchestrator(db_config)
        await orchestrator.start_system()
        
        try:
            test_suite = EndToEndTestSuite(orchestrator)
            test_report = await test_suite.run_all_tests()
            
            # Save test report
            test_report_filename = f"end_to_end_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(test_report_filename, 'w') as f:
                json.dump(test_report, f, indent=2)
            
            logger.info(f"End-to-end test report saved to {test_report_filename}")
            
            # Log test summary
            test_summary = test_report['summary']
            logger.info("End-to-end tests completed:")
            logger.info(f"  Total tests: {test_summary['total_tests']}")
            logger.info(f"  Passed: {test_summary['passed_tests']}")
            logger.info(f"  Failed: {test_summary['failed_tests']}")
            logger.info(f"  Success rate: {test_summary['success_rate']:.2%}")
            
        finally:
            await orchestrator.stop_system()
        
        # Overall success
        overall_success = (validation_report['overall_success'] and 
                          test_report['summary']['failed_tests'] == 0)
        
        if overall_success:
            logger.info("✓ All integration validation and testing completed successfully")
            return 0
        else:
            logger.error("✗ Integration validation or testing failed")
            return 1
            
    except Exception as e:
        logger.error(f"Integration validation failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
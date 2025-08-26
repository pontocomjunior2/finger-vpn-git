#!/usr/bin/env python3
"""
Performance Validation for Integrated Orchestrator System

This script validates system performance under various load conditions
to ensure the integrated system meets performance requirements.

Task: 10. Integrate all components and perform end-to-end testing
Requirements: All requirements integration and validation
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from integration_system import IntegratedOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for operations"""
    operation_name: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    min_time: float
    max_time: float
    avg_time: float
    median_time: float
    p95_time: float
    p99_time: float
    throughput_ops_per_sec: float
    error_rate: float


class PerformanceValidator:
    """Performance validation for integrated orchestrator system"""
    
    def __init__(self, orchestrator: IntegratedOrchestrator):
        self.orchestrator = orchestrator
        self.performance_results = []
    
    async def measure_operation_performance(
        self, 
        operation_name: str,
        operation_func,
        operation_args: List[Any],
        num_operations: int = 100,
        concurrent: bool = False,
        max_concurrency: int = 10
    ) -> PerformanceMetrics:
        """Measure performance of a specific operation"""
        logger.info(f"Measuring performance for {operation_name} ({num_operations} operations)")
        
        execution_times = []
        successful_operations = 0
        failed_operations = 0
        
        start_time = time.time()
        
        if concurrent:
            # Run operations concurrently
            semaphore = asyncio.Semaphore(max_concurrency)
            
            async def run_operation_with_semaphore(args):
                async with semaphore:
                    op_start = time.time()
                    try:
                        result = await operation_func(*args)
                        op_time = time.time() - op_start
                        return op_time, True, result
                    except Exception as e:
                        op_time = time.time() - op_start
                        logger.warning(f"Operation failed: {e}")
                        return op_time, False, None
            
            # Create tasks
            tasks = []
            for i in range(num_operations):
                # Modify args for each operation if needed
                args = [arg.format(i=i) if isinstance(arg, str) else arg for arg in operation_args]
                tasks.append(run_operation_with_semaphore(args))
            
            # Execute all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failed_operations += 1
                    execution_times.append(0.0)  # Add 0 for failed operations
                else:
                    op_time, success, _ = result
                    execution_times.append(op_time)
                    if success:
                        successful_operations += 1
                    else:
                        failed_operations += 1
        else:
            # Run operations sequentially
            for i in range(num_operations):
                # Modify args for each operation if needed
                args = [arg.format(i=i) if isinstance(arg, str) else arg for arg in operation_args]
                
                op_start = time.time()
                try:
                    await operation_func(*args)
                    op_time = time.time() - op_start
                    execution_times.append(op_time)
                    successful_operations += 1
                except Exception as e:
                    op_time = time.time() - op_start
                    execution_times.append(op_time)
                    failed_operations += 1
                    logger.warning(f"Operation {i} failed: {e}")
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        if execution_times:
            min_time = min(execution_times)
            max_time = max(execution_times)
            avg_time = statistics.mean(execution_times)
            median_time = statistics.median(execution_times)
            
            # Calculate percentiles
            sorted_times = sorted(execution_times)
            p95_time = sorted_times[int(0.95 * len(sorted_times))] if sorted_times else 0
            p99_time = sorted_times[int(0.99 * len(sorted_times))] if sorted_times else 0
        else:
            min_time = max_time = avg_time = median_time = p95_time = p99_time = 0
        
        throughput = num_operations / total_time if total_time > 0 else 0
        error_rate = failed_operations / num_operations if num_operations > 0 else 0
        
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            total_operations=num_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            min_time=min_time,
            max_time=max_time,
            avg_time=avg_time,
            median_time=median_time,
            p95_time=p95_time,
            p99_time=p99_time,
            throughput_ops_per_sec=throughput,
            error_rate=error_rate
        )
        
        logger.info(f"Performance metrics for {operation_name}:")
        logger.info(f"  Throughput: {throughput:.2f} ops/sec")
        logger.info(f"  Average time: {avg_time*1000:.2f}ms")
        logger.info(f"  P95 time: {p95_time*1000:.2f}ms")
        logger.info(f"  Error rate: {error_rate:.2%}")
        
        return metrics
    
    async def test_instance_registration_performance(self) -> PerformanceMetrics:
        """Test instance registration performance"""
        async def register_instance(server_id, ip, port, max_streams):
            return await self.orchestrator.register_instance(server_id, ip, port, max_streams)
        
        return await self.measure_operation_performance(
            "Instance Registration",
            register_instance,
            ["perf-worker-{i}", "127.0.0.1", 8000, 20],
            num_operations=50,
            concurrent=False
        )
    
    async def test_heartbeat_processing_performance(self) -> PerformanceMetrics:
        """Test heartbeat processing performance"""
        # First register some instances
        for i in range(10):
            await self.orchestrator.register_instance(f"heartbeat-worker-{i}", "127.0.0.1", 8000 + i, 20)
        
        async def process_heartbeat(server_id, heartbeat_data):
            return await self.orchestrator.process_heartbeat(server_id, heartbeat_data)
        
        heartbeat_data = {
            'current_streams': 5,
            'cpu_percent': 45.0,
            'memory_percent': 60.0,
            'response_time_ms': 150.0
        }
        
        return await self.measure_operation_performance(
            "Heartbeat Processing",
            process_heartbeat,
            ["heartbeat-worker-{i}", heartbeat_data],
            num_operations=100,
            concurrent=True,
            max_concurrency=10
        )
    
    async def test_stream_assignment_performance(self) -> PerformanceMetrics:
        """Test stream assignment performance"""
        # Register instances for stream assignment
        for i in range(5):
            await self.orchestrator.register_instance(f"stream-worker-{i}", "127.0.0.1", 8100 + i, 50)
        
        async def assign_streams(server_id, requested_count):
            return await self.orchestrator.assign_streams(server_id, requested_count)
        
        return await self.measure_operation_performance(
            "Stream Assignment",
            assign_streams,
            ["stream-worker-{i}", 10],
            num_operations=25,  # 5 workers * 5 assignments each
            concurrent=False
        )
    
    async def test_system_status_performance(self) -> PerformanceMetrics:
        """Test system status retrieval performance"""
        async def get_system_status():
            return await self.orchestrator.get_system_status()
        
        return await self.measure_operation_performance(
            "System Status Retrieval",
            get_system_status,
            [],
            num_operations=50,
            concurrent=True,
            max_concurrency=5
        )
    
    async def test_concurrent_mixed_operations(self) -> PerformanceMetrics:
        """Test performance under mixed concurrent operations"""
        logger.info("Testing mixed concurrent operations performance")
        
        # Register base instances
        for i in range(10):
            await self.orchestrator.register_instance(f"mixed-worker-{i}", "127.0.0.1", 8200 + i, 20)
        
        operations_completed = 0
        operations_failed = 0
        execution_times = []
        
        start_time = time.time()
        
        async def mixed_operation(operation_id: int):
            op_start = time.time()
            try:
                operation_type = operation_id % 4
                
                if operation_type == 0:
                    # Heartbeat
                    heartbeat_data = {'current_streams': 5, 'cpu_percent': 45.0}
                    await self.orchestrator.process_heartbeat(f"mixed-worker-{operation_id % 10}", heartbeat_data)
                elif operation_type == 1:
                    # Stream assignment
                    await self.orchestrator.assign_streams(f"mixed-worker-{operation_id % 10}", 2)
                elif operation_type == 2:
                    # System status
                    await self.orchestrator.get_system_status()
                elif operation_type == 3:
                    # Instance registration (new instances)
                    await self.orchestrator.register_instance(
                        f"mixed-new-worker-{operation_id}", "127.0.0.1", 9000 + operation_id, 20
                    )
                
                op_time = time.time() - op_start
                return op_time, True
                
            except Exception as e:
                op_time = time.time() - op_start
                logger.warning(f"Mixed operation {operation_id} failed: {e}")
                return op_time, False
        
        # Run mixed operations concurrently
        semaphore = asyncio.Semaphore(15)  # Higher concurrency for mixed operations
        
        async def run_mixed_operation_with_semaphore(op_id):
            async with semaphore:
                return await mixed_operation(op_id)
        
        # Create tasks for mixed operations
        num_mixed_operations = 100
        tasks = [run_mixed_operation_with_semaphore(i) for i in range(num_mixed_operations)]
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                operations_failed += 1
                execution_times.append(0.0)
            else:
                op_time, success = result
                execution_times.append(op_time)
                if success:
                    operations_completed += 1
                else:
                    operations_failed += 1
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        if execution_times:
            min_time = min(execution_times)
            max_time = max(execution_times)
            avg_time = statistics.mean(execution_times)
            median_time = statistics.median(execution_times)
            
            sorted_times = sorted(execution_times)
            p95_time = sorted_times[int(0.95 * len(sorted_times))] if sorted_times else 0
            p99_time = sorted_times[int(0.99 * len(sorted_times))] if sorted_times else 0
        else:
            min_time = max_time = avg_time = median_time = p95_time = p99_time = 0
        
        throughput = num_mixed_operations / total_time if total_time > 0 else 0
        error_rate = operations_failed / num_mixed_operations if num_mixed_operations > 0 else 0
        
        return PerformanceMetrics(
            operation_name="Mixed Concurrent Operations",
            total_operations=num_mixed_operations,
            successful_operations=operations_completed,
            failed_operations=operations_failed,
            min_time=min_time,
            max_time=max_time,
            avg_time=avg_time,
            median_time=median_time,
            p95_time=p95_time,
            p99_time=p99_time,
            throughput_ops_per_sec=throughput,
            error_rate=error_rate
        )
    
    async def test_high_load_performance(self) -> PerformanceMetrics:
        """Test performance under high load conditions"""
        logger.info("Testing high load performance")
        
        # Register many instances
        num_instances = 100
        for i in range(num_instances):
            await self.orchestrator.register_instance(f"load-worker-{i}", "127.0.0.1", 7000 + i, 50)
        
        # Simulate high load with many concurrent heartbeats
        async def high_load_heartbeat(worker_id):
            heartbeat_data = {
                'current_streams': 45,  # Near capacity
                'cpu_percent': 85.0,    # High CPU
                'memory_percent': 80.0, # High memory
                'response_time_ms': 300.0  # Slower response
            }
            return await self.orchestrator.process_heartbeat(f"load-worker-{worker_id}", heartbeat_data)
        
        return await self.measure_operation_performance(
            "High Load Heartbeats",
            high_load_heartbeat,
            ["{i}"],
            num_operations=num_instances,
            concurrent=True,
            max_concurrency=20
        )
    
    async def run_all_performance_tests(self) -> Dict[str, Any]:
        """Run all performance tests"""
        logger.info("Starting comprehensive performance testing")
        
        performance_tests = [
            self.test_instance_registration_performance,
            self.test_heartbeat_processing_performance,
            self.test_stream_assignment_performance,
            self.test_system_status_performance,
            self.test_concurrent_mixed_operations,
            self.test_high_load_performance
        ]
        
        test_results = []
        
        for test_func in performance_tests:
            try:
                logger.info(f"Running {test_func.__name__}")
                metrics = await test_func()
                test_results.append(metrics)
                
                # Add small delay between tests
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Performance test {test_func.__name__} failed: {e}")
                # Create failed metrics
                failed_metrics = PerformanceMetrics(
                    operation_name=test_func.__name__,
                    total_operations=0,
                    successful_operations=0,
                    failed_operations=1,
                    min_time=0, max_time=0, avg_time=0,
                    median_time=0, p95_time=0, p99_time=0,
                    throughput_ops_per_sec=0,
                    error_rate=1.0
                )
                test_results.append(failed_metrics)
        
        # Generate performance report
        return self._generate_performance_report(test_results)
    
    def _generate_performance_report(self, test_results: List[PerformanceMetrics]) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        total_operations = sum(metrics.total_operations for metrics in test_results)
        total_successful = sum(metrics.successful_operations for metrics in test_results)
        total_failed = sum(metrics.failed_operations for metrics in test_results)
        
        overall_error_rate = total_failed / total_operations if total_operations > 0 else 0
        overall_success_rate = total_successful / total_operations if total_operations > 0 else 0
        
        # Calculate average throughput
        avg_throughput = statistics.mean([m.throughput_ops_per_sec for m in test_results if m.throughput_ops_per_sec > 0])
        
        # Performance thresholds (configurable)
        performance_thresholds = {
            'max_avg_response_time_ms': float(os.getenv('MAX_AVG_RESPONSE_TIME_MS', '500')),
            'max_p95_response_time_ms': float(os.getenv('MAX_P95_RESPONSE_TIME_MS', '1000')),
            'min_throughput_ops_per_sec': float(os.getenv('MIN_THROUGHPUT_OPS_PER_SEC', '10')),
            'max_error_rate': float(os.getenv('MAX_ERROR_RATE', '0.05'))
        }
        
        # Check performance requirements
        performance_issues = []
        
        for metrics in test_results:
            if metrics.avg_time * 1000 > performance_thresholds['max_avg_response_time_ms']:
                performance_issues.append(
                    f"{metrics.operation_name}: Average response time {metrics.avg_time*1000:.2f}ms exceeds threshold"
                )
            
            if metrics.p95_time * 1000 > performance_thresholds['max_p95_response_time_ms']:
                performance_issues.append(
                    f"{metrics.operation_name}: P95 response time {metrics.p95_time*1000:.2f}ms exceeds threshold"
                )
            
            if metrics.throughput_ops_per_sec < performance_thresholds['min_throughput_ops_per_sec']:
                performance_issues.append(
                    f"{metrics.operation_name}: Throughput {metrics.throughput_ops_per_sec:.2f} ops/sec below threshold"
                )
            
            if metrics.error_rate > performance_thresholds['max_error_rate']:
                performance_issues.append(
                    f"{metrics.operation_name}: Error rate {metrics.error_rate:.2%} exceeds threshold"
                )
        
        return {
            'summary': {
                'total_operations': total_operations,
                'successful_operations': total_successful,
                'failed_operations': total_failed,
                'overall_success_rate': overall_success_rate,
                'overall_error_rate': overall_error_rate,
                'average_throughput_ops_per_sec': avg_throughput,
                'performance_requirements_met': len(performance_issues) == 0,
                'performance_issues_count': len(performance_issues)
            },
            'performance_thresholds': performance_thresholds,
            'performance_issues': performance_issues,
            'test_results': [
                {
                    'operation_name': m.operation_name,
                    'total_operations': m.total_operations,
                    'successful_operations': m.successful_operations,
                    'failed_operations': m.failed_operations,
                    'min_time_ms': m.min_time * 1000,
                    'max_time_ms': m.max_time * 1000,
                    'avg_time_ms': m.avg_time * 1000,
                    'median_time_ms': m.median_time * 1000,
                    'p95_time_ms': m.p95_time * 1000,
                    'p99_time_ms': m.p99_time * 1000,
                    'throughput_ops_per_sec': m.throughput_ops_per_sec,
                    'error_rate': m.error_rate
                }
                for m in test_results
            ],
            'timestamp': datetime.now().isoformat()
        }


async def main():
    """Main performance validation function"""
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
    
    logger.info("Starting performance validation")
    
    # Create and start integrated orchestrator
    orchestrator = IntegratedOrchestrator(db_config)
    
    try:
        # Start system
        if not await orchestrator.start_system():
            logger.error("Failed to start integrated orchestrator for performance testing")
            return 1
        
        logger.info("Integrated orchestrator started for performance testing")
        
        # Create performance validator
        validator = PerformanceValidator(orchestrator)
        
        # Run performance tests
        performance_report = await validator.run_all_performance_tests()
        
        # Save performance report
        report_filename = f"performance_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump(performance_report, f, indent=2)
        
        logger.info(f"Performance report saved to {report_filename}")
        
        # Log summary
        summary = performance_report['summary']
        logger.info("Performance validation completed:")
        logger.info(f"  Total operations: {summary['total_operations']}")
        logger.info(f"  Success rate: {summary['overall_success_rate']:.2%}")
        logger.info(f"  Average throughput: {summary['average_throughput_ops_per_sec']:.2f} ops/sec")
        logger.info(f"  Performance requirements met: {summary['performance_requirements_met']}")
        
        # Log performance issues
        if performance_report['performance_issues']:
            logger.warning("Performance issues detected:")
            for issue in performance_report['performance_issues']:
                logger.warning(f"  - {issue}")
        
        # Return success if performance requirements are met
        return 0 if summary['performance_requirements_met'] else 1
        
    except Exception as e:
        logger.error(f"Performance validation failed: {e}")
        return 1
    finally:
        # Stop system
        await orchestrator.stop_system()
        logger.info("Performance validation cleanup completed")


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
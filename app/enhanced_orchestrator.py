"""
Enhanced Stream Orchestrator with Smart Load Balancing
Integrates the smart load balancer for intelligent stream distribution
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from load_balancer_config import create_load_balance_config, validate_config
from smart_load_balancer import (InstanceMetrics, LoadBalanceConfig,
                                 RebalanceReason, RebalanceResult,
                                 SmartLoadBalancer)

logger = logging.getLogger(__name__)


class EnhancedStreamOrchestrator:
    """
    Enhanced orchestrator that uses smart load balancing algorithm
    for intelligent stream distribution.
    """
    
    def __init__(self, db_config: Dict, load_balance_config: Optional[LoadBalanceConfig] = None):
        self.db_config = db_config
        
        # Use provided config or create from environment
        if load_balance_config is None:
            load_balance_config = create_load_balance_config()
        
        # Validate configuration
        if not validate_config(load_balance_config):
            logger.warning("Invalid load balance configuration, using defaults")
            load_balance_config = LoadBalanceConfig()
        
        self.load_balancer = SmartLoadBalancer(load_balance_config)
        self.active_instances: Dict[str, dict] = {}
        self.stream_assignments: Dict[int, str] = {}
        
        # Performance tracking
        self.instance_performance_history = {}
        self.last_performance_update = {}
        
        logger.info(f"Enhanced orchestrator initialized with config: "
                   f"imbalance_threshold={load_balance_config.imbalance_threshold}, "
                   f"max_stream_difference={load_balance_config.max_stream_difference}")
    
    def get_db_connection(self):
        """Get database connection with error handling"""
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def get_instance_metrics(self) -> List[InstanceMetrics]:
        """
        Retrieve current instance metrics from database.
        
        Returns:
            List of InstanceMetrics objects
        """
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Get instance data with latest metrics
            cursor.execute("""
                SELECT 
                    oi.server_id,
                    oi.max_streams,
                    COALESCE(COUNT(osa.stream_id), 0) as current_streams,
                    oi.last_heartbeat,
                    COALESCE(oim.cpu_percent, 0) as cpu_percent,
                    COALESCE(oim.memory_percent, 0) as memory_percent,
                    COALESCE(oim.load_average_1m, 0) as load_average_1m
                FROM orchestrator_instances oi
                LEFT JOIN orchestrator_stream_assignments osa 
                    ON oi.server_id = osa.server_id AND osa.status = 'active'
                LEFT JOIN LATERAL (
                    SELECT cpu_percent, memory_percent, load_average_1m
                    FROM orchestrator_instance_metrics 
                    WHERE server_id = oi.server_id 
                    ORDER BY recorded_at DESC 
                    LIMIT 1
                ) oim ON true
                WHERE oi.status = 'active' 
                  AND oi.last_heartbeat > NOW() - INTERVAL '5 minutes'
                GROUP BY oi.server_id, oi.max_streams, oi.last_heartbeat,
                         oim.cpu_percent, oim.memory_percent, oim.load_average_1m
                ORDER BY oi.server_id
            """)
            
            instances_data = cursor.fetchall()
            
            # Convert to InstanceMetrics objects
            metrics = []
            for row in instances_data:
                # Get failure count from performance history
                failure_count = self.instance_performance_history.get(row['server_id'], {}).get('failure_count', 0)
                
                # Calculate response time (mock for now, could be tracked separately)
                response_time_ms = self._get_average_response_time(row['server_id'])
                
                metric = InstanceMetrics(
                    server_id=row['server_id'],
                    current_streams=row['current_streams'],
                    max_streams=row['max_streams'],
                    cpu_percent=float(row['cpu_percent'] or 0),
                    memory_percent=float(row['memory_percent'] or 0),
                    load_average_1m=float(row['load_average_1m'] or 0),
                    response_time_ms=response_time_ms,
                    failure_count=failure_count,
                    last_heartbeat=row['last_heartbeat']
                )
                metrics.append(metric)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error retrieving instance metrics: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def _get_average_response_time(self, server_id: str) -> float:
        """Get average response time for an instance (mock implementation)"""
        # This would be implemented with actual response time tracking
        # For now, return a default value
        return 50.0  # 50ms default
    
    def intelligent_rebalance(self, reason: RebalanceReason = RebalanceReason.MANUAL) -> RebalanceResult:
        """
        Perform intelligent rebalancing using the smart load balancer.
        
        Args:
            reason: Reason for triggering rebalancing
            
        Returns:
            RebalanceResult with execution details
        """
        start_time = time.time()
        
        try:
            # Get current instance metrics
            instances = self.get_instance_metrics()
            
            if not instances:
                return RebalanceResult(
                    success=False,
                    reason=reason,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=0,
                    execution_time_ms=0,
                    error_message="No active instances found"
                )
            
            # Check if rebalancing is needed
            should_rebalance, rebalance_reason = self.load_balancer.should_rebalance(instances)
            
            if not should_rebalance and reason != RebalanceReason.MANUAL:
                return RebalanceResult(
                    success=True,
                    reason=reason,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_message=f"Rebalancing not needed: {rebalance_reason}"
                )
            
            # Calculate total streams
            total_streams = sum(inst.current_streams for inst in instances)
            
            if total_streams == 0:
                return RebalanceResult(
                    success=True,
                    reason=reason,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_message="No streams to rebalance"
                )
            
            # Generate rebalance plan
            migrations = self.load_balancer.generate_rebalance_plan(instances, total_streams, reason)
            
            if not migrations:
                return RebalanceResult(
                    success=True,
                    reason=reason,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error_message="No migrations needed"
                )
            
            # Execute gradual migration
            result = self.load_balancer.execute_gradual_migration(
                migrations,
                self._get_server_stream_ids,
                self._execute_stream_migration
            )
            
            # Log rebalancing result
            if result.success:
                logger.info(
                    f"Smart rebalancing completed: {result.streams_moved} streams moved, "
                    f"{result.instances_affected} instances affected, "
                    f"execution time: {result.execution_time_ms:.1f}ms"
                )
                
                # Record in database
                self._record_rebalance_history(result)
            else:
                logger.error(f"Smart rebalancing failed: {result.error_message}")
            
            return result
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Error during intelligent rebalancing: {e}")
            
            return RebalanceResult(
                success=False,
                reason=reason,
                migrations=[],
                streams_moved=0,
                instances_affected=0,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
    
    def _get_server_stream_ids(self, server_id: str) -> List[int]:
        """Get list of stream IDs assigned to a server"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND status = 'active'
                ORDER BY assigned_at ASC
                """,
                (server_id,)
            )
            
            return [row[0] for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting stream IDs for server {server_id}: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def _execute_stream_migration(self, stream_ids: List[int], from_server: str, to_server: str) -> bool:
        """
        Execute migration of streams from one server to another.
        
        Args:
            stream_ids: List of stream IDs to migrate
            from_server: Source server ID
            to_server: Target server ID
            
        Returns:
            True if migration was successful, False otherwise
        """
        if not stream_ids:
            return True
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Start transaction
            conn.autocommit = False
            
            # Verify target server has capacity
            cursor.execute(
                """
                SELECT current_streams, max_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
                """,
                (to_server,)
            )
            
            target_data = cursor.fetchone()
            if not target_data:
                logger.error(f"Target server {to_server} not found or inactive")
                conn.rollback()
                return False
            
            current_streams, max_streams = target_data
            available_capacity = max_streams - current_streams
            
            if len(stream_ids) > available_capacity:
                logger.error(
                    f"Target server {to_server} has insufficient capacity: "
                    f"needs {len(stream_ids)}, available {available_capacity}"
                )
                conn.rollback()
                return False
            
            # Update stream assignments
            cursor.execute(
                """
                UPDATE orchestrator_stream_assignments 
                SET server_id = %s, assigned_at = CURRENT_TIMESTAMP
                WHERE stream_id = ANY(%s) AND server_id = %s AND status = 'active'
                """,
                (to_server, stream_ids, from_server)
            )
            
            updated_count = cursor.rowcount
            
            if updated_count != len(stream_ids):
                logger.warning(
                    f"Expected to update {len(stream_ids)} assignments, "
                    f"but updated {updated_count}"
                )
            
            # Update instance stream counts
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = (
                    SELECT COUNT(*) 
                    FROM orchestrator_stream_assignments 
                    WHERE server_id = orchestrator_instances.server_id 
                      AND status = 'active'
                )
                WHERE server_id IN (%s, %s)
                """,
                (from_server, to_server)
            )
            
            # Commit transaction
            conn.commit()
            
            logger.info(
                f"Successfully migrated {updated_count} streams from "
                f"{from_server} to {to_server}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error migrating streams: {e}")
            conn.rollback()
            return False
        finally:
            conn.autocommit = True
            cursor.close()
            conn.close()
    
    def _record_rebalance_history(self, result: RebalanceResult):
        """Record rebalancing operation in database history"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                INSERT INTO orchestrator_rebalance_history 
                (rebalance_type, streams_moved, instances_affected, reason, executed_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    "smart_" + result.reason.value,
                    result.streams_moved,
                    result.instances_affected,
                    f"Smart rebalancing: {result.reason.value}"
                )
            )
            
        except Exception as e:
            logger.error(f"Error recording rebalance history: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def handle_instance_failure(self, failed_server_id: str) -> RebalanceResult:
        """
        Handle instance failure by redistributing its streams.
        
        Args:
            failed_server_id: ID of the failed server
            
        Returns:
            RebalanceResult with redistribution details
        """
        logger.info(f"Handling failure of instance {failed_server_id}")
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Mark instance as inactive
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET status = 'inactive', current_streams = 0
                WHERE server_id = %s
                """,
                (failed_server_id,)
            )
            
            # Get orphaned streams
            cursor.execute(
                """
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND status = 'active'
                """,
                (failed_server_id,)
            )
            
            orphaned_streams = [row[0] for row in cursor.fetchall()]
            
            if not orphaned_streams:
                logger.info(f"No orphaned streams found for failed instance {failed_server_id}")
                return RebalanceResult(
                    success=True,
                    reason=RebalanceReason.INSTANCE_FAILURE,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=1,
                    execution_time_ms=0
                )
            
            # Remove orphaned stream assignments
            cursor.execute(
                """
                DELETE FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND status = 'active'
                """,
                (failed_server_id,)
            )
            
            logger.info(f"Removed {len(orphaned_streams)} orphaned streams from {failed_server_id}")
            
            # Redistribute orphaned streams using smart load balancer
            instances = self.get_instance_metrics()
            active_instances = [inst for inst in instances if inst.server_id != failed_server_id]
            
            if not active_instances:
                logger.error("No active instances available for stream redistribution")
                return RebalanceResult(
                    success=False,
                    reason=RebalanceReason.INSTANCE_FAILURE,
                    migrations=[],
                    streams_moved=0,
                    instances_affected=1,
                    execution_time_ms=0,
                    error_message="No active instances available"
                )
            
            # Calculate optimal distribution for orphaned streams
            optimal_distribution = self.load_balancer.calculate_optimal_distribution(
                active_instances, len(orphaned_streams)
            )
            
            # Assign orphaned streams to active instances
            stream_index = 0
            total_assigned = 0
            
            for server_id, target_count in optimal_distribution.items():
                if stream_index >= len(orphaned_streams):
                    break
                
                streams_to_assign = orphaned_streams[stream_index:stream_index + target_count]
                
                if streams_to_assign:
                    # Insert new assignments
                    cursor.executemany(
                        """
                        INSERT INTO orchestrator_stream_assignments 
                        (stream_id, server_id, assigned_at, status)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
                        """,
                        [(stream_id, server_id) for stream_id in streams_to_assign]
                    )
                    
                    total_assigned += len(streams_to_assign)
                    stream_index += len(streams_to_assign)
                    
                    logger.info(f"Assigned {len(streams_to_assign)} streams to {server_id}")
            
            # Update instance stream counts
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = (
                    SELECT COUNT(*) 
                    FROM orchestrator_stream_assignments 
                    WHERE server_id = orchestrator_instances.server_id 
                      AND status = 'active'
                )
                WHERE status = 'active'
                """
            )
            
            # Update performance history
            if failed_server_id not in self.instance_performance_history:
                self.instance_performance_history[failed_server_id] = {}
            
            self.instance_performance_history[failed_server_id]['failure_count'] = \
                self.instance_performance_history[failed_server_id].get('failure_count', 0) + 1
            
            logger.info(
                f"Successfully redistributed {total_assigned} streams from failed instance {failed_server_id}"
            )
            
            return RebalanceResult(
                success=True,
                reason=RebalanceReason.INSTANCE_FAILURE,
                migrations=[],  # Direct assignment, not migration
                streams_moved=total_assigned,
                instances_affected=len(optimal_distribution) + 1,
                execution_time_ms=0  # Would be calculated in real implementation
            )
            
        except Exception as e:
            logger.error(f"Error handling instance failure: {e}")
            return RebalanceResult(
                success=False,
                reason=RebalanceReason.INSTANCE_FAILURE,
                migrations=[],
                streams_moved=0,
                instances_affected=1,
                execution_time_ms=0,
                error_message=str(e)
            )
        finally:
            cursor.close()
            conn.close()
    
    def verify_system_consistency(self) -> Dict:
        """
        Verify system consistency and detect imbalances.
        
        Returns:
            Dictionary with consistency report
        """
        instances = self.get_instance_metrics()
        
        if not instances:
            return {
                "consistent": False,
                "error": "No active instances found"
            }
        
        # Check for load imbalance
        needs_rebalance, reason = self.load_balancer.detect_imbalance(instances)
        
        # Calculate statistics
        stream_counts = [inst.current_streams for inst in instances]
        load_factors = [inst.load_factor for inst in instances]
        
        avg_streams = sum(stream_counts) / len(stream_counts) if stream_counts else 0
        max_streams = max(stream_counts) if stream_counts else 0
        min_streams = min(stream_counts) if stream_counts else 0
        
        max_load = max(load_factors) if load_factors else 0
        min_load = min(load_factors) if load_factors else 0
        
        return {
            "consistent": not needs_rebalance,
            "needs_rebalancing": needs_rebalance,
            "reason": reason,
            "statistics": {
                "total_instances": len(instances),
                "total_streams": sum(stream_counts),
                "average_streams_per_instance": avg_streams,
                "max_streams_per_instance": max_streams,
                "min_streams_per_instance": min_streams,
                "stream_difference": max_streams - min_streams,
                "max_load_factor": max_load,
                "min_load_factor": min_load,
                "load_imbalance": max_load - min_load
            },
            "instances": [
                {
                    "server_id": inst.server_id,
                    "current_streams": inst.current_streams,
                    "max_streams": inst.max_streams,
                    "load_factor": inst.load_factor,
                    "performance_score": inst.performance_score,
                    "available_capacity": inst.available_capacity
                }
                for inst in instances
            ]
        }
    
    def get_load_balancer_statistics(self) -> Dict:
        """Get load balancer statistics and performance metrics"""
        return self.load_balancer.get_rebalance_statistics()
"""
Integration module for Consistency Verification System

This module provides integration points between the consistency checker
and the existing orchestrator system, enabling seamless consistency
monitoring and auto-recovery in production.

Requirements addressed: 3.1, 3.2, 3.3, 3.4
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from consistency_checker import (ConsistencyChecker, ConsistencyMonitor,
                                 ConsistencyReport)
from enhanced_db_manager import EnhancedDatabaseManager

logger = logging.getLogger(__name__)


class ConsistencyService:
    """
    Main service class that integrates consistency checking with the orchestrator.
    Provides high-level API for consistency operations.
    """
    
    def __init__(self, db_manager: EnhancedDatabaseManager, 
                 auto_recovery_enabled: bool = True,
                 monitoring_interval: int = 300):
        self.db_manager = db_manager
        self.auto_recovery_enabled = auto_recovery_enabled
        self.monitoring_interval = monitoring_interval
        
        # Initialize components
        self.consistency_checker = ConsistencyChecker(db_manager)
        self.consistency_monitor = ConsistencyMonitor(
            self.consistency_checker, 
            check_interval=monitoring_interval
        )
        
        # Service state
        self.is_running = False
        self.last_health_check = None
        self.monitoring_task = None
        
        # Statistics
        self.stats = {
            'total_checks': 0,
            'issues_detected': 0,
            'successful_recoveries': 0,
            'failed_recoveries': 0,
            'last_check_time': None,
            'average_consistency_score': 0.0
        }
    
    async def start(self):
        """Start the consistency service with monitoring."""
        if self.is_running:
            logger.warning("Consistency service is already running")
            return
        
        logger.info("Starting consistency service")
        self.is_running = True
        
        # Start background monitoring
        self.monitoring_task = asyncio.create_task(self._run_monitoring())
        
        logger.info(f"Consistency service started with {self.monitoring_interval}s monitoring interval")
    
    async def stop(self):
        """Stop the consistency service."""
        if not self.is_running:
            return
        
        logger.info("Stopping consistency service")
        self.is_running = False
        
        # Stop monitoring
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.consistency_monitor.stop_monitoring()
        logger.info("Consistency service stopped")
    
    async def perform_health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive system health check.
        
        Returns detailed health information including consistency status.
        Requirements: 3.1, 3.4
        """
        logger.info("Performing system health check")
        
        try:
            # Run consistency verification
            report = await self.consistency_checker.verify_stream_assignments()
            self.last_health_check = report
            
            # Update statistics
            self._update_stats(report)
            
            # Determine overall health status
            health_status = self._determine_health_status(report)
            
            health_info = {
                'timestamp': datetime.now().isoformat(),
                'overall_status': health_status,
                'consistency_score': report.consistency_score,
                'total_streams': report.total_streams_checked,
                'total_instances': report.total_instances_checked,
                'issues_found': len(report.stream_issues),
                'critical_issues': len(report.critical_issues),
                'instance_issues': len(report.instance_issues),
                'recommendations': report.recommendations,
                'service_stats': self.stats.copy(),
                'auto_recovery_enabled': self.auto_recovery_enabled
            }
            
            # Log health status
            if health_status == 'healthy':
                logger.info(f"System health check: HEALTHY (score: {report.consistency_score:.2f})")
            elif health_status == 'warning':
                logger.warning(f"System health check: WARNING (score: {report.consistency_score:.2f}, issues: {len(report.stream_issues)})")
            else:
                logger.error(f"System health check: CRITICAL (score: {report.consistency_score:.2f}, critical issues: {len(report.critical_issues)})")
            
            return health_info
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'error',
                'error': str(e),
                'service_stats': self.stats.copy()
            }
    
    async def force_consistency_check(self) -> ConsistencyReport:
        """
        Force an immediate consistency check outside of regular monitoring.
        
        Requirements: 3.1, 3.3
        """
        logger.info("Forcing immediate consistency check")
        
        report = await self.consistency_checker.verify_stream_assignments()
        self._update_stats(report)
        
        return report
    
    async def resolve_specific_issue(self, stream_id: int) -> Dict[str, Any]:
        """
        Resolve consistency issues for a specific stream.
        
        Requirements: 3.2, 3.3
        """
        logger.info(f"Resolving consistency issues for stream {stream_id}")
        
        try:
            # Get current report
            report = await self.consistency_checker.verify_stream_assignments()
            
            # Find issues for this stream
            stream_issues = [issue for issue in report.stream_issues if issue.stream_id == stream_id]
            
            if not stream_issues:
                return {
                    'stream_id': stream_id,
                    'status': 'no_issues',
                    'message': f'No consistency issues found for stream {stream_id}'
                }
            
            # Attempt resolution
            recovery_results = await self.consistency_checker.resolve_conflicts(stream_issues)
            
            successful_recoveries = [r for r in recovery_results if r.success]
            failed_recoveries = [r for r in recovery_results if not r.success]
            
            # Update stats
            self.stats['successful_recoveries'] += len(successful_recoveries)
            self.stats['failed_recoveries'] += len(failed_recoveries)
            
            return {
                'stream_id': stream_id,
                'status': 'resolved' if len(successful_recoveries) > 0 else 'failed',
                'issues_found': len(stream_issues),
                'successful_recoveries': len(successful_recoveries),
                'failed_recoveries': len(failed_recoveries),
                'recovery_details': [
                    {
                        'action': r.action_taken.value,
                        'success': r.success,
                        'details': r.details
                    }
                    for r in recovery_results
                ]
            }
            
        except Exception as e:
            logger.error(f"Error resolving issues for stream {stream_id}: {e}")
            return {
                'stream_id': stream_id,
                'status': 'error',
                'error': str(e)
            }
    
    async def sync_instance(self, instance_id: str) -> Dict[str, Any]:
        """
        Synchronize state for a specific instance.
        
        Requirements: 3.1, 3.2, 3.4
        """
        logger.info(f"Synchronizing instance {instance_id}")
        
        try:
            result = await self.consistency_checker.synchronize_instance_state(instance_id)
            
            return {
                'instance_id': instance_id,
                'status': 'success' if result.success else 'failed',
                'action_taken': result.action_taken.value,
                'details': result.details,
                'affected_streams': result.affected_streams,
                'timestamp': result.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error synchronizing instance {instance_id}: {e}")
            return {
                'instance_id': instance_id,
                'status': 'error',
                'error': str(e)
            }
    
    async def get_consistency_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent consistency check history."""
        history = self.consistency_checker.consistency_history[-limit:]
        
        return {
            'total_reports': len(self.consistency_checker.consistency_history),
            'recent_reports': [
                {
                    'timestamp': report.timestamp.isoformat(),
                    'consistency_score': report.consistency_score,
                    'issues_count': len(report.stream_issues),
                    'critical_issues': len(report.critical_issues),
                    'is_healthy': report.is_healthy
                }
                for report in history
            ],
            'service_stats': self.stats.copy()
        }
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status and statistics."""
        return {
            'is_running': self.is_running,
            'auto_recovery_enabled': self.auto_recovery_enabled,
            'monitoring_interval': self.monitoring_interval,
            'last_health_check': self.last_health_check.timestamp.isoformat() if self.last_health_check else None,
            'stats': self.stats.copy()
        }
    
    # Private methods
    
    async def _run_monitoring(self):
        """Run continuous monitoring in background."""
        try:
            await self.consistency_monitor.start_monitoring()
        except asyncio.CancelledError:
            logger.info("Consistency monitoring cancelled")
        except Exception as e:
            logger.error(f"Error in consistency monitoring: {e}")
    
    def _update_stats(self, report: ConsistencyReport):
        """Update service statistics based on consistency report."""
        self.stats['total_checks'] += 1
        self.stats['issues_detected'] += len(report.stream_issues)
        self.stats['last_check_time'] = report.timestamp.isoformat()
        
        # Update average consistency score
        current_avg = self.stats['average_consistency_score']
        total_checks = self.stats['total_checks']
        self.stats['average_consistency_score'] = (
            (current_avg * (total_checks - 1) + report.consistency_score) / total_checks
        )
    
    def _determine_health_status(self, report: ConsistencyReport) -> str:
        """Determine overall health status based on consistency report."""
        if len(report.critical_issues) > 0:
            return 'critical'
        elif report.consistency_score < 0.8 or len(report.stream_issues) > 5:
            return 'warning'
        elif report.consistency_score >= 0.95 and len(report.stream_issues) == 0:
            return 'healthy'
        else:
            return 'warning'


class ConsistencyAPI:
    """
    REST API endpoints for consistency operations.
    Provides HTTP interface for consistency management.
    """
    
    def __init__(self, consistency_service: ConsistencyService):
        self.service = consistency_service
    
    async def health_check_endpoint(self) -> Dict[str, Any]:
        """GET /consistency/health - System health check."""
        return await self.service.perform_health_check()
    
    async def force_check_endpoint(self) -> Dict[str, Any]:
        """POST /consistency/check - Force consistency check."""
        report = await self.service.force_consistency_check()
        
        return {
            'timestamp': report.timestamp.isoformat(),
            'consistency_score': report.consistency_score,
            'total_streams': report.total_streams_checked,
            'total_instances': report.total_instances_checked,
            'issues_found': len(report.stream_issues),
            'critical_issues': len(report.critical_issues),
            'recommendations': report.recommendations,
            'is_healthy': report.is_healthy
        }
    
    async def resolve_stream_endpoint(self, stream_id: int) -> Dict[str, Any]:
        """POST /consistency/resolve/{stream_id} - Resolve stream issues."""
        return await self.service.resolve_specific_issue(stream_id)
    
    async def sync_instance_endpoint(self, instance_id: str) -> Dict[str, Any]:
        """POST /consistency/sync/{instance_id} - Sync instance state."""
        return await self.service.sync_instance(instance_id)
    
    async def history_endpoint(self, limit: int = 10) -> Dict[str, Any]:
        """GET /consistency/history - Get consistency history."""
        return await self.service.get_consistency_history(limit)
    
    async def status_endpoint(self) -> Dict[str, Any]:
        """GET /consistency/status - Get service status."""
        return self.service.get_service_status()


# Utility functions for integration

async def setup_consistency_service(db_manager: EnhancedDatabaseManager, 
                                  config: Dict[str, Any] = None) -> ConsistencyService:
    """
    Set up and configure the consistency service.
    
    Args:
        db_manager: Database manager instance
        config: Configuration dictionary with optional settings:
            - auto_recovery_enabled: bool (default: True)
            - monitoring_interval: int (default: 300)
    
    Returns:
        Configured ConsistencyService instance
    """
    config = config or {}
    
    service = ConsistencyService(
        db_manager=db_manager,
        auto_recovery_enabled=config.get('auto_recovery_enabled', True),
        monitoring_interval=config.get('monitoring_interval', 300)
    )
    
    return service


async def emergency_consistency_recovery(db_manager: EnhancedDatabaseManager) -> Dict[str, Any]:
    """
    Emergency consistency recovery function for critical situations.
    
    This function performs immediate consistency checking and recovery
    without starting the full service. Useful for emergency situations.
    
    Requirements: 3.2, 3.4
    """
    logger.warning("Performing emergency consistency recovery")
    
    try:
        # Create temporary checker
        checker = ConsistencyChecker(db_manager)
        
        # Perform immediate check
        report = await checker.verify_stream_assignments()
        
        # Attempt recovery for all issues
        recovery_results = []
        if len(report.stream_issues) > 0:
            recovery_results = await checker.auto_recover_inconsistencies(report)
        
        # Perform post-recovery check
        post_recovery_report = await checker.verify_stream_assignments()
        
        successful_recoveries = len([r for r in recovery_results if r.success])
        
        return {
            'timestamp': datetime.now().isoformat(),
            'emergency_recovery': True,
            'initial_issues': len(report.stream_issues),
            'initial_score': report.consistency_score,
            'recovery_attempts': len(recovery_results),
            'successful_recoveries': successful_recoveries,
            'final_issues': len(post_recovery_report.stream_issues),
            'final_score': post_recovery_report.consistency_score,
            'improvement': post_recovery_report.consistency_score - report.consistency_score,
            'recommendations': post_recovery_report.recommendations
        }
        
    except Exception as e:
        logger.error(f"Emergency recovery failed: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'emergency_recovery': True,
            'success': False,
            'error': str(e)
        }


# Configuration helpers

def get_default_consistency_config() -> Dict[str, Any]:
    """Get default configuration for consistency service."""
    return {
        'auto_recovery_enabled': True,
        'monitoring_interval': 300,  # 5 minutes
        'max_recovery_attempts': 3,
        'critical_issue_threshold': 0.8,  # Consistency score threshold for critical status
        'warning_issue_threshold': 0.9,   # Consistency score threshold for warning status
        'stale_heartbeat_threshold': 300,  # 5 minutes in seconds
        'enable_emergency_recovery': True
    }


def validate_consistency_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize consistency configuration."""
    defaults = get_default_consistency_config()
    
    # Merge with defaults
    validated_config = {**defaults, **config}
    
    # Validate ranges
    if validated_config['monitoring_interval'] < 60:
        logger.warning("Monitoring interval too low, setting to 60 seconds")
        validated_config['monitoring_interval'] = 60
    
    if validated_config['max_recovery_attempts'] < 1:
        validated_config['max_recovery_attempts'] = 1
    
    if not 0.0 <= validated_config['critical_issue_threshold'] <= 1.0:
        validated_config['critical_issue_threshold'] = 0.8
    
    if not 0.0 <= validated_config['warning_issue_threshold'] <= 1.0:
        validated_config['warning_issue_threshold'] = 0.9
    
    return validated_config
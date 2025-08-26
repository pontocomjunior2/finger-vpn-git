"""
Demonstration of the Consistency Verification and Auto-Recovery System

This script demonstrates how the consistency system integrates with the
existing orchestrator to provide comprehensive consistency checking and
automatic recovery capabilities.

Requirements demonstrated: 3.1, 3.2, 3.3, 3.4
"""

import asyncio
import logging
from datetime import datetime, timedelta

from consistency_checker import ConsistencyChecker, ConsistencyStatus
from consistency_integration import (ConsistencyService,
                                     emergency_consistency_recovery,
                                     setup_consistency_service)
from test_consistency_simple import SimpleDatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def demonstrate_consistency_system():
    """Demonstrate the complete consistency system functionality."""
    
    print("🔍 Consistency Verification and Auto-Recovery System Demo")
    print("=" * 60)
    
    # Setup test environment
    db_manager = SimpleDatabaseManager()
    await db_manager.setup_test_db()
    
    try:
        # Add some problematic data to demonstrate recovery
        await setup_problematic_data(db_manager)
        
        # 1. Demonstrate basic consistency checking
        print("\n1. 📊 Basic Consistency Checking")
        print("-" * 40)
        await demo_basic_consistency_check(db_manager)
        
        # 2. Demonstrate auto-recovery
        print("\n2. 🔧 Automatic Recovery")
        print("-" * 40)
        await demo_auto_recovery(db_manager)
        
        # 3. Demonstrate consistency service
        print("\n3. 🚀 Consistency Service Integration")
        print("-" * 40)
        await demo_consistency_service(db_manager)
        
        # 4. Demonstrate emergency recovery
        print("\n4. 🚨 Emergency Recovery")
        print("-" * 40)
        await demo_emergency_recovery(db_manager)
        
        print("\n" + "=" * 60)
        print("✅ All demonstrations completed successfully!")
        
    finally:
        await db_manager.cleanup()


async def setup_problematic_data(db_manager):
    """Set up some problematic data to demonstrate recovery."""
    print("Setting up problematic test data...")
    
    async with db_manager.get_connection() as conn:
        # Add orphaned streams
        await conn.execute("""
            INSERT INTO stream_assignments VALUES 
            (100, 'dead_worker', 'active', ?),
            (101, 'another_dead_worker', 'active', ?)
        """, (datetime.now().isoformat(), datetime.now().isoformat()))
        
        # Add instance with stale heartbeat
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        await conn.execute("""
            INSERT INTO instances VALUES 
            ('stale_worker', '192.168.1.99', 8099, 5, 2, 'active', ?)
        """, (old_time,))
        
        # Add duplicate assignment (simulate by adding same stream to multiple workers)
        await conn.execute("""
            INSERT INTO stream_assignments VALUES 
            (1, 'worker2', 'active', ?)
        """, (datetime.now().isoformat(),))
        
        await conn.commit()
    
    print("✓ Problematic data setup complete")


async def demo_basic_consistency_check(db_manager):
    """Demonstrate basic consistency checking capabilities."""
    
    checker = ConsistencyChecker(db_manager)
    
    print("Running comprehensive consistency check...")
    report = await checker.verify_stream_assignments()
    
    print(f"📈 Consistency Score: {report.consistency_score:.2f}")
    print(f"🔍 Total Streams Checked: {report.total_streams_checked}")
    print(f"🖥️  Total Instances Checked: {report.total_instances_checked}")
    print(f"⚠️  Issues Found: {len(report.stream_issues)}")
    print(f"🚨 Critical Issues: {len(report.critical_issues)}")
    
    if report.stream_issues:
        print("\n📋 Detected Issues:")
        for i, issue in enumerate(report.stream_issues[:3], 1):  # Show first 3
            print(f"  {i}. Stream {issue.stream_id}: {issue.issue_type.value} - {issue.description}")
    
    if report.recommendations:
        print("\n💡 Recommendations:")
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")
    
    print(f"\n🏥 System Health: {'✅ Healthy' if report.is_healthy else '⚠️ Needs Attention'}")


async def demo_auto_recovery(db_manager):
    """Demonstrate automatic recovery capabilities."""
    
    checker = ConsistencyChecker(db_manager)
    
    print("Detecting issues for auto-recovery...")
    report = await checker.verify_stream_assignments()
    
    if len(report.stream_issues) > 0:
        print(f"Found {len(report.stream_issues)} issues to recover")
        
        print("\nAttempting auto-recovery...")
        recovery_results = await checker.auto_recover_inconsistencies(report)
        
        successful = len([r for r in recovery_results if r.success])
        failed = len([r for r in recovery_results if not r.success])
        
        print(f"✅ Successful recoveries: {successful}")
        print(f"❌ Failed recoveries: {failed}")
        
        if recovery_results:
            print("\n🔧 Recovery Actions Taken:")
            for i, result in enumerate(recovery_results[:3], 1):  # Show first 3
                status = "✅" if result.success else "❌"
                print(f"  {i}. {status} {result.action_taken.value}: {result.details}")
        
        # Check improvement
        print("\nVerifying recovery effectiveness...")
        post_recovery_report = await checker.verify_stream_assignments()
        improvement = post_recovery_report.consistency_score - report.consistency_score
        
        print(f"📈 Consistency improvement: {improvement:+.2f}")
        print(f"📊 New consistency score: {post_recovery_report.consistency_score:.2f}")
    else:
        print("No issues found - system is already consistent!")


async def demo_consistency_service(db_manager):
    """Demonstrate the integrated consistency service."""
    
    print("Setting up consistency service...")
    
    # Setup service with custom configuration
    config = {
        'auto_recovery_enabled': True,
        'monitoring_interval': 60  # 1 minute for demo
    }
    
    service = await setup_consistency_service(db_manager, config)
    
    try:
        print("✓ Consistency service initialized")
        
        # Perform health check
        print("\nPerforming system health check...")
        health_info = await service.perform_health_check()
        
        print(f"🏥 Overall Status: {health_info['overall_status']}")
        print(f"📊 Consistency Score: {health_info['consistency_score']:.2f}")
        print(f"⚠️  Issues Found: {health_info['issues_found']}")
        
        # Force a consistency check
        print("\nForcing immediate consistency check...")
        report = await service.force_consistency_check()
        
        print(f"✅ Check completed - Score: {report.consistency_score:.2f}")
        
        # Resolve specific issue if any exist
        if len(report.stream_issues) > 0:
            stream_id = report.stream_issues[0].stream_id
            print(f"\nResolving specific issue for stream {stream_id}...")
            
            resolution_result = await service.resolve_specific_issue(stream_id)
            print(f"🔧 Resolution status: {resolution_result['status']}")
            
        # Get service statistics
        print("\nService Statistics:")
        stats = service.get_service_status()
        service_stats = stats['stats']
        print(f"  📈 Total Checks: {service_stats['total_checks']}")
        print(f"  🔍 Issues Detected: {service_stats['issues_detected']}")
        print(f"  ✅ Successful Recoveries: {service_stats['successful_recoveries']}")
        print(f"  📊 Average Score: {service_stats['average_consistency_score']:.2f}")
        
    finally:
        await service.stop()
        print("✓ Consistency service stopped")


async def demo_emergency_recovery(db_manager):
    """Demonstrate emergency recovery capabilities."""
    
    print("Simulating emergency recovery scenario...")
    
    # Add more critical issues
    async with db_manager.get_connection() as conn:
        await conn.execute("""
            INSERT INTO stream_assignments VALUES 
            (200, 'critical_dead_worker', 'active', ?),
            (201, 'critical_dead_worker', 'active', ?)
        """, (datetime.now().isoformat(), datetime.now().isoformat()))
        await conn.commit()
    
    print("🚨 Critical issues added - running emergency recovery...")
    
    # Run emergency recovery
    recovery_info = await emergency_consistency_recovery(db_manager)
    
    print(f"⚡ Emergency Recovery Results:")
    print(f"  📊 Initial Issues: {recovery_info['initial_issues']}")
    print(f"  📈 Initial Score: {recovery_info['initial_score']:.2f}")
    print(f"  🔧 Recovery Attempts: {recovery_info['recovery_attempts']}")
    print(f"  ✅ Successful Recoveries: {recovery_info['successful_recoveries']}")
    print(f"  📊 Final Score: {recovery_info['final_score']:.2f}")
    print(f"  📈 Improvement: {recovery_info['improvement']:+.2f}")
    
    if recovery_info['recommendations']:
        print("\n💡 Post-Recovery Recommendations:")
        for i, rec in enumerate(recovery_info['recommendations'], 1):
            print(f"  {i}. {rec}")


async def demo_monitoring_cycle():
    """Demonstrate continuous monitoring (shortened for demo)."""
    
    print("\n5. 🔄 Continuous Monitoring Demo")
    print("-" * 40)
    
    db_manager = SimpleDatabaseManager()
    await db_manager.setup_test_db()
    
    try:
        service = await setup_consistency_service(db_manager, {'monitoring_interval': 5})
        
        print("Starting monitoring service for 15 seconds...")
        
        # Start monitoring
        await service.start()
        
        # Let it run for a short time
        await asyncio.sleep(15)
        
        # Check what happened
        history = await service.get_consistency_history(limit=5)
        print(f"📊 Monitoring completed - {len(history['recent_reports'])} checks performed")
        
        if history['recent_reports']:
            latest = history['recent_reports'][-1]
            print(f"📈 Latest consistency score: {latest['consistency_score']:.2f}")
        
        await service.stop()
        
    finally:
        await db_manager.cleanup()


if __name__ == "__main__":
    print("Starting Consistency System Demonstration...")
    asyncio.run(demonstrate_consistency_system())
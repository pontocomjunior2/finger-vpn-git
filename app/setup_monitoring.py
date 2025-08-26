#!/usr/bin/env python3
"""
Monitoring System Setup Script

This script sets up the comprehensive monitoring and alerting system
for the orchestrator and worker components.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from monitoring_api import create_monitoring_api, run_monitoring_server
from monitoring_config import (MonitoringConfigManager, add_custom_alert_rule,
                               get_monitoring_config,
                               validate_monitoring_config)
from monitoring_dashboard import setup_comprehensive_monitoring
from monitoring_integration import (add_monitoring_to_orchestrator,
                                    add_monitoring_to_worker,
                                    setup_orchestrator_monitoring,
                                    setup_worker_monitoring)
# Import monitoring components
from monitoring_system import AlertSeverity, create_monitoring_system

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonitoringSetup:
    """Comprehensive monitoring system setup"""
    
    def __init__(self):
        self.monitoring_system = None
        self.monitoring_api = None
        self.config_manager = MonitoringConfigManager()
        self.dashboard_components = None
    
    async def setup_monitoring_system(self, db_config=None):
        """Setup the core monitoring system"""
        logger.info("Setting up monitoring system...")
        
        # Create monitoring system
        self.monitoring_system = create_monitoring_system(db_config)
        
        # Load and apply configuration
        config = self.config_manager.get_config()
        
        # Add custom alert rules from configuration
        for rule_name, rule_config in config.alert_rules.items():
            if rule_config.enabled:
                self.monitoring_system.add_custom_alert_rule(
                    rule_name=rule_config.name,
                    metric_name=rule_config.metric_name,
                    threshold=rule_config.threshold,
                    severity=getattr(AlertSeverity, rule_config.severity.upper()),
                    duration=rule_config.duration
                )
        
        logger.info("Monitoring system setup complete")
        return self.monitoring_system
    
    async def setup_monitoring_api(self, host="0.0.0.0", port=8080):
        """Setup the monitoring API server"""
        logger.info(f"Setting up monitoring API on {host}:{port}...")
        
        if not self.monitoring_system:
            await self.setup_monitoring_system()
        
        self.monitoring_api = create_monitoring_api(self.monitoring_system)
        
        logger.info("Monitoring API setup complete")
        return self.monitoring_api
    
    async def setup_dashboard_and_notifications(self):
        """Setup dashboard and notification system"""
        logger.info("Setting up dashboard and notifications...")
        
        if not self.monitoring_system:
            await self.setup_monitoring_system()
        
        self.dashboard_components = setup_comprehensive_monitoring(self.monitoring_system)
        
        logger.info("Dashboard and notifications setup complete")
        return self.dashboard_components
    
    async def start_monitoring(self):
        """Start all monitoring components"""
        logger.info("Starting monitoring system...")
        
        if not self.monitoring_system:
            await self.setup_monitoring_system()
        
        # Start monitoring tasks
        await self.monitoring_system.start_monitoring()
        
        logger.info("Monitoring system started successfully")
    
    async def stop_monitoring(self):
        """Stop all monitoring components"""
        logger.info("Stopping monitoring system...")
        
        if self.monitoring_system:
            await self.monitoring_system.stop_monitoring()
        
        logger.info("Monitoring system stopped")
    
    def validate_setup(self):
        """Validate monitoring setup"""
        logger.info("Validating monitoring setup...")
        
        validation_results = []
        
        # Validate configuration
        config_validation = validate_monitoring_config()
        validation_results.append(("Configuration", config_validation))
        
        # Check if monitoring system is created
        if self.monitoring_system:
            validation_results.append(("Monitoring System", {"valid": True, "message": "Created successfully"}))
        else:
            validation_results.append(("Monitoring System", {"valid": False, "message": "Not created"}))
        
        # Check if API is setup
        if self.monitoring_api:
            validation_results.append(("Monitoring API", {"valid": True, "message": "Setup successfully"}))
        else:
            validation_results.append(("Monitoring API", {"valid": False, "message": "Not setup"}))
        
        # Print validation results
        logger.info("Validation Results:")
        for component, result in validation_results:
            status = "✓" if result.get("valid", False) else "✗"
            logger.info(f"  {status} {component}: {result.get('message', 'Unknown status')}")
            
            if "errors" in result and result["errors"]:
                for error in result["errors"]:
                    logger.error(f"    Error: {error}")
            
            if "warnings" in result and result["warnings"]:
                for warning in result["warnings"]:
                    logger.warning(f"    Warning: {warning}")
        
        return validation_results
    
    async def run_monitoring_server(self, host="0.0.0.0", port=8080):
        """Run the monitoring server"""
        logger.info("Starting monitoring server...")
        
        # Setup everything
        await self.setup_monitoring_system()
        await self.setup_monitoring_api(host, port)
        await self.setup_dashboard_and_notifications()
        
        # Start monitoring
        await self.start_monitoring()
        
        # Validate setup
        self.validate_setup()
        
        try:
            # Run the API server
            await run_monitoring_server(host, port, self.monitoring_system)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            await self.stop_monitoring()
    
    def create_example_config(self, filepath="monitoring_config_example.json"):
        """Create example configuration file"""
        logger.info(f"Creating example configuration: {filepath}")
        
        self.config_manager.export_config_template(filepath)
        
        logger.info(f"Example configuration created: {filepath}")
    
    def add_orchestrator_monitoring(self, orchestrator_class):
        """Add monitoring to orchestrator class"""
        logger.info("Adding monitoring to orchestrator class...")
        
        monitored_class = add_monitoring_to_orchestrator(orchestrator_class)
        
        logger.info("Orchestrator monitoring integration complete")
        return monitored_class
    
    def add_worker_monitoring(self, worker_class):
        """Add monitoring to worker class"""
        logger.info("Adding monitoring to worker class...")
        
        monitored_class = add_monitoring_to_worker(worker_class)
        
        logger.info("Worker monitoring integration complete")
        return monitored_class


async def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description="Setup Orchestrator Monitoring System")
    parser.add_argument("--action", choices=["setup", "run", "validate", "config"], 
                       default="setup", help="Action to perform")
    parser.add_argument("--host", default="0.0.0.0", help="API server host")
    parser.add_argument("--port", type=int, default=8080, help="API server port")
    parser.add_argument("--config-file", help="Configuration file path")
    
    args = parser.parse_args()
    
    # Create setup instance
    setup = MonitoringSetup()
    
    try:
        if args.action == "setup":
            # Full setup without running server
            await setup.setup_monitoring_system()
            await setup.setup_monitoring_api(args.host, args.port)
            await setup.setup_dashboard_and_notifications()
            setup.validate_setup()
            logger.info("Monitoring system setup complete. Use --action=run to start server.")
        
        elif args.action == "run":
            # Setup and run server
            await setup.run_monitoring_server(args.host, args.port)
        
        elif args.action == "validate":
            # Validate current setup
            setup.validate_setup()
        
        elif args.action == "config":
            # Create example configuration
            config_file = args.config_file or "monitoring_config_example.json"
            setup.create_example_config(config_file)
    
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)


def setup_orchestrator_with_monitoring(orchestrator_class, db_config=None):
    """Convenience function to setup orchestrator with monitoring"""
    
    async def _setup():
        setup = MonitoringSetup()
        
        # Add monitoring to orchestrator class
        monitored_orchestrator_class = setup.add_orchestrator_monitoring(orchestrator_class)
        
        # Setup monitoring system
        monitoring_system = await setup.setup_monitoring_system(db_config)
        
        return monitored_orchestrator_class, monitoring_system
    
    return asyncio.run(_setup())


def setup_worker_with_monitoring(worker_class):
    """Convenience function to setup worker with monitoring"""
    
    async def _setup():
        setup = MonitoringSetup()
        
        # Add monitoring to worker class
        monitored_worker_class = setup.add_worker_monitoring(worker_class)
        
        # Setup monitoring system
        monitoring_system = await setup.setup_monitoring_system()
        
        return monitored_worker_class, monitoring_system
    
    return asyncio.run(_setup())


# Example usage functions
def example_orchestrator_integration():
    """Example of integrating monitoring with orchestrator"""
    
    class ExampleOrchestrator:
        def __init__(self):
            self.instances = {}
        
        def register_instance(self, server_id, instance_info):
            self.instances[server_id] = instance_info
        
        def get_instances(self):
            return self.instances
    
    # Add monitoring
    MonitoredOrchestrator, monitoring_system = setup_orchestrator_with_monitoring(ExampleOrchestrator)
    
    # Create monitored instance
    orchestrator = MonitoredOrchestrator()
    
    # Use monitoring features
    with orchestrator.monitor_operation("register_instance"):
        orchestrator.register_instance("server1", {"ip": "192.168.1.100", "port": 8080})
    
    logger.info("Example orchestrator integration complete")
    return orchestrator, monitoring_system


def example_worker_integration():
    """Example of integrating monitoring with worker"""
    
    class ExampleWorker:
        def __init__(self):
            self.assigned_streams = []
        
        def process_stream(self, stream_id):
            self.assigned_streams.append(stream_id)
            return f"Processed stream {stream_id}"
    
    # Add monitoring
    MonitoredWorker, monitoring_system = setup_worker_with_monitoring(ExampleWorker)
    
    # Create monitored instance
    worker = MonitoredWorker()
    
    # Use monitoring features
    worker.record_stream_processing(123, 150.0, True)
    
    logger.info("Example worker integration complete")
    return worker, monitoring_system


if __name__ == "__main__":
    # Run main setup
    asyncio.run(main())
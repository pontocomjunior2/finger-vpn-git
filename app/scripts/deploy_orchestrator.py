#!/usr/bin/env python3
"""
Orchestrator Deployment Automation Script
Complete deployment automation with configuration, validation, and monitoring setup
"""
import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager
from scripts.configure_deployment import DeploymentConfigurator
from scripts.deploy import DeploymentConfig, DeploymentManager
from scripts.health_check import HealthChecker
from scripts.setup_monitoring import MonitoringSetup
from scripts.validate_deployment import DeploymentValidator

logger = logging.getLogger(__name__)


class OrchestratorDeployment:
    """Complete orchestrator deployment automation"""
    
    def __init__(self, environment: str = "production", options: Dict = None):
        self.environment = environment
        self.options = options or {}
        self.deployment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize components
        self.config_manager = ConfigManager()
        self.configurator = DeploymentConfigurator(environment)
        self.validator = DeploymentValidator(environment)
        self.health_checker = HealthChecker(environment)
        
        # Deployment options
        self.skip_validation = self.options.get('skip_validation', False)
        self.skip_monitoring = self.options.get('skip_monitoring', False)
        self.skip_backup = self.options.get('skip_backup', False)
        self.force_deploy = self.options.get('force_deploy', False)
        self.dry_run = self.options.get('dry_run', False)
    
    def deploy(self) -> bool:
        """Execute complete deployment process"""
        logger.info(f"Starting orchestrator deployment {self.deployment_id} for {self.environment}")
        
        try:
            # Phase 1: Pre-deployment validation
            if not self.skip_validation and not self._validate_deployment():
                if not self.force_deploy:
                    logger.error("Pre-deployment validation failed. Use --force to override.")
                    return False
                logger.warning("Validation failed but continuing due to --force flag")
            
            # Phase 2: Configuration generation
            if not self._generate_configuration():
                logger.error("Configuration generation failed")
                return False
            
            # Phase 3: Monitoring setup
            if not self.skip_monitoring and not self._setup_monitoring():
                logger.warning("Monitoring setup failed, continuing without monitoring")
            
            # Phase 4: Deployment execution
            if self.dry_run:
                logger.info("Dry run mode - skipping actual deployment")
                return True
            
            if not self._execute_deployment():
                logger.error("Deployment execution failed")
                return False
            
            # Phase 5: Post-deployment verification
            if not self._verify_deployment():
                logger.error("Post-deployment verification failed")
                return False
            
            # Phase 6: Final health check
            if not self._final_health_check():
                logger.error("Final health check failed")
                return False
            
            logger.info(f"Deployment {self.deployment_id} completed successfully!")
            self._log_deployment_success()
            return True
            
        except Exception as e:
            logger.error(f"Deployment failed with exception: {e}")
            self._log_deployment_failure(str(e))
            return False
    
    def _validate_deployment(self) -> bool:
        """Run pre-deployment validation"""
        logger.info("Running pre-deployment validation...")
        
        try:
            return self.validator.validate_deployment()
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
    
    def _generate_configuration(self) -> bool:
        """Generate deployment configuration"""
        logger.info("Generating deployment configuration...")
        
        try:
            return self.configurator.configure_deployment()
        except Exception as e:
            logger.error(f"Configuration generation failed: {e}")
            return False
    
    def _setup_monitoring(self) -> bool:
        """Setup monitoring infrastructure"""
        logger.info("Setting up monitoring...")
        
        try:
            monitoring_setup = MonitoringSetup(self.environment)
            return monitoring_setup.setup_monitoring()
        except Exception as e:
            logger.error(f"Monitoring setup failed: {e}")
            return False
    
    def _execute_deployment(self) -> bool:
        """Execute the actual deployment"""
        logger.info("Executing deployment...")
        
        try:
            deployment_config = DeploymentConfig(
                environment=self.environment,
                services=["orchestrator", "monitoring"] if not self.skip_monitoring else ["orchestrator"],
                rollback_enabled=not self.skip_backup,
                backup_enabled=not self.skip_backup,
                pre_deploy_tests=not self.skip_validation,
                post_deploy_tests=True
            )
            
            deployment_manager = DeploymentManager(deployment_config)
            return deployment_manager.deploy()
            
        except Exception as e:
            logger.error(f"Deployment execution failed: {e}")
            return False
    
    def _verify_deployment(self) -> bool:
        """Verify deployment was successful"""
        logger.info("Verifying deployment...")
        
        try:
            # Check if services are running
            compose_file = f"deployment_{self.environment}/docker-compose.{self.environment}.yml"
            if not Path(compose_file).exists():
                compose_file = f"docker-compose.{self.environment}.yml"
            
            result = subprocess.run([
                "docker-compose", "-f", compose_file, "ps"
            ], capture_output=True, text=True, check=True)
            
            # Check if all expected services are running
            expected_services = ["orchestrator"]
            if not self.skip_monitoring:
                expected_services.extend(["prometheus", "grafana"])
            
            running_services = []
            for line in result.stdout.split('\n'):
                if 'Up' in line:
                    for service in expected_services:
                        if service in line:
                            running_services.append(service)
            
            missing_services = set(expected_services) - set(running_services)
            if missing_services:
                logger.error(f"Services not running: {missing_services}")
                return False
            
            logger.info(f"All expected services are running: {running_services}")
            return True
            
        except Exception as e:
            logger.error(f"Deployment verification failed: {e}")
            return False
    
    def _final_health_check(self) -> bool:
        """Perform final health check"""
        logger.info("Performing final health check...")
        
        try:
            # Wait for services to be healthy
            import asyncio
            return asyncio.run(self.health_checker.wait_for_healthy(timeout=300))
            
        except Exception as e:
            logger.error(f"Final health check failed: {e}")
            return False
    
    def _log_deployment_success(self):
        """Log successful deployment"""
        deployment_log = {
            "event": "deployment_success",
            "deployment_id": self.deployment_id,
            "environment": self.environment,
            "timestamp": datetime.now().isoformat(),
            "options": self.options
        }
        
        log_file = Path("deployment_history.log")
        with open(log_file, "a") as f:
            f.write(json.dumps(deployment_log) + "\n")
    
    def _log_deployment_failure(self, error: str):
        """Log failed deployment"""
        deployment_log = {
            "event": "deployment_failure",
            "deployment_id": self.deployment_id,
            "environment": self.environment,
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "options": self.options
        }
        
        log_file = Path("deployment_history.log")
        with open(log_file, "a") as f:
            f.write(json.dumps(deployment_log) + "\n")
    
    def rollback(self, snapshot_id: str = None) -> bool:
        """Rollback deployment"""
        logger.info(f"Rolling back deployment for {self.environment}")
        
        try:
            deployment_config = DeploymentConfig(environment=self.environment)
            deployment_manager = DeploymentManager(deployment_config)
            
            if snapshot_id:
                return deployment_manager.rollback_to_snapshot(snapshot_id)
            else:
                # Find latest backup
                backup_dirs = list(Path(".").glob("deployment_backup_*"))
                if not backup_dirs:
                    logger.error("No backup found for rollback")
                    return False
                
                latest_backup = max(backup_dirs, key=lambda p: p.stat().st_mtime)
                logger.info(f"Rolling back to: {latest_backup}")
                
                # Use the existing rollback method
                return deployment_manager._rollback()
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    def status(self) -> Dict:
        """Get deployment status"""
        try:
            deployment_config = DeploymentConfig(environment=self.environment)
            deployment_manager = DeploymentManager(deployment_config)
            return deployment_manager.get_deployment_status()
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"error": str(e)}


def main():
    """CLI interface for orchestrator deployment"""
    parser = argparse.ArgumentParser(description="Orchestrator Deployment Automation")
    
    # Environment and basic options
    parser.add_argument("--environment", "-e", default="production",
                       help="Environment to deploy")
    parser.add_argument("--dry-run", action="store_true",
                       help="Perform dry run without actual deployment")
    parser.add_argument("--force", action="store_true",
                       help="Force deployment even if validation fails")
    
    # Skip options
    parser.add_argument("--skip-validation", action="store_true",
                       help="Skip pre-deployment validation")
    parser.add_argument("--skip-monitoring", action="store_true",
                       help="Skip monitoring setup")
    parser.add_argument("--skip-backup", action="store_true",
                       help="Skip backup creation")
    
    # Actions
    parser.add_argument("--rollback", metavar="SNAPSHOT_ID", nargs="?", const="latest",
                       help="Rollback deployment (optionally to specific snapshot)")
    parser.add_argument("--status", action="store_true",
                       help="Show deployment status")
    
    # Logging
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    parser.add_argument("--quiet", "-q", action="store_true",
                       help="Quiet mode - minimal output")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Prepare options
    options = {
        'skip_validation': args.skip_validation,
        'skip_monitoring': args.skip_monitoring,
        'skip_backup': args.skip_backup,
        'force_deploy': args.force,
        'dry_run': args.dry_run
    }
    
    deployment = OrchestratorDeployment(args.environment, options)
    
    # Handle different actions
    if args.status:
        status = deployment.status()
        print(json.dumps(status, indent=2))
        return
    
    if args.rollback:
        snapshot_id = args.rollback if args.rollback != "latest" else None
        success = deployment.rollback(snapshot_id)
        sys.exit(0 if success else 1)
    
    # Default action: deploy
    success = deployment.deploy()
    
    if success:
        print(f"\n✅ Deployment completed successfully!")
        print(f"Environment: {args.environment}")
        print(f"Deployment ID: {deployment.deployment_id}")
        
        if not args.skip_monitoring:
            print(f"\n📊 Monitoring URLs:")
            print(f"  Grafana: http://localhost:3000 (admin/admin)")
            print(f"  Prometheus: http://localhost:9090")
            print(f"  Alertmanager: http://localhost:9093")
        
        print(f"\n🔍 Health check: python app/scripts/health_check.py -e {args.environment}")
    else:
        print(f"\n❌ Deployment failed!")
        print(f"Check logs for details.")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
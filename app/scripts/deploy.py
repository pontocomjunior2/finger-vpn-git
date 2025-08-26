#!/usr/bin/env python3
"""
Deployment Script with Health Checks and Rollback Capabilities
Handles deployment of orchestrator system components with safety checks
"""
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import argp
import requests

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Deployment configuration"""
    environment: str = "production"
    services: List[str] = None
    health_check_timeout: int = 300  # 5 minutes
    health_check_interval: int = 10  # 10 seconds
    rollback_enabled: bool = True
    backup_enabled: bool = True
    pre_deploy_tests: bool = True
    post_deploy_tests: bool = True
    
    def __post_init__(self):
        if self.services is None:
            self.services = ["orchestrator", "monitoring"]


@dataclass
class HealthCheckResult:
    """Health check result"""
    service: str
    healthy: bool
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class DeploymentManager:
    """Manages deployment process with health checks and rollback"""
    
    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.config_manager = ConfigManager()
        self.deployment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = Path(f"deployment_backup_{self.deployment_id}")
        
        # Service health check endpoints
        self.health_endpoints = {
            "orchestrator": "/health",
            "monitoring": "/api/health"
        }
        
        # Service ports from config
        env_config = self.config_manager.load_environment_config(config.environment)
        self.service_ports = {
            "orchestrator": env_config.get("ORCHESTRATOR_PORT", "8001"),
            "monitoring": env_config.get("API_PORT", "8080")
        }
    
    def deploy(self) -> bool:
        """Execute full deployment process"""
        logger.info(f"Starting deployment {self.deployment_id} for environment: {self.config.environment}")
        
        try:
            # Pre-deployment steps
            if not self._pre_deployment_checks():
                logger.error("Pre-deployment checks failed")
                return False
            
            # Backup current state
            if self.config.backup_enabled:
                if not self._backup_current_state():
                    logger.error("Backup failed")
                    return False
            
            # Deploy services
            if not self._deploy_services():
                logger.error("Service deployment failed")
                if self.config.rollback_enabled:
                    self._rollback()
                return False
            
            # Health checks
            if not self._wait_for_services_healthy():
                logger.error("Health checks failed")
                if self.config.rollback_enabled:
                    self._rollback()
                return False
            
            # Post-deployment tests
            if self.config.post_deploy_tests:
                if not self._run_post_deployment_tests():
                    logger.error("Post-deployment tests failed")
                    if self.config.rollback_enabled:
                        self._rollback()
                    return False
            
            logger.info(f"Deployment {self.deployment_id} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Deployment failed with exception: {e}")
            if self.config.rollback_enabled:
                self._rollback()
            return False
    
    def _pre_deployment_checks(self) -> bool:
        """Run pre-deployment checks"""
        logger.info("Running pre-deployment checks...")
        
        # Validate configuration
        env_config = self.config_manager.load_environment_config(self.config.environment)
        validation_result = self.config_manager.validate_configuration(env_config, "orchestrator")
        
        if not validation_result.valid:
            logger.error("Configuration validation failed:")
            for error in validation_result.errors:
                logger.error(f"  - {error}")
            return False
        
        # Check Docker availability
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            subprocess.run(["docker-compose", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Docker or docker-compose not available")
            return False
        
        # Run pre-deployment tests if enabled
        if self.config.pre_deploy_tests:
            if not self._run_pre_deployment_tests():
                return False
        
        logger.info("Pre-deployment checks passed")
        return True 
   
    def _backup_current_state(self) -> bool:
        """Backup current deployment state"""
        logger.info("Backing up current state...")
        
        try:
            self.backup_dir.mkdir(exist_ok=True)
            
            # Backup configuration
            self.config_manager.backup_configuration(str(self.backup_dir / "config"))
            
            # Backup docker-compose files
            for compose_file in Path(".").glob("docker-compose*.yaml"):
                if compose_file.exists():
                    import shutil
                    shutil.copy2(compose_file, self.backup_dir)
            
            # Export current container states
            try:
                result = subprocess.run(
                    ["docker-compose", "ps", "--format", "json"],
                    capture_output=True, text=True, check=True
                )
                
                with open(self.backup_dir / "container_states.json", "w") as f:
                    f.write(result.stdout)
                    
            except subprocess.CalledProcessError:
                logger.warning("Could not backup container states")
            
            logger.info(f"Backup completed: {self.backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False
    
    def _deploy_services(self) -> bool:
        """Deploy services using docker-compose"""
        logger.info("Deploying services...")
        
        try:
            # Generate docker-compose file for environment
            compose_file = f"docker-compose.{self.config.environment}.yaml"
            if not self.config_manager.generate_docker_compose(
                self.config.environment, compose_file
            ):
                logger.error("Failed to generate docker-compose file")
                return False
            
            # Pull latest images
            logger.info("Pulling latest images...")
            subprocess.run([
                "docker-compose", "-f", compose_file, "pull"
            ], check=True)
            
            # Stop existing services
            logger.info("Stopping existing services...")
            subprocess.run([
                "docker-compose", "-f", compose_file, "down"
            ], check=False)  # Don't fail if services weren't running
            
            # Start services
            logger.info("Starting services...")
            subprocess.run([
                "docker-compose", "-f", compose_file, "up", "-d"
            ], check=True)
            
            logger.info("Services deployed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker-compose command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Service deployment failed: {e}")
            return False
    
    def _wait_for_services_healthy(self) -> bool:
        """Wait for all services to become healthy"""
        logger.info("Waiting for services to become healthy...")
        
        start_time = time.time()
        
        while time.time() - start_time < self.config.health_check_timeout:
            all_healthy = True
            
            for service in self.config.services:
                health_result = self._check_service_health(service)
                
                if not health_result.healthy:
                    all_healthy = False
                    logger.info(f"Service {service} not healthy yet: {health_result.error}")
                else:
                    logger.info(f"Service {service} is healthy (response time: {health_result.response_time:.2f}s)")
            
            if all_healthy:
                logger.info("All services are healthy")
                return True
            
            time.sleep(self.config.health_check_interval)
        
        logger.error("Health check timeout reached")
        return False
    
    def _check_service_health(self, service: str) -> HealthCheckResult:
        """Check health of a specific service"""
        port = self.service_ports.get(service)
        endpoint = self.health_endpoints.get(service, "/health")
        
        if not port:
            return HealthCheckResult(
                service=service,
                healthy=False,
                error=f"No port configured for service {service}"
            )
        
        url = f"http://localhost:{port}{endpoint}"
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=10)
            response_time = time.time() - start_time
            
            healthy = response.status_code == 200
            
            return HealthCheckResult(
                service=service,
                healthy=healthy,
                status_code=response.status_code,
                response_time=response_time,
                error=None if healthy else f"HTTP {response.status_code}"
            )
            
        except requests.exceptions.RequestException as e:
            return HealthCheckResult(
                service=service,
                healthy=False,
                error=str(e)
            )
    
    def _run_pre_deployment_tests(self) -> bool:
        """Run pre-deployment tests"""
        logger.info("Running pre-deployment tests...")
        
        try:
            # Run configuration validation tests
            test_script = Path(__file__).parent.parent / "test_configuration.py"
            if test_script.exists():
                result = subprocess.run([
                    sys.executable, str(test_script), "--environment", self.config.environment
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.error(f"Pre-deployment tests failed: {result.stderr}")
                    return False
            
            logger.info("Pre-deployment tests passed")
            return True
            
        except Exception as e:
            logger.error(f"Pre-deployment tests failed: {e}")
            return False
    
    def _run_post_deployment_tests(self) -> bool:
        """Run post-deployment tests"""
        logger.info("Running post-deployment tests...")
        
        try:
            # Test service endpoints
            for service in self.config.services:
                health_result = self._check_service_health(service)
                if not health_result.healthy:
                    logger.error(f"Post-deployment health check failed for {service}")
                    return False
            
            # Run integration tests if available
            test_script = Path(__file__).parent.parent / "test_integration_orchestrator_worker.py"
            if test_script.exists():
                result = subprocess.run([
                    sys.executable, str(test_script)
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    logger.error(f"Integration tests failed: {result.stderr}")
                    return False
            
            logger.info("Post-deployment tests passed")
            return True
            
        except Exception as e:
            logger.error(f"Post-deployment tests failed: {e}")
            return False
    
    def _rollback(self) -> bool:
        """Rollback to previous deployment state"""
        logger.info(f"Rolling back deployment {self.deployment_id}...")
        
        try:
            if not self.backup_dir.exists():
                logger.error("No backup found for rollback")
                return False
            
            # Stop current services
            compose_file = f"docker-compose.{self.config.environment}.yaml"
            subprocess.run([
                "docker-compose", "-f", compose_file, "down"
            ], check=False)
            
            # Restore configuration
            config_backup = self.backup_dir / "config"
            if config_backup.exists():
                import shutil
                shutil.copytree(config_backup, "config", dirs_exist_ok=True)
            
            # Restore docker-compose files
            for backup_file in self.backup_dir.glob("docker-compose*.yaml"):
                import shutil
                shutil.copy2(backup_file, ".")
            
            # Restore environment files
            for backup_file in self.backup_dir.glob(".env*"):
                import shutil
                shutil.copy2(backup_file, ".")
            
            # Restart services with previous configuration
            subprocess.run([
                "docker-compose", "-f", compose_file, "up", "-d"
            ], check=True)
            
            # Wait for services to be healthy
            if self._wait_for_services_healthy():
                logger.info("Rollback completed successfully")
                self._log_rollback_event()
                return True
            else:
                logger.error("Rollback completed but services are not healthy")
                return False
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    def _log_rollback_event(self):
        """Log rollback event for audit purposes"""
        rollback_log = {
            "event": "rollback",
            "deployment_id": self.deployment_id,
            "environment": self.config.environment,
            "timestamp": datetime.now().isoformat(),
            "backup_dir": str(self.backup_dir)
        }
        
        log_file = Path("deployment_rollbacks.log")
        with open(log_file, "a") as f:
            f.write(json.dumps(rollback_log) + "\n")
    
    def create_deployment_snapshot(self) -> str:
        """Create a deployment snapshot for quick rollback"""
        snapshot_id = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_dir = Path(f"deployment_snapshots/{snapshot_id}")
        
        try:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup current state
            self.config_manager.backup_configuration(str(snapshot_dir / "config"))
            
            # Backup docker-compose files
            for compose_file in Path(".").glob("docker-compose*.yml"):
                if compose_file.exists():
                    shutil.copy2(compose_file, snapshot_dir)
            
            # Backup environment files
            for env_file in Path(".").glob(".env*"):
                if env_file.exists():
                    shutil.copy2(env_file, snapshot_dir)
            
            # Save container states
            try:
                result = subprocess.run([
                    "docker-compose", "ps", "--format", "json"
                ], capture_output=True, text=True, check=True)
                
                with open(snapshot_dir / "container_states.json", "w") as f:
                    f.write(result.stdout)
            except subprocess.CalledProcessError:
                logger.warning("Could not save container states in snapshot")
            
            logger.info(f"Deployment snapshot created: {snapshot_id}")
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to create deployment snapshot: {e}")
            return ""
    
    def get_deployment_status(self) -> Dict:
        """Get current deployment status"""
        status = {
            "deployment_id": self.deployment_id,
            "environment": self.config.environment,
            "timestamp": datetime.now().isoformat(),
            "services": {}
        }
        
        for service in self.config.services:
            health_result = self._check_service_health(service)
            status["services"][service] = {
                "healthy": health_result.healthy,
                "status_code": health_result.status_code,
                "response_time": health_result.response_time,
                "error": health_result.error,
                "last_check": health_result.timestamp.isoformat()
            }
        
        return status


def main():
    """CLI interface for deployment"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deployment Manager")
    parser.add_argument("--environment", "-e", default="production",
                       help="Environment to deploy")
    parser.add_argument("--services", "-s", nargs="+", 
                       default=["orchestrator", "monitoring"],
                       help="Services to deploy")
    parser.add_argument("--no-rollback", action="store_true",
                       help="Disable rollback on failure")
    parser.add_argument("--no-backup", action="store_true",
                       help="Disable backup before deployment")
    parser.add_argument("--no-tests", action="store_true",
                       help="Skip pre and post deployment tests")
    parser.add_argument("--health-timeout", type=int, default=300,
                       help="Health check timeout in seconds")
    parser.add_argument("--status", action="store_true",
                       help="Show deployment status")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    config = DeploymentConfig(
        environment=args.environment,
        services=args.services,
        health_check_timeout=args.health_timeout,
        rollback_enabled=not args.no_rollback,
        backup_enabled=not args.no_backup,
        pre_deploy_tests=not args.no_tests,
        post_deploy_tests=not args.no_tests
    )
    
    deployment_manager = DeploymentManager(config)
    
    if args.status:
        status = deployment_manager.get_deployment_status()
        print(json.dumps(status, indent=2))
        return
    
    success = deployment_manager.deploy()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Deployment Validation Script
Validates deployment configuration and performs pre-deployment checks
"""
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager, get_config

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Validation result for a specific check"""
    check_name: str
    passed: bool
    message: str
    details: Optional[Dict] = None


class DeploymentValidator:
    """Validates deployment configuration and environment"""
    
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.config_manager = ConfigManager()
        self.config = get_config(environment)
        self.validation_results: List[ValidationResult] = []
    
    def validate_deployment(self) -> bool:
        """Run all deployment validations"""
        logger.info(f"Validating deployment for environment: {self.environment}")
        
        # Configuration validation
        self._validate_configuration()
        
        # Docker validation
        self._validate_docker_environment()
        
        # Network validation
        self._validate_network_connectivity()
        
        # Resource validation
        self._validate_system_resources()
        
        # Security validation
        self._validate_security_settings()
        
        # File validation
        self._validate_deployment_files()
        
        # Generate validation report
        return self._generate_validation_report()
    
    def _validate_configuration(self):
        """Validate configuration files and settings"""
        logger.info("Validating configuration...")
        
        try:
            # Validate config loading
            config = self.config_manager.load_config(self.environment)
            self.validation_results.append(ValidationResult(
                check_name="config_loading",
                passed=True,
                message="Configuration loaded successfully"
            ))
            
            # Validate database configuration
            db_valid = all([
                config.database.host,
                config.database.database,
                config.database.username,
                config.database.port > 0
            ])
            
            self.validation_results.append(ValidationResult(
                check_name="database_config",
                passed=db_valid,
                message="Database configuration valid" if db_valid else "Database configuration incomplete",
                details={
                    "host": config.database.host,
                    "port": config.database.port,
                    "database": config.database.database,
                    "username": config.database.username
                }
            ))
            
            # Validate orchestrator configuration
            orch_valid = all([
                config.orchestrator.host,
                config.orchestrator.port > 0,
                config.orchestrator.max_instances > 0
            ])
            
            self.validation_results.append(ValidationResult(
                check_name="orchestrator_config",
                passed=orch_valid,
                message="Orchestrator configuration valid" if orch_valid else "Orchestrator configuration incomplete"
            ))
            
        except Exception as e:
            self.validation_results.append(ValidationResult(
                check_name="config_loading",
                passed=False,
                message=f"Configuration validation failed: {e}"
            ))
    
    def _validate_docker_environment(self):
        """Validate Docker environment"""
        logger.info("Validating Docker environment...")
        
        # Check Docker availability
        try:
            result = subprocess.run(["docker", "--version"], 
                                  capture_output=True, text=True, check=True)
            self.validation_results.append(ValidationResult(
                check_name="docker_available",
                passed=True,
                message=f"Docker available: {result.stdout.strip()}"
            ))
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.validation_results.append(ValidationResult(
                check_name="docker_available",
                passed=False,
                message="Docker not available or not working"
            ))
            return
        
        # Check Docker Compose availability
        try:
            result = subprocess.run(["docker-compose", "--version"], 
                                  capture_output=True, text=True, check=True)
            self.validation_results.append(ValidationResult(
                check_name="docker_compose_available",
                passed=True,
                message=f"Docker Compose available: {result.stdout.strip()}"
            ))
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.validation_results.append(ValidationResult(
                check_name="docker_compose_available",
                passed=False,
                message="Docker Compose not available"
            ))
        
        # Check Docker daemon status
        try:
            result = subprocess.run(["docker", "info"], 
                                  capture_output=True, text=True, check=True)
            self.validation_results.append(ValidationResult(
                check_name="docker_daemon",
                passed=True,
                message="Docker daemon is running"
            ))
        except subprocess.CalledProcessError:
            self.validation_results.append(ValidationResult(
                check_name="docker_daemon",
                passed=False,
                message="Docker daemon is not running or accessible"
            ))
    
    def _validate_network_connectivity(self):
        """Validate network connectivity"""
        logger.info("Validating network connectivity...")
        
        # Check database connectivity
        if self.config.database.host != "localhost":
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((self.config.database.host, self.config.database.port))
                sock.close()
                
                self.validation_results.append(ValidationResult(
                    check_name="database_connectivity",
                    passed=result == 0,
                    message=f"Database connectivity {'OK' if result == 0 else 'FAILED'}"
                ))
            except Exception as e:
                self.validation_results.append(ValidationResult(
                    check_name="database_connectivity",
                    passed=False,
                    message=f"Database connectivity check failed: {e}"
                ))
        
        # Check port availability
        ports_to_check = [
            self.config.orchestrator.port,
            self.config.monitoring.metrics_port if self.config.monitoring.enabled else None
        ]
        
        for port in filter(None, ports_to_check):
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                
                # Port should be available (not in use)
                port_available = result != 0
                
                self.validation_results.append(ValidationResult(
                    check_name=f"port_{port}_available",
                    passed=port_available,
                    message=f"Port {port} {'available' if port_available else 'already in use'}"
                ))
            except Exception as e:
                self.validation_results.append(ValidationResult(
                    check_name=f"port_{port}_available",
                    passed=False,
                    message=f"Port {port} check failed: {e}"
                ))
    
    def _validate_system_resources(self):
        """Validate system resources"""
        logger.info("Validating system resources...")
        
        try:
            import psutil

            # Check memory
            memory = psutil.virtual_memory()
            memory_gb = memory.total / (1024**3)
            memory_sufficient = memory_gb >= 2.0  # Minimum 2GB
            
            self.validation_results.append(ValidationResult(
                check_name="system_memory",
                passed=memory_sufficient,
                message=f"System memory: {memory_gb:.1f}GB {'(sufficient)' if memory_sufficient else '(insufficient - need 2GB+)'}",
                details={"total_gb": memory_gb, "available_gb": memory.available / (1024**3)}
            ))
            
            # Check disk space
            disk = psutil.disk_usage('.')
            disk_gb = disk.free / (1024**3)
            disk_sufficient = disk_gb >= 5.0  # Minimum 5GB free
            
            self.validation_results.append(ValidationResult(
                check_name="disk_space",
                passed=disk_sufficient,
                message=f"Disk space: {disk_gb:.1f}GB free {'(sufficient)' if disk_sufficient else '(insufficient - need 5GB+)'}",
                details={"free_gb": disk_gb, "total_gb": disk.total / (1024**3)}
            ))
            
            # Check CPU
            cpu_count = psutil.cpu_count()
            cpu_sufficient = cpu_count >= 2
            
            self.validation_results.append(ValidationResult(
                check_name="cpu_cores",
                passed=cpu_sufficient,
                message=f"CPU cores: {cpu_count} {'(sufficient)' if cpu_sufficient else '(insufficient - need 2+)'}",
                details={"cores": cpu_count}
            ))
            
        except ImportError:
            self.validation_results.append(ValidationResult(
                check_name="system_resources",
                passed=False,
                message="Cannot check system resources (psutil not available)"
            ))
        except Exception as e:
            self.validation_results.append(ValidationResult(
                check_name="system_resources",
                passed=False,
                message=f"System resource check failed: {e}"
            ))
    
    def _validate_security_settings(self):
        """Validate security settings"""
        logger.info("Validating security settings...")
        
        # Check if running as root (not recommended)
        running_as_root = os.getuid() == 0 if hasattr(os, 'getuid') else False
        
        self.validation_results.append(ValidationResult(
            check_name="not_running_as_root",
            passed=not running_as_root,
            message="Running as root" if running_as_root else "Not running as root (good)"
        ))
        
        # Check environment variables for sensitive data
        sensitive_vars = ['DB_PASSWORD', 'ALERT_WEBHOOK']
        for var in sensitive_vars:
            value = os.getenv(var, '')
            if value and len(value) < 8:
                self.validation_results.append(ValidationResult(
                    check_name=f"secure_{var.lower()}",
                    passed=False,
                    message=f"{var} appears to be too short or insecure"
                ))
            elif value:
                self.validation_results.append(ValidationResult(
                    check_name=f"secure_{var.lower()}",
                    passed=True,
                    message=f"{var} is configured"
                ))
    
    def _validate_deployment_files(self):
        """Validate deployment files exist and are valid"""
        logger.info("Validating deployment files...")
        
        # Check required files
        required_files = [
            f"docker-compose.{self.environment}.yml",
            f".env.{self.environment}",
            "app/config/base.yaml",
            f"app/config/environments/{self.environment}.yaml"
        ]
        
        for file_path in required_files:
            path = Path(file_path)
            exists = path.exists()
            
            self.validation_results.append(ValidationResult(
                check_name=f"file_{path.name}",
                passed=exists,
                message=f"File {file_path} {'exists' if exists else 'missing'}"
            ))
        
        # Validate docker-compose syntax
        compose_file = f"docker-compose.{self.environment}.yml"
        if Path(compose_file).exists():
            try:
                result = subprocess.run([
                    "docker-compose", "-f", compose_file, "config"
                ], capture_output=True, text=True, check=True)
                
                self.validation_results.append(ValidationResult(
                    check_name="docker_compose_syntax",
                    passed=True,
                    message="Docker-compose file syntax is valid"
                ))
            except subprocess.CalledProcessError as e:
                self.validation_results.append(ValidationResult(
                    check_name="docker_compose_syntax",
                    passed=False,
                    message=f"Docker-compose syntax error: {e.stderr}"
                ))
    
    def _generate_validation_report(self) -> bool:
        """Generate validation report and return overall status"""
        passed_count = sum(1 for result in self.validation_results if result.passed)
        total_count = len(self.validation_results)
        overall_passed = passed_count == total_count
        
        report = {
            "environment": self.environment,
            "timestamp": datetime.now().isoformat(),
            "overall_status": "PASSED" if overall_passed else "FAILED",
            "summary": {
                "total_checks": total_count,
                "passed": passed_count,
                "failed": total_count - passed_count
            },
            "results": [
                {
                    "check": result.check_name,
                    "status": "PASS" if result.passed else "FAIL",
                    "message": result.message,
                    "details": result.details
                }
                for result in self.validation_results
            ]
        }
        
        # Save report
        report_file = f"deployment_validation_{self.environment}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Validation report saved: {report_file}")
        
        # Print summary
        print(f"\nDeployment Validation Summary for {self.environment}:")
        print(f"Overall Status: {report['summary']}")
        print(f"Checks: {passed_count}/{total_count} passed")
        
        if not overall_passed:
            print("\nFailed Checks:")
            for result in self.validation_results:
                if not result.passed:
                    print(f"  ❌ {result.check_name}: {result.message}")
        
        print(f"\nDetailed report: {report_file}")
        
        return overall_passed


def main():
    """CLI interface for deployment validation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deployment Validator")
    parser.add_argument("--environment", "-e", default="production",
                       help="Environment to validate")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    validator = DeploymentValidator(args.environment)
    success = validator.validate_deployment()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
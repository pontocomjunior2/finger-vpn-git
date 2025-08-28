#!/usr/bin/env python3
"""
Deployment Configuration Script
Generates environment-specific configuration files and deployment artifacts
"""
import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager, get_config

logger = logging.getLogger(__name__)


class DeploymentConfigurator:
    """Handles deployment configuration generation"""

    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.config_manager = ConfigManager()
        self.config = get_config(environment)

        # Paths
        self.templates_dir = Path("app/config/templates")
        self.output_dir = Path(f"deployment_{environment}")

    def configure_deployment(self) -> bool:
        """Generate all deployment configuration files"""
        logger.info(f"Configuring deployment for environment: {self.environment}")

        try:
            # Create output directory
            self.output_dir.mkdir(exist_ok=True)

            # Generate environment file
            if not self._generate_env_file():
                return False

            # Generate docker-compose file
            if not self._generate_docker_compose():
                return False

            # Generate monitoring configuration
            if not self._generate_monitoring_config():
                return False

            # Generate deployment scripts
            if not self._generate_deployment_scripts():
                return False

            # Copy necessary files
            if not self._copy_deployment_files():
                return False

            logger.info(f"Deployment configuration generated in: {self.output_dir}")
            return True

        except Exception as e:
            logger.error(f"Configuration generation failed: {e}")
            return False

    def _generate_env_file(self) -> bool:
        """Generate environment-specific .env file"""
        logger.info("Generating environment file...")

        try:
            env_file = self.output_dir / f".env.{self.environment}"
            self.config_manager.generate_env_file(self.environment, str(env_file))

            # Also create a generic .env file
            shutil.copy2(env_file, self.output_dir / ".env")

            return True

        except Exception as e:
            logger.error(f"Failed to generate env file: {e}")
            return False

    def _generate_docker_compose(self) -> bool:
        """Generate docker-compose file from template"""
        logger.info("Generating docker-compose file...")

        try:
            template_file = self.templates_dir / "docker-compose.template.yml"
            output_file = self.output_dir / f"docker-compose.{self.environment}.yml"

            if not template_file.exists():
                logger.error(f"Template file not found: {template_file}")
                return False

            # Load template
            with open(template_file, "r") as f:
                template_content = f.read()

            # Replace environment variables
            env_vars = self._get_environment_variables()

            for key, value in env_vars.items():
                template_content = template_content.replace(f"${{{key}}}", str(value))

            # Write processed template
            with open(output_file, "w") as f:
                f.write(template_content)

            # Also create a generic docker-compose.yml
            shutil.copy2(output_file, self.output_dir / "docker-compose.yml")

            logger.info(f"Docker-compose file generated: {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate docker-compose: {e}")
            return False

    def _generate_monitoring_config(self) -> bool:
        """Generate monitoring configuration files"""
        logger.info("Generating monitoring configuration...")

        try:
            monitoring_dir = self.output_dir / "monitoring"
            monitoring_dir.mkdir(exist_ok=True)

            # Copy monitoring templates
            source_monitoring = Path("app/config/monitoring")
            if source_monitoring.exists():
                shutil.copytree(source_monitoring, monitoring_dir, dirs_exist_ok=True)

            # Generate environment-specific monitoring config
            self._generate_prometheus_config(monitoring_dir)
            self._generate_grafana_config(monitoring_dir)
            self._generate_alertmanager_config(monitoring_dir)

            return True

        except Exception as e:
            logger.error(f"Failed to generate monitoring config: {e}")
            return False

    def _generate_prometheus_config(self, monitoring_dir: Path):
        """Generate Prometheus configuration"""
        prometheus_dir = monitoring_dir / "prometheus"
        prometheus_dir.mkdir(exist_ok=True)

        prometheus_config = {
            "global": {"scrape_interval": "15s", "evaluation_interval": "15s"},
            "rule_files": ["alert_rules.yml"],
            "alerting": {
                "alertmanagers": [
                    {"static_configs": [{"targets": ["alertmanager:9093"]}]}
                ]
            },
            "scrape_configs": [
                {
                    "job_name": "orchestrator",
                    "static_configs": [
                        {"targets": [f"orchestrator:{self.config.orchestrator.port}"]}
                    ],
                    "metrics_path": "/metrics",
                    "scrape_interval": "10s",
                },
                {
                    "job_name": "prometheus",
                    "static_configs": [{"targets": ["localhost:9090"]}],
                },
            ],
        }

        with open(prometheus_dir / "prometheus.yml", "w") as f:
            yaml.dump(prometheus_config, f, default_flow_style=False)

    def _generate_grafana_config(self, monitoring_dir: Path):
        """Generate Grafana configuration"""
        grafana_dir = monitoring_dir / "grafana"
        grafana_dir.mkdir(exist_ok=True)

        # Create provisioning directories
        (grafana_dir / "provisioning" / "datasources").mkdir(
            parents=True, exist_ok=True
        )
        (grafana_dir / "provisioning" / "dashboards").mkdir(parents=True, exist_ok=True)
        (grafana_dir / "dashboards").mkdir(exist_ok=True)

        # Datasource configuration
        datasource_config = {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": "Prometheus",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prometheus:9090",
                    "isDefault": True,
                }
            ],
        }

        with open(
            grafana_dir / "provisioning" / "datasources" / "prometheus.yml", "w"
        ) as f:
            yaml.dump(datasource_config, f, default_flow_style=False)

    def _generate_alertmanager_config(self, monitoring_dir: Path):
        """Generate Alertmanager configuration"""
        alertmanager_dir = monitoring_dir / "alertmanager"
        alertmanager_dir.mkdir(exist_ok=True)

        alertmanager_config = {
            "global": {
                "smtp_smarthost": "localhost:587",
                "smtp_from": f"alerts@orchestrator-{self.environment}.local",
            },
            "route": {
                "group_by": ["alertname"],
                "group_wait": "10s",
                "group_interval": "10s",
                "repeat_interval": "1h",
                "receiver": "web.hook",
            },
            "receivers": [{"name": "web.hook", "webhook_configs": []}],
        }

        # Add webhook if configured
        if self.config.monitoring.alert_webhook:
            alertmanager_config["receivers"][0]["webhook_configs"].append(
                {"url": self.config.monitoring.alert_webhook, "send_resolved": True}
            )

        with open(alertmanager_dir / "alertmanager.yml", "w") as f:
            yaml.dump(alertmanager_config, f, default_flow_style=False)

    def _generate_deployment_scripts(self) -> bool:
        """Generate deployment helper scripts"""
        logger.info("Generating deployment scripts...")

        try:
            scripts_dir = self.output_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)

            # Generate start script
            start_script = f"""#!/bin/bash
# Start script for {self.environment} environment

set -e

echo "Starting orchestrator system for {self.environment}..."

# Load environment variables
source .env.{self.environment}

# Start services
docker-compose -f docker-compose.{self.environment}.yml up -d

# Wait for services to be healthy
echo "Waiting for services to become healthy..."
python ../app/scripts/health_check.py --environment {self.environment} --wait 300

echo "Deployment started successfully!"
"""

            with open(scripts_dir / "start.sh", "w") as f:
                f.write(start_script)

            # Generate stop script
            stop_script = f"""#!/bin/bash
# Stop script for {self.environment} environment

set -e

echo "Stopping orchestrator system for {self.environment}..."

# Stop services
docker-compose -f docker-compose.{self.environment}.yml down

echo "Services stopped successfully!"
"""

            with open(scripts_dir / "stop.sh", "w") as f:
                f.write(stop_script)

            # Make scripts executable
            os.chmod(scripts_dir / "start.sh", 0o755)
            os.chmod(scripts_dir / "stop.sh", 0o755)

            return True

        except Exception as e:
            logger.error(f"Failed to generate deployment scripts: {e}")
            return False

    def _copy_deployment_files(self) -> bool:
        """Copy necessary deployment files"""
        logger.info("Copying deployment files...")

        try:
            # Copy health check script
            source_health = Path("app/scripts/health_check.py")
            if source_health.exists():
                shutil.copy2(source_health, self.output_dir / "health_check.py")

            # Copy deployment script
            source_deploy = Path("app/scripts/deploy.py")
            if source_deploy.exists():
                shutil.copy2(source_deploy, self.output_dir / "deploy.py")

            # Create README
            readme_content = f"""# Deployment Package for {self.environment.title()} Environment

Generated on: {datetime.now().isoformat()}

## Files

- `.env.{self.environment}` - Environment-specific configuration
- `docker-compose.{self.environment}.yml` - Docker compose configuration
- `monitoring/` - Monitoring configuration files
- `scripts/start.sh` - Start deployment script
- `scripts/stop.sh` - Stop deployment script
- `health_check.py` - Health check utility
- `deploy.py` - Full deployment script

## Usage

### Quick Start
```bash
cd scripts
./start.sh
```

### Full Deployment with Health Checks
```bash
python deploy.py --environment {self.environment}
```

### Health Check
```bash
python health_check.py --environment {self.environment}
```

### Stop Services
```bash
cd scripts
./stop.sh
```

## Configuration

Environment variables are loaded from `.env.{self.environment}`.
Modify this file to customize the deployment.

## Monitoring

If monitoring is enabled, the following services will be available:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Alertmanager: http://localhost:9093
"""

            with open(self.output_dir / "README.md", "w") as f:
                f.write(readme_content)

            return True

        except Exception as e:
            logger.error(f"Failed to copy deployment files: {e}")
            return False

    def _get_environment_variables(self) -> Dict[str, str]:
        """Get all environment variables for template processing"""
        return {
            "ENVIRONMENT": self.environment,
            "DEBUG": str(self.config.debug).lower(),
            "DB_HOST": self.config.database.host,
            "DB_PORT": str(self.config.database.port),
            "DB_NAME": self.config.database.database,
            "DB_USER": self.config.database.username,
            "DB_PASSWORD": self.config.database.password,
            "DB_POOL_SIZE": str(self.config.database.pool_size),
            "DB_TIMEOUT": str(self.config.database.timeout),
            "DB_RETRY_ATTEMPTS": str(self.config.database.retry_attempts),
            "ORCHESTRATOR_HOST": self.config.orchestrator.host,
            "ORCHESTRATOR_PORT": str(self.config.orchestrator.port),
            "MAX_INSTANCES": str(self.config.orchestrator.max_instances),
            "HEARTBEAT_INTERVAL": str(self.config.orchestrator.heartbeat_interval),
            "REBALANCE_THRESHOLD": str(self.config.orchestrator.rebalance_threshold),
            "EMERGENCY_TIMEOUT": str(self.config.orchestrator.emergency_timeout),
            "API_TIMEOUT": str(self.config.orchestrator.api_timeout),
            "MONITORING_ENABLED": str(self.config.monitoring.enabled).lower(),
            "METRICS_PORT": str(self.config.monitoring.metrics_port),
            "LOG_LEVEL": self.config.monitoring.log_level,
            "RETENTION_DAYS": str(self.config.monitoring.retention_days),
            "ALERT_WEBHOOK": self.config.monitoring.alert_webhook or "",
            "GRAFANA_ADMIN_PASSWORD": os.getenv("GRAFANA_ADMIN_PASSWORD", "admin"),
        }

    def validate_deployment_config(self) -> bool:
        """Validate deployment configuration"""
        logger.info("Validating deployment configuration...")

        try:
            # Check if all required files exist
            required_files = [
                self.output_dir / f".env.{self.environment}",
                self.output_dir / f"docker-compose.{self.environment}.yml",
            ]

            for file_path in required_files:
                if not file_path.exists():
                    logger.error(f"Required file missing: {file_path}")
                    return False

            # Validate docker-compose syntax
            import subprocess

            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    str(self.output_dir / f"docker-compose.{self.environment}.yml"),
                    "config",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Docker-compose validation failed: {result.stderr}")
                return False

            logger.info("Deployment configuration validation passed")
            return True

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False


def main():
    """CLI interface for deployment configuration"""
    parser = argparse.ArgumentParser(description="Deployment Configuration Generator")
    parser.add_argument(
        "--environment", "-e", default="production", help="Environment to configure"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate generated configuration"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    configurator = DeploymentConfigurator(args.environment)

    success = configurator.configure_deployment()

    if success and args.validate:
        success = configurator.validate_deployment_config()

    if success:
        logger.info(
            f"Deployment configuration completed successfully for {args.environment}"
        )
        print(f"Deployment package created in: deployment_{args.environment}/")
    else:
        logger.error("Deployment configuration failed")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

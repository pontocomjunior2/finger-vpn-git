#!/usr/bin/env python3
"""
Monitoring Setup Script
Sets up monitoring infrastructure including Prometheus, Grafana, and alerting
"""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config.config_manager import ConfigManager, get_config

logger = logging.getLogger(__name__)


class MonitoringSetup:
    """Sets up monitoring infrastructure"""
    
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.config = get_config(environment)
        self.config_manager = ConfigManager()
        
        # Monitoring directories
        self.monitoring_dir = Path("monitoring")
        self.prometheus_dir = self.monitoring_dir / "prometheus"
        self.grafana_dir = self.monitoring_dir / "grafana"
        self.alertmanager_dir = self.monitoring_dir / "alertmanager"
    
    def setup_monitoring(self) -> bool:
        """Setup complete monitoring infrastructure"""
        logger.info(f"Setting up monitoring for environment: {self.environment}")
        
        try:
            # Create directory structure
            self._create_directories()
            
            # Setup Prometheus
            if not self._setup_prometheus():
                return False
            
            # Setup Grafana
            if not self._setup_grafana():
                return False
            
            # Setup Alertmanager
            if not self._setup_alertmanager():
                return False
            
            # Generate docker-compose for monitoring
            if not self._generate_monitoring_compose():
                return False
            
            logger.info("Monitoring setup completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Monitoring setup failed: {e}")
            return False
    
    def _create_directories(self):
        """Create monitoring directory structure"""
        directories = [
            self.monitoring_dir,
            self.prometheus_dir,
            self.grafana_dir,
            self.grafana_dir / "dashboards",
            self.grafana_dir / "provisioning" / "dashboards",
            self.grafana_dir / "provisioning" / "datasources",
            self.alertmanager_dir
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _setup_prometheus(self) -> bool:
        """Setup Prometheus configuration"""
        logger.info("Setting up Prometheus...")
        
        try:
            # Copy base prometheus config
            source_config = Path("app/config/monitoring/prometheus.yml")
            target_config = self.prometheus_dir / "prometheus.yml"
            
            if source_config.exists():
                shutil.copy2(source_config, target_config)
            else:
                # Generate basic config
                prometheus_config = {
                    'global': {
                        'scrape_interval': '15s',
                        'evaluation_interval': '15s'
                    },
                    'rule_files': ['alert_rules.yml'],
                    'alerting': {
                        'alertmanagers': [{
                            'static_configs': [{'targets': ['alertmanager:9093']}]
                        }]
                    },
                    'scrape_configs': [
                        {
                            'job_name': 'orchestrator',
                            'static_configs': [{'targets': [f'orchestrator:{self.config.orchestrator.port}']}],
                            'metrics_path': '/metrics',
                            'scrape_interval': '10s'
                        },
                        {
                            'job_name': 'prometheus',
                            'static_configs': [{'targets': ['localhost:9090']}]
                        }
                    ]
                }
                
                with open(target_config, 'w') as f:
                    yaml.dump(prometheus_config, f, default_flow_style=False)
            
            # Copy alert rules
            source_rules = Path("app/config/monitoring/alert_rules.yml")
            target_rules = self.prometheus_dir / "alert_rules.yml"
            
            if source_rules.exists():
                shutil.copy2(source_rules, target_rules)
            
            logger.info("Prometheus setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Prometheus setup failed: {e}")
            return False
    
    def _setup_grafana(self) -> bool:
        """Setup Grafana configuration"""
        logger.info("Setting up Grafana...")
        
        try:
            # Datasource configuration
            datasource_config = {
                'apiVersion': 1,
                'datasources': [{
                    'name': 'Prometheus',
                    'type': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'isDefault': True
                }]
            }
            
            with open(self.grafana_dir / "provisioning" / "datasources" / "prometheus.yml", 'w') as f:
                yaml.dump(datasource_config, f, default_flow_style=False)
            
            # Dashboard provisioning
            dashboard_config = {
                'apiVersion': 1,
                'providers': [{
                    'name': 'orchestrator',
                    'orgId': 1,
                    'folder': '',
                    'type': 'file',
                    'disableDeletion': False,
                    'updateIntervalSeconds': 10,
                    'options': {
                        'path': '/etc/grafana/provisioning/dashboards'
                    }
                }]
            }
            
            with open(self.grafana_dir / "provisioning" / "dashboards" / "orchestrator.yml", 'w') as f:
                yaml.dump(dashboard_config, f, default_flow_style=False)
            
            # Copy dashboard
            source_dashboard = Path("app/config/monitoring/grafana_dashboard.json")
            target_dashboard = self.grafana_dir / "dashboards" / "orchestrator.json"
            
            if source_dashboard.exists():
                shutil.copy2(source_dashboard, target_dashboard)
            
            logger.info("Grafana setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Grafana setup failed: {e}")
            return False
    
    def _setup_alertmanager(self) -> bool:
        """Setup Alertmanager configuration"""
        logger.info("Setting up Alertmanager...")
        
        try:
            alertmanager_config = {
                'global': {
                    'smtp_smarthost': 'localhost:587',
                    'smtp_from': 'alerts@orchestrator.local'
                },
                'route': {
                    'group_by': ['alertname'],
                    'group_wait': '10s',
                    'group_interval': '10s',
                    'repeat_interval': '1h',
                    'receiver': 'web.hook'
                },
                'receivers': [{
                    'name': 'web.hook',
                    'webhook_configs': []
                }]
            }
            
            # Add webhook if configured
            if self.config.monitoring.alert_webhook:
                alertmanager_config['receivers'][0]['webhook_configs'].append({
                    'url': self.config.monitoring.alert_webhook,
                    'send_resolved': True
                })
            
            with open(self.alertmanager_dir / "alertmanager.yml", 'w') as f:
                yaml.dump(alertmanager_config, f, default_flow_style=False)
            
            logger.info("Alertmanager setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Alertmanager setup failed: {e}")
            return False
    
    def _generate_monitoring_compose(self) -> bool:
        """Generate docker-compose file for monitoring services"""
        logger.info("Generating monitoring docker-compose...")
        
        try:
            compose_config = {
                'version': '3.8',
                'services': {
                    'prometheus': {
                        'image': 'prom/prometheus:latest',
                        'container_name': 'prometheus',
                        'ports': [f'{self.config.monitoring.metrics_port}:9090'],
                        'volumes': [
                            './monitoring/prometheus:/etc/prometheus',
                            'prometheus_data:/prometheus'
                        ],
                        'command': [
                            '--config.file=/etc/prometheus/prometheus.yml',
                            '--storage.tsdb.path=/prometheus',
                            '--web.console.libraries=/etc/prometheus/console_libraries',
                            '--web.console.templates=/etc/prometheus/consoles',
                            '--storage.tsdb.retention.time=200h',
                            '--web.enable-lifecycle'
                        ],
                        'restart': 'unless-stopped'
                    },
                    'grafana': {
                        'image': 'grafana/grafana:latest',
                        'container_name': 'grafana',
                        'ports': ['3000:3000'],
                        'volumes': [
                            'grafana_data:/var/lib/grafana',
                            './monitoring/grafana/provisioning:/etc/grafana/provisioning',
                            './monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards'
                        ],
                        'environment': [
                            'GF_SECURITY_ADMIN_PASSWORD=admin',
                            'GF_USERS_ALLOW_SIGN_UP=false'
                        ],
                        'restart': 'unless-stopped'
                    },
                    'alertmanager': {
                        'image': 'prom/alertmanager:latest',
                        'container_name': 'alertmanager',
                        'ports': ['9093:9093'],
                        'volumes': [
                            './monitoring/alertmanager:/etc/alertmanager',
                            'alertmanager_data:/alertmanager'
                        ],
                        'command': [
                            '--config.file=/etc/alertmanager/alertmanager.yml',
                            '--storage.path=/alertmanager',
                            '--web.external-url=http://localhost:9093'
                        ],
                        'restart': 'unless-stopped'
                    }
                },
                'volumes': {
                    'prometheus_data': {},
                    'grafana_data': {},
                    'alertmanager_data': {}
                }
            }
            
            with open(self.monitoring_dir / "docker-compose.monitoring.yml", 'w') as f:
                yaml.dump(compose_config, f, default_flow_style=False)
            
            logger.info("Monitoring docker-compose generated")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate monitoring docker-compose: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """Start monitoring services"""
        logger.info("Starting monitoring services...")
        
        try:
            subprocess.run([
                "docker-compose", "-f", "monitoring/docker-compose.monitoring.yml", "up", "-d"
            ], check=True)
            
            logger.info("Monitoring services started successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start monitoring services: {e}")
            return False
    
    def stop_monitoring(self) -> bool:
        """Stop monitoring services"""
        logger.info("Stopping monitoring services...")
        
        try:
            subprocess.run([
                "docker-compose", "-f", "monitoring/docker-compose.monitoring.yml", "down"
            ], check=True)
            
            logger.info("Monitoring services stopped successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop monitoring services: {e}")
            return False


def main():
    """CLI interface for monitoring setup"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitoring Setup")
    parser.add_argument("--environment", "-e", default="production",
                       help="Environment to setup monitoring for")
    parser.add_argument("--setup", action="store_true",
                       help="Setup monitoring infrastructure")
    parser.add_argument("--start", action="store_true",
                       help="Start monitoring services")
    parser.add_argument("--stop", action="store_true",
                       help="Stop monitoring services")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    monitoring_setup = MonitoringSetup(args.environment)
    
    success = True
    
    if args.setup:
        success = monitoring_setup.setup_monitoring()
    
    if args.start and success:
        success = monitoring_setup.start_monitoring()
    
    if args.stop:
        success = monitoring_setup.stop_monitoring()
    
    if not any([args.setup, args.start, args.stop]):
        # Default action: setup and start
        success = monitoring_setup.setup_monitoring()
        if success:
            success = monitoring_setup.start_monitoring()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
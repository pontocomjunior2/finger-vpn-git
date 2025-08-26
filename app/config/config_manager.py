"""
Configuration Management System
Handles environment-specific configurations and template processing
"""
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class DatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    pool_size: int = 10
    timeout: int = 30
    retry_attempts: int = 3


@dataclass
class OrchestatorConfig:
    host: str
    port: int
    max_instances: int
    heartbeat_interval: int
    rebalance_threshold: float
    emergency_timeout: int
    api_timeout: int = 30


@dataclass
class MonitoringConfig:
    enabled: bool
    metrics_port: int
    alert_webhook: Optional[str]
    log_level: str
    retention_days: int


@dataclass
class SystemConfig:
    environment: Environment
    database: DatabaseConfig
    orchestrator: OrchestatorConfig
    monitoring: MonitoringConfig
    debug: bool = False


class ConfigManager:
    """Manages configuration loading and environment-specific settings"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.templates_dir = self.config_dir / "templates"
        self.environments_dir = self.config_dir / "environments"
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create configuration directories if they don't exist"""
        self.config_dir.mkdir(exist_ok=True)
        self.templates_dir.mkdir(exist_ok=True)
        self.environments_dir.mkdir(exist_ok=True)
    
    def load_config(self, environment: str = None) -> SystemConfig:
        """Load configuration for specified environment"""
        if not environment:
            environment = os.getenv('ENVIRONMENT', 'development')
        
        env_enum = Environment(environment.lower())
        
        # Load base configuration
        base_config = self._load_base_config()
        
        # Load environment-specific overrides
        env_config = self._load_environment_config(env_enum)
        
        # Merge configurations
        merged_config = self._merge_configs(base_config, env_config)
        
        return self._create_system_config(env_enum, merged_config)
    
    def _load_base_config(self) -> Dict[str, Any]:
        """Load base configuration template"""
        config_file = self.config_dir / "base.yaml"
        if config_file.exists():
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_environment_config(self, environment: Environment) -> Dict[str, Any]:
        """Load environment-specific configuration"""
        config_file = self.environments_dir / f"{environment.value}.yaml"
        if config_file.exists():
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        return {}
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge base and environment configurations"""
        merged = base.copy()
        for key, value in override.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = self._merge_configs(merged[key], value)
            else:
                merged[key] = value
        return merged
    
    def _create_system_config(self, environment: Environment, config: Dict[str, Any]) -> SystemConfig:
        """Create SystemConfig object from merged configuration"""
        db_config = config.get('database', {})
        orch_config = config.get('orchestrator', {})
        mon_config = config.get('monitoring', {})
        
        return SystemConfig(
            environment=environment,
            database=DatabaseConfig(
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432),
                database=db_config.get('database', 'orchestrator'),
                username=db_config.get('username', 'postgres'),
                password=db_config.get('password', ''),
                pool_size=db_config.get('pool_size', 10),
                timeout=db_config.get('timeout', 30),
                retry_attempts=db_config.get('retry_attempts', 3)
            ),
            orchestrator=OrchestatorConfig(
                host=orch_config.get('host', '0.0.0.0'),
                port=orch_config.get('port', 8000),
                max_instances=orch_config.get('max_instances', 10),
                heartbeat_interval=orch_config.get('heartbeat_interval', 30),
                rebalance_threshold=orch_config.get('rebalance_threshold', 0.2),
                emergency_timeout=orch_config.get('emergency_timeout', 300),
                api_timeout=orch_config.get('api_timeout', 30)
            ),
            monitoring=MonitoringConfig(
                enabled=mon_config.get('enabled', True),
                metrics_port=mon_config.get('metrics_port', 9090),
                alert_webhook=mon_config.get('alert_webhook'),
                log_level=mon_config.get('log_level', 'INFO'),
                retention_days=mon_config.get('retention_days', 30)
            ),
            debug=config.get('debug', False)
        )
    
    def generate_env_file(self, environment: str, output_path: str = None):
        """Generate .env file from configuration"""
        config = self.load_config(environment)
        
        if not output_path:
            output_path = f".env.{environment}"
        
        env_vars = [
            f"ENVIRONMENT={config.environment.value}",
            f"DEBUG={str(config.debug).lower()}",
            "",
            "# Database Configuration",
            f"DB_HOST={config.database.host}",
            f"DB_PORT={config.database.port}",
            f"DB_NAME={config.database.database}",
            f"DB_USER={config.database.username}",
            f"DB_PASSWORD={config.database.password}",
            f"DB_POOL_SIZE={config.database.pool_size}",
            f"DB_TIMEOUT={config.database.timeout}",
            f"DB_RETRY_ATTEMPTS={config.database.retry_attempts}",
            "",
            "# Orchestrator Configuration",
            f"ORCHESTRATOR_HOST={config.orchestrator.host}",
            f"ORCHESTRATOR_PORT={config.orchestrator.port}",
            f"MAX_INSTANCES={config.orchestrator.max_instances}",
            f"HEARTBEAT_INTERVAL={config.orchestrator.heartbeat_interval}",
            f"REBALANCE_THRESHOLD={config.orchestrator.rebalance_threshold}",
            f"EMERGENCY_TIMEOUT={config.orchestrator.emergency_timeout}",
            f"API_TIMEOUT={config.orchestrator.api_timeout}",
            "",
            "# Monitoring Configuration",
            f"MONITORING_ENABLED={str(config.monitoring.enabled).lower()}",
            f"METRICS_PORT={config.monitoring.metrics_port}",
            f"LOG_LEVEL={config.monitoring.log_level}",
            f"RETENTION_DAYS={config.monitoring.retention_days}",
        ]
        
        if config.monitoring.alert_webhook:
            env_vars.append(f"ALERT_WEBHOOK={config.monitoring.alert_webhook}")
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(env_vars))
        
        print(f"Generated environment file: {output_path}")
    
    def validate_config(self, environment: str) -> bool:
        """Validate configuration for environment"""
        try:
            config = self.load_config(environment)
            
            # Validate required fields
            required_checks = [
                (config.database.host, "Database host"),
                (config.database.database, "Database name"),
                (config.database.username, "Database username"),
                (config.orchestrator.host, "Orchestrator host"),
                (config.orchestrator.port > 0, "Orchestrator port"),
            ]
            
            for check, description in required_checks:
                if not check:
                    print(f"Validation failed: {description} is required")
                    return False
            
            print(f"Configuration validation passed for {environment}")
            return True
            
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return False


# Global config manager instance
config_manager = ConfigManager()


    def load_environment_config(self, environment: str) -> Dict[str, Any]:
        """Load environment configuration as dictionary"""
        env_enum = Environment(environment.lower())
        return self._load_environment_config(env_enum)
    
    def validate_configuration(self, config: Dict[str, Any], service: str) -> 'ValidationResult':
        """Validate configuration for a specific service"""
        errors = []
        
        # Database validation
        if 'database' in config:
            db_config = config['database']
            if not db_config.get('host'):
                errors.append("Database host is required")
            if not db_config.get('database'):
                errors.append("Database name is required")
            if not db_config.get('username'):
                errors.append("Database username is required")
        
        # Orchestrator validation
        if service == 'orchestrator' and 'orchestrator' in config:
            orch_config = config['orchestrator']
            if not orch_config.get('port') or orch_config.get('port') <= 0:
                errors.append("Valid orchestrator port is required")
            if not orch_config.get('max_instances') or orch_config.get('max_instances') <= 0:
                errors.append("Max instances must be greater than 0")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def backup_configuration(self, backup_path: str):
        """Backup current configuration"""
        import shutil
        backup_dir = Path(backup_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup config directory
        if self.config_dir.exists():
            shutil.copytree(self.config_dir, backup_dir / "config", dirs_exist_ok=True)
    
    def generate_docker_compose(self, environment: str, output_file: str) -> bool:
        """Generate docker-compose file for environment"""
        try:
            config = self.load_config(environment)
            
            compose_content = {
                'version': '3.8',
                'services': {
                    'orchestrator': {
                        'build': '.',
                        'ports': [f"{config.orchestrator.port}:{config.orchestrator.port}"],
                        'environment': [
                            f"ENVIRONMENT={environment}",
                            f"DB_HOST={config.database.host}",
                            f"DB_PORT={config.database.port}",
                            f"DB_NAME={config.database.database}",
                            f"DB_USER={config.database.username}",
                            f"DB_PASSWORD={config.database.password}",
                            f"ORCHESTRATOR_PORT={config.orchestrator.port}",
                            f"MAX_INSTANCES={config.orchestrator.max_instances}",
                            f"HEARTBEAT_INTERVAL={config.orchestrator.heartbeat_interval}",
                            f"REBALANCE_THRESHOLD={config.orchestrator.rebalance_threshold}",
                        ],
                        'restart': 'unless-stopped',
                        'healthcheck': {
                            'test': ['CMD', 'curl', '-f', f'http://localhost:{config.orchestrator.port}/health'],
                            'interval': '30s',
                            'timeout': '10s',
                            'retries': 3
                        }
                    }
                }
            }
            
            if config.monitoring.enabled:
                compose_content['services']['monitoring'] = {
                    'image': 'prom/prometheus:latest',
                    'ports': [f"{config.monitoring.metrics_port}:{config.monitoring.metrics_port}"],
                    'volumes': ['./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml'],
                    'restart': 'unless-stopped'
                }
            
            import yaml
            with open(output_file, 'w') as f:
                yaml.dump(compose_content, f, default_flow_style=False)
            
            return True
            
        except Exception as e:
            print(f"Failed to generate docker-compose: {e}")
            return False


@dataclass
class ValidationResult:
    """Configuration validation result"""
    valid: bool
    errors: List[str]


def get_config(environment: str = None) -> SystemConfig:
    """Get system configuration for environment"""
    return config_manager.load_config(environment)
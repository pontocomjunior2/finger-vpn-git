#!/usr/bin/env python3
"""
Monitoring Configuration

This module provides configuration management for the monitoring system,
including alert rules, thresholds, and notification settings.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from monitoring_system import AlertSeverity

logger = logging.getLogger(__name__)


@dataclass
class AlertRuleConfig:
    """Alert rule configuration"""

    name: str
    metric_name: str
    threshold: float
    severity: str
    duration: int = 300  # seconds
    enabled: bool = True
    description: str = ""


@dataclass
class MonitoringConfig:
    """Main monitoring configuration"""

    # System settings
    retention_hours: int = 24
    pattern_window_size: int = 100
    monitoring_interval: int = 30  # seconds

    # Performance thresholds
    response_time_warning: float = 5000.0  # ms
    response_time_critical: float = 10000.0  # ms
    error_rate_warning: float = 0.1  # 10%
    error_rate_critical: float = 0.25  # 25%
    resource_usage_warning: float = 85.0  # %
    resource_usage_critical: float = 95.0  # %

    # Pattern detection thresholds
    cascading_failure_threshold: int = 5
    cascading_failure_window: int = 300  # seconds
    heartbeat_failure_threshold: int = 3
    heartbeat_failure_window: int = 300  # seconds

    # Notification settings
    enable_console_notifications: bool = True
    enable_file_notifications: bool = True
    enable_email_notifications: bool = False
    notification_file: str = "notifications.log"

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    enable_dashboard: bool = True

    # Alert rules
    alert_rules: Dict[str, AlertRuleConfig] = None

    def __post_init__(self):
        if self.alert_rules is None:
            self.alert_rules = self._get_default_alert_rules()

    def _get_default_alert_rules(self) -> Dict[str, AlertRuleConfig]:
        """Get default alert rules"""
        return {
            "high_response_time": AlertRuleConfig(
                name="high_response_time",
                metric_name="response_time",
                threshold=self.response_time_warning,
                severity="warning",
                duration=300,
                description="Response time exceeds warning threshold",
            ),
            "critical_response_time": AlertRuleConfig(
                name="critical_response_time",
                metric_name="response_time",
                threshold=self.response_time_critical,
                severity="critical",
                duration=60,
                description="Response time exceeds critical threshold",
            ),
            "high_error_rate": AlertRuleConfig(
                name="high_error_rate",
                metric_name="error_rate",
                threshold=self.error_rate_warning,
                severity="warning",
                duration=300,
                description="Error rate exceeds warning threshold",
            ),
            "critical_error_rate": AlertRuleConfig(
                name="critical_error_rate",
                metric_name="error_rate",
                threshold=self.error_rate_critical,
                severity="critical",
                duration=60,
                description="Error rate exceeds critical threshold",
            ),
            "high_cpu_usage": AlertRuleConfig(
                name="high_cpu_usage",
                metric_name="resource_usage_cpu",
                threshold=self.resource_usage_warning,
                severity="warning",
                duration=300,
                description="CPU usage exceeds warning threshold",
            ),
            "critical_cpu_usage": AlertRuleConfig(
                name="critical_cpu_usage",
                metric_name="resource_usage_cpu",
                threshold=self.resource_usage_critical,
                severity="critical",
                duration=60,
                description="CPU usage exceeds critical threshold",
            ),
            "high_memory_usage": AlertRuleConfig(
                name="high_memory_usage",
                metric_name="resource_usage_memory",
                threshold=self.resource_usage_warning,
                severity="warning",
                duration=300,
                description="Memory usage exceeds warning threshold",
            ),
            "critical_memory_usage": AlertRuleConfig(
                name="critical_memory_usage",
                metric_name="resource_usage_memory",
                threshold=self.resource_usage_critical,
                severity="critical",
                duration=60,
                description="Memory usage exceeds critical threshold",
            ),
            "high_disk_usage": AlertRuleConfig(
                name="high_disk_usage",
                metric_name="resource_usage_disk",
                threshold=self.resource_usage_warning,
                severity="warning",
                duration=600,  # 10 minutes for disk
                description="Disk usage exceeds warning threshold",
            ),
            "critical_disk_usage": AlertRuleConfig(
                name="critical_disk_usage",
                metric_name="resource_usage_disk",
                threshold=self.resource_usage_critical,
                severity="critical",
                duration=300,
                description="Disk usage exceeds critical threshold",
            ),
        }


class MonitoringConfigManager:
    """Manages monitoring configuration"""

    def __init__(self, config_file: str = "monitoring_config.json"):
        self.config_file = Path(config_file)
        self.config = self._load_config()

    def _load_config(self) -> MonitoringConfig:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)

                # Convert alert rules
                if "alert_rules" in data:
                    alert_rules = {}
                    for name, rule_data in data["alert_rules"].items():
                        alert_rules[name] = AlertRuleConfig(**rule_data)
                    data["alert_rules"] = alert_rules

                config = MonitoringConfig(**data)
                logger.info(f"Loaded monitoring configuration from {self.config_file}")
                return config

            except Exception as e:
                logger.error(f"Failed to load config from {self.config_file}: {e}")
                logger.info("Using default configuration")

        return MonitoringConfig()

    def save_config(self):
        """Save configuration to file"""
        try:
            # Convert to dict for serialization
            config_dict = asdict(self.config)

            # Convert alert rules to serializable format
            if "alert_rules" in config_dict:
                alert_rules_dict = {}
                for name, rule in config_dict["alert_rules"].items():
                    alert_rules_dict[name] = asdict(rule)
                config_dict["alert_rules"] = alert_rules_dict

            with open(self.config_file, "w") as f:
                json.dump(config_dict, f, indent=2)

            logger.info(f"Saved monitoring configuration to {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to save config to {self.config_file}: {e}")
            raise

    def get_config(self) -> MonitoringConfig:
        """Get current configuration"""
        return self.config

    def update_config(self, **kwargs):
        """Update configuration parameters"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Updated config parameter {key} = {value}")
            else:
                logger.warning(f"Unknown config parameter: {key}")

    def add_alert_rule(self, rule: AlertRuleConfig):
        """Add or update alert rule"""
        self.config.alert_rules[rule.name] = rule
        logger.info(f"Added/updated alert rule: {rule.name}")

    def remove_alert_rule(self, rule_name: str) -> bool:
        """Remove alert rule"""
        if rule_name in self.config.alert_rules:
            del self.config.alert_rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
            return True
        return False

    def get_alert_rule(self, rule_name: str) -> Optional[AlertRuleConfig]:
        """Get specific alert rule"""
        return self.config.alert_rules.get(rule_name)

    def get_enabled_alert_rules(self) -> Dict[str, AlertRuleConfig]:
        """Get only enabled alert rules"""
        return {
            name: rule for name, rule in self.config.alert_rules.items() if rule.enabled
        }

    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return validation results"""
        validation_results = {"valid": True, "warnings": [], "errors": []}

        # Validate thresholds
        if self.config.response_time_warning >= self.config.response_time_critical:
            validation_results["errors"].append(
                "Response time warning threshold must be less than critical threshold"
            )
            validation_results["valid"] = False

        if self.config.error_rate_warning >= self.config.error_rate_critical:
            validation_results["errors"].append(
                "Error rate warning threshold must be less than critical threshold"
            )
            validation_results["valid"] = False

        if self.config.resource_usage_warning >= self.config.resource_usage_critical:
            validation_results["errors"].append(
                "Resource usage warning threshold must be less than critical threshold"
            )
            validation_results["valid"] = False

        # Validate alert rules
        for name, rule in self.config.alert_rules.items():
            if rule.threshold <= 0:
                validation_results["errors"].append(
                    f"Alert rule '{name}' has invalid threshold: {rule.threshold}"
                )
                validation_results["valid"] = False

            if rule.duration <= 0:
                validation_results["errors"].append(
                    f"Alert rule '{name}' has invalid duration: {rule.duration}"
                )
                validation_results["valid"] = False

            try:
                AlertSeverity(rule.severity)
            except ValueError:
                validation_results["errors"].append(
                    f"Alert rule '{name}' has invalid severity: {rule.severity}"
                )
                validation_results["valid"] = False

        # Warnings
        if self.config.retention_hours < 1:
            validation_results["warnings"].append(
                "Retention hours is very low, consider increasing for better analysis"
            )

        if self.config.monitoring_interval < 10:
            validation_results["warnings"].append(
                "Monitoring interval is very low, may impact performance"
            )

        return validation_results

    def export_config_template(self, filepath: str):
        """Export configuration template"""
        try:
            template_config = MonitoringConfig()
            config_dict = asdict(template_config)

            # Convert alert rules to serializable format
            alert_rules_dict = {}
            for name, rule in config_dict["alert_rules"].items():
                alert_rules_dict[name] = asdict(rule)
            config_dict["alert_rules"] = alert_rules_dict

            # Add comments for documentation
            config_with_comments = {
                "_comment": "Monitoring System Configuration Template",
                "_description": {
                    "retention_hours": "How long to keep metrics data (hours)",
                    "pattern_window_size": "Number of failure events to analyze for patterns",
                    "monitoring_interval": "How often to run monitoring checks (seconds)",
                    "response_time_warning": "Response time warning threshold (milliseconds)",
                    "response_time_critical": "Response time critical threshold (milliseconds)",
                    "error_rate_warning": "Error rate warning threshold (0.0-1.0)",
                    "error_rate_critical": "Error rate critical threshold (0.0-1.0)",
                    "resource_usage_warning": "Resource usage warning threshold (percentage)",
                    "resource_usage_critical": "Resource usage critical threshold (percentage)",
                    "alert_rules": "Custom alert rules configuration",
                },
                **config_dict,
            }

            with open(filepath, "w") as f:
                json.dump(config_with_comments, f, indent=2)

            logger.info(f"Configuration template exported to {filepath}")

        except Exception as e:
            logger.error(f"Failed to export config template: {e}")
            raise


# Global configuration manager instance
config_manager = MonitoringConfigManager()


def get_monitoring_config() -> MonitoringConfig:
    """Get current monitoring configuration"""
    return config_manager.get_config()


def update_monitoring_config(**kwargs):
    """Update monitoring configuration"""
    config_manager.update_config(**kwargs)
    config_manager.save_config()


def add_custom_alert_rule(
    name: str,
    metric_name: str,
    threshold: float,
    severity: str,
    duration: int = 300,
    description: str = "",
):
    """Add custom alert rule"""
    rule = AlertRuleConfig(
        name=name,
        metric_name=metric_name,
        threshold=threshold,
        severity=severity,
        duration=duration,
        description=description,
    )
    config_manager.add_alert_rule(rule)
    config_manager.save_config()


def remove_alert_rule(rule_name: str) -> bool:
    """Remove alert rule"""
    success = config_manager.remove_alert_rule(rule_name)
    if success:
        config_manager.save_config()
    return success


def validate_monitoring_config() -> Dict[str, Any]:
    """Validate current monitoring configuration"""
    return config_manager.validate_config()


# Initialize configuration on import
if __name__ == "__main__":
    # Create example configuration file
    config_manager.export_config_template("monitoring_config_template.json")
    print("Configuration template created: monitoring_config_template.json")

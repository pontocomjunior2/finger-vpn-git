# Orchestrator Deployment System

This directory contains a comprehensive deployment system for the Orchestrator stream balancing system. The deployment system provides configuration management, automated deployment, health checking, monitoring setup, and rollback capabilities.

## Overview

The deployment system consists of several interconnected components:

- **Configuration Management**: Environment-specific configuration templates and generation
- **Deployment Automation**: Automated deployment with health checks and rollback
- **Monitoring Setup**: Prometheus, Grafana, and Alertmanager configuration
- **Health Checking**: Comprehensive system health validation
- **Validation**: Pre-deployment validation and verification

## Quick Start

### 1. Complete Deployment (Recommended)

```bash
# Deploy to production with full automation
python app/scripts/deploy_orchestrator.py --environment production

# Deploy to development with verbose logging
python app/scripts/deploy_orchestrator.py --environment development --verbose

# Dry run to see what would be deployed
python app/scripts/deploy_orchestrator.py --environment production --dry-run
```

### 2. Step-by-Step Deployment

```bash
# 1. Validate environment
python app/scripts/validate_deployment.py --environment production

# 2. Generate configuration
python app/scripts/configure_deployment.py --environment production

# 3. Setup monitoring
python app/scripts/setup_monitoring.py --environment production

# 4. Deploy services
python app/scripts/deploy.py --environment production

# 5. Check health
python app/scripts/health_check.py --environment production
```

## Scripts Overview

### `deploy_orchestrator.py` - Main Deployment Script

Complete deployment automation with all phases:

```bash
# Full deployment
python deploy_orchestrator.py -e production

# Skip monitoring setup
python deploy_orchestrator.py -e production --skip-monitoring

# Force deployment even if validation fails
python deploy_orchestrator.py -e production --force

# Rollback to previous deployment
python deploy_orchestrator.py -e production --rollback

# Check deployment status
python deploy_orchestrator.py -e production --status
```

### `configure_deployment.py` - Configuration Generator

Generates environment-specific configuration files:

```bash
# Generate configuration for production
python configure_deployment.py -e production

# Generate and validate configuration
python configure_deployment.py -e production --validate
```

**Generates:**
- `.env.production` - Environment variables
- `docker-compose.production.yml` - Docker compose configuration
- `monitoring/` - Monitoring configuration files
- `scripts/start.sh` and `scripts/stop.sh` - Helper scripts
- `README.md` - Deployment package documentation

### `validate_deployment.py` - Pre-deployment Validation

Validates deployment environment and configuration:

```bash
# Validate production environment
python validate_deployment.py -e production

# Verbose validation with detailed output
python validate_deployment.py -e production --verbose
```

**Validates:**
- Configuration files and syntax
- Docker environment and availability
- Network connectivity and port availability
- System resources (memory, disk, CPU)
- Security settings
- Required files existence

### `deploy.py` - Core Deployment Engine

Handles the actual deployment process with health checks and rollback:

```bash
# Deploy with default settings
python deploy.py -e production

# Deploy without rollback capability
python deploy.py -e production --no-rollback

# Deploy without backup
python deploy.py -e production --no-backup

# Deploy without tests
python deploy.py -e production --no-tests

# Get deployment status
python deploy.py -e production --status
```

### `health_check.py` - Health Monitoring

Comprehensive health checking for all system components:

```bash
# Full health check
python health_check.py -e production

# Wait for system to become healthy (5 minutes timeout)
python health_check.py -e production --wait 300

# Quick readiness check
python health_check.py --readiness

# Quick liveness check
python health_check.py --liveness

# JSON output for automation
python health_check.py -e production --json
```

### `setup_monitoring.py` - Monitoring Infrastructure

Sets up Prometheus, Grafana, and Alertmanager:

```bash
# Setup monitoring infrastructure
python setup_monitoring.py -e production --setup

# Start monitoring services
python setup_monitoring.py -e production --start

# Stop monitoring services
python setup_monitoring.py -e production --stop
```

## Configuration Structure

### Environment Files

Configuration is organized by environment:

```
app/config/
├── base.yaml                    # Base configuration template
├── environments/
│   ├── development.yaml         # Development overrides
│   ├── staging.yaml            # Staging overrides
│   └── production.yaml         # Production overrides
└── templates/
    ├── docker-compose.template.yml
    ├── nginx.conf.template
    └── systemd.service.template
```

### Generated Deployment Package

After running `configure_deployment.py`, you get:

```
deployment_production/
├── .env.production              # Environment variables
├── docker-compose.production.yml # Docker compose file
├── monitoring/                  # Monitoring configuration
│   ├── prometheus/
│   ├── grafana/
│   └── alertmanager/
├── scripts/
│   ├── start.sh                # Start script
│   └── stop.sh                 # Stop script
├── health_check.py             # Health check utility
├── deploy.py                   # Deployment script
└── README.md                   # Package documentation
```

## Environment Variables

Key environment variables for configuration:

### Database Configuration
- `DB_HOST` - Database host
- `DB_PORT` - Database port
- `DB_NAME` - Database name
- `DB_USER` - Database username
- `DB_PASSWORD` - Database password
- `DB_POOL_SIZE` - Connection pool size
- `DB_TIMEOUT` - Connection timeout
- `DB_RETRY_ATTEMPTS` - Retry attempts

### Orchestrator Configuration
- `ORCHESTRATOR_HOST` - Orchestrator bind host
- `ORCHESTRATOR_PORT` - Orchestrator port
- `MAX_INSTANCES` - Maximum worker instances
- `HEARTBEAT_INTERVAL` - Heartbeat interval (seconds)
- `REBALANCE_THRESHOLD` - Load imbalance threshold
- `EMERGENCY_TIMEOUT` - Emergency recovery timeout

### Monitoring Configuration
- `MONITORING_ENABLED` - Enable monitoring
- `METRICS_PORT` - Prometheus metrics port
- `LOG_LEVEL` - Logging level
- `ALERT_WEBHOOK` - Alert webhook URL
- `GRAFANA_ADMIN_PASSWORD` - Grafana admin password

## Monitoring and Alerting

### Prometheus Metrics

The system exposes various metrics:

- `orchestrator_active_instances` - Number of active instances
- `orchestrator_streams_per_instance` - Streams per instance
- `orchestrator_requests_total` - Total requests
- `orchestrator_request_duration_seconds` - Request duration
- `orchestrator_errors_total` - Total errors
- `orchestrator_db_connections_active` - Active DB connections
- `orchestrator_load_balance_score` - Load balance score
- `orchestrator_instance_last_heartbeat` - Last heartbeat timestamp

### Grafana Dashboards

Pre-configured dashboards include:

- System Overview
- Active Instances
- Stream Distribution
- Request Rate and Response Time
- Database Connections
- Error Rate
- Load Balance Score
- Heartbeat Status

### Alert Rules

Configured alerts for:

- Orchestrator service down
- High error rate
- Database connection issues
- Load imbalance
- Missing heartbeats
- High response time
- Low active instances
- Database deadlocks
- Stream assignment failures
- Consistency check failures

## Rollback and Recovery

### Automatic Rollback

The deployment system automatically creates backups and can rollback on failure:

```bash
# Rollback to previous deployment
python deploy_orchestrator.py -e production --rollback

# Rollback to specific snapshot
python deploy_orchestrator.py -e production --rollback snapshot_20231201_143022
```

### Manual Recovery

If automatic rollback fails:

```bash
# Stop services
docker-compose -f docker-compose.production.yml down

# Restore from backup
cp -r deployment_backup_*/config ./
cp deployment_backup_*/docker-compose.*.yml ./

# Restart services
docker-compose -f docker-compose.production.yml up -d
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Check what's using the port
   netstat -tulpn | grep :8000
   
   # Kill the process or change port in configuration
   ```

2. **Docker Not Available**
   ```bash
   # Check Docker status
   systemctl status docker
   
   # Start Docker if needed
   sudo systemctl start docker
   ```

3. **Database Connection Failed**
   ```bash
   # Test database connectivity
   python -c "import psycopg2; psycopg2.connect('host=localhost dbname=orchestrator user=postgres')"
   ```

4. **Health Check Timeout**
   ```bash
   # Check service logs
   docker-compose -f docker-compose.production.yml logs orchestrator
   
   # Manual health check
   curl http://localhost:8000/health
   ```

### Log Files

Important log files:

- `deployment_history.log` - Deployment events
- `deployment_rollbacks.log` - Rollback events
- `deployment_validation_*.json` - Validation reports
- Docker container logs via `docker-compose logs`

### Getting Help

1. Run validation to identify issues:
   ```bash
   python validate_deployment.py -e production --verbose
   ```

2. Check system health:
   ```bash
   python health_check.py -e production --verbose
   ```

3. Review deployment status:
   ```bash
   python deploy_orchestrator.py -e production --status
   ```

## Security Considerations

- Never commit sensitive environment variables to version control
- Use strong passwords for database and Grafana
- Restrict monitoring endpoints to internal networks
- Regularly update Docker images and dependencies
- Monitor for security alerts and apply patches promptly

## Performance Tuning

### Database Optimization
- Adjust `DB_POOL_SIZE` based on load
- Monitor connection usage
- Optimize query performance

### Resource Allocation
- Monitor memory and CPU usage
- Adjust Docker resource limits
- Scale horizontally when needed

### Network Optimization
- Use appropriate timeouts
- Enable connection pooling
- Monitor network latency

## Contributing

When adding new deployment features:

1. Update configuration templates
2. Add validation checks
3. Update health checks
4. Add monitoring metrics
5. Update documentation
6. Test in development environment first

## Support

For deployment issues:

1. Check this documentation
2. Review log files
3. Run diagnostic scripts
4. Check monitoring dashboards
5. Contact the development team with specific error messages and logs
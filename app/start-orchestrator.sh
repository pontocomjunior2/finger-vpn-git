#!/bin/bash
set -e

# Enhanced Orchestrator Startup Script with Improved Service Sequencing
# Configuration from environment variables with detailed logging and validation
POSTGRES_STARTUP_TIMEOUT=${POSTGRES_STARTUP_TIMEOUT:-60}
REDIS_STARTUP_TIMEOUT=${REDIS_STARTUP_TIMEOUT:-30}
APP_STARTUP_TIMEOUT=${APP_STARTUP_TIMEOUT:-120}
DB_PASSWORD=${DB_PASSWORD:-orchestrator_pass}
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-orchestrator}
DB_USER=${DB_USER:-orchestrator_user}
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}

# Validation function for required environment variables
validate_environment_variables() {
    log_step "Validating required environment variables"
    
    local validation_errors=()
    local validation_warnings=()
    
    # Required variables validation
    if [ -z "$DB_HOST" ]; then
        validation_errors+=("DB_HOST is required but not set")
    fi
    
    if [ -z "$DB_PORT" ] || ! [[ "$DB_PORT" =~ ^[0-9]+$ ]] || [ "$DB_PORT" -lt 1 ] || [ "$DB_PORT" -gt 65535 ]; then
        validation_errors+=("DB_PORT must be a valid port number (1-65535), got: '$DB_PORT'")
    fi
    
    if [ -z "$DB_NAME" ]; then
        validation_errors+=("DB_NAME is required but not set")
    fi
    
    if [ -z "$DB_USER" ]; then
        validation_errors+=("DB_USER is required but not set")
    fi
    
    if [ -z "$DB_PASSWORD" ]; then
        validation_errors+=("DB_PASSWORD is required but not set")
    fi
    
    if [ -z "$REDIS_HOST" ]; then
        validation_errors+=("REDIS_HOST is required but not set")
    fi
    
    if [ -z "$REDIS_PORT" ] || ! [[ "$REDIS_PORT" =~ ^[0-9]+$ ]] || [ "$REDIS_PORT" -lt 1 ] || [ "$REDIS_PORT" -gt 65535 ]; then
        validation_errors+=("REDIS_PORT must be a valid port number (1-65535), got: '$REDIS_PORT'")
    fi
    
    # Timeout validation with warnings
    if ! [[ "$POSTGRES_STARTUP_TIMEOUT" =~ ^[0-9]+$ ]] || [ "$POSTGRES_STARTUP_TIMEOUT" -lt 10 ]; then
        validation_warnings+=("POSTGRES_STARTUP_TIMEOUT should be at least 10 seconds, got: '$POSTGRES_STARTUP_TIMEOUT'")
    fi
    
    if ! [[ "$REDIS_STARTUP_TIMEOUT" =~ ^[0-9]+$ ]] || [ "$REDIS_STARTUP_TIMEOUT" -lt 5 ]; then
        validation_warnings+=("REDIS_STARTUP_TIMEOUT should be at least 5 seconds, got: '$REDIS_STARTUP_TIMEOUT'")
    fi
    
    if ! [[ "$APP_STARTUP_TIMEOUT" =~ ^[0-9]+$ ]] || [ "$APP_STARTUP_TIMEOUT" -lt 30 ]; then
        validation_warnings+=("APP_STARTUP_TIMEOUT should be at least 30 seconds, got: '$APP_STARTUP_TIMEOUT'")
    fi
    
    # Report validation results
    if [ ${#validation_errors[@]} -gt 0 ]; then
        log_error "Environment variable validation failed with ${#validation_errors[@]} errors:"
        for error in "${validation_errors[@]}"; do
            log_error "  - $error"
        done
        handle_startup_failure "Environment Validation" 12 "Required environment variables are missing or invalid" \
            "Set all required environment variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, REDIS_HOST, REDIS_PORT"
        return 1
    fi
    
    if [ ${#validation_warnings[@]} -gt 0 ]; then
        log_warning "Environment variable validation found ${#validation_warnings[@]} warnings:"
        for warning in "${validation_warnings[@]}"; do
            log_warning "  - $warning"
        done
    fi
    
    # Log validated configuration
    log_info "Environment variables validated successfully:"
    log_info "  Database: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"
    log_info "  Redis: $REDIS_HOST:$REDIS_PORT"
    log_info "  Timeouts: PostgreSQL=${POSTGRES_STARTUP_TIMEOUT}s, Redis=${REDIS_STARTUP_TIMEOUT}s, App=${APP_STARTUP_TIMEOUT}s"
    
    log_success "Environment variable validation completed"
    return 0
}

# Enhanced logging functions with structured output
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] [STARTUP] $1"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] [STARTUP] $1" >&2
}

log_warning() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] [STARTUP] $1" >&2
}

log_step() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [STEP] [STARTUP] $1"
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] [STARTUP] $1"
}

# Graceful failure handling with specific error messages
handle_startup_failure() {
    local service=$1
    local error_code=$2
    local error_message=$3
    local suggested_solution=$4
    
    log_error "=== STARTUP FAILURE DETECTED ==="
    log_error "Service: $service"
    log_error "Error Code: $error_code"
    log_error "Error Message: $error_message"
    log_error "Suggested Solution: $suggested_solution"
    log_error "=== END FAILURE REPORT ==="
    
    # Cleanup any started services
    cleanup_services
    
    exit $error_code
}

# Enhanced cleanup function for graceful shutdown with improved error handling
cleanup_services() {
    log_warning "Performing cleanup of started services..."
    
    local cleanup_start_time=$(date +%s)
    local cleanup_timeout=30
    local services_stopped=0
    local services_failed=0
    
    # Stop Redis if running
    if pgrep redis-server > /dev/null 2>&1; then
        log_info "Stopping Redis server..."
        if pkill -TERM redis-server 2>/dev/null; then
            # Wait for graceful shutdown
            local redis_wait=0
            while [ $redis_wait -lt 10 ] && pgrep redis-server > /dev/null 2>&1; do
                sleep 1
                redis_wait=$((redis_wait + 1))
            done
            
            # Force kill if still running
            if pgrep redis-server > /dev/null 2>&1; then
                log_warning "Redis didn't stop gracefully, forcing shutdown..."
                pkill -KILL redis-server 2>/dev/null || true
            fi
            
            if ! pgrep redis-server > /dev/null 2>&1; then
                log_success "Redis server stopped successfully"
                services_stopped=$((services_stopped + 1))
            else
                log_error "Failed to stop Redis server"
                services_failed=$((services_failed + 1))
            fi
        else
            log_warning "Redis server was not running or failed to send stop signal"
        fi
    else
        log_info "Redis server was not running"
    fi
    
    # Stop PostgreSQL if running
    if pgrep postgres > /dev/null 2>&1; then
        log_info "Stopping PostgreSQL server..."
        if sudo -u postgres /usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/data stop -m fast -t 15 2>/dev/null; then
            log_success "PostgreSQL server stopped successfully"
            services_stopped=$((services_stopped + 1))
        else
            log_warning "PostgreSQL graceful stop failed, trying immediate stop..."
            if sudo -u postgres /usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/data stop -m immediate -t 5 2>/dev/null; then
                log_success "PostgreSQL server stopped (immediate mode)"
                services_stopped=$((services_stopped + 1))
            else
                log_error "Failed to stop PostgreSQL server"
                services_failed=$((services_failed + 1))
            fi
        fi
    else
        log_info "PostgreSQL server was not running"
    fi
    
    # Clean up any remaining processes
    local remaining_processes=$(pgrep -f "postgres\|redis" | wc -l)
    if [ "$remaining_processes" -gt 0 ]; then
        log_warning "Found $remaining_processes remaining database processes, attempting cleanup..."
        pkill -f "postgres\|redis" 2>/dev/null || true
        sleep 2
    fi
    
    local cleanup_end_time=$(date +%s)
    local cleanup_duration=$((cleanup_end_time - cleanup_start_time))
    
    log_info "Cleanup completed in ${cleanup_duration}s (stopped: $services_stopped, failed: $services_failed)"
    
    # Clean up temporary files and startup lock
    if [ -f "/tmp/orchestrator_startup.lock" ]; then
        local lock_pid=$(cat "/tmp/orchestrator_startup.lock" 2>/dev/null || echo "unknown")
        if [ "$lock_pid" = "$$" ] || [ "$lock_pid" = "unknown" ]; then
            rm -f "/tmp/orchestrator_startup.lock" 2>/dev/null || true
            log_info "Removed startup lock file"
        else
            log_warning "Startup lock belongs to different process (PID: $lock_pid), not removing"
        fi
    fi
}

# Enhanced service verification functions with improved timeout handling
wait_for_postgres() {
    local host=${1:-$DB_HOST}
    local port=${2:-$DB_PORT}
    local timeout=${3:-$POSTGRES_STARTUP_TIMEOUT}
    
    log_step "Waiting for PostgreSQL at $host:$port (timeout: ${timeout}s)"
    
    local start_time=$(date +%s)
    local retry_delay=1
    local max_retry_delay=8
    local check_count=0
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        check_count=$((check_count + 1))
        
        if [ $elapsed -ge $timeout ]; then
            handle_startup_failure "PostgreSQL" 1 "PostgreSQL not ready after ${timeout}s timeout" \
                "Check PostgreSQL logs, verify configuration, ensure sufficient startup time"
            return 1
        fi
        
        log_info "PostgreSQL readiness check #$check_count (elapsed: ${elapsed}s)"
        
        # Try pg_isready first (most reliable)
        if command -v pg_isready >/dev/null 2>&1; then
            if sudo -u postgres pg_isready -h "$host" -p "$port" >/dev/null 2>&1; then
                log_success "PostgreSQL is ready at $host:$port (verified with pg_isready)"
                return 0
            fi
        fi
        
        # Fallback to netcat test
        if command -v nc >/dev/null 2>&1; then
            if nc -z "$host" "$port" >/dev/null 2>&1; then
                log_success "PostgreSQL port is open at $host:$port (verified with netcat)"
                return 0
            fi
        fi
        
        # Fallback to telnet test
        if command -v telnet >/dev/null 2>&1; then
            if timeout 3 telnet "$host" "$port" </dev/null >/dev/null 2>&1; then
                log_success "PostgreSQL port is accessible at $host:$port (verified with telnet)"
                return 0
            fi
        fi
        
        local remaining=$((timeout - elapsed))
        local actual_delay=$((retry_delay < remaining ? retry_delay : remaining))
        
        if [ $actual_delay -le 0 ]; then
            break
        fi
        
        log_info "PostgreSQL not ready, retrying in ${actual_delay}s (remaining: ${remaining}s)"
        sleep $actual_delay
        
        # Exponential backoff with jitter
        retry_delay=$((retry_delay * 3 / 2))
        if [ $retry_delay -gt $max_retry_delay ]; then
            retry_delay=$max_retry_delay
        fi
    done
    
    handle_startup_failure "PostgreSQL" 1 "PostgreSQL startup timeout after ${timeout}s" \
        "Increase POSTGRES_STARTUP_TIMEOUT, check PostgreSQL configuration, verify system resources"
    return 1
}

wait_for_redis() {
    local host=${1:-$REDIS_HOST}
    local port=${2:-$REDIS_PORT}
    local timeout=${3:-$REDIS_STARTUP_TIMEOUT}
    
    log_step "Waiting for Redis at $host:$port (timeout: ${timeout}s)"
    
    local start_time=$(date +%s)
    local retry_delay=1
    local max_retry_delay=4
    local check_count=0
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        check_count=$((check_count + 1))
        
        if [ $elapsed -ge $timeout ]; then
            handle_startup_failure "Redis" 2 "Redis not ready after ${timeout}s timeout" \
                "Check Redis logs, verify configuration, ensure Redis is properly installed"
            return 1
        fi
        
        log_info "Redis readiness check #$check_count (elapsed: ${elapsed}s)"
        
        # Try redis-cli ping (most reliable)
        if command -v redis-cli >/dev/null 2>&1; then
            if redis-cli -h "$host" -p "$port" ping >/dev/null 2>&1; then
                log_success "Redis is ready at $host:$port (verified with redis-cli ping)"
                return 0
            fi
        fi
        
        # Fallback to netcat test
        if command -v nc >/dev/null 2>&1; then
            if nc -z "$host" "$port" >/dev/null 2>&1; then
                log_success "Redis port is open at $host:$port (verified with netcat)"
                return 0
            fi
        fi
        
        # Fallback to telnet test
        if command -v telnet >/dev/null 2>&1; then
            if timeout 3 telnet "$host" "$port" </dev/null >/dev/null 2>&1; then
                log_success "Redis port is accessible at $host:$port (verified with telnet)"
                return 0
            fi
        fi
        
        local remaining=$((timeout - elapsed))
        local actual_delay=$((retry_delay < remaining ? retry_delay : remaining))
        
        if [ $actual_delay -le 0 ]; then
            break
        fi
        
        log_info "Redis not ready, retrying in ${actual_delay}s (remaining: ${remaining}s)"
        sleep $actual_delay
        
        # Exponential backoff
        retry_delay=$((retry_delay * 3 / 2))
        if [ $retry_delay -gt $max_retry_delay ]; then
            retry_delay=$max_retry_delay
        fi
    done
    
    handle_startup_failure "Redis" 2 "Redis startup timeout after ${timeout}s" \
        "Increase REDIS_STARTUP_TIMEOUT, check Redis configuration, verify system resources"
    return 1
}

setup_database() {
    log_step "Setting up PostgreSQL database and user"
    
    local setup_start_time=$(date +%s)
    
    # Create user with detailed error handling
    log_info "Creating PostgreSQL user: $DB_USER"
    if sudo -u postgres psql -c "CREATE USER $DB_USER WITH SUPERUSER PASSWORD '$DB_PASSWORD';" 2>/dev/null; then
        log_success "Created PostgreSQL user: $DB_USER"
    else
        # Check if user already exists
        if sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER';" | grep -q "1 row"; then
            log_info "PostgreSQL user $DB_USER already exists"
        else
            handle_startup_failure "PostgreSQL Setup" 3 "Failed to create PostgreSQL user $DB_USER" \
                "Check PostgreSQL permissions, verify postgres user privileges"
            return 1
        fi
    fi
    
    # Create database with detailed error handling
    log_info "Creating PostgreSQL database: $DB_NAME"
    if sudo -u postgres createdb -O "$DB_USER" "$DB_NAME" 2>/dev/null; then
        log_success "Created PostgreSQL database: $DB_NAME"
    else
        # Check if database already exists
        if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
            log_info "PostgreSQL database $DB_NAME already exists"
        else
            handle_startup_failure "PostgreSQL Setup" 3 "Failed to create PostgreSQL database $DB_NAME" \
                "Check PostgreSQL permissions, verify disk space, check database naming"
            return 1
        fi
    fi
    
    # Test connection with comprehensive verification
    log_info "Verifying database setup and connectivity"
    if sudo -u postgres psql -d "$DB_NAME" -c "SELECT current_timestamp, version();" >/dev/null 2>&1; then
        local setup_end_time=$(date +%s)
        local setup_duration=$((setup_end_time - setup_start_time))
        log_success "Database setup verification successful (completed in ${setup_duration}s)"
        return 0
    else
        handle_startup_failure "PostgreSQL Setup" 3 "Database setup verification failed" \
            "Check database connectivity, verify user permissions, check PostgreSQL logs"
        return 1
    fi
}

verify_services() {
    log_step "Performing comprehensive service verification"
    
    local verification_start_time=$(date +%s)
    local all_services_ready=true
    local verification_timeout=30
    
    # Verify PostgreSQL with detailed checks
    log_info "Verifying PostgreSQL service connectivity and functionality..."
    if wait_for_postgres "$DB_HOST" "$DB_PORT" 10; then
        # Additional PostgreSQL functionality test
        if sudo -u postgres psql -d "$DB_NAME" -c "SELECT current_timestamp;" >/dev/null 2>&1; then
            log_success "PostgreSQL verification passed (connectivity and functionality)"
        else
            log_error "PostgreSQL connectivity OK but functionality test failed"
            all_services_ready=false
        fi
    else
        log_error "PostgreSQL verification failed (connectivity)"
        all_services_ready=false
    fi
    
    # Verify Redis with detailed checks
    log_info "Verifying Redis service connectivity and functionality..."
    if wait_for_redis "$REDIS_HOST" "$REDIS_PORT" 10; then
        # Additional Redis functionality test
        if command -v redis-cli >/dev/null 2>&1; then
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" set "startup_test" "$(date)" >/dev/null 2>&1; then
                redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" del "startup_test" >/dev/null 2>&1
                log_success "Redis verification passed (connectivity and functionality)"
            else
                log_error "Redis connectivity OK but functionality test failed"
                all_services_ready=false
            fi
        else
            log_success "Redis verification passed (connectivity only - redis-cli not available)"
        fi
    else
        log_error "Redis verification failed (connectivity)"
        all_services_ready=false
    fi
    
    # Environment variables verification
    log_info "Verifying environment variables configuration..."
    local env_vars_ok=true
    
    if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ]; then
        log_error "Missing required database environment variables"
        env_vars_ok=false
    fi
    
    if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ]; then
        log_error "Missing required Redis environment variables"
        env_vars_ok=false
    fi
    
    if [ "$env_vars_ok" = true ]; then
        log_success "Environment variables verification passed"
    else
        log_error "Environment variables verification failed"
        all_services_ready=false
    fi
    
    local verification_end_time=$(date +%s)
    local verification_duration=$((verification_end_time - verification_start_time))
    
    if [ "$all_services_ready" = true ]; then
        log_success "All services verified successfully (completed in ${verification_duration}s)"
        return 0
    else
        handle_startup_failure "Service Verification" 4 "Service verification failed after ${verification_duration}s" \
            "Check individual service logs, verify configurations, ensure all services are properly started"
        return 1
    fi
}

# Main startup sequence with enhanced service sequencing
startup_start_time=$(date +%s)

log_info "=== ENHANCED ORCHESTRATOR STARTUP SEQUENCE ==="
log_info "Startup initiated at $(date)"
log_info "Configuration: PostgreSQL timeout=${POSTGRES_STARTUP_TIMEOUT}s, Redis timeout=${REDIS_STARTUP_TIMEOUT}s"

# Trap signals for graceful cleanup
trap cleanup_services EXIT INT TERM

# Step 0: Environment variable validation (must be first)
log_step "Step 0: Environment variable validation"
if ! validate_environment_variables; then
    handle_startup_failure "Environment Validation" 12 "Environment variable validation failed" \
        "Check and set all required environment variables before starting the container"
fi
log_success "Step 0 completed: Environment variables validated successfully"

# Step 1: Pre-startup environment validation and lock management
log_step "Step 1: Pre-startup environment validation and lock management"
log_info "Validating startup environment and prerequisites..."

# Check for existing startup lock to prevent concurrent startups
STARTUP_LOCK="/tmp/orchestrator_startup.lock"
if [ -f "$STARTUP_LOCK" ]; then
    lock_pid=$(cat "$STARTUP_LOCK" 2>/dev/null || echo "unknown")
    if [ "$lock_pid" != "unknown" ] && kill -0 "$lock_pid" 2>/dev/null; then
        handle_startup_failure "Startup Lock" 13 "Another orchestrator startup is already in progress (PID: $lock_pid)" \
            "Wait for the existing startup to complete or remove the lock file: $STARTUP_LOCK"
    else
        log_warning "Found stale startup lock file, removing..."
        rm -f "$STARTUP_LOCK" 2>/dev/null || true
    fi
fi

# Create startup lock
echo $$ > "$STARTUP_LOCK" || {
    handle_startup_failure "Startup Lock" 14 "Failed to create startup lock file" \
        "Check write permissions for /tmp directory"
}
log_info "Created startup lock (PID: $$)"

# Check required directories with proper error handling
if [ ! -d "/var/lib/postgresql/data" ]; then
    log_warning "PostgreSQL data directory does not exist, creating..."
    if ! sudo mkdir -p /var/lib/postgresql/data 2>/dev/null; then
        handle_startup_failure "Directory Creation" 15 "Failed to create PostgreSQL data directory" \
            "Check sudo permissions and filesystem space"
    fi
    if ! sudo chown postgres:postgres /var/lib/postgresql/data 2>/dev/null; then
        handle_startup_failure "Directory Permissions" 16 "Failed to set PostgreSQL data directory permissions" \
            "Check sudo permissions and user/group existence"
    fi
    log_success "Created PostgreSQL data directory with proper permissions"
fi

# Check log directory with proper error handling
if [ ! -d "/app/logs" ]; then
    log_info "Creating logs directory..."
    if ! mkdir -p /app/logs 2>/dev/null; then
        handle_startup_failure "Directory Creation" 17 "Failed to create logs directory" \
            "Check write permissions for /app directory"
    fi
    log_success "Created logs directory"
fi

# Verify directory permissions
if [ ! -w "/app/logs" ]; then
    handle_startup_failure "Directory Permissions" 18 "Logs directory is not writable" \
        "Check permissions for /app/logs directory"
fi

# Check available disk space
available_space=$(df /var/lib/postgresql/data | awk 'NR==2 {print $4}')
if [ "$available_space" -lt 1048576 ]; then  # Less than 1GB
    log_warning "Low disk space available: ${available_space}KB (recommended: >1GB)"
fi

log_success "Step 1 completed: Environment validation and lock management successful"

# Step 2: PostgreSQL service startup
log_step "Step 2: PostgreSQL service startup"
log_info "Starting PostgreSQL internal service..."

# Initialize PostgreSQL if needed
if [ ! -f "/var/lib/postgresql/data/PG_VERSION" ]; then
    log_info "Initializing PostgreSQL database cluster..."
    sudo -u postgres /usr/lib/postgresql/*/bin/initdb -D /var/lib/postgresql/data
fi

# Start PostgreSQL with detailed logging
if sudo -u postgres /usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/data -l /app/logs/postgresql.log start; then
    log_success "PostgreSQL service started successfully"
else
    handle_startup_failure "PostgreSQL Service" 5 "Failed to start PostgreSQL service" \
        "Check PostgreSQL installation, verify data directory permissions, check system resources"
fi

log_success "Step 2 completed: PostgreSQL service startup successful"

# Step 3: PostgreSQL readiness verification
log_step "Step 3: PostgreSQL readiness verification"
if ! wait_for_postgres "$DB_HOST" "$DB_PORT" $POSTGRES_STARTUP_TIMEOUT; then
    handle_startup_failure "PostgreSQL Readiness" 6 "PostgreSQL startup failed or timed out" \
        "Increase POSTGRES_STARTUP_TIMEOUT, check PostgreSQL logs at /app/logs/postgresql.log"
fi

log_success "Step 3 completed: PostgreSQL readiness verified"

# Step 4: Database and user setup
log_step "Step 4: Database and user setup"
if ! setup_database; then
    handle_startup_failure "Database Setup" 7 "Database setup failed" \
        "Check PostgreSQL user permissions, verify database creation privileges"
fi

log_success "Step 4 completed: Database and user setup successful"

# Step 5: Redis service startup
log_step "Step 5: Redis service startup"
log_info "Starting Redis service..."

# Start Redis with configuration
if redis-server --daemonize yes --bind 0.0.0.0 --port "$REDIS_PORT" --logfile /app/logs/redis.log; then
    log_success "Redis service started successfully"
else
    handle_startup_failure "Redis Service" 8 "Failed to start Redis service" \
        "Check Redis installation, verify port availability, check system resources"
fi

log_success "Step 5 completed: Redis service startup successful"

# Step 6: Redis readiness verification
log_step "Step 6: Redis readiness verification"
if ! wait_for_redis "$REDIS_HOST" "$REDIS_PORT" $REDIS_STARTUP_TIMEOUT; then
    handle_startup_failure "Redis Readiness" 9 "Redis startup failed or timed out" \
        "Increase REDIS_STARTUP_TIMEOUT, check Redis logs at /app/logs/redis.log"
fi

log_success "Step 6 completed: Redis readiness verified"

# Step 7: Comprehensive service verification
log_step "Step 7: Comprehensive service verification"
if ! verify_services; then
    handle_startup_failure "Service Verification" 10 "Comprehensive service verification failed" \
        "Check individual service status, verify network connectivity, review service logs"
fi

log_success "Step 7 completed: All services verified successfully"

# Step 8: Environment configuration
log_step "Step 8: Environment configuration for application"
export DB_HOST="$DB_HOST"
export DB_PORT="$DB_PORT"
export DB_NAME="$DB_NAME"
export DB_USER="$DB_USER"
export DB_PASSWORD="$DB_PASSWORD"
export REDIS_HOST="$REDIS_HOST"
export REDIS_PORT="$REDIS_PORT"

log_info "Environment variables configured:"
log_info "  DB_HOST=$DB_HOST"
log_info "  DB_PORT=$DB_PORT"
log_info "  DB_NAME=$DB_NAME"
log_info "  DB_USER=$DB_USER"
log_info "  REDIS_HOST=$REDIS_HOST"
log_info "  REDIS_PORT=$REDIS_PORT"

log_success "Step 8 completed: Environment configuration successful"

# Calculate total startup time
startup_end_time=$(date +%s)
total_startup_time=$((startup_end_time - startup_start_time))

log_success "=== STARTUP SEQUENCE COMPLETED SUCCESSFULLY ==="
log_success "Total startup time: ${total_startup_time}s"
log_success "All services are ready and verified"

# Step 9: Application startup
log_step "Step 9: Starting Python application"
log_info "Launching orchestrator application with uvicorn..."

# Use Python verification functions for final check before app start with enhanced diagnostics
python3 -c "
import sys
sys.path.append('/app')
from orchestrator import verify_services, validate_startup_environment, DB_CONFIG
from diagnostic_logger import diagnostic_logger

# Run comprehensive startup validation
diagnostic_logger.set_phase('FINAL_VALIDATION')
validation_result = validate_startup_environment()

if validation_result['overall_status'] == 'CRITICAL_ISSUES':
    print('Startup validation found critical issues:')
    for issue in validation_result['critical_issues']:
        print(f'  - {issue}')
    print('Recommendations:')
    for rec in validation_result['recommendations']:
        print(f'  - {rec}')
    sys.exit(1)

# Run service verification
result = verify_services(DB_CONFIG, '$REDIS_HOST', int('$REDIS_PORT'))
if result['overall_status'] != 'ready':
    print('Python service verification failed:', result['errors'])
    print('Service details:')
    for service_name, service_data in result['services'].items():
        print(f'  {service_name}: {service_data[\"status\"]}')
        if service_data.get('error'):
            print(f'    Error: {service_data[\"error\"]}')
    sys.exit(1)

print('Python service verification passed')
print('All diagnostic checks completed successfully')
" || handle_startup_failure "Python Verification" 11 "Python service verification failed" \
    "Check Python dependencies, verify orchestrator module, check service connectivity"

log_success "Python service verification passed"

# Start the application with proper error handling
log_info "Starting uvicorn server..."
exec python -m uvicorn app.main_orchestrator:app --host 0.0.0.0 --port 8000 --log-level info
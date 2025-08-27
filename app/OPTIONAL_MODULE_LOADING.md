# Optional Module Loading with Graceful Degradation

## Overview

The orchestrator system implements optional module loading with graceful degradation to ensure the system continues operating even when some enhanced features are not available. This approach provides flexibility in deployment scenarios and improves system reliability.

## Supported Optional Modules

### 1. psutil
- **Purpose**: System metrics collection (CPU, memory, disk usage)
- **Fallback**: System metrics are disabled, but orchestrator continues functioning
- **Impact**: Heartbeat requests won't include system metrics

### 2. enhanced_orchestrator
- **Purpose**: Smart load balancing and advanced stream distribution
- **Fallback**: Basic load balancing algorithm is used
- **Impact**: No intelligent rebalancing, but basic stream assignment works

### 3. resilient_orchestrator  
- **Purpose**: Enhanced failure handling and circuit breaker patterns
- **Fallback**: Basic failure handling and retry logic
- **Impact**: No advanced failure recovery, but basic error handling works

## Implementation Details

### Module Loading Process

1. **Safe Import**: Each optional module is imported within try-catch blocks
2. **Error Logging**: Import failures are logged with appropriate warning levels
3. **Fallback Flags**: Boolean flags indicate module availability
4. **Graceful Initialization**: Components initialize with None values when modules are missing

### Status Monitoring

The system provides detailed status information about optional modules:

```python
# Get module status
status = orchestrator.get_optional_modules_status()

# Check functionality availability
if status["functionality"]["smart_load_balancing"]:
    # Use enhanced features
else:
    # Use basic functionality
```

### API Endpoint

Access module status via REST API:

```bash
GET /modules/status
```

Response includes:
- Module availability status
- Error messages for failed imports
- Functionality flags
- Summary statistics

## Configuration

No additional configuration is required. The system automatically detects available modules and adjusts functionality accordingly.

## Environment Variables

Optional modules respect the same environment variables as the main orchestrator:

- `HEARTBEAT_TIMEOUT`: Timeout for heartbeat monitoring
- `MAX_RETRY_ATTEMPTS`: Maximum retry attempts for operations
- `CIRCUIT_BREAKER_THRESHOLD`: Circuit breaker failure threshold
- `EXPONENTIAL_BACKOFF`: Enable exponential backoff (true/false)

## Logging

The system provides detailed logging for module loading:

```
INFO - psutil loaded successfully - system metrics available
WARNING - Enhanced orchestrator not available: ImportError. Using basic load balancing.
INFO - Optional modules loaded: ['psutil', 'resilient_orchestrator']
WARNING - Optional modules not available: ['enhanced_orchestrator']
```

## Testing

### Unit Tests
Run the optional module loading tests:
```bash
python -m pytest test_optional_module_loading.py -v
```

### Integration Tests
Test graceful degradation:
```bash
python test_graceful_degradation.py
```

## Deployment Scenarios

### Minimal Deployment
- Only core orchestrator functionality
- No optional modules required
- Basic load balancing and error handling

### Standard Deployment  
- Core orchestrator + psutil
- System metrics available
- Enhanced monitoring capabilities

### Full Deployment
- All optional modules available
- Complete feature set
- Advanced load balancing and failure handling

## Troubleshooting

### Module Import Failures

1. **Check Dependencies**: Ensure required packages are installed
2. **Check Logs**: Review startup logs for specific error messages
3. **Verify Status**: Use `/modules/status` endpoint to check module availability
4. **Test Functionality**: Verify that basic orchestrator functions work despite missing modules

### Common Issues

- **Missing Dependencies**: Install required packages (psutil, etc.)
- **Import Errors**: Check Python path and module locations
- **Configuration Issues**: Verify environment variables are set correctly

## Requirements Compliance

This implementation satisfies the following requirements:

- **6.1**: Safe import handling for enhanced_orchestrator module
- **6.2**: Warning logging for missing optional modules  
- **6.3**: System continues with basic functionality when modules are missing
- **6.4**: Orchestrator initialization handles missing dependencies gracefully

## Future Enhancements

- Dynamic module loading/unloading
- Hot-swapping of optional components
- Plugin architecture for additional modules
- Configuration-driven module selection
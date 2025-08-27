# Design Document

## Overview

Esta solução corrige os problemas críticos de inicialização do orchestrator no Docker, focando em três áreas principais: sequenciamento correto de serviços, tratamento robusto de erros no código Python, e implementação de verificações de saúde adequadas. A abordagem prioriza confiabilidade e facilidade de diagnóstico.

## Architecture

### Service Startup Sequence
```
1. PostgreSQL Initialization
   ├── Start PostgreSQL service
   ├── Wait for TCP/IP readiness
   ├── Create user and database
   └── Verify connection
   
2. Redis Initialization
   ├── Start Redis service
   ├── Wait for ping response
   └── Verify connectivity
   
3. Application Startup
   ├── Load environment variables
   ├── Test database connection
   ├── Create tables safely
   └── Start FastAPI server
```

### Error Handling Strategy
- **Graceful Degradation**: Sistema continua funcionando mesmo sem módulos opcionais
- **Retry Logic**: Implementação de backoff exponencial para conexões
- **Safe Resource Management**: Verificação de inicialização antes de cleanup
- **Detailed Logging**: Logs estruturados para facilitar diagnóstico

## Components and Interfaces

### 1. Enhanced Startup Script (`start-orchestrator.sh`)
**Responsabilidades:**
- Inicializar PostgreSQL com verificações robustas
- Configurar Redis com validação de conectividade
- Implementar timeouts e retry logic
- Fornecer logs detalhados de cada etapa

**Interface:**
```bash
# Funções principais
wait_for_postgres()     # Aguarda PostgreSQL estar pronto
wait_for_redis()        # Aguarda Redis estar pronto
setup_database()        # Cria usuário e banco
verify_services()       # Verifica todos os serviços
```

### 2. Database Connection Handler
**Responsabilidades:**
- Gerenciar conexões de banco com retry automático
- Tratar erros de conexão graciosamente
- Implementar timeouts configuráveis
- Manter pool de conexões saudável

**Interface:**
```python
class DatabaseManager:
    def connect_with_retry(self, max_retries=3)
    def create_tables_safely(self)
    def verify_connection(self)
    def close_connection_safely(self)
```

### 3. Service Health Monitor
**Responsabilidades:**
- Monitorar saúde de PostgreSQL e Redis
- Implementar health checks detalhados
- Reportar status específico de cada serviço
- Detectar problemas de conectividade

**Interface:**
```python
class HealthMonitor:
    def check_postgres_health(self)
    def check_redis_health(self)
    def check_application_health(self)
    def get_detailed_status(self)
```

## Data Models

### Service Status Model
```python
@dataclass
class ServiceStatus:
    name: str
    status: Literal["starting", "ready", "error", "unknown"]
    last_check: datetime
    error_message: Optional[str]
    retry_count: int
```

### Connection Config Model
```python
@dataclass
class ConnectionConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
```

## Error Handling

### 1. PostgreSQL Connection Errors
```python
def create_tables_safely(self):
    conn = None
    cursor = None
    try:
        conn = self.get_connection()
        cursor = conn.cursor()
        # Execute table creation
        conn.commit()
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
```

### 2. Missing Module Handling
```python
def load_optional_modules():
    modules = {}
    try:
        import enhanced_orchestrator
        modules['enhanced'] = enhanced_orchestrator
    except ImportError:
        logger.warning("Enhanced orchestrator not available, using standard version")
        modules['enhanced'] = None
    
    return modules
```

### 3. Service Startup Timeouts
```bash
wait_for_service() {
    local service=$1
    local timeout=${2:-60}
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        if check_service_ready $service; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    
    echo "Timeout waiting for $service after ${timeout}s"
    return 1
}
```

## Testing Strategy

### 1. Unit Tests
- **Database Connection**: Testar cenários de falha e recuperação
- **Service Health**: Validar detecção de problemas
- **Error Handling**: Verificar tratamento de exceções
- **Module Loading**: Testar carregamento opcional de módulos

### 2. Integration Tests
- **Container Startup**: Testar inicialização completa
- **Service Dependencies**: Validar ordem de inicialização
- **Health Checks**: Verificar endpoints de saúde
- **Error Recovery**: Testar recuperação de falhas

### 3. Docker Tests
```dockerfile
# Test stage no Dockerfile
FROM orchestrator:latest as test
RUN python -m pytest tests/
RUN ./test-startup.sh
```

### 4. Startup Validation Tests
```bash
# test-startup.sh
#!/bin/bash
echo "Testing PostgreSQL startup..."
test_postgres_startup

echo "Testing Redis startup..."
test_redis_startup

echo "Testing application startup..."
test_app_startup

echo "Testing health endpoints..."
test_health_endpoints
```

## Implementation Notes

### Dockerfile Modifications
- Adicionar scripts de teste e validação
- Melhorar health check com verificações específicas
- Implementar multi-stage build para testes
- Otimizar ordem de comandos para cache

### Environment Variables
```bash
# Database configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=orchestrator_pass
DB_TIMEOUT=30
DB_MAX_RETRIES=3

# Service timeouts
POSTGRES_STARTUP_TIMEOUT=60
REDIS_STARTUP_TIMEOUT=30
APP_STARTUP_TIMEOUT=120

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=structured
```

### Monitoring and Observability
- Structured logging com timestamps
- Métricas de startup time
- Health check endpoints detalhados
- Status dashboard para diagnóstico
# 🎯 CONFIGURAÇÃO EASYPANEL - VARIÁVEIS CORRETAS

## 🔧 Variáveis de Ambiente para EasyPanel

### ✅ OBRIGATÓRIAS (Configure no painel):

```env
# Segurança (ALTERE ESTAS!)
DB_PASSWORD=SuaSenhaSegura123!
SECRET_KEY=sua_chave_secreta_muito_segura_de_pelo_menos_32_caracteres_aqui

# Rede (localhost porque tudo está no mesmo container)
DB_HOST=localhost
DB_PORT=5432
REDIS_HOST=localhost
REDIS_PORT=6379

# Aplicação
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
```

### ⚙️ OPCIONAIS (Performance otimizada):

```env
# Database
DB_NAME=orchestrator
DB_USER=orchestrator_user

# Logs e Workers
LOG_LEVEL=INFO
MAX_WORKERS=2

# Performance
IMBALANCE_THRESHOLD=0.15
MAX_STREAM_DIFFERENCE=3
HEARTBEAT_TIMEOUT=180
HEARTBEAT_WARNING_THRESHOLD=90
MAX_MISSED_HEARTBEATS=2
MAX_RETRY_ATTEMPTS=5
RETRY_DELAY_SECONDS=3
EXPONENTIAL_BACKOFF=true

# Features
RUN_MIGRATIONS=true
RUN_HEALTH_CHECK=true

# Localização
TZ=America/Sao_Paulo
```

## 🐳 Configuração do Deploy

### Dockerfile: `Dockerfile.easypanel`
### Porta: `8000`
### Health Check: `/health`

## 🔍 Verificação Pós-Deploy

### 1. Health Check:
```
GET https://seu-dominio.com/health
```

### 2. Resposta Esperada:
```json
{
  "status": "healthy",
  "message": "Enhanced Stream Orchestrator is running",
  "database": "connected",
  "redis": "connected"
}
```

## 🚨 Diferenças Importantes

### ❌ Docker Compose (desenvolvimento):
```env
DB_HOST=postgres    # Nome do serviço
REDIS_HOST=redis    # Nome do serviço
```

### ✅ EasyPanel (produção):
```env
DB_HOST=localhost   # Mesmo container
REDIS_HOST=localhost # Mesmo container
```

## 🎯 Checklist de Deploy

- [ ] Repositório atualizado com branch `orchestrator-v1`
- [ ] Dockerfile configurado: `Dockerfile.easypanel`
- [ ] Variáveis obrigatórias configuradas no EasyPanel
- [ ] Porta 8000 exposta
- [ ] Domínio configurado
- [ ] Health check funcionando

**🚀 Com essas configurações, seu orchestrator funcionará perfeitamente no EasyPanel!**
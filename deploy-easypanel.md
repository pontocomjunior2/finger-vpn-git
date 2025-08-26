# 🚀 Deploy no EasyPanel - Guia Completo

## 📋 Pré-requisitos

1. **Conta no EasyPanel** configurada
2. **Repositório Git** com o código
3. **Variáveis de ambiente** configuradas

## 🔧 Configuração das Variáveis de Ambiente

### ✅ Variáveis OBRIGATÓRIAS no EasyPanel:

```env
# Senha do banco (ALTERE!)
DB_PASSWORD=SuaSenhaSegura123!

# Chave secreta (ALTERE!)
SECRET_KEY=sua_chave_secreta_muito_segura_de_pelo_menos_32_caracteres_aqui
```

### ✅ Variáveis de Rede (Configuração Automática):

```env
# Database - localhost porque está no mesmo container
DB_HOST=localhost
DB_PORT=5432
DB_NAME=orchestrator
DB_USER=orchestrator_user

# Redis - localhost porque está no mesmo container
REDIS_HOST=localhost
REDIS_PORT=6379

# Aplicação
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
```

### ⚙️ Variáveis Opcionais (Performance):

```env
LOG_LEVEL=INFO
MAX_WORKERS=2
IMBALANCE_THRESHOLD=0.15
MAX_STREAM_DIFFERENCE=3
HEARTBEAT_TIMEOUT=180
HEARTBEAT_WARNING_THRESHOLD=90
MAX_MISSED_HEARTBEATS=2
MAX_RETRY_ATTEMPTS=5
RETRY_DELAY_SECONDS=3
EXPONENTIAL_BACKOFF=true
RUN_MIGRATIONS=true
RUN_HEALTH_CHECK=true
TZ=America/Sao_Paulo
```

## 🐳 Configuração do EasyPanel

### 1. **Criar Nova Aplicação**
- Nome: `enhanced-orchestrator`
- Tipo: `Docker`
- Repositório: Seu repositório Git

### 2. **Configurar Build**
- **Dockerfile**: `Dockerfile.easypanel`
- **Context**: `.` (raiz do projeto)
- **Branch**: `orchestrator-v1`

### 3. **Configurar Portas**
- **Porta da Aplicação**: `8000`
- **Protocolo**: `HTTP`

### 4. **Configurar Domínio**
- Adicionar seu domínio personalizado
- Ou usar o domínio fornecido pelo EasyPanel

### 5. **Adicionar Variáveis de Ambiente**
Copie todas as variáveis do arquivo `.env.easypanel` para o painel do EasyPanel.

## 🔍 Verificação Pós-Deploy

### 1. **Health Check**
```bash
curl https://seu-dominio.com/health
```

**Resposta esperada:**
```json
{
  "status": "healthy",
  "message": "Enhanced Stream Orchestrator is running",
  "timestamp": "2025-01-XX...",
  "database": "connected",
  "redis": "connected"
}
```

### 2. **Endpoints Principais**
```bash
# Dashboard
https://seu-dominio.com/

# API Status
https://seu-dominio.com/api/status

# Métricas
https://seu-dominio.com/api/metrics

# Workers
https://seu-dominio.com/api/workers
```

### 3. **Logs no EasyPanel**
Monitore os logs para verificar:
- ✅ PostgreSQL iniciado
- ✅ Redis iniciado  
- ✅ Migrations executadas
- ✅ Orchestrator rodando na porta 8000

## 🚨 Troubleshooting

### Problema: "Database connection failed"
**Solução:**
```env
# Verifique se as variáveis estão corretas:
DB_HOST=localhost  # NÃO postgres
DB_PASSWORD=sua_senha_aqui
```

### Problema: "Redis connection failed"
**Solução:**
```env
# Verifique se está usando localhost:
REDIS_HOST=localhost  # NÃO redis
REDIS_PORT=6379
```

### Problema: "Application not starting"
**Verificações:**
1. Dockerfile correto: `Dockerfile.easypanel`
2. Porta exposta: `8000`
3. Variável `SECRET_KEY` configurada
4. Logs do EasyPanel para detalhes

### Problema: "Health check failing"
**Verificações:**
1. Aplicação rodando na porta `8000`
2. Endpoint `/health` acessível
3. Aguardar 60s para inicialização completa

## 📊 Monitoramento

### Logs Importantes:
```bash
# No EasyPanel, monitore:
- /var/log/supervisor/postgresql.log
- /var/log/supervisor/redis.log  
- /var/log/supervisor/orchestrator.log
- /var/log/supervisor/init-db.log
```

### Métricas de Performance:
- CPU: < 80%
- Memória: < 512MB
- Resposta: < 2s

## 🔐 Segurança

### ✅ Checklist de Segurança:
- [ ] `DB_PASSWORD` alterada do padrão
- [ ] `SECRET_KEY` com 32+ caracteres únicos
- [ ] HTTPS habilitado no domínio
- [ ] Logs não expõem senhas
- [ ] Backup do banco configurado

## 🎯 Deploy Rápido

### Comando Único (se usando CLI):
```bash
# 1. Fazer push do código
git push origin orchestrator-v1

# 2. No EasyPanel:
# - Criar app com Dockerfile.easypanel
# - Adicionar variáveis do .env.easypanel
# - Deploy!
```

**🚀 Seu Enhanced Stream Orchestrator estará rodando em poucos minutos!**
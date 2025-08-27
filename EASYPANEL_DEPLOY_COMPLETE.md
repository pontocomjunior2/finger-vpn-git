# 🚀 GUIA COMPLETO DE DEPLOY NO EASYPANEL - ORCHESTRATOR

## 📋 Pré-requisitos

1. **Conta no EasyPanel** configurada
2. **Repositório Git** com o código
3. **Variáveis de ambiente** definidas

## 🔧 Configuração no EasyPanel

### 1. Criar Nova Aplicação

1. Acesse o painel do EasyPanel
2. Clique em **"Create New App"**
3. Escolha **"Docker Compose"**
4. Nome da aplicação: `orchestrator`

### 2. Configurar Repositório

```
Repository URL: https://github.com/seu-usuario/seu-repositorio.git
Branch: main
Docker Compose File: docker-compose.easypanel.yml
```

### 3. Variáveis de Ambiente Obrigatórias

Configure estas variáveis no EasyPanel:

```bash
# =============================================================================
# VARIÁVEIS OBRIGATÓRIAS - CONFIGURAR NO EASYPANEL
# =============================================================================

# Senha do banco PostgreSQL (ALTERE ESTA!)
DB_PASSWORD=SuaSenhaSeguraAqui123!

# =============================================================================
# VARIÁVEIS OPCIONAIS - CONFIGURAÇÕES AVANÇADAS
# =============================================================================

# Configurações de Log
LOG_LEVEL=INFO

# Configurações de Performance
MAX_WORKERS=2
IMBALANCE_THRESHOLD=0.15
MAX_STREAM_DIFFERENCE=3

# Configurações de Timeout (ajustar se necessário)
POSTGRES_STARTUP_TIMEOUT=60
REDIS_STARTUP_TIMEOUT=30
APP_STARTUP_TIMEOUT=120

# Timezone
TZ=America/Sao_Paulo

# Feature Flags
RUN_MIGRATIONS=true
RUN_HEALTH_CHECK=true
```

### 4. Configurações de Recursos

**Recursos Mínimos Recomendados:**
- **CPU**: 0.5 vCPU
- **RAM**: 1GB
- **Storage**: 5GB

**Recursos Ideais:**
- **CPU**: 1 vCPU
- **RAM**: 2GB
- **Storage**: 10GB

## 📁 Estrutura de Arquivos

Certifique-se que estes arquivos estão no repositório:

```
├── Dockerfile.easypanel              # Dockerfile otimizado
├── docker-compose.easypanel.yml      # Compose para EasyPanel
├── requirements.txt                  # Dependências Python
├── app/
│   ├── orchestrator.py              # Aplicação principal
│   ├── start-orchestrator.sh        # Script de inicialização
│   └── ...                         # Outros arquivos da app
└── ...
```

## 🚀 Processo de Deploy

### 1. Preparar o Código

```bash
# 1. Verificar se todos os arquivos estão corretos
git status

# 2. Executar testes (se disponíveis)
python -m pytest tests/ -v

# 3. Verificar formatação do código
black app/ --check

# 4. Fazer commit das alterações
git add .
git commit -m "feat: deploy configuration for EasyPanel"
git push origin main
```

### 2. Deploy no EasyPanel

1. **Configurar a aplicação** no EasyPanel com as informações acima
2. **Definir as variáveis de ambiente** obrigatórias
3. **Iniciar o deploy** clicando em "Deploy"
4. **Aguardar o build** (pode levar 5-10 minutos)
5. **Verificar os logs** durante o processo

### 3. Verificação Pós-Deploy

Após o deploy, verifique:

```bash
# 1. Health Check
curl https://seu-app.easypanel.host/health

# 2. Endpoint de status
curl https://seu-app.easypanel.host/ready

# 3. Logs da aplicação (no painel do EasyPanel)
```

## 🔍 Monitoramento e Logs

### Endpoints de Monitoramento

- **Health Check**: `GET /health`
- **Ready Check**: `GET /ready`
- **Metrics**: `GET /metrics` (se habilitado)

### Logs Importantes

No EasyPanel, monitore estes logs:

1. **Container Logs**: Logs da aplicação Python
2. **Build Logs**: Logs do processo de build
3. **System Logs**: Logs do sistema Docker

### Exemplo de Logs Saudáveis

```
[INFO] [STARTUP] === ENHANCED ORCHESTRATOR STARTUP SEQUENCE ===
[SUCCESS] [STARTUP] Step 0 completed: Environment variables validated successfully
[SUCCESS] [STARTUP] Step 2 completed: PostgreSQL service startup successful
[SUCCESS] [STARTUP] Step 5 completed: Redis service startup successful
[SUCCESS] [STARTUP] === STARTUP SEQUENCE COMPLETED SUCCESSFULLY ===
[INFO] Starting uvicorn server...
```

## 🛠️ Troubleshooting

### Problemas Comuns

#### 1. Erro de Variáveis de Ambiente

**Sintoma:**
```
ERROR: Missing required environment variables: DB_PASSWORD
```

**Solução:**
- Verificar se `DB_PASSWORD` está definida no EasyPanel
- Verificar se não há espaços ou caracteres especiais

#### 2. Timeout de Startup

**Sintoma:**
```
PostgreSQL not ready after 60s timeout
```

**Solução:**
- Aumentar `POSTGRES_STARTUP_TIMEOUT` para 120
- Verificar recursos disponíveis no plano

#### 3. Erro de Memória

**Sintoma:**
```
Container killed due to memory limit
```

**Solução:**
- Aumentar limite de memória no EasyPanel
- Reduzir `MAX_WORKERS` para 1

#### 4. Erro de Build

**Sintoma:**
```
Failed to build Docker image
```

**Solução:**
- Verificar se `Dockerfile.easypanel` existe
- Verificar se `requirements.txt` está correto
- Verificar logs de build no EasyPanel

### Comandos de Debug

Para debugar problemas, use estes comandos no terminal do EasyPanel:

```bash
# Verificar status dos serviços
ps aux | grep -E "(postgres|redis|python)"

# Verificar logs do PostgreSQL
tail -f /app/logs/postgresql.log

# Verificar logs do Redis
tail -f /app/logs/redis.log

# Testar conectividade
nc -z localhost 5432  # PostgreSQL
nc -z localhost 6379  # Redis

# Executar validação manual
python /app/app/run_startup_validation.py --simple --no-env-check
```

## 📊 Configurações de Performance

### Para Planos Básicos (1GB RAM)

```bash
MAX_WORKERS=1
POSTGRES_STARTUP_TIMEOUT=90
REDIS_STARTUP_TIMEOUT=45
APP_STARTUP_TIMEOUT=180
```

### Para Planos Intermediários (2GB RAM)

```bash
MAX_WORKERS=2
POSTGRES_STARTUP_TIMEOUT=60
REDIS_STARTUP_TIMEOUT=30
APP_STARTUP_TIMEOUT=120
```

### Para Planos Avançados (4GB+ RAM)

```bash
MAX_WORKERS=4
POSTGRES_STARTUP_TIMEOUT=45
REDIS_STARTUP_TIMEOUT=20
APP_STARTUP_TIMEOUT=90
```

## 🔒 Segurança

### Variáveis Sensíveis

**NUNCA** commite estas informações no Git:
- `DB_PASSWORD`
- `SECRET_KEY`
- Chaves de API
- Tokens de acesso

### Configurações Recomendadas

```bash
# Use senhas fortes
DB_PASSWORD=MinhaSenh@Muito$egura2024!

# Configure timezone corretamente
TZ=America/Sao_Paulo

# Use logs apropriados para produção
LOG_LEVEL=INFO
```

## 📈 Escalabilidade

### Horizontal Scaling

Para escalar horizontalmente:

1. **Configurar Load Balancer** no EasyPanel
2. **Usar Redis externo** para sessões compartilhadas
3. **Configurar PostgreSQL externo** para dados compartilhados

### Vertical Scaling

Para escalar verticalmente:

1. **Aumentar recursos** no plano do EasyPanel
2. **Ajustar `MAX_WORKERS`** proporcionalmente
3. **Otimizar configurações** de timeout

## 📞 Suporte

### Logs para Suporte

Se precisar de suporte, colete estas informações:

```bash
# 1. Versão da aplicação
curl https://seu-app.easypanel.host/health

# 2. Logs recentes
# (Copiar do painel do EasyPanel)

# 3. Configurações de ambiente
# (Remover informações sensíveis)

# 4. Recursos utilizados
# (Verificar no painel do EasyPanel)
```

### Contatos

- **Documentação**: Este arquivo
- **Issues**: GitHub Issues do repositório
- **Suporte EasyPanel**: Suporte oficial do EasyPanel

---

## ✅ Checklist de Deploy

- [ ] Código commitado e pushed
- [ ] `Dockerfile.easypanel` presente
- [ ] `docker-compose.easypanel.yml` configurado
- [ ] Variáveis de ambiente definidas no EasyPanel
- [ ] `DB_PASSWORD` configurada (senha forte)
- [ ] Recursos adequados selecionados
- [ ] Deploy iniciado no EasyPanel
- [ ] Health check funcionando
- [ ] Logs verificados
- [ ] Aplicação acessível

**🎉 Parabéns! Seu Orchestrator está rodando no EasyPanel!**
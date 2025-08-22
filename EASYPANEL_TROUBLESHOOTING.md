# Troubleshooting EasyPanel - Orquestrador

## Problema: "Service is not reachable" no EasyPanel

### Sintomas
- Orquestrador funciona localmente (logs mostram sucesso)
- URL pública do EasyPanel retorna "Service is not reachable"
- Endpoints `/health`, `/status` não acessíveis externamente

### Possíveis Causas e Soluções

#### 1. Configuração de Porta no EasyPanel

**Problema**: EasyPanel não está mapeando corretamente a porta 8080

**Solução**:
1. No EasyPanel, vá em **Settings** > **Domains**
2. Verifique se a porta está configurada como `8080`
3. Se não estiver, adicione/edite:
   - **Port**: `8080`
   - **Protocol**: `HTTP`

#### 2. Health Check Configuração

**Problema**: EasyPanel pode estar usando health check incorreto

**Solução**:
1. No EasyPanel, vá em **Settings** > **Health Check**
2. Configure:
   - **Path**: `/health`
   - **Port**: `8080`
   - **Protocol**: `HTTP`
   - **Timeout**: `10s`
   - **Interval**: `30s`

#### 3. Docker Compose - Verificar Configuração

**Problema**: Docker compose pode não estar expondo a porta corretamente

**Verificar no docker-compose.orchestrator.yaml**:
```yaml
services:
  orchestrator:
    ports:
      - "8080:8080"  # ✅ Correto
    environment:
      - ORCHESTRATOR_HOST=0.0.0.0  # ✅ Importante: deve ser 0.0.0.0
      - ORCHESTRATOR_PORT=8080
```

#### 4. Firewall/Rede do EasyPanel

**Problema**: Configuração de rede do EasyPanel

**Solução**:
1. Verificar se não há configuração de rede customizada
2. Remover qualquer configuração de `networks:` do docker-compose
3. Deixar o EasyPanel gerenciar a rede automaticamente

#### 5. Logs do EasyPanel

**Verificar logs específicos**:
1. **Container Logs**: Verificar se o orquestrador está realmente iniciando
2. **Proxy Logs**: Verificar se o proxy reverso está funcionando
3. **System Logs**: Verificar erros de sistema

### ✅ SOLUÇÃO ENCONTRADA: Acesso via HTTP com Porta Específica

**Problema**: O EasyPanel fornece uma URL HTTPS, mas o orquestrador roda em HTTP na porta 8080.

**Solução**: 
1. Remover o `https://` da URL fornecida pelo EasyPanel
2. Adicionar `:8080` ao final da URL
3. Usar `http://` ao invés de `https://`

**Exemplo**:
- ❌ URL fornecida: `https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/`
- ✅ URL correta: `http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080/`

**Teste**:
```bash
# Testar endpoints
curl http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080/health
curl http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080/status
curl http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080/instances
```

## 2. Erro: "Bind for 0.0.0.0:8080 failed: port is already allocated"

### Sintomas
- Erro ao fazer deploy de instância fingerv7
- Mensagem: "port is already allocated"
- Conflito na porta 8080

### Causa
O `docker-compose.github.yaml` inclui tanto o orquestrador quanto a instância fingerv7, causando conflito quando o orquestrador já está rodando em outro projeto.

### ✅ SOLUÇÃO: Usar docker-compose específico para instâncias

**Para instâncias fingerv7**, use o arquivo `docker-compose.fingerv7.yaml` que NÃO inclui o orquestrador:

1. **No EasyPanel**, ao criar uma nova instância fingerv7:
   - Use o arquivo: `docker-compose.fingerv7.yaml`
   - NÃO use: `docker-compose.github.yaml`

2. **Configurar variáveis de ambiente corretas**:
```bash
# URL CORRETA do orquestrador (sem https, com :8080)
ORCHESTRATOR_URL=http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080

# ID único para cada instância
INSTANCE_ID=finger_app_8
SERVER_ID=finger_app_8

# Configurações do orquestrador
USE_ORCHESTRATOR=True
HEARTBEAT_INTERVAL=30
DISTRIBUTE_LOAD=True
ENABLE_ROTATION=False
TOTAL_SERVERS=1
```

### Arquivos por Tipo de Deploy
- **Orquestrador**: `docker-compose.orchestrator.yaml`
- **Instâncias fingerv7**: `docker-compose.fingerv7.yaml`
- **Deploy completo (orquestrador + instância)**: `docker-compose.github.yaml`

## 3. Erro: "No module named 'orchestrator_client'"

### Sintomas
- Instância fingerv7 não consegue importar o módulo orchestrator_client
- Fallback para modo sem orquestrador
- Uso de consistent hashing em vez do orquestrador

### Causa
O arquivo `orchestrator_client.py` não está sendo copiado para o container no `Dockerfilegit`.

### ✅ SOLUÇÃO: Atualizar Dockerfilegit

O `Dockerfilegit` foi corrigido para incluir o arquivo `orchestrator_client.py`:

```dockerfile
# Copiar somente o necessário para o worker
COPY app/fingerv7.py .
COPY app/db_pool.py .
COPY app/async_queue.py .
COPY app/orchestrator_client.py .  # ← ADICIONADO
COPY app/__init__.py .
```

**Após essa correção**, faça um novo deploy da instância para que o container seja reconstruído com o arquivo correto.

### Comandos de Diagnóstico

#### Dentro do Container (via EasyPanel Terminal)
```bash
# Verificar se o serviço está rodando internamente
curl http://localhost:8080/health

# Verificar se a porta está aberta
netstat -tlnp | grep 8080

# Verificar processos
ps aux | grep python
```

#### Teste de Conectividade Externa
```bash
# Testar conectividade direta (substitua pela URL do EasyPanel)
curl -v https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# Verificar DNS
nslookup n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host
```

### Configuração Recomendada para EasyPanel

#### docker-compose.orchestrator.yaml (Versão EasyPanel)
```yaml
version: '3.8'

services:
  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile.orchestrator
    ports:
      - "8080:8080"
    environment:
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_PORT=${POSTGRES_PORT:-5432}
      - ORCHESTRATOR_HOST=0.0.0.0
      - ORCHESTRATOR_PORT=8080
      - PYTHONUNBUFFERED=1
      - TZ=${TZ:-America/Sao_Paulo}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

### Passos de Resolução

1. **Verificar Configuração de Domínio**:
   - EasyPanel > Projeto > Settings > Domains
   - Confirmar porta 8080 configurada

2. **Verificar Health Check**:
   - EasyPanel > Projeto > Settings > Health Check
   - Path: `/health`, Port: `8080`

3. **Redeploy**:
   - Fazer redeploy após ajustes
   - Aguardar inicialização completa

4. **Verificar Logs**:
   - Container deve mostrar "Uvicorn running on http://0.0.0.0:8080"
   - Sem erros de bind ou permissão

5. **Teste Gradual**:
   - Primeiro teste interno: `curl http://localhost:8080/health`
   - Depois teste externo via URL pública

### Contato com Suporte EasyPanel

Se o problema persistir, contatar suporte com:
- Logs do container
- Configuração do docker-compose
- URL pública que não está funcionando
- Evidência de que funciona localmente

---

**Nota**: O orquestrador está funcionando corretamente localmente, o problema é específico da configuração de proxy/rede do EasyPanel.
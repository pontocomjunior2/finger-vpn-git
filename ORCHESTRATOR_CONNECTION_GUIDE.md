# Guia de Conexão das Instâncias ao Orquestrador

## 📋 Visão Geral

O orquestrador é um serviço independente que **não precisa de VPN** pois apenas distribui streams para as instâncias fingerv7. As instâncias fingerv7 se conectam diretamente ao orquestrador para receber suas atribuições de streams.

## 🏗️ Arquitetura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Instância 1   │    │   Orquestrador  │    │   Instância 2   │
│   (com VPN)     │◄──►│   (sem VPN)     │◄──►│   (com VPN)     │
│   fingerv7.py   │    │ orchestrator.py │    │   fingerv7.py   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Shazam API    │    │   PostgreSQL    │    │   Shazam API    │
│   (via VPN)     │    │   (Database)    │    │   (via VPN)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Deploy do Orquestrador

### 1. Usando Docker Compose Exclusivo

```bash
# No servidor onde ficará o orquestrador
cd /path/to/finger_vpn

# Usar o docker-compose exclusivo (sem VPN)
docker-compose -f docker-compose.orchestrator.yaml up -d
```

### 2. Verificar se está funcionando

```bash
# Verificar logs
docker-compose -f docker-compose.orchestrator.yaml logs -f

# Testar endpoints
curl http://localhost:8080/health
curl http://localhost:8080/status
```

## ⚙️ Configuração das Instâncias Fingerv7

### 1. Variáveis de Ambiente Necessárias

Adicione estas variáveis no arquivo `.env` ou nas configurações do EasyPanel de cada instância fingerv7:

```bash
# === Configuração do Orquestrador ===
USE_ORCHESTRATOR=True
ORCHESTRATOR_URL=http://SEU_ORCHESTRATOR_HOST:8080
INSTANCE_ID=finger_app_1  # ID único para cada instância
HEARTBEAT_INTERVAL=30     # Intervalo de heartbeat em segundos

# === Distribuição de Carga ===
DISTRIBUTE_LOAD=True
SERVER_ID=finger_app_1    # Mesmo valor do INSTANCE_ID

# === Configurações Legadas (manter para compatibilidade) ===
TOTAL_SERVERS=1           # Não usado com orquestrador, mas manter
ENABLE_ROTATION=False     # Sempre False com orquestrador
```

### 2. Exemplo de Configuração por Instância

#### Instância 1:
```bash
USE_ORCHESTRATOR=True
ORCHESTRATOR_URL=http://orchestrator.exemplo.com:8080
INSTANCE_ID=finger_app_1
SERVER_ID=finger_app_1
DISTRIBUTE_LOAD=True
HEARTBEAT_INTERVAL=30
```

#### Instância 2:
```bash
USE_ORCHESTRATOR=True
ORCHESTRATOR_URL=http://orchestrator.exemplo.com:8080
INSTANCE_ID=finger_app_2
SERVER_ID=finger_app_2
DISTRIBUTE_LOAD=True
HEARTBEAT_INTERVAL=30
```

### 3. No docker-compose.github.yaml (para instâncias com VPN)

O arquivo `docker-compose.github.yaml` já está configurado corretamente:

```yaml
services:
  finger_app:
    # ... outras configurações ...
    environment:
      # --- Orquestrador Central ---
      - USE_ORCHESTRATOR=${USE_ORCHESTRATOR:-True}
      - ORCHESTRATOR_URL=${ORCHESTRATOR_URL:-http://orchestrator:8080}
      - INSTANCE_ID=${INSTANCE_ID:-finger_app_1}
      - HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-30}
    depends_on:
      gluetun:
        condition: service_healthy
      orchestrator:
        condition: service_healthy  # Remove se orquestrador estiver em servidor separado
```

## 🔧 Configuração no EasyPanel

### 1. Deploy do Orquestrador

1. **Criar novo projeto no EasyPanel**:
   - Nome: `finger-orchestrator`
   - Tipo: GitHub
   - Branch: `orchestrator-v1`
   - Arquivo: `docker-compose.orchestrator.yaml`

2. **Configurar variáveis de ambiente**:
   ```bash
   POSTGRES_HOST=seu_host_postgres
   POSTGRES_USER=seu_usuario
   POSTGRES_PASSWORD=sua_senha
   POSTGRES_DB=radio_db
   POSTGRES_PORT=5432
   ```

3. **Obter URL do orquestrador**:
   - Após deploy, o EasyPanel fornecerá uma URL como:
   - `https://finger-orchestrator-abc123.easypanel.host`

### 2. Configurar Instâncias Fingerv7

1. **Atualizar variáveis de ambiente** em cada projeto fingerv7:
   ```bash
   USE_ORCHESTRATOR=True
   ORCHESTRATOR_URL=https://finger-orchestrator-abc123.easypanel.host
   INSTANCE_ID=finger_app_1  # Único para cada instância
   SERVER_ID=finger_app_1
   DISTRIBUTE_LOAD=True
   ```

2. **Remover dependência do orquestrador** no docker-compose.github.yaml:
   ```yaml
   depends_on:
     gluetun:
       condition: service_healthy
     # orchestrator:  # Comentar ou remover esta linha
     #   condition: service_healthy
   ```

## 🔍 Verificação e Monitoramento

### 1. Verificar Conexão das Instâncias

```bash
# Verificar status do orquestrador
curl https://seu-orchestrator.easypanel.host/status

# Verificar instâncias registradas
curl https://seu-orchestrator.easypanel.host/instances
```

### 2. Logs das Instâncias

Nos logs do fingerv7.py, você deve ver:

```
INFO - Cliente do orquestrador inicializado: https://seu-orchestrator.easypanel.host
INFO - Instância finger_app_1 registrada no orquestrador
INFO - Recebidos 5 streams do orquestrador
INFO - Processando 5 streams atribuídos pelo orquestrador
```

### 3. Monitoramento Contínuo

- **Heartbeat**: Cada instância envia heartbeat a cada 30 segundos
- **Rebalanceamento**: O orquestrador redistribui streams automaticamente
- **Failover**: Streams de instâncias inativas são redistribuídos

## 🚨 Resolução de Problemas

### Instância não consegue se conectar ao orquestrador

1. **Verificar URL**: Confirme se `ORCHESTRATOR_URL` está correto
2. **Verificar rede**: Teste conectividade com `curl`
3. **Verificar logs**: Procure erros de conexão nos logs

### Instância não recebe streams

1. **Verificar registro**: Confirme se aparece em `/instances`
2. **Verificar heartbeat**: Deve aparecer como "active" no status
3. **Verificar capacidade**: Confirme se `max_streams` está configurado

### Orquestrador não inicia

1. **Verificar banco**: Confirme conexão PostgreSQL
2. **Verificar porta**: Confirme se porta 8080 está disponível
3. **Verificar variáveis**: Confirme se todas as variáveis estão definidas

## 📝 Resumo dos Passos

1. ✅ **Deploy do orquestrador** usando `docker-compose.orchestrator.yaml`
2. ✅ **Obter URL** do orquestrador após deploy no EasyPanel
3. ✅ **Configurar variáveis** `ORCHESTRATOR_URL` em cada instância fingerv7
4. ✅ **Remover dependência** do orquestrador no docker-compose das instâncias
5. ✅ **Verificar conexão** através dos endpoints de status
6. ✅ **Monitorar logs** para confirmar funcionamento

Com essa configuração, o orquestrador funcionará independentemente das instâncias fingerv7, distribuindo streams de forma inteligente e automática.
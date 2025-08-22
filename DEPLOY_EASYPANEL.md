# Deploy via EasyPanel - Versão com Orquestrador Central

Este guia detalha como fazer o deploy da nova versão com orquestrador central via EasyPanel.

## Pré-requisitos

1. **Branch**: Certifique-se de estar no branch `orchestrator-v1`
2. **Banco de Dados**: PostgreSQL configurado e acessível
3. **EasyPanel**: Conta configurada com acesso ao repositório GitHub

## Configuração no EasyPanel

### 1. Criar Novo Projeto

1. Acesse o EasyPanel
2. Clique em "New Project"
3. Selecione "Docker Compose"
4. Configure:
   - **Name**: `finger-vpn-orchestrator`
   - **Repository**: Seu repositório GitHub
   - **Branch**: `orchestrator-v1`
   - **Docker Compose File**: `docker-compose.github.yaml`

### 2. Variáveis de Ambiente Obrigatórias

Configure as seguintes variáveis no EasyPanel:

#### Banco de Dados
```env
POSTGRES_HOST=seu_host_postgres
POSTGRES_USER=seu_usuario
POSTGRES_PASSWORD=sua_senha
POSTGRES_DB=seu_banco
POSTGRES_PORT=5432
```

#### VPN (Gluetun)
```env
VPN_SERVICE_PROVIDER=protonvpn
VPN_TYPE=wireguard
SERVER_COUNTRIES=Brazil
WIREGUARD_PRIVATE_KEY=sua_chave_privada
# OU para OpenVPN:
VPN_USER=seu_usuario_vpn
VPN_PASSWORD=sua_senha_vpn
```

#### Aplicação
```env
DB_TABLE_NAME=music_log
SERVER_ID=1
TOTAL_SERVERS=1
DISTRIBUTE_LOAD=True
ENABLE_ROTATION=False
ROTATION_HOURS=24
IDENTIFICATION_DURATION=15
DUPLICATE_PREVENTION_WINDOW_SECONDS=900
TZ=America/Sao_Paulo
```

#### Redis (Opcional - para heartbeats)
```env
REDIS_URL=redis://seu_redis:6379
REDIS_CHANNEL=smf:server_heartbeats
REDIS_KEY_PREFIX=smf:server
REDIS_HEARTBEAT_TTL_SECS=60
```

#### Orquestrador Central (Novas Variáveis)
```env
USE_ORCHESTRATOR=True
ORCHESTRATOR_URL=http://orchestrator:8080
INSTANCE_ID=finger_app_1
HEARTBEAT_INTERVAL=30
```

### 3. Configuração de Rede

#### Portas Expostas
- **8080**: API do Orquestrador (interno)
- O EasyPanel irá configurar automaticamente o proxy reverso

#### Volumes
- `gluetun_data`: Dados do Gluetun
- `app_segments`: Segmentos de áudio processados

## Preparação do Banco de Dados

### 1. Executar Setup do Orquestrador

Antes do primeiro deploy, execute o script de setup:

```bash
# No seu ambiente local ou servidor de banco
python setup_orchestrator.py
```

Ou execute manualmente as queries SQL:

```sql
-- Tabela de instâncias registradas
CREATE TABLE IF NOT EXISTS orchestrator_instances (
    instance_id VARCHAR(255) PRIMARY KEY,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stream_count INTEGER DEFAULT 0,
    max_streams INTEGER DEFAULT 10
);

-- Tabela de atribuições de streams
CREATE TABLE IF NOT EXISTS orchestrator_stream_assignments (
    stream_id VARCHAR(255) PRIMARY KEY,
    instance_id VARCHAR(255) REFERENCES orchestrator_instances(instance_id),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active'
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_instances_status ON orchestrator_instances(status);
CREATE INDEX IF NOT EXISTS idx_instances_heartbeat ON orchestrator_instances(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_assignments_instance ON orchestrator_stream_assignments(instance_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status ON orchestrator_stream_assignments(status);
```

## Deploy

### 1. Deploy do Orquestrador (Primeiro)

1. **Criar projeto separado para o orquestrador**:
   - Nome: `finger-orchestrator`
   - Usar arquivo: `docker-compose.orchestrator.yaml`

2. **Configurar variáveis de ambiente do orquestrador**:
   ```bash
   POSTGRES_HOST=seu_host_postgres
   POSTGRES_USER=seu_usuario
   POSTGRES_PASSWORD=sua_senha
   POSTGRES_DB=seu_banco
   POSTGRES_PORT=5432
   ```

3. **Fazer deploy do orquestrador**
4. **Anotar a URL pública do orquestrador** (será usada pelas instâncias)

### 2. Deploy de Instâncias fingerv7

1. **Criar projeto separado para cada instância**:
   - Nome: `finger_1_vpn`, `finger_2_vpn`, etc.
   - Usar arquivo: `docker-compose.fingerv7.yaml`

2. **Configurar variáveis de ambiente da instância**:
   ```bash
   # Banco de dados
   POSTGRES_HOST=seu_host_postgres
   POSTGRES_USER=seu_usuario
   POSTGRES_PASSWORD=sua_senha
   POSTGRES_DB=seu_banco
   
   # VPN
   VPN_SERVICE_PROVIDER=protonvpn
   WIREGUARD_PRIVATE_KEY=sua_chave_wireguard
   
   # Redis
   REDIS_URL=sua_url_redis
   
   # Orquestrador (URL CORRETA)
   USE_ORCHESTRATOR=True
   ORCHESTRATOR_URL=http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080
   INSTANCE_ID=finger_app_1  # ID único para cada instância
   SERVER_ID=finger_app_1    # Mesmo valor do INSTANCE_ID
   HEARTBEAT_INTERVAL=30
   DISTRIBUTE_LOAD=True
   ENABLE_ROTATION=False
   TOTAL_SERVERS=1
   ```

3. **Fazer deploy da instância**
4. **Verificar logs para confirmar conexão com orquestrador**

### 3. Arquivos por Tipo de Deploy

- **Orquestrador apenas**: `docker-compose.orchestrator.yaml`
- **Instância fingerv7 apenas**: `docker-compose.fingerv7.yaml`
- **Deploy completo (orquestrador + instância)**: `docker-compose.github.yaml`

⚠️ **IMPORTANTE**: Não use `docker-compose.github.yaml` para instâncias quando o orquestrador já estiver rodando em outro projeto, pois causará conflito de porta 8080.

### 4. Fazer Deploy

1. No EasyPanel, clique em "Deploy"
2. Aguarde o build e inicialização dos serviços
3. Verifique os logs para confirmar que:
   - Gluetun conectou à VPN
   - Orquestrador iniciou na porta 8080
   - finger_app conectou ao orquestrador

### 2. Verificação de Saúde

#### Verificar Orquestrador

**⚠️ IMPORTANTE**: O EasyPanel fornece uma URL HTTPS, mas o orquestrador roda em HTTP na porta 8080.

**Para acessar o orquestrador**:
1. Use a URL fornecida pelo EasyPanel
2. Remova o `https://` e adicione `http://`
3. Adicione `:8080` ao final da URL

```bash
# Exemplo: se sua URL do EasyPanel for:
# https://seu-projeto-orchestrator.azfa0v.easypanel.host/
# Use:

# Verificar se o orquestrador está rodando
curl http://seu-projeto-orchestrator.azfa0v.easypanel.host:8080/health
# Deve retornar: {"status": "healthy", "timestamp": "..."}
```

#### Verificar Instâncias Registradas
```bash
curl http://seu-projeto-orchestrator.azfa0v.easypanel.host:8080/instances
# Deve mostrar a instância finger_app_1 registrada
```

#### Verificar Logs
```bash
# No EasyPanel, verifique os logs de cada serviço:
# - orchestrator: Deve mostrar "Orchestrator started"
# - finger_app: Deve mostrar "Registered with orchestrator"
# - gluetun: Deve mostrar conexão VPN estabelecida
```

## Monitoramento

### Métricas Importantes

1. **Saúde do Orquestrador**: `/health`
2. **Instâncias Ativas**: `/instances`
3. **Distribuição de Streams**: `/streams`
4. **Logs de Heartbeat**: Verificar regularidade

### Alertas Recomendados

1. **Orquestrador Down**: Se `/health` falhar
2. **Instância Sem Heartbeat**: > 2 minutos sem heartbeat
3. **Streams Órfãos**: Streams sem instância ativa
4. **VPN Desconectada**: Verificar logs do Gluetun

## Troubleshooting

### Problemas Comuns

#### 1. Orquestrador não inicia
- Verificar variáveis de ambiente do banco
- Confirmar que as tabelas foram criadas
- Verificar logs para erros de conexão

#### 2. finger_app não conecta ao orquestrador
- Verificar `ORCHESTRATOR_URL`
- Confirmar que orquestrador está healthy
- Verificar conectividade de rede entre serviços

#### 3. Streams não são distribuídos
- Verificar se `USE_ORCHESTRATOR=True`
- Confirmar registro da instância
- Verificar logs de atribuição de streams

#### 4. VPN não conecta
- Verificar credenciais VPN
- Confirmar configuração do Gluetun
- Verificar logs do serviço gluetun

### Rollback para Versão Anterior

1. No EasyPanel, altere o branch para `main`
2. Defina `USE_ORCHESTRATOR=False`
3. Faça redeploy
4. O sistema voltará ao modo de consistent hashing

## Escalabilidade

### Adicionando Mais Instâncias

1. Duplique o serviço `finger_app` no docker-compose
2. Altere `INSTANCE_ID` para cada instância
3. Configure `TOTAL_SERVERS` adequadamente
4. O orquestrador distribuirá automaticamente

### Exemplo para 3 Instâncias

```yaml
finger_app_1:
  # ... configuração base
  environment:
    - INSTANCE_ID=finger_app_1
    - SERVER_ID=1
    - TOTAL_SERVERS=3

finger_app_2:
  # ... configuração base
  environment:
    - INSTANCE_ID=finger_app_2
    - SERVER_ID=2
    - TOTAL_SERVERS=3

finger_app_3:
  # ... configuração base
  environment:
    - INSTANCE_ID=finger_app_3
    - SERVER_ID=3
    - TOTAL_SERVERS=3
```

## Suporte

Para problemas ou dúvidas:
1. Verifique os logs de todos os serviços
2. Consulte o `MIGRATION_GUIDE.md`
3. Execute `test_migration.py` para diagnósticos
4. Verifique a conectividade entre serviços

---

**Nota**: Esta versão implementa balanceamento de carga inteligente, failover automático e monitoramento em tempo real. O sistema é backward-compatible e pode fazer rollback para o modo legado se necessário.
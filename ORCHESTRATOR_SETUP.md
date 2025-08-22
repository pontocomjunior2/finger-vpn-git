# Configuração do Orquestrador - Guia Completo

## ✅ Status Atual

O orquestrador está **funcionando corretamente** e configurado para usar as variáveis de ambiente do arquivo `.env` na raiz do projeto.

## 🔧 Configuração Automática

O sistema foi configurado para:

### 1. Carregamento de Variáveis de Ambiente
- **Prioridade 1**: Arquivo `.env` na raiz do projeto (`/finger_vpn/.env`)
- **Prioridade 2**: Arquivo `.env` no diretório da aplicação (`/finger_vpn/app/.env`)
- **Mapeamento automático**: `POSTGRES_*` → `DB_*`

### 2. Variáveis Utilizadas
```bash
# Banco de Dados (já configuradas no .env)
POSTGRES_HOST=104.234.173.96
POSTGRES_DB=radio_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=sua_senha
POSTGRES_PORT=5432

# Orquestrador (opcionais)
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8001
MAX_STREAMS_PER_INSTANCE=20
HEARTBEAT_TIMEOUT=300
REBALANCE_INTERVAL=60
```

## 🚀 Como Usar

### Desenvolvimento Local
```bash
# 1. Configurar orquestrador (pula teste de DB se necessário)
python app/setup_orchestrator.py --skip-db-test

# 2. Iniciar orquestrador
python app/orchestrator.py
# ou
start_orchestrator.bat
```

### Deploy no EasyPanel

1. **Configurar projeto no EasyPanel**:
   - Nome: `finger-vpn-orchestrator`
   - Tipo: GitHub
   - Branch: `orchestrator-v1`
   - Arquivo: `docker-compose.github.yaml`

2. **Variáveis de ambiente** (já configuradas no .env):
   - `POSTGRES_HOST`
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `POSTGRES_PORT`

3. **Após deploy**, obter URL do orquestrador:
   ```bash
   # Exemplo de URL gerada pelo EasyPanel
   ORCHESTRATOR_URL=https://finger-vpn-orchestrator-abc123.easypanel.host
   ```

## 📊 Endpoints Disponíveis

### API do Orquestrador
- `POST /register` - Registrar instância
- `POST /heartbeat` - Enviar heartbeat
- `POST /streams` - Solicitar streams
- `POST /release` - Liberar streams
- `GET /status` - Status do orquestrador
- `GET /instances` - Listar instâncias
- `GET /docs` - Documentação Swagger

### URLs de Acesso
- **API**: `http://localhost:8001`
- **Documentação**: `http://localhost:8001/docs`
- **Status**: `http://localhost:8001/status`

## 🔍 Verificação de Funcionamento

### 1. Verificar se está rodando
```bash
curl http://localhost:8001/status
```

### 2. Logs do orquestrador
```bash
# Deve mostrar:
# - Variáveis carregadas de .env
# - Tabelas criadas com sucesso
# - Servidor rodando em 0.0.0.0:8001
# - Tarefas de monitoramento iniciadas
```

### 3. Testar registro de instância
```bash
curl -X POST "http://localhost:8001/register" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "test-server-1",
    "ip": "192.168.1.100",
    "port": 8080,
    "max_streams": 20
  }'
```

## 🗃️ Estrutura do Banco de Dados

O orquestrador cria automaticamente as seguintes tabelas:

### `orchestrator_instances`
- Registro de todas as instâncias do sistema
- Controle de capacidade e status
- Monitoramento de heartbeat

### `orchestrator_stream_assignments`
- Atribuições de streams para instâncias
- Controle de distribuição de carga
- Status de cada stream

### `orchestrator_rebalance_history`
- Histórico de rebalanceamentos
- Auditoria de movimentações
- Análise de performance

## 🔧 Resolução de Problemas

### Erro de Conexão com Banco
```bash
# Use a opção --skip-db-test durante setup
python app/setup_orchestrator.py --skip-db-test
```

### Porta 8001 em uso
```bash
# Definir porta diferente
export ORCHESTRATOR_PORT=8002
python app/orchestrator.py
```

### Verificar variáveis carregadas
```bash
# O orquestrador mostra no log qual .env foi carregado
# Exemplo: "Orquestrador: Variáveis carregadas de D:\dataradio\finger_vpn\.env"
```

## 📋 Próximos Passos

1. **Deploy no EasyPanel**: Usar as configurações do `DEPLOY_SUMMARY.md`
2. **Obter URL do orquestrador**: Após deploy no EasyPanel
3. **Configurar instâncias**: Atualizar fingerv7.py com URL do orquestrador
4. **Monitoramento**: Acompanhar logs e métricas via `/status`

## 🆘 Suporte

- **Logs**: Verificar saída do `python app/orchestrator.py`
- **Status**: Acessar `http://localhost:8001/status`
- **Documentação**: Acessar `http://localhost:8001/docs`
- **Arquivos**: `DEPLOY_SUMMARY.md` e `DEPLOY_EASYPANEL.md`
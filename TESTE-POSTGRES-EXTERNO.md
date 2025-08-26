# 🔗 Teste PostgreSQL Externo - Tabela de Streams

## 📊 **Configuração Atual**

### **PostgreSQL Externo (Streams):**
```
Host: 104.234.173.96
Database: music_log
User: postgres
Password: Conquista@@2
Port: 5432
Tabela: streams
```

### **PostgreSQL Interno (Orchestrator):**
```
Host: localhost
Database: orchestrator
User: orchestrator_user
Port: 5432
```

## 🧪 **Endpoints de Teste**

### 1. **Testar Conexão PostgreSQL Externo**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/postgres/test
```

**Resposta Esperada:**
```json
{
  "status": "success",
  "message": "PostgreSQL connection successful",
  "database": "music_log",
  "table": "streams",
  "total_streams": 1234,
  "timestamp": "2025-01-XX..."
}
```

### 2. **Obter Streams Recentes**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/streams
```

**Resposta Esperada:**
```json
{
  "status": "success",
  "total": 10,
  "streams": [
    {
      "id": 123,
      "stream_name": "exemplo",
      "status": "active",
      ...
    }
  ],
  "timestamp": "2025-01-XX..."
}
```

### 3. **Health Check Completo**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health
```

### 4. **Dashboard Principal**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/
```

## 🔧 **Variáveis de Ambiente no EasyPanel**

**Adicione estas variáveis no painel:**

```env
# PostgreSQL Externo (Streams)
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Conquista@@2
POSTGRES_DB=music_log
POSTGRES_PORT=5432
DB_TABLE_NAME=streams

# PostgreSQL Interno (Orchestrator)
DB_PASSWORD=MinhaSenh@Segura123!
SECRET_KEY=minha_chave_secreta_muito_longa_32_caracteres_ou_mais
DB_HOST=localhost
DB_NAME=orchestrator
DB_USER=orchestrator_user
REDIS_HOST=localhost
REDIS_PORT=6379
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
LOG_LEVEL=INFO
```

## 🚀 **Próximos Passos**

1. **Adicionar as variáveis** no EasyPanel
2. **Fazer redeploy** da aplicação
3. **Testar endpoints** conforme acima
4. **Verificar logs** para conexões

## 📋 **Checklist de Verificação**

- [ ] Variáveis PostgreSQL externo configuradas
- [ ] Endpoint `/postgres/test` funcionando
- [ ] Endpoint `/streams` retornando dados
- [ ] Logs mostrando conexão bem-sucedida
- [ ] Dashboard acessível

## 🎯 **Resultado Esperado**

Após a configuração, você terá:

- ✅ **Orchestrator interno** funcionando (localhost)
- ✅ **Conexão com streams** no PostgreSQL externo
- ✅ **Monitoramento** das streams em tempo real
- ✅ **APIs** para consultar dados das streams

**🚀 Configure as variáveis e teste os endpoints!**
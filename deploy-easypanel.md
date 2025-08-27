# 🚀 Deploy Orchestrator Atualizado no EasyPanel

## 📋 RESUMO DAS MUDANÇAS

✅ **Novos endpoints implementados:**
- `POST /api/workers/register` - Registrar workers FingerV7
- `POST /api/heartbeat` - Receber heartbeats dos workers
- `GET /api/workers` - Listar workers registrados
- `GET /api/streams/assign` - Atribuir streams para workers
- `POST /api/streams/update` - Atualizar status de processamento
- `GET /api/metrics` - Métricas do orchestrator

✅ **Testes locais aprovados:**
```
🎉 TODOS OS TESTES PASSARAM!
✅ Os novos endpoints estão funcionando
🚀 Pronto para deploy no EasyPanel
```

## 🔄 **PASSOS PARA DEPLOY**

### 1. **Fazer Backup do Código Atual**

No EasyPanel, faça backup do código atual:
```bash
# Conectar via SSH ou terminal do EasyPanel
cp -r /app /app_backup_$(date +%Y%m%d_%H%M%S)
```

### 2. **Atualizar o Código**

Substitua o arquivo `app/main_orchestrator.py` com a versão atualizada.

**Principais mudanças no arquivo:**
- Adicionados endpoints da API para workers
- Sistema de registro de workers em memória
- Sistema de atribuição de streams
- Métricas do orchestrator
- Correção do sistema de logs

### 3. **Verificar Variáveis de Ambiente**

No EasyPanel, certifique-se que estas variáveis estão configuradas:

```env
# PostgreSQL Externo (Streams) - JÁ CONFIGURADO
POSTGRES_HOST=104.234.173.96
POSTGRES_PORT=5432
POSTGRES_DB=music_log
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
DB_TABLE_NAME=streams

# Configurações do Servidor
ORCHESTRATOR_PORT=8000
ORCHESTRATOR_HOST=0.0.0.0
LOG_LEVEL=INFO

# Banco Interno (Opcional - para modo completo)
DB_HOST=localhost
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=MinhaSenh@Segura123!
```

### 4. **Reiniciar a Aplicação**

No EasyPanel:
1. Vá para a aba **"Deployments"**
2. Clique em **"Restart"** ou **"Redeploy"**
3. Aguarde a aplicação reiniciar

### 5. **Testar os Novos Endpoints**

Após o restart, teste os endpoints:

```bash
# 1. Health check
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# 2. Dashboard atualizado
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/

# 3. Testar registro de worker
curl -X POST https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers/register \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-worker-001",
    "worker_type": "fingerv7",
    "capacity": 5,
    "status": "active",
    "metadata": {"version": "7.0", "test": true}
  }'

# 4. Listar workers
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers

# 5. Testar heartbeat
curl -X POST https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "worker_instance_id": "test-worker-001",
    "status": "active",
    "current_load": 2,
    "available_capacity": 3,
    "metrics": {"cpu_usage": 45.2}
  }'

# 6. Testar atribuição de streams
curl "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/streams/assign?worker_id=test-worker-001&capacity=2"

# 7. Métricas da API
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

## ✅ **RESULTADO ESPERADO**

### **Dashboard Atualizado:**
```json
{
  "message": "Enhanced Stream Orchestrator",
  "version": "1.0.0",
  "status": "running",
  "endpoints": {
    "health": "/health",
    "metrics": "/metrics",
    "postgres_test": "/postgres/test",
    "streams": "/streams",
    "docs": "/docs",
    "api": {
      "workers_register": "/api/workers/register",
      "workers_list": "/api/workers",
      "heartbeat": "/api/heartbeat",
      "streams_assign": "/api/streams/assign",
      "streams_update": "/api/streams/update",
      "api_metrics": "/api/metrics"
    }
  }
}
```

### **Registro de Worker:**
```json
{
  "success": true,
  "worker_id": "test-worker-001",
  "message": "Worker registered successfully"
}
```

### **Lista de Workers:**
```json
{
  "workers": [
    {
      "instance_id": "test-worker-001",
      "worker_type": "fingerv7",
      "status": "active",
      "capacity": 5,
      "current_load": 2,
      "available_capacity": 3,
      "last_heartbeat": "2025-08-26T19:57:22.793805",
      "registered_at": "2025-08-26T19:57:22.793805"
    }
  ],
  "total": 1
}
```

### **Atribuição de Streams:**
```json
{
  "streams": [
    {
      "stream_id": "92",
      "id": 92,
      "stream_url": "http://cloud1.radyou.com.br/BANDABFMCWB",
      "url": "http://cloud1.radyou.com.br/BANDABFMCWB",
      "name": "Banda B FM Curitiba - PR",
      "metadata": {
        "cidade": "Curitiba",
        "estado": "PR",
        "regiao": "Sul",
        "segmento": "Popular",
        "frequencia": "89,7"
      }
    }
  ],
  "total": 1,
  "worker_id": "test-worker-001"
}
```

## 🔧 **TROUBLESHOOTING**

### **Se os endpoints retornarem 404:**
1. Verifique se o arquivo foi atualizado corretamente
2. Reinicie a aplicação no EasyPanel
3. Verifique os logs da aplicação

### **Se der erro 500:**
1. Verifique as variáveis de ambiente
2. Verifique os logs da aplicação
3. Teste a conexão com PostgreSQL: `/postgres/test`

### **Para verificar logs:**
No EasyPanel, vá para **"Logs"** e procure por:
- `✅ Worker registered`
- `💓 Heartbeat received`
- `📤 Assigned X streams`

## 🎯 **PRÓXIMOS PASSOS APÓS DEPLOY**

1. **Testar integração completa:**
   ```bash
   python test_fingerv7_integration.py
   ```

2. **Configurar instâncias FingerV7:**
   - Copiar `fingerv7_orchestrator_client.py`
   - Configurar variáveis de ambiente
   - Iniciar clientes

3. **Monitorar dashboard:**
   - Workers registrados
   - Streams sendo processados
   - Métricas em tempo real

## 🚀 **COMANDO RÁPIDO PARA TESTAR TUDO**

Após o deploy, execute:
```bash
python test_fingerv7_integration.py
```

**Se todos os testes passarem, a integração está pronta!**

---

## 📝 **CHECKLIST DE DEPLOY**

- [ ] Backup do código atual
- [ ] Atualizar `app/main_orchestrator.py`
- [ ] Verificar variáveis de ambiente
- [ ] Reiniciar aplicação no EasyPanel
- [ ] Testar health check
- [ ] Testar novos endpoints da API
- [ ] Executar teste de integração completo
- [ ] Configurar primeira instância FingerV7
- [ ] Monitorar logs e métricas

**🎉 Pronto para integrar as instâncias FingerV7!**
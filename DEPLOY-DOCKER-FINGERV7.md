# 🚀 Deploy FingerV7 + Orchestrator via Docker

## 📋 RESUMO DAS MUDANÇAS

✅ **Arquivos atualizados para integração:**
- `app/orchestrator_client.py` - Cliente atualizado para nova API
- `docker-compose.fingerv7.yaml` - Novas variáveis de ambiente
- `fingerv7-orchestrator.env.example` - Configuração de exemplo

✅ **Mantidos seus arquivos existentes:**
- `Dockerfilegit` - Dockerfile original (sem mudanças significativas)
- `app/fingerv7.py` - Código principal (será integrado automaticamente)

## 🔄 **DEPLOY EM DUAS FASES**

### **FASE 1: DEPLOY DO ORCHESTRATOR (EasyPanel)**

1. **Atualizar arquivo no EasyPanel:**
   - Substitua `app/main_orchestrator.py` com a versão atualizada
   - Reinicie a aplicação no EasyPanel

2. **Testar se funcionou:**
   ```bash
   curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
   ```
   
   **Deve retornar:** `{"workers": [], "total": 0}` (não mais 404)

### **FASE 2: DEPLOY DAS INSTÂNCIAS FINGERV7**

#### **Para cada instância FingerV7:**

1. **Atualizar arquivos:**
   ```bash
   # Fazer backup
   cp app/orchestrator_client.py app/orchestrator_client.py.backup
   cp docker-compose.fingerv7.yaml docker-compose.fingerv7.yaml.backup
   
   # Atualizar com versões novas
   # (copiar arquivos atualizados)
   ```

2. **Configurar variáveis de ambiente:**
   ```bash
   # Copiar arquivo de exemplo
   cp fingerv7-orchestrator.env.example .env
   
   # Editar para cada instância
   nano .env
   ```

3. **Configuração por instância:**

   **Instância 1:**
   ```env
   INSTANCE_ID=fingerv7-001
   WORKER_CAPACITY=8
   WORKER_REGION=brasil-sudeste
   ```

   **Instância 2:**
   ```env
   INSTANCE_ID=fingerv7-002
   WORKER_CAPACITY=5
   WORKER_REGION=brasil-sul
   ```

   **Instância 3 (com VPN):**
   ```env
   INSTANCE_ID=fingerv7-003
   WORKER_CAPACITY=3
   WORKER_REGION=brasil-nordeste
   # + configurações VPN
   ```

4. **Rebuild e restart:**
   ```bash
   # Parar containers
   docker-compose -f docker-compose.fingerv7.yaml down
   
   # Rebuild (para pegar código atualizado)
   docker-compose -f docker-compose.fingerv7.yaml build --no-cache
   
   # Iniciar novamente
   docker-compose -f docker-compose.fingerv7.yaml up -d
   ```

## 📊 **VERIFICAÇÃO DO DEPLOY**

### **1. Verificar Orchestrator:**
```bash
# Health check
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# Novos endpoints
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

### **2. Verificar Workers Registrados:**
```bash
# Deve mostrar suas instâncias
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
```

**Resultado esperado:**
```json
{
  "workers": [
    {
      "instance_id": "fingerv7-001",
      "worker_type": "fingerv7",
      "status": "active",
      "capacity": 8,
      "current_load": 3,
      "available_capacity": 5,
      "last_heartbeat": "2025-08-26T20:15:30.123456",
      "registered_at": "2025-08-26T20:10:15.654321"
    },
    {
      "instance_id": "fingerv7-002", 
      "worker_type": "fingerv7",
      "status": "active",
      "capacity": 5,
      "current_load": 2,
      "available_capacity": 3
    }
  ],
  "total": 2
}
```

### **3. Verificar Logs das Instâncias:**
```bash
# Ver logs de cada instância
docker-compose -f docker-compose.fingerv7.yaml logs finger_app

# Procurar por:
# "Cliente do orquestrador inicializado"
# "Instância fingerv7-001 registrada com sucesso"
# "Heartbeat enviado com sucesso"
# "Recebidos X streams do orquestrador"
```

### **4. Verificar Métricas:**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

**Resultado esperado:**
```json
{
  "orchestrator": {
    "status": "running",
    "timestamp": "2025-08-26T20:15:30.123456"
  },
  "workers": {
    "total": 3,
    "active": 3,
    "total_capacity": 16,
    "current_load": 8,
    "utilization_percent": 50.0
  },
  "streams": {
    "total_assignments": 25,
    "completed": 20,
    "failed": 1,
    "processing": 4,
    "success_rate": 95.2
  }
}
```

## 🔧 **TROUBLESHOOTING**

### **Problema: Worker não registra**
```bash
# Verificar logs
docker-compose -f docker-compose.fingerv7.yaml logs finger_app | grep -i orchestrator

# Verificar conectividade
docker-compose -f docker-compose.fingerv7.yaml exec finger_app curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# Verificar variáveis
docker-compose -f docker-compose.fingerv7.yaml exec finger_app env | grep -E "(ORCHESTRATOR|INSTANCE|WORKER)"
```

### **Problema: Não recebe streams**
```bash
# Verificar capacidade disponível
curl "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/streams/assign?worker_id=fingerv7-001&capacity=5"

# Verificar se há streams na base
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/streams
```

### **Problema: Heartbeat falha**
```bash
# Testar heartbeat manual
curl -X POST https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "worker_instance_id": "fingerv7-001",
    "status": "active",
    "current_load": 2,
    "available_capacity": 3
  }'
```

## 📁 **ARQUIVOS PARA COMMIT**

**Arquivos essenciais para o deploy via GitHub:**

### **Para o Orchestrator (EasyPanel):**
- `app/main_orchestrator.py` (atualizado)

### **Para as Instâncias FingerV7:**
- `app/orchestrator_client.py` (atualizado)
- `docker-compose.fingerv7.yaml` (atualizado)
- `fingerv7-orchestrator.env.example` (novo)
- `Dockerfilegit` (mantido)

### **Documentação:**
- `DEPLOY-DOCKER-FINGERV7.md` (este arquivo)

## 🎯 **ORDEM DE DEPLOY RECOMENDADA**

1. **✅ Commit e push dos arquivos atualizados**
2. **✅ Deploy orchestrator no EasyPanel**
3. **✅ Testar endpoints da API**
4. **✅ Deploy instância 1 (teste)**
5. **✅ Verificar se registrou e recebe streams**
6. **✅ Deploy demais instâncias**
7. **✅ Monitorar métricas e logs**

## 🎉 **RESULTADO FINAL**

Após o deploy completo, você terá:

- **Sistema distribuído** funcionando com seus Dockerfiles existentes
- **Load balancing automático** entre instâncias
- **Monitoramento em tempo real** via API
- **Escalabilidade** fácil adicionando mais instâncias
- **Compatibilidade** com sua infraestrutura Docker atual

**🚀 Pronto para orquestrar suas instâncias FingerV7!**
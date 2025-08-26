# 🐳 Deploy com Docker Compose - EasyPanel

## 📋 **ARQUIVOS DOCKER-COMPOSE PADRONIZADOS**

### **🎯 ORCHESTRATOR**
- **Sem VPN:** `docker-compose.orchestrator.simple.yaml` ← **RECOMENDADO**
- **Com VPN:** `docker-compose.orchestrator.yaml`

### **🎵 FINGERV7**
- **Com VPN:** `docker-compose.fingerv7.yaml` ← **PADRÃO**

---

## 🚀 **DEPLOY ORCHESTRATOR (EasyPanel)**

### **CENÁRIO 1: Orchestrator SEM VPN (Mais Comum)**

#### **1. Configuração no EasyPanel:**
- **Build Method:** Docker Compose
- **Docker Compose File:** `docker-compose.orchestrator.simple.yaml`
- **Port:** 8000

#### **2. Variáveis de Ambiente (.env):**
```env
# PostgreSQL INTERNO
DB_PASSWORD=MinhaSenh@Segura123!

# PostgreSQL EXTERNO
POSTGRES_HOST=104.234.173.96
POSTGRES_DB=music_log
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!

# Servidor
LOG_LEVEL=INFO
```

#### **3. Deploy:**
```bash
git add docker-compose.orchestrator.simple.yaml orchestrator.env.example
git commit -m "feat: Docker Compose para orchestrator"
git push origin main

# No EasyPanel: Deploy via Docker Compose
```

### **CENÁRIO 2: Orchestrator COM VPN (Se Necessário)**

#### **1. Configuração no EasyPanel:**
- **Build Method:** Docker Compose
- **Docker Compose File:** `docker-compose.orchestrator.yaml`
- **Port:** 8000
- **Profile:** `vpn` (ativar VPN)

#### **2. Variáveis de Ambiente (.env):**
```env
# PostgreSQL (mesmo do cenário 1)
DB_PASSWORD=MinhaSenh@Segura123!
POSTGRES_HOST=104.234.173.96
POSTGRES_DB=music_log
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!

# VPN
VPN_SERVICE_PROVIDER=protonvpn
VPN_TYPE=wireguard
SERVER_COUNTRIES=Brazil
WIREGUARD_PRIVATE_KEY=sua_chave_privada_aqui

# Network Mode para usar VPN
NETWORK_MODE=service:gluetun
```

---

## 🚀 **DEPLOY FINGERV7 (Cada Servidor)**

### **Configuração Padrão (COM VPN):**

#### **1. Configuração:**
- **Docker Compose File:** `docker-compose.fingerv7.yaml`
- **Dockerfile:** `Dockerfilegit`

#### **2. Variáveis por Servidor:**

**Servidor 1:**
```env
# Orchestrator
ORCHESTRATOR_URL=https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host
INSTANCE_ID=fingerv7-001
WORKER_CAPACITY=8
WORKER_REGION=brasil-sudeste

# PostgreSQL
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
POSTGRES_DB=music_log

# VPN
VPN_SERVICE_PROVIDER=protonvpn
VPN_TYPE=wireguard
SERVER_COUNTRIES=Brazil
WIREGUARD_PRIVATE_KEY=chave_servidor_1

# Outras
USE_ORCHESTRATOR=True
```

**Servidor 2:**
```env
# Orchestrator
ORCHESTRATOR_URL=https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host
INSTANCE_ID=fingerv7-002
WORKER_CAPACITY=5
WORKER_REGION=brasil-sul

# PostgreSQL (mesmo)
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
POSTGRES_DB=music_log

# VPN (diferente)
VPN_SERVICE_PROVIDER=protonvpn
VPN_TYPE=wireguard
SERVER_COUNTRIES=Brazil
WIREGUARD_PRIVATE_KEY=chave_servidor_2

# Outras
USE_ORCHESTRATOR=True
```

#### **3. Deploy:**
```bash
# Em cada servidor
git pull origin main
cp fingerv7-orchestrator.env.example .env
nano .env  # Configurar variáveis específicas

# Deploy
docker-compose -f docker-compose.fingerv7.yaml down
docker-compose -f docker-compose.fingerv7.yaml build --no-cache
docker-compose -f docker-compose.fingerv7.yaml up -d

# Logs
docker-compose -f docker-compose.fingerv7.yaml logs -f finger_app
```

---

## 🧪 **VALIDAÇÃO COMPLETA**

### **1. Testar Orchestrator:**
```bash
# Health check
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# Deve retornar:
{
  "status": "healthy",
  "timestamp": "2025-08-26T...",
  "system_status": {
    "database": "connected"
  }
}
```

### **2. Testar API:**
```bash
# Workers registrados
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers

# Métricas
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics

# Streams disponíveis
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/streams
```

### **3. Verificar Workers:**
```bash
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
      "current_load": 0,
      "available_capacity": 8,
      "last_heartbeat": "2025-08-26T...",
      "registered_at": "2025-08-26T..."
    },
    {
      "instance_id": "fingerv7-002",
      "worker_type": "fingerv7",
      "status": "active",
      "capacity": 5,
      "current_load": 0,
      "available_capacity": 5
    }
  ],
  "total": 2
}
```

### **4. Teste Automatizado:**
```bash
python test-deploy-fingerv7.py
```

---

## 📋 **VANTAGENS DO DOCKER COMPOSE**

### **✅ Orchestrator:**
- **Volumes persistentes** para dados e logs
- **Health checks** automáticos
- **Restart policies** configurados
- **VPN opcional** quando necessário
- **Configuração centralizada** via .env

### **✅ FingerV7:**
- **VPN integrada** com Gluetun
- **Dependências** gerenciadas automaticamente
- **Volumes** para segmentos de áudio
- **Network isolation** via VPN
- **Restart automático** em caso de falha

---

## 🎯 **COMANDOS RÁPIDOS**

### **Deploy Orchestrator (EasyPanel):**
```bash
# Docker Compose: docker-compose.orchestrator.simple.yaml
# Port: 8000
# Configurar .env com variáveis
```

### **Deploy FingerV7 (Servidores):**
```bash
git pull
cp fingerv7-orchestrator.env.example .env
nano .env  # INSTANCE_ID único + VPN
docker-compose -f docker-compose.fingerv7.yaml up -d --build
```

**🎉 Sistema completo com Docker Compose funcionando!**
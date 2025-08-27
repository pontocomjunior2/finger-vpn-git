# 🐳 Docker Setup Padronizado - Orchestrator + FingerV7

## 📋 **ARQUIVOS PADRONIZADOS**

### **🎯 ORCHESTRATOR (EasyPanel)**
- **Dockerfile:** `Dockerfile.orchestrator`
- **Docker Compose:** `docker-compose.orchestrator.simple.yaml` (sem VPN) ou `docker-compose.orchestrator.yaml` (com VPN)
- **Código:** `app/main_orchestrator.py`

### **🎵 FINGERV7 (Servidores)**
- **Dockerfile:** `Dockerfilegit`
- **Docker Compose:** `docker-compose.fingerv7.yaml`
- **Código:** `app/orchestrator_client.py`

---

## 🚀 **DEPLOY ORCHESTRATOR (EasyPanel)**

### **OPÇÃO A: Docker Compose (RECOMENDADO)**

#### **1. Configuração no EasyPanel:**
- **Build Method:** Docker Compose
- **Docker Compose Path:** `docker-compose.orchestrator.simple.yaml` (sem VPN)
- **Port:** 8000

#### **2. Para usar VPN (se necessário):**
- **Docker Compose Path:** `docker-compose.orchestrator.yaml`
- **Profile:** `vpn` (ativar VPN)

### **OPÇÃO B: Dockerfile Simples**

#### **1. Configuração no EasyPanel:**
- **Build Method:** Dockerfile
- **Dockerfile Path:** `Dockerfile.orchestrator`
- **Port:** 8000

### **2. Variáveis de Ambiente:**
```env
# PostgreSQL INTERNO (Orchestrator)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=MinhaSenh@Segura123!

# PostgreSQL EXTERNO (Streams)
POSTGRES_HOST=104.234.173.96
POSTGRES_PORT=5432
POSTGRES_DB=music_log
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
DB_TABLE_NAME=streams

# Servidor
ORCHESTRATOR_PORT=8000
ORCHESTRATOR_HOST=0.0.0.0
LOG_LEVEL=INFO
```

### **3. Deploy:**
```bash
# Commit código atualizado
git add Dockerfile.orchestrator app/main_orchestrator.py
git commit -m "feat: Orchestrator com PostgreSQL interno corrigido"
git push origin main

# No EasyPanel: Deploy via interface
```

---

## 🚀 **DEPLOY FINGERV7 (Cada Servidor)**

### **1. Atualizar Código:**
```bash
git pull origin main
```

### **2. Configurar Variáveis (.env):**

**Servidor 1:**
```env
# Orchestrator
ORCHESTRATOR_URL=https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host
INSTANCE_ID=fingerv7-001
WORKER_CAPACITY=8
WORKER_REGION=brasil-sudeste

# PostgreSQL (mesmo para todos)
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
POSTGRES_DB=music_log

# Outras configurações
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

# VPN (se necessário)
VPN_SERVICE_PROVIDER=protonvpn
WIREGUARD_PRIVATE_KEY=sua_chave_aqui

# Outras configurações
USE_ORCHESTRATOR=True
```

### **3. Deploy:**
```bash
# Parar containers
docker-compose -f docker-compose.fingerv7.yaml down

# Rebuild
docker-compose -f docker-compose.fingerv7.yaml build --no-cache

# Iniciar
docker-compose -f docker-compose.fingerv7.yaml up -d

# Verificar logs
docker-compose -f docker-compose.fingerv7.yaml logs -f finger_app
```

---

## 🧪 **VALIDAÇÃO DO DEPLOY**

### **1. Testar Orchestrator:**
```bash
# Health check
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# API endpoints
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

### **2. Verificar Workers:**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
```

**Deve mostrar:**
```json
{
  "workers": [
    {
      "instance_id": "fingerv7-001",
      "worker_type": "fingerv7",
      "status": "active",
      "capacity": 8,
      "current_load": 0,
      "available_capacity": 8
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

### **3. Teste Automatizado:**
```bash
python test-deploy-fingerv7.py
```

---

## 📁 **ARQUIVOS FINAIS PARA COMMIT**

### **Essenciais:**
```
# Orchestrator
Dockerfile.orchestrator                    # ✅ Orchestrator Dockerfile
docker-compose.orchestrator.simple.yaml   # ✅ Orchestrator sem VPN
docker-compose.orchestrator.yaml          # ✅ Orchestrator com VPN
orchestrator.env.example                  # ✅ Configuração orchestrator

# FingerV7
Dockerfilegit                             # ✅ FingerV7 Dockerfile
docker-compose.fingerv7.yaml             # ✅ FingerV7 com VPN
fingerv7-orchestrator.env.example        # ✅ Configuração FingerV7

# Código
app/main_orchestrator.py                 # ✅ Código orchestrator
app/orchestrator_client.py              # ✅ Cliente atualizado

# Validação
test-deploy-fingerv7.py                  # ✅ Teste deploy
```

### **Documentação:**
```
DOCKER-PADRONIZADO.md               # ✅ Este guia
DEPLOY-DOCKER-FINGERV7.md          # ✅ Guia detalhado
```

---

## 🎯 **COMANDOS RÁPIDOS**

### **Deploy Orchestrator:**
```bash
# OPÇÃO A: Docker Compose (Recomendado)
# EasyPanel: docker-compose.orchestrator.simple.yaml, Port 8000

# OPÇÃO B: Dockerfile
# EasyPanel: Dockerfile.orchestrator, Port 8000
```

### **Deploy FingerV7:**
```bash
git pull
cp fingerv7-orchestrator.env.example .env
nano .env  # Configurar INSTANCE_ID único
docker-compose -f docker-compose.fingerv7.yaml down
docker-compose -f docker-compose.fingerv7.yaml build --no-cache
docker-compose -f docker-compose.fingerv7.yaml up -d
```

**🎉 Sistema distribuído padronizado e funcionando!**
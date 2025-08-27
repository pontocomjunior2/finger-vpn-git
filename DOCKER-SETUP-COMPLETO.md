# 🐳 Setup Docker Completo - Orchestrator + FingerV7

## 📋 **VISÃO GERAL DOS COMPONENTES**

Você tem **2 componentes principais** que precisam de deploy separado:

1. **🎯 ORCHESTRATOR** - Gerencia e distribui streams (EasyPanel)
2. **🎵 FINGERV7** - Processa streams de áudio (Servidores individuais)

## 🎯 **COMPONENT 1: ORCHESTRATOR (EasyPanel)**

### **Arquivos para usar:**

#### **📁 Dockerfile: `Dockerfile.orchestrator`**
```dockerfile
# =============================================================================
# DOCKERFILE SIMPLIFICADO PARA EASYPANEL
# =============================================================================

FROM python:3.11-slim

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    postgresql \
    postgresql-client \
    postgresql-contrib \
    redis-server \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Configurar diretório da aplicação
WORKDIR /app

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/data /var/lib/postgresql/data /var/run/postgresql

# Configurar PostgreSQL
RUN chown -R postgres:postgres /var/lib/postgresql/ /var/run/postgresql/
RUN chmod 755 /var/run/postgresql

# Inicializar banco PostgreSQL
USER postgres
RUN /usr/lib/postgresql/*/bin/initdb -D /var/lib/postgresql/data --encoding=UTF-8 --locale=C
RUN echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf
RUN echo "listen_addresses='*'" >> /var/lib/postgresql/data/postgresql.conf
RUN echo "port = 5432" >> /var/lib/postgresql/data/postgresql.conf

USER root

# Copiar script de inicialização
COPY scripts/start-services.sh /app/start-services.sh
RUN chmod +x /app/start-services.sh

# Expor porta da aplicação
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
CMD ["/app/start-services.sh"]
```

#### **📁 Docker Compose: NÃO USAR**
❌ **O EasyPanel não usa docker-compose**
✅ **EasyPanel usa apenas o Dockerfile.easypanel**

### **🚀 Deploy no EasyPanel:**

1. **Configurar no EasyPanel:**
   - **Build Method:** Dockerfile
   - **Dockerfile Path:** `Dockerfile.easypanel`
   - **Port:** 8000

2. **Variáveis de Ambiente no EasyPanel:**
   ```env
   # PostgreSQL Externo (Streams)
   POSTGRES_HOST=104.234.173.96
   POSTGRES_PORT=5432
   POSTGRES_DB=music_log
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=Mudar123!
   DB_TABLE_NAME=streams

   # Banco Interno (Orchestrator)
   DB_HOST=localhost
   DB_NAME=orchestrator
   DB_USER=orchestrator_user
   DB_PASSWORD=MinhaSenh@Segura123!

   # Servidor
   ORCHESTRATOR_PORT=8000
   ORCHESTRATOR_HOST=0.0.0.0
   LOG_LEVEL=INFO
   ```

---

## 🎵 **COMPONENT 2: FINGERV7 (Servidores Individuais)**

### **Arquivos para usar:**

#### **📁 Dockerfile: `Dockerfilegit`**
```dockerfile
# Dockerfile otimizado para deploy GitHub via EasyPanel
FROM python:3.11-slim-bookworm

# Instalar dependências do sistema: ffmpeg (essencial) e ca-certificates (para HTTPS)
# Limpar cache do apt para reduzir o tamanho da imagem
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Definir o diretório de trabalho dentro do container
WORKDIR /app

# Copiar apenas o arquivo de dependências primeiro para aproveitar o cache do Docker
COPY app/requirements.txt .

# Instalar as dependências Python
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar somente o necessário para o worker
COPY app/fingerv7.py .
COPY app/db_pool.py .
COPY app/async_queue.py .
COPY app/orchestrator_client.py .
COPY app/__init__.py .

# Criar usuário não-root e permissões para a aplicação
RUN adduser --disabled-password --gecos "" appuser && \
    mkdir -p /app/segments && \
    chown -R appuser:appuser /app

# Saída sem buffer para logs em tempo real
ENV PYTHONUNBUFFERED=1

# Executar como usuário não-root
USER appuser

# Comando de inicialização da aplicação
CMD ["python", "fingerv7.py"]
```

#### **📁 Docker Compose: `docker-compose.fingerv7.yaml`**
```yaml
# docker-compose.yaml específico para instâncias fingerv7 no EasyPanel
# Este arquivo NÃO inclui o orquestrador - apenas a instância fingerv7
# Use este arquivo quando o orquestrador já estiver rodando em outro projeto
services:
  gluetun:
    image: qmcgaw/gluetun:latest
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    volumes:
      - gluetun_data:/gluetun
    environment:
      - VPN_SERVICE_PROVIDER=${VPN_SERVICE_PROVIDER:-protonvpn}
      - VPN_TYPE=${VPN_TYPE:-wireguard}
      - SERVER_COUNTRIES=${SERVER_COUNTRIES:-Brazil}
      - WIREGUARD_PRIVATE_KEY=${WIREGUARD_PRIVATE_KEY}
      - OPENVPN_USER=${VPN_USER}
      - OPENVPN_PASSWORD=${VPN_PASSWORD}
      - TZ=${TZ:-America/Sao_Paulo}
    healthcheck:
      test: ["CMD", "/gluetun-entrypoint", "healthcheck"]
      interval: 20s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: unless-stopped

  finger_app:
    # BUILD LOCAL: EasyPanel irá construir a imagem a partir do Dockerfile na raiz
    build:
      context: .
      dockerfile: Dockerfilegit
    network_mode: "service:gluetun"
    depends_on:
      gluetun:
        condition: service_healthy
    volumes:
      - app_segments:/app/segments
    environment:
      # --- Variáveis da Aplicação (Definidas no EasyPanel) ---
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_PORT=${POSTGRES_PORT:-5432}
      - DB_TABLE_NAME=${DB_TABLE_NAME:-music_log}
      - SERVER_ID=${SERVER_ID:-1}
      - TOTAL_SERVERS=${TOTAL_SERVERS:-1}
      - DISTRIBUTE_LOAD=${DISTRIBUTE_LOAD:-False}
      - ENABLE_ROTATION=${ENABLE_ROTATION:-False}
      - ROTATION_HOURS=${ROTATION_HOURS:-24}
      - IDENTIFICATION_DURATION=${IDENTIFICATION_DURATION:-15}
      - DUPLICATE_PREVENTION_WINDOW_SECONDS=${DUPLICATE_PREVENTION_WINDOW_SECONDS:-900}
      - SEGMENTS_DIR=/app/segments
      - PYTHONUNBUFFERED=1
      - TZ=${TZ:-America/Sao_Paulo}
      # --- Redis (Heartbeats em tempo real) ---
      - REDIS_URL=${REDIS_URL}
      - REDIS_CHANNEL=${REDIS_CHANNEL:-smf:server_heartbeats}
      - REDIS_KEY_PREFIX=${REDIS_KEY_PREFIX:-smf:server}
      - REDIS_HEARTBEAT_TTL_SECS=${REDIS_HEARTBEAT_TTL_SECS:-60}
      # --- Orquestrador Central (Nova API) ---
      - USE_ORCHESTRATOR=${USE_ORCHESTRATOR:-True}
      - ORCHESTRATOR_URL=${ORCHESTRATOR_URL}
      - INSTANCE_ID=${INSTANCE_ID}
      - WORKER_INSTANCE_ID=${INSTANCE_ID}
      - WORKER_TYPE=fingerv7
      - WORKER_CAPACITY=${WORKER_CAPACITY:-5}
      - WORKER_REGION=${WORKER_REGION:-brasil}
      - HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-30}
      - MAX_CONCURRENT_STREAMS=${MAX_CONCURRENT_STREAMS:-5}
      - STREAM_TIMEOUT=${STREAM_TIMEOUT:-300}
      - RETRY_ATTEMPTS=${RETRY_ATTEMPTS:-3}
    restart: unless-stopped

volumes:
  gluetun_data:
  app_segments:
```

---

## 🚀 **PASSO A PASSO COMPLETO DE DEPLOY**

### **ETAPA 1: DEPLOY ORCHESTRATOR (EasyPanel)**

#### **1.1 Preparar Código:**
```bash
# Fazer commit das mudanças
git add app/main_orchestrator.py
git commit -m "feat: Adiciona API endpoints para workers"
git push origin main
```

#### **1.2 Configurar no EasyPanel:**
1. **Projeto:** Seu projeto do orchestrator
2. **Source:** GitHub repository
3. **Build Method:** Dockerfile
4. **Dockerfile:** `Dockerfile.orchestrator`
5. **Port:** 8000

#### **1.3 Variáveis de Ambiente:**
```env
# PostgreSQL Externo
POSTGRES_HOST=104.234.173.96
POSTGRES_PORT=5432
POSTGRES_DB=music_log
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
DB_TABLE_NAME=streams

# Banco Interno
DB_HOST=localhost
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=MinhaSenh@Segura123!

# Servidor
ORCHESTRATOR_PORT=8000
ORCHESTRATOR_HOST=0.0.0.0
LOG_LEVEL=INFO
```

#### **1.4 Deploy:**
1. Clicar **"Deploy"**
2. Aguardar build
3. Testar: `curl https://seu-dominio.com/api/workers`

---

### **ETAPA 2: DEPLOY FINGERV7 (Cada Servidor)**

#### **2.1 Preparar Código em Cada Servidor:**
```bash
# Atualizar código
git pull origin main

# Verificar arquivos atualizados
ls -la app/orchestrator_client.py
ls -la docker-compose.fingerv7.yaml
ls -la Dockerfilegit
```

#### **2.2 Configurar Variáveis (.env):**

**Servidor 1:**
```bash
cp fingerv7-orchestrator.env.example .env
nano .env
```

```env
# Configuração Servidor 1
ORCHESTRATOR_URL=https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host
INSTANCE_ID=fingerv7-001
WORKER_CAPACITY=8
WORKER_REGION=brasil-sudeste

# PostgreSQL
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Mudar123!
POSTGRES_DB=music_log

# Outras configurações...
USE_ORCHESTRATOR=True
```

**Servidor 2:**
```env
# Configuração Servidor 2
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
```

#### **2.3 Deploy em Cada Servidor:**
```bash
# Parar containers
docker-compose -f docker-compose.fingerv7.yaml down

# Rebuild (pegar código atualizado)
docker-compose -f docker-compose.fingerv7.yaml build --no-cache

# Iniciar
docker-compose -f docker-compose.fingerv7.yaml up -d

# Verificar logs
docker-compose -f docker-compose.fingerv7.yaml logs -f finger_app
```

---

## 🔍 **VERIFICAÇÃO DO DEPLOY**

### **1. Testar Orchestrator:**
```bash
# Health check
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# API endpoints
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

### **2. Verificar Workers Registrados:**
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

### **3. Verificar Logs:**
```bash
# Em cada servidor FingerV7
docker-compose -f docker-compose.fingerv7.yaml logs finger_app | grep -i orchestrator

# Procurar por:
# "Cliente do orquestrador inicializado"
# "Instância fingerv7-001 registrada com sucesso"
# "Heartbeat enviado com sucesso"
```

### **4. Teste Automatizado:**
```bash
python test-deploy-fingerv7.py
```

---

## 📋 **RESUMO DOS ARQUIVOS**

### **Para Orchestrator (EasyPanel):**
- ✅ **Dockerfile:** `Dockerfile.orchestrator`
- ❌ **Docker Compose:** Não usar (EasyPanel não suporta)
- ✅ **Código:** `app/main_orchestrator.py`

### **Para FingerV7 (Servidores):**
- ✅ **Dockerfile:** `Dockerfilegit`
- ✅ **Docker Compose:** `docker-compose.fingerv7.yaml`
- ✅ **Código:** `app/orchestrator_client.py`
- ✅ **Config:** `.env` (baseado em `fingerv7-orchestrator.env.example`)

## 🎯 **COMANDOS RÁPIDOS**

### **Deploy Orchestrator:**
```bash
# No EasyPanel: Deploy via interface web
# Usar Dockerfile.easypanel
```

### **Deploy FingerV7:**
```bash
# Em cada servidor
git pull
cp fingerv7-orchestrator.env.example .env
nano .env  # Configurar INSTANCE_ID único
docker-compose -f docker-compose.fingerv7.yaml down
docker-compose -f docker-compose.fingerv7.yaml build --no-cache
docker-compose -f docker-compose.fingerv7.yaml up -d
```

**🎉 Pronto! Sistema distribuído funcionando!**
# 🧪 Teste de Integração - FingerV7 + Orchestrator

## 🎯 TESTE RÁPIDO

### 1. **Primeiro: Configurar Orchestrator**

No EasyPanel, adicione as variáveis e reinicie:

```env
DB_HOST=localhost
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=MinhaSenh@Segura123!
SECRET_KEY=minha_chave_secreta_muito_longa_32_caracteres_ou_mais
REDIS_HOST=localhost
```

### 2. **Testar Orchestrator**

```bash
# Health check
curl https://seu-dominio.com/health

# Deve retornar:
{
  "status": "healthy",
  "database": "connected"
}
```

### 3. **Teste Manual de Registro**

Teste registrar um worker manualmente:

```bash
curl -X POST https://seu-dominio.com/api/workers/register \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-worker-001",
    "worker_type": "fingerv7",
    "capacity": 5,
    "status": "active",
    "metadata": {
      "version": "7.0",
      "region": "test"
    }
  }'
```

### 4. **Verificar Workers**

```bash
curl https://seu-dominio.com/api/workers
```

### 5. **Teste de Heartbeat**

```bash
curl -X POST https://seu-dominio.com/api/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "worker_instance_id": "test-worker-001",
    "status": "active",
    "current_load": 2,
    "available_capacity": 3,
    "metrics": {
      "cpu_usage": 45.2,
      "memory_usage": 67.8
    }
  }'
```

## 🔧 SCRIPT DE TESTE SIMPLES

Crie um arquivo `test_integration.py`:

```python
import asyncio
import aiohttp
import json

async def test_orchestrator():
    orchestrator_url = "https://seu-dominio.com"  # ALTERE AQUI
    
    async with aiohttp.ClientSession() as session:
        
        # 1. Testar health
        print("🔍 Testando health...")
        async with session.get(f"{orchestrator_url}/health") as resp:
            health = await resp.json()
            print(f"Health: {health}")
            
        # 2. Registrar worker de teste
        print("📝 Registrando worker de teste...")
        worker_data = {
            "instance_id": "test-fingerv7-001",
            "worker_type": "fingerv7",
            "capacity": 5,
            "status": "active",
            "metadata": {"version": "7.0", "test": True}
        }
        
        async with session.post(
            f"{orchestrator_url}/api/workers/register",
            json=worker_data
        ) as resp:
            print(f"Registro: {resp.status}")
            if resp.status == 200:
                result = await resp.json()
                print(f"Resultado: {result}")
                
        # 3. Listar workers
        print("👥 Listando workers...")
        async with session.get(f"{orchestrator_url}/api/workers") as resp:
            workers = await resp.json()
            print(f"Workers: {workers}")
            
        # 4. Enviar heartbeat
        print("💓 Enviando heartbeat...")
        heartbeat_data = {
            "worker_instance_id": "test-fingerv7-001",
            "status": "active",
            "current_load": 1,
            "available_capacity": 4,
            "metrics": {"cpu_usage": 30.5, "memory_usage": 45.2}
        }
        
        async with session.post(
            f"{orchestrator_url}/api/heartbeat",
            json=heartbeat_data
        ) as resp:
            print(f"Heartbeat: {resp.status}")

if __name__ == "__main__":
    asyncio.run(test_orchestrator())
```

Execute:
```bash
python test_integration.py
```

## ✅ RESULTADO ESPERADO

```
🔍 Testando health...
Health: {'status': 'healthy', 'database': 'connected'}

📝 Registrando worker de teste...
Registro: 200
Resultado: {'success': True, 'worker_id': 'test-fingerv7-001'}

👥 Listando workers...
Workers: {'workers': [{'instance_id': 'test-fingerv7-001', 'status': 'active'}]}

💓 Enviando heartbeat...
Heartbeat: 200
```

## 🚨 SE DER ERRO

### Erro 500 - Internal Server Error
- Verifique se as variáveis de ambiente estão configuradas
- Reinicie a aplicação no EasyPanel

### Erro de Conexão
- Verifique se o domínio está correto
- Teste o health check primeiro

### Database Error
- Verifique se `DB_HOST=localhost` está configurado
- Verifique se `DB_PASSWORD` está definido

## 🎉 PRÓXIMO PASSO

Se os testes passarem, você pode:
1. **Integrar** o código nas instâncias FingerV7 reais
2. **Configurar** múltiplos workers
3. **Monitorar** no dashboard

**🚀 Teste primeiro, depois integre!**
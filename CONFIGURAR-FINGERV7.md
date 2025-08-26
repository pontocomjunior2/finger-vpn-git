# 🔗 Configurar FingerV7 com Orchestrator

## 📋 VISÃO GERAL

Agora que o Orchestrator está rodando, precisamos configurar as instâncias FingerV7 para:
1. **Registrar-se** no orchestrator
2. **Receber streams** para processar
3. **Enviar heartbeats** e métricas

## 🔧 CONFIGURAÇÃO DAS INSTÂNCIAS FINGERV7

### 1. **Variáveis de Ambiente para FingerV7**

Adicione estas variáveis em cada instância FingerV7:

```env
# Orchestrator Configuration
ORCHESTRATOR_URL=https://seu-dominio-orchestrator.com
ORCHESTRATOR_API_KEY=sua_chave_api_opcional

# Worker Configuration  
WORKER_INSTANCE_ID=fingerv7-001  # Único para cada instância
WORKER_TYPE=fingerv7
WORKER_CAPACITY=10  # Quantos streams simultâneos
WORKER_REGION=us-east-1  # Ou sua região

# Heartbeat Configuration
HEARTBEAT_INTERVAL=30  # Segundos
HEARTBEAT_TIMEOUT=120  # Segundos

# Performance Configuration
MAX_CONCURRENT_STREAMS=10
STREAM_TIMEOUT=300
RETRY_ATTEMPTS=3
```

### 2. **Código para Integração FingerV7**

Crie um arquivo `orchestrator_client.py` em cada FingerV7:

```python
import asyncio
import aiohttp
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

class OrchestratorClient:
    def __init__(self):
        self.orchestrator_url = os.getenv('ORCHESTRATOR_URL')
        self.worker_id = os.getenv('WORKER_INSTANCE_ID')
        self.worker_type = os.getenv('WORKER_TYPE', 'fingerv7')
        self.capacity = int(os.getenv('WORKER_CAPACITY', '10'))
        self.heartbeat_interval = int(os.getenv('HEARTBEAT_INTERVAL', '30'))
        self.session = None
        self.running = False
        
    async def start(self):
        """Iniciar cliente do orchestrator"""
        self.session = aiohttp.ClientSession()
        self.running = True
        
        # Registrar worker
        await self.register_worker()
        
        # Iniciar heartbeat
        asyncio.create_task(self.heartbeat_loop())
        
        # Iniciar polling de streams
        asyncio.create_task(self.stream_polling_loop())
        
    async def stop(self):
        """Parar cliente do orchestrator"""
        self.running = False
        if self.session:
            await self.session.close()
            
    async def register_worker(self):
        """Registrar worker no orchestrator"""
        try:
            data = {
                "instance_id": self.worker_id,
                "worker_type": self.worker_type,
                "capacity": self.capacity,
                "status": "active",
                "metadata": {
                    "version": "7.0",
                    "capabilities": ["stream_processing", "fingerprinting"],
                    "region": os.getenv('WORKER_REGION', 'default')
                }
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/workers/register",
                json=data
            ) as response:
                if response.status == 200:
                    print(f"✅ Worker {self.worker_id} registrado com sucesso")
                else:
                    print(f"❌ Erro ao registrar worker: {response.status}")
                    
        except Exception as e:
            print(f"❌ Erro na conexão com orchestrator: {e}")
            
    async def heartbeat_loop(self):
        """Loop de heartbeat"""
        while self.running:
            try:
                await self.send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                print(f"❌ Erro no heartbeat: {e}")
                await asyncio.sleep(5)
                
    async def send_heartbeat(self):
        """Enviar heartbeat para orchestrator"""
        try:
            data = {
                "worker_instance_id": self.worker_id,
                "status": "active",
                "current_load": self.get_current_load(),
                "available_capacity": self.get_available_capacity(),
                "metrics": self.get_metrics(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/heartbeat",
                json=data
            ) as response:
                if response.status != 200:
                    print(f"⚠️ Heartbeat falhou: {response.status}")
                    
        except Exception as e:
            print(f"❌ Erro ao enviar heartbeat: {e}")
            
    async def stream_polling_loop(self):
        """Loop para buscar novos streams"""
        while self.running:
            try:
                await self.poll_for_streams()
                await asyncio.sleep(5)  # Poll a cada 5 segundos
            except Exception as e:
                print(f"❌ Erro no polling: {e}")
                await asyncio.sleep(10)
                
    async def poll_for_streams(self):
        """Buscar novos streams para processar"""
        try:
            params = {
                "worker_id": self.worker_id,
                "capacity": self.get_available_capacity()
            }
            
            async with self.session.get(
                f"{self.orchestrator_url}/api/streams/assign",
                params=params
            ) as response:
                if response.status == 200:
                    streams = await response.json()
                    for stream in streams.get('streams', []):
                        asyncio.create_task(self.process_stream(stream))
                        
        except Exception as e:
            print(f"❌ Erro ao buscar streams: {e}")
            
    async def process_stream(self, stream_data: Dict[str, Any]):
        """Processar um stream"""
        stream_id = stream_data.get('stream_id')
        
        try:
            # Notificar início do processamento
            await self.update_stream_status(stream_id, "processing")
            
            # AQUI: Integrar com seu código FingerV7 existente
            result = await self.fingerv7_process_stream(stream_data)
            
            # Notificar conclusão
            await self.update_stream_status(stream_id, "completed", result)
            
        except Exception as e:
            print(f"❌ Erro ao processar stream {stream_id}: {e}")
            await self.update_stream_status(stream_id, "failed", {"error": str(e)})
            
    async def fingerv7_process_stream(self, stream_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        INTEGRAR COM SEU CÓDIGO FINGERV7 AQUI
        
        Esta função deve:
        1. Pegar os dados do stream
        2. Processar com FingerV7
        3. Retornar os resultados
        """
        # Exemplo de integração:
        stream_url = stream_data.get('stream_url')
        
        # Simular processamento (substitua pelo seu código)
        await asyncio.sleep(2)
        
        return {
            "fingerprint": "exemplo_fingerprint_123",
            "metadata": {"duration": 120, "quality": "high"},
            "processed_at": datetime.utcnow().isoformat()
        }
        
    async def update_stream_status(self, stream_id: str, status: str, result: Optional[Dict] = None):
        """Atualizar status do stream"""
        try:
            data = {
                "stream_id": stream_id,
                "worker_instance_id": self.worker_id,
                "status": status,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/streams/update",
                json=data
            ) as response:
                if response.status != 200:
                    print(f"⚠️ Erro ao atualizar stream: {response.status}")
                    
        except Exception as e:
            print(f"❌ Erro ao atualizar status: {e}")
            
    def get_current_load(self) -> int:
        """Retornar carga atual (número de streams sendo processados)"""
        # Implementar baseado no seu sistema
        return 0
        
    def get_available_capacity(self) -> int:
        """Retornar capacidade disponível"""
        return self.capacity - self.get_current_load()
        
    def get_metrics(self) -> Dict[str, Any]:
        """Retornar métricas do worker"""
        return {
            "cpu_usage": 45.2,
            "memory_usage": 67.8,
            "processed_streams": 150,
            "failed_streams": 2,
            "uptime_seconds": time.time()
        }

# Uso no seu FingerV7
async def main():
    client = OrchestratorClient()
    
    try:
        await client.start()
        print(f"🚀 FingerV7 conectado ao orchestrator")
        
        # Manter rodando
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("🛑 Parando FingerV7...")
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. **Integração no FingerV7 Existente**

No seu código principal do FingerV7, adicione:

```python
# No início do seu main.py
from orchestrator_client import OrchestratorClient

# Inicializar cliente
orchestrator = OrchestratorClient()

# No startup
await orchestrator.start()

# No shutdown  
await orchestrator.stop()
```

## 🚀 PRÓXIMOS PASSOS

1. **Configure as variáveis** de ambiente no orchestrator
2. **Reinicie** o orchestrator no EasyPanel
3. **Adicione o código** de integração nas instâncias FingerV7
4. **Configure as variáveis** de ambiente em cada FingerV7
5. **Inicie** as instâncias FingerV7

## 📊 MONITORAMENTO

Após configurar, você pode monitorar em:
- **Dashboard**: https://seu-dominio.com/
- **Workers**: https://seu-dominio.com/api/workers
- **Streams**: https://seu-dominio.com/api/streams
- **Métricas**: https://seu-dominio.com/api/metrics

**🎉 Pronto! Suas instâncias FingerV7 estarão conectadas ao orchestrator!**
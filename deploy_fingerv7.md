# 🚀 Deploy FingerV7 com Orchestrator

## 📋 GUIA COMPLETO DE IMPLEMENTAÇÃO

### 1. **PREPARAÇÃO DOS ARQUIVOS**

Você já tem os arquivos necessários:
- `fingerv7_orchestrator_client.py` - Cliente principal
- `fingerv7_config.env` - Configurações
- `test_fingerv7_integration.py` - Testes

### 2. **EXECUTAR TESTES PRIMEIRO**

Antes de implementar, vamos testar se tudo está funcionando:

```bash
# Instalar dependências
pip install aiohttp psutil

# Executar teste de integração
python test_fingerv7_integration.py
```

**Resultado esperado:**
```
🧪 TESTE DE INTEGRAÇÃO FINGERV7 + ORCHESTRATOR
============================================================

🔍 TESTANDO ENDPOINTS BÁSICOS
========================================

📡 Health Check: /health
   Status: 200
   Status: limited
   ✅ OK

📡 Dashboard: /
   Status: 200
   ✅ OK

📡 Lista de Streams: /streams
   Status: 200
   Streams: 86
   ✅ OK

📡 Teste PostgreSQL: /postgres/test
   Status: 200
   DB: music_log
   Streams: 86
   ✅ OK

============================================================

🧪 INICIANDO TESTES DE INTEGRAÇÃO FINGERV7
==================================================

🔍 Testando health do orchestrator...
✅ Health: limited
✅ Orchestrator está funcionando

📝 Testando registro de worker...
📊 Status: 200
✅ Worker registrado: {'success': True, 'worker_id': 'test-fingerv7-xxx'}

💓 Testando heartbeat...
📊 Status: 200
✅ Heartbeat enviado com sucesso

🎵 Testando atribuição de streams...
📊 Status: 200
✅ Streams recebidos: 10
📋 Exemplo de stream:
   ID: 92
   URL: http://cloud1.radyou.com.br/BANDABFMCWB
   Nome: Banda B FM Curitiba - PR

📊 Testando atualização de stream...
📊 Status: 200
✅ Status do stream atualizado

👥 Testando listagem de workers...
📊 Status: 200
✅ Workers encontrados: 1
✅ Worker de teste encontrado: test-fingerv7-xxx

🧹 Limpando worker de teste...
📭 Endpoint de remoção não implementado (normal)

🎉 TESTES CONCLUÍDOS!
```

### 3. **CONFIGURAR INSTÂNCIAS FINGERV7**

Para cada instância FingerV7:

#### **3.1 Copiar Arquivos**

```bash
# Copiar para cada instância FingerV7
scp fingerv7_orchestrator_client.py usuario@fingerv7-001:/path/to/fingerv7/
scp fingerv7_config.env usuario@fingerv7-001:/path/to/fingerv7/
```

#### **3.2 Configurar Variáveis de Ambiente**

Edite `fingerv7_config.env` para cada instância:

**Instância 1:**
```env
WORKER_INSTANCE_ID=fingerv7-001
WORKER_CAPACITY=5
WORKER_REGION=brasil-sul
```

**Instância 2:**
```env
WORKER_INSTANCE_ID=fingerv7-002
WORKER_CAPACITY=3
WORKER_REGION=brasil-sudeste
```

**Instância 3:**
```env
WORKER_INSTANCE_ID=fingerv7-003
WORKER_CAPACITY=8
WORKER_REGION=brasil-nordeste
```

#### **3.3 Instalar Dependências**

Em cada instância:
```bash
pip install aiohttp psutil
```

### 4. **INTEGRAR COM CÓDIGO FINGERV7 EXISTENTE**

#### **4.1 Modificar seu main.py do FingerV7**

```python
# No início do arquivo
import os
import asyncio
from fingerv7_orchestrator_client import FingerV7OrchestratorClient

# Carregar configurações
from dotenv import load_dotenv
load_dotenv('fingerv7_config.env')

class FingerV7Enhanced:
    def __init__(self):
        # Seu código FingerV7 existente
        self.setup_fingerv7()
        
        # Adicionar cliente do orchestrator
        self.orchestrator_client = FingerV7OrchestratorClient()
        
    def setup_fingerv7(self):
        """Seu código de setup existente"""
        pass
        
    async def start(self):
        """Iniciar FingerV7 com orchestrator"""
        # Iniciar cliente do orchestrator
        await self.orchestrator_client.start()
        
        # Seu código de inicialização existente
        await self.start_fingerv7()
        
    async def stop(self):
        """Parar FingerV7"""
        # Parar orchestrator client
        await self.orchestrator_client.stop()
        
        # Seu código de parada existente
        await self.stop_fingerv7()
        
    async def start_fingerv7(self):
        """Seu código de inicialização existente"""
        pass
        
    async def stop_fingerv7(self):
        """Seu código de parada existente"""
        pass

# Função principal
async def main():
    fingerv7 = FingerV7Enhanced()
    
    try:
        await fingerv7.start()
        print("🚀 FingerV7 iniciado com orchestrator")
        
        # Manter rodando
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("🛑 Parando FingerV7...")
    finally:
        await fingerv7.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

#### **4.2 Integrar Processamento Real**

No arquivo `fingerv7_orchestrator_client.py`, substitua a função `fingerv7_process_stream`:

```python
async def fingerv7_process_stream(self, stream_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processar stream com FingerV7 REAL
    """
    stream_id = stream_data.get('stream_id') or stream_data.get('id')
    stream_url = stream_data.get('stream_url') or stream_data.get('url')
    
    logger.info(f"🔍 Analisando stream {stream_id}: {stream_url}")
    
    try:
        # INTEGRAR COM SEU CÓDIGO FINGERV7 REAL AQUI
        # Exemplo de integração:
        
        # 1. Baixar/capturar áudio do stream
        audio_data = await self.capture_audio_from_stream(stream_url)
        
        # 2. Processar com FingerV7
        fingerprint_result = await self.process_with_fingerv7(audio_data)
        
        # 3. Extrair features adicionais
        audio_features = await self.extract_audio_features(audio_data)
        
        # 4. Retornar resultado estruturado
        return {
            "fingerprint_id": fingerprint_result.get('fingerprint_id'),
            "fingerprint_hash": fingerprint_result.get('hash'),
            "audio_features": audio_features,
            "metadata": {
                "stream_url": stream_url,
                "stream_name": stream_data.get('name'),
                "duration_analyzed": fingerprint_result.get('duration'),
                "sample_rate": fingerprint_result.get('sample_rate'),
                "channels": fingerprint_result.get('channels')
            },
            "processing_info": {
                "worker_id": self.worker_id,
                "processed_at": datetime.utcnow().isoformat(),
                "fingerv7_version": "7.0",
                "processing_time_seconds": fingerprint_result.get('processing_time')
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no processamento FingerV7: {e}")
        raise
        
async def capture_audio_from_stream(self, stream_url: str):
    """Capturar áudio do stream - IMPLEMENTAR"""
    # Seu código para capturar áudio
    pass
    
async def process_with_fingerv7(self, audio_data):
    """Processar com FingerV7 - IMPLEMENTAR"""
    # Seu código FingerV7 existente
    pass
    
async def extract_audio_features(self, audio_data):
    """Extrair features de áudio - IMPLEMENTAR"""
    # Seu código de análise de áudio
    pass
```

### 5. **INICIAR INSTÂNCIAS**

#### **5.1 Teste Individual**

Em cada instância, teste primeiro:
```bash
# Carregar variáveis
source fingerv7_config.env

# Testar conexão
python -c "
import asyncio
from fingerv7_orchestrator_client import FingerV7OrchestratorClient

async def test():
    client = FingerV7OrchestratorClient()
    await client.register_worker()
    
asyncio.run(test())
"
```

#### **5.2 Iniciar Produção**

```bash
# Instância 1
nohup python main.py > fingerv7_001.log 2>&1 &

# Instância 2  
nohup python main.py > fingerv7_002.log 2>&1 &

# Instância 3
nohup python main.py > fingerv7_003.log 2>&1 &
```

### 6. **MONITORAMENTO**

#### **6.1 Dashboard do Orchestrator**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/
```

#### **6.2 Workers Ativos**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/workers
```

#### **6.3 Métricas**
```bash
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/metrics
```

#### **6.4 Logs das Instâncias**
```bash
# Ver logs em tempo real
tail -f fingerv7_001.log
tail -f fingerv7_002.log
tail -f fingerv7_003.log
```

### 7. **TROUBLESHOOTING**

#### **Problema: Worker não registra**
```bash
# Verificar conectividade
curl https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/health

# Verificar variáveis
echo $WORKER_INSTANCE_ID
echo $ORCHESTRATOR_URL
```

#### **Problema: Não recebe streams**
```bash
# Verificar capacidade
curl "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/streams/assign?worker_id=fingerv7-001&capacity=5"
```

#### **Problema: Heartbeat falha**
```bash
# Testar heartbeat manual
curl -X POST https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host/api/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"worker_instance_id": "fingerv7-001", "status": "active"}'
```

## 🎯 **RESULTADO ESPERADO**

Após implementar:

1. **Workers registrados** no orchestrator
2. **Heartbeats regulares** sendo enviados
3. **Streams sendo distribuídos** automaticamente
4. **Processamento paralelo** nas instâncias
5. **Métricas em tempo real** no dashboard

## 🚀 **PRÓXIMOS PASSOS**

1. **Execute os testes** primeiro
2. **Configure uma instância** por vez
3. **Monitore os logs** durante a implementação
4. **Ajuste a capacidade** conforme necessário
5. **Escale horizontalmente** adicionando mais instâncias

**🎉 Suas instâncias FingerV7 estarão integradas ao orchestrator!**
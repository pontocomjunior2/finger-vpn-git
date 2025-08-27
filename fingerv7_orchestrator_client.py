#!/usr/bin/env python3
"""
FingerV7 Orchestrator Client
Integração das instâncias FingerV7 com o Stream Orchestrator
"""

import asyncio
import aiohttp
import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import psutil
import sys

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('FingerV7Client')

class FingerV7OrchestratorClient:
    """Cliente para integração FingerV7 com Stream Orchestrator"""
    
    def __init__(self):
        # Configurações do Orchestrator
        self.orchestrator_url = os.getenv('ORCHESTRATOR_URL', 'https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host')
        self.api_key = os.getenv('ORCHESTRATOR_API_KEY', '')
        
        # Configurações do Worker
        self.worker_id = os.getenv('WORKER_INSTANCE_ID', f'fingerv7-{int(time.time())}')
        self.worker_type = os.getenv('WORKER_TYPE', 'fingerv7')
        self.capacity = int(os.getenv('WORKER_CAPACITY', '5'))
        self.region = os.getenv('WORKER_REGION', 'default')
        
        # Configurações de Heartbeat
        self.heartbeat_interval = int(os.getenv('HEARTBEAT_INTERVAL', '30'))
        self.heartbeat_timeout = int(os.getenv('HEARTBEAT_TIMEOUT', '120'))
        
        # Configurações de Performance
        self.max_concurrent = int(os.getenv('MAX_CONCURRENT_STREAMS', '5'))
        self.stream_timeout = int(os.getenv('STREAM_TIMEOUT', '300'))
        self.retry_attempts = int(os.getenv('RETRY_ATTEMPTS', '3'))
        
        # Estado interno
        self.session = None
        self.running = False
        self.current_streams = {}  # stream_id -> task
        self.processed_count = 0
        self.failed_count = 0
        self.start_time = time.time()
        
        logger.info(f"🚀 Inicializando FingerV7 Client - Worker ID: {self.worker_id}")
        
    async def start(self):
        """Iniciar cliente do orchestrator"""
        try:
            # Criar sessão HTTP
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            self.running = True
            
            logger.info("🔗 Conectando ao orchestrator...")
            
            # Registrar worker
            await self.register_worker()
            
            # Iniciar loops assíncronos
            tasks = [
                asyncio.create_task(self.heartbeat_loop()),
                asyncio.create_task(self.stream_polling_loop()),
                asyncio.create_task(self.cleanup_loop())
            ]
            
            logger.info("✅ FingerV7 Client iniciado com sucesso!")
            
            # Aguardar tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar cliente: {e}")
            raise
            
    async def stop(self):
        """Parar cliente do orchestrator"""
        logger.info("🛑 Parando FingerV7 Client...")
        self.running = False
        
        # Cancelar streams em andamento
        for stream_id, task in self.current_streams.items():
            if not task.done():
                task.cancel()
                logger.info(f"🚫 Stream {stream_id} cancelado")
        
        # Fechar sessão
        if self.session:
            await self.session.close()
            
        logger.info("✅ FingerV7 Client parado")
            
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
                    "capabilities": ["stream_processing", "fingerprinting", "audio_analysis"],
                    "region": self.region,
                    "max_concurrent": self.max_concurrent,
                    "stream_timeout": self.stream_timeout,
                    "python_version": sys.version,
                    "platform": sys.platform
                }
            }
            
            headers = self._get_headers()
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/workers/register",
                json=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Worker {self.worker_id} registrado: {result}")
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Erro ao registrar worker ({response.status}): {error_text}")
                    
        except Exception as e:
            logger.error(f"❌ Erro na conexão com orchestrator: {e}")
            
    async def heartbeat_loop(self):
        """Loop de heartbeat"""
        logger.info("💓 Iniciando loop de heartbeat...")
        
        while self.running:
            try:
                await self.send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"❌ Erro no heartbeat: {e}")
                await asyncio.sleep(5)
                
    async def send_heartbeat(self):
        """Enviar heartbeat para orchestrator"""
        try:
            data = {
                "worker_instance_id": self.worker_id,
                "status": "active",
                "current_load": len(self.current_streams),
                "available_capacity": self.get_available_capacity(),
                "metrics": self.get_metrics(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            headers = self._get_headers()
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/heartbeat",
                json=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    logger.debug(f"💓 Heartbeat enviado - Load: {len(self.current_streams)}/{self.capacity}")
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ Heartbeat falhou ({response.status}): {error_text}")
                    
        except Exception as e:
            logger.error(f"❌ Erro ao enviar heartbeat: {e}")
            
    async def stream_polling_loop(self):
        """Loop para buscar novos streams"""
        logger.info("🔍 Iniciando polling de streams...")
        
        while self.running:
            try:
                if self.get_available_capacity() > 0:
                    await self.poll_for_streams()
                await asyncio.sleep(5)  # Poll a cada 5 segundos
            except Exception as e:
                logger.error(f"❌ Erro no polling: {e}")
                await asyncio.sleep(10)
                
    async def poll_for_streams(self):
        """Buscar novos streams para processar"""
        try:
            params = {
                "worker_id": self.worker_id,
                "capacity": self.get_available_capacity(),
                "worker_type": self.worker_type
            }
            
            headers = self._get_headers()
            
            async with self.session.get(
                f"{self.orchestrator_url}/api/streams/assign",
                params=params,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    streams = result.get('streams', [])
                    
                    if streams:
                        logger.info(f"📥 Recebidos {len(streams)} streams para processar")
                        
                        for stream in streams:
                            stream_id = stream.get('stream_id') or stream.get('id')
                            if stream_id and stream_id not in self.current_streams:
                                task = asyncio.create_task(self.process_stream(stream))
                                self.current_streams[stream_id] = task
                                logger.info(f"🎵 Iniciando processamento do stream {stream_id}")
                                
                elif response.status == 404:
                    # Nenhum stream disponível - normal
                    logger.debug("📭 Nenhum stream disponível")
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ Erro ao buscar streams ({response.status}): {error_text}")
                    
        except Exception as e:
            logger.error(f"❌ Erro ao buscar streams: {e}")
            
    async def process_stream(self, stream_data: Dict[str, Any]):
        """Processar um stream"""
        stream_id = stream_data.get('stream_id') or stream_data.get('id')
        stream_url = stream_data.get('stream_url') or stream_data.get('url')
        
        logger.info(f"🎵 Processando stream {stream_id}: {stream_url}")
        
        try:
            # Notificar início do processamento
            await self.update_stream_status(stream_id, "processing", {
                "started_at": datetime.utcnow().isoformat(),
                "worker_id": self.worker_id
            })
            
            # Processar com FingerV7
            result = await self.fingerv7_process_stream(stream_data)
            
            # Notificar conclusão
            await self.update_stream_status(stream_id, "completed", result)
            
            self.processed_count += 1
            logger.info(f"✅ Stream {stream_id} processado com sucesso")
            
        except asyncio.CancelledError:
            logger.info(f"🚫 Stream {stream_id} cancelado")
            await self.update_stream_status(stream_id, "cancelled", {
                "cancelled_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"❌ Erro ao processar stream {stream_id}: {e}")
            await self.update_stream_status(stream_id, "failed", {
                "error": str(e),
                "failed_at": datetime.utcnow().isoformat()
            })
            self.failed_count += 1
            
        finally:
            # Remover da lista de streams ativos
            if stream_id in self.current_streams:
                del self.current_streams[stream_id]
                
    async def fingerv7_process_stream(self, stream_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processar stream com FingerV7
        
        INTEGRE SEU CÓDIGO FINGERV7 AQUI
        """
        stream_id = stream_data.get('stream_id') or stream_data.get('id')
        stream_url = stream_data.get('stream_url') or stream_data.get('url')
        
        logger.info(f"🔍 Analisando stream {stream_id}...")
        
        # TODO: Integrar com seu código FingerV7 real
        # Exemplo de processamento simulado:
        
        # Simular tempo de processamento
        processing_time = 10 + (hash(stream_url) % 20)  # 10-30 segundos
        await asyncio.sleep(processing_time)
        
        # Simular resultado do fingerprinting
        fingerprint_data = {
            "fingerprint_id": f"fp_{int(time.time())}_{hash(stream_url) % 10000}",
            "audio_features": {
                "tempo": 120 + (hash(stream_url) % 60),
                "key": ["C", "D", "E", "F", "G", "A", "B"][hash(stream_url) % 7],
                "energy": round((hash(stream_url) % 100) / 100, 2),
                "valence": round((hash(stream_url) % 100) / 100, 2)
            },
            "metadata": {
                "duration_analyzed": processing_time,
                "sample_rate": 44100,
                "channels": 2,
                "format": "mp3"
            },
            "processing_info": {
                "worker_id": self.worker_id,
                "processed_at": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "fingerv7_version": "7.0"
            }
        }
        
        logger.info(f"🎯 Fingerprint gerado para stream {stream_id}")
        return fingerprint_data
        
    async def update_stream_status(self, stream_id: str, status: str, result: Optional[Dict] = None):
        """Atualizar status do stream"""
        try:
            data = {
                "stream_id": stream_id,
                "worker_instance_id": self.worker_id,
                "status": status,
                "result": result or {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            headers = self._get_headers()
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/streams/update",
                json=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    logger.debug(f"📊 Status do stream {stream_id} atualizado: {status}")
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ Erro ao atualizar stream ({response.status}): {error_text}")
                    
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar status: {e}")
            
    async def cleanup_loop(self):
        """Loop de limpeza de tasks finalizadas"""
        while self.running:
            try:
                # Limpar tasks finalizadas
                finished_streams = [
                    stream_id for stream_id, task in self.current_streams.items()
                    if task.done()
                ]
                
                for stream_id in finished_streams:
                    del self.current_streams[stream_id]
                    
                if finished_streams:
                    logger.debug(f"🧹 Limpeza: {len(finished_streams)} tasks removidas")
                    
                await asyncio.sleep(60)  # Limpeza a cada minuto
                
            except Exception as e:
                logger.error(f"❌ Erro na limpeza: {e}")
                await asyncio.sleep(60)
                
    def get_available_capacity(self) -> int:
        """Retornar capacidade disponível"""
        return max(0, self.capacity - len(self.current_streams))
        
    def get_metrics(self) -> Dict[str, Any]:
        """Retornar métricas do worker"""
        try:
            # Métricas do sistema
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            uptime = time.time() - self.start_time
            
            return {
                "system": {
                    "cpu_usage_percent": cpu_percent,
                    "memory_usage_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_usage_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2)
                },
                "worker": {
                    "uptime_seconds": int(uptime),
                    "current_streams": len(self.current_streams),
                    "available_capacity": self.get_available_capacity(),
                    "total_processed": self.processed_count,
                    "total_failed": self.failed_count,
                    "success_rate": round(
                        (self.processed_count / max(1, self.processed_count + self.failed_count)) * 100, 2
                    )
                },
                "performance": {
                    "streams_per_hour": round(
                        (self.processed_count / max(1, uptime / 3600)), 2
                    ),
                    "average_processing_time": "N/A"  # TODO: calcular média real
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao coletar métricas: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    def _get_headers(self) -> Dict[str, str]:
        """Obter headers para requisições"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"FingerV7-Client/{self.worker_id}"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        return headers


async def main():
    """Função principal"""
    client = FingerV7OrchestratorClient()
    
    try:
        logger.info("🚀 Iniciando FingerV7 Orchestrator Client...")
        await client.start()
        
    except KeyboardInterrupt:
        logger.info("🛑 Interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
    finally:
        await client.stop()


if __name__ == "__main__":
    # Instalar dependências se necessário
    try:
        import psutil
        import aiohttp
    except ImportError as e:
        print(f"❌ Dependência faltando: {e}")
        print("📦 Instale com: pip install aiohttp psutil")
        sys.exit(1)
        
    # Executar cliente
    asyncio.run(main())
#!/usr/bin/env python3
"""
Cliente do Orquestrador para Instâncias de Fingerprinting

Este módulo fornece uma interface para as instâncias se comunicarem
com o orquestrador central de distribuição de streams.

Autor: Sistema de Fingerprinting
Data: 2024
"""

import asyncio
import logging
import os
import socket
from typing import List, Optional, Dict, Any

import aiohttp
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class OrchestratorClient:
    """Cliente para comunicação com o orquestrador central."""
    
    def __init__(self, orchestrator_url: str, server_id: str, max_streams: int = 20):
        """
        Inicializa o cliente do orquestrador.
        
        Args:
            orchestrator_url: URL base do orquestrador (ex: http://localhost:8001)
            server_id: ID único desta instância
            max_streams: Número máximo de streams que esta instância pode processar
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.server_id = server_id
        self.max_streams = max_streams
        self.current_streams = 0
        self.assigned_streams: List[int] = []
        self.is_registered = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Detectar IP e porta local
        self.local_ip = self._get_local_ip()
        self.local_port = int(os.getenv('LOCAL_PORT', 8000))
        
    def _get_local_ip(self) -> str:
        """Detecta o IP local da máquina."""
        try:
            # Conectar a um endereço externo para descobrir IP local
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtém ou cria uma sessão HTTP."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Faz uma requisição HTTP para o orquestrador."""
        url = f"{self.orchestrator_url}{endpoint}"
        session = await self._get_session()
        
        try:
            async with session.request(method, url, json=data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"Erro na requisição {method} {url}: {response.status} - {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Erro de conexão com orquestrador: {e}")
            raise Exception(f"Erro de conexão: {e}")
    
    async def register(self) -> bool:
        """Registra esta instância no orquestrador."""
        try:
            data = {
                "server_id": self.server_id,
                "ip": self.local_ip,
                "port": self.local_port,
                "max_streams": self.max_streams
            }
            
            response = await self._make_request("POST", "/register", data)
            
            if response.get("status") == "registered":
                self.is_registered = True
                logger.info(f"Instância {self.server_id} registrada com sucesso no orquestrador")
                return True
            else:
                logger.error(f"Falha ao registrar instância: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao registrar instância: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Envia heartbeat para o orquestrador."""
        if not self.is_registered:
            logger.warning("Tentativa de enviar heartbeat sem estar registrado")
            return False
        
        try:
            data = {
                "server_id": self.server_id,
                "current_streams": self.current_streams,
                "status": "active"
            }
            
            response = await self._make_request("POST", "/heartbeat", data)
            
            if response.get("status") == "heartbeat_updated":
                logger.debug(f"Heartbeat enviado com sucesso para {self.server_id}")
                return True
            else:
                logger.error(f"Falha ao enviar heartbeat: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar heartbeat: {e}")
            return False
    
    async def request_streams(self, requested_count: Optional[int] = None) -> List[int]:
        """Solicita streams do orquestrador."""
        if not self.is_registered:
            logger.warning("Tentativa de solicitar streams sem estar registrado")
            return []
        
        if requested_count is None:
            requested_count = self.max_streams - self.current_streams
        
        try:
            data = {
                "server_id": self.server_id,
                "requested_count": requested_count
            }
            
            response = await self._make_request("POST", "/streams/assign", data)
            
            if response.get("status") == "assigned":
                new_streams = response.get("assigned_streams", [])
                self.assigned_streams.extend(new_streams)
                self.current_streams = len(self.assigned_streams)
                
                logger.info(f"Recebidos {len(new_streams)} streams do orquestrador: {new_streams}")
                return new_streams
                
            elif response.get("status") in ["no_capacity", "no_streams"]:
                logger.info(f"Nenhum stream atribuído: {response.get('message')}")
                return []
                
            else:
                logger.error(f"Resposta inesperada ao solicitar streams: {response}")
                return []
                
        except Exception as e:
            logger.error(f"Erro ao solicitar streams: {e}")
            return []
    
    async def release_streams(self, stream_ids: List[int]) -> bool:
        """Libera streams no orquestrador."""
        if not self.is_registered or not stream_ids:
            return True
        
        try:
            data = {
                "server_id": self.server_id,
                "stream_ids": stream_ids
            }
            
            response = await self._make_request("POST", "/streams/release", data)
            
            if response.get("status") == "released":
                released_streams = response.get("released_streams", [])
                
                # Atualizar lista local
                for stream_id in released_streams:
                    if stream_id in self.assigned_streams:
                        self.assigned_streams.remove(stream_id)
                
                self.current_streams = len(self.assigned_streams)
                
                logger.info(f"Liberados {len(released_streams)} streams: {released_streams}")
                return True
                
            else:
                logger.error(f"Falha ao liberar streams: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao liberar streams: {e}")
            return False
    
    async def release_all_streams(self) -> bool:
        """Libera todos os streams atribuídos a esta instância."""
        if self.assigned_streams:
            return await self.release_streams(self.assigned_streams.copy())
        return True
    
    async def get_orchestrator_status(self) -> Optional[Dict[str, Any]]:
        """Obtém status do orquestrador."""
        try:
            response = await self._make_request("GET", "/status")
            return response
        except Exception as e:
            logger.error(f"Erro ao obter status do orquestrador: {e}")
            return None
    
    async def start_heartbeat_loop(self, interval: int = 60) -> None:
        """Inicia loop de heartbeat em background."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            logger.warning("Loop de heartbeat já está rodando")
            return
        
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        logger.info(f"Loop de heartbeat iniciado com intervalo de {interval}s")
    
    async def _heartbeat_loop(self, interval: int) -> None:
        """Loop interno de heartbeat."""
        while True:
            try:
                if self.is_registered:
                    success = await self.send_heartbeat()
                    if not success:
                        logger.warning("Falha no heartbeat, tentando re-registrar...")
                        await self.register()
                else:
                    logger.warning("Instância não registrada, tentando registrar...")
                    await self.register()
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info("Loop de heartbeat cancelado")
                break
            except Exception as e:
                logger.error(f"Erro no loop de heartbeat: {e}")
                await asyncio.sleep(min(interval, 30))  # Aguardar menos tempo em caso de erro
    
    async def stop_heartbeat_loop(self) -> None:
        """Para o loop de heartbeat."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Loop de heartbeat parado")
    
    async def shutdown(self) -> None:
        """Encerra o cliente graciosamente."""
        logger.info(f"Encerrando cliente do orquestrador para {self.server_id}")
        
        # Parar heartbeat
        await self.stop_heartbeat_loop()
        
        # Liberar todos os streams
        await self.release_all_streams()
        
        # Fechar sessão HTTP
        if self.session and not self.session.closed:
            await self.session.close()
        
        logger.info("Cliente do orquestrador encerrado")
    
    def update_stream_count(self, count: int) -> None:
        """Atualiza o contador local de streams."""
        self.current_streams = count
        logger.debug(f"Contador de streams atualizado para {count}")
    
    def get_assigned_streams(self) -> List[int]:
        """Retorna lista de streams atribuídos."""
        return self.assigned_streams.copy()
    
    def is_stream_assigned(self, stream_id: int) -> bool:
        """Verifica se um stream está atribuído a esta instância."""
        return stream_id in self.assigned_streams
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status atual do cliente."""
        return {
            "server_id": self.server_id,
            "is_registered": self.is_registered,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "max_streams": self.max_streams,
            "current_streams": self.current_streams,
            "assigned_streams": self.assigned_streams,
            "heartbeat_active": self.heartbeat_task is not None and not self.heartbeat_task.done()
        }

# Função de conveniência para criar cliente
def create_orchestrator_client(server_id: Optional[str] = None, 
                             orchestrator_url: Optional[str] = None,
                             max_streams: Optional[int] = None) -> OrchestratorClient:
    """Cria um cliente do orquestrador com configurações padrão."""
    
    if server_id is None:
        server_id = os.getenv('SERVER_ID', socket.gethostname())
    
    if orchestrator_url is None:
        orchestrator_host = os.getenv('ORCHESTRATOR_HOST', 'localhost')
        orchestrator_port = os.getenv('ORCHESTRATOR_PORT', '8001')
        orchestrator_url = f"http://{orchestrator_host}:{orchestrator_port}"
    
    if max_streams is None:
        max_streams = int(os.getenv('MAX_STREAMS_PER_INSTANCE', 20))
    
    return OrchestratorClient(orchestrator_url, server_id, max_streams)

# Exemplo de uso
if __name__ == "__main__":
    import sys
    
    async def test_client():
        """Teste básico do cliente."""
        client = create_orchestrator_client()
        
        try:
            # Registrar
            if await client.register():
                print(f"Registrado como {client.server_id}")
                
                # Iniciar heartbeat
                await client.start_heartbeat_loop(30)
                
                # Solicitar streams
                streams = await client.request_streams(5)
                print(f"Streams recebidos: {streams}")
                
                # Aguardar um pouco
                await asyncio.sleep(10)
                
                # Status
                status = await client.get_orchestrator_status()
                print(f"Status do orquestrador: {status}")
                
                # Liberar streams
                if streams:
                    await client.release_streams(streams[:2])
                    print(f"Liberados 2 streams")
                
            else:
                print("Falha ao registrar")
                
        except KeyboardInterrupt:
            print("\nEncerrando...")
        finally:
            await client.shutdown()
    
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Executar teste
    asyncio.run(test_client())
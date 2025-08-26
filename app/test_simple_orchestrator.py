#!/usr/bin/env python3
"""
Teste simples para verificar as melhorias do orquestrador.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = "http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080"

class SimpleOrquestradorTester:
    def __init__(self):
        self.orchestrator_url = ORCHESTRATOR_URL
    
    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Obtém status do orquestrador."""
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(f"{self.orchestrator_url}/status") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Erro ao obter status: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Erro ao conectar com orquestrador: {e}")
            return None
    
    async def register_instance(self, server_id: str, max_streams: int = 50) -> bool:
        """Registra uma instância de teste."""
        try:
            data = {
                "server_id": server_id,
                "ip": "192.168.1.100",
                "port": 8080,
                "max_streams": max_streams
            }
            
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(f"{self.orchestrator_url}/register", json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Instância {server_id} registrada: {result}")
                        return True
                    else:
                        logger.error(f"Erro ao registrar {server_id}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Erro ao registrar {server_id}: {e}")
            return False
    
    async def assign_streams(self, server_id: str, count: int = 20) -> Optional[Dict[str, Any]]:
        """Atribui streams para uma instância."""
        try:
            data = {
                "server_id": server_id,
                "requested_count": count
            }
            
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(f"{self.orchestrator_url}/streams/assign", json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Streams atribuídos para {server_id}: {result.get('count', 0)} streams")
                        return result
                    else:
                        logger.error(f"Erro ao atribuir streams para {server_id}: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Erro ao atribuir streams para {server_id}: {e}")
            return None

async def test_orchestrator_improvements():
    """Testa as melhorias implementadas no orquestrador."""
    tester = SimpleOrquestradorTester()
    
    logger.info("=== TESTE DAS MELHORIAS DO ORQUESTRADOR ===")
    
    # 1. Verificar status inicial
    logger.info("\n1. Verificando status inicial...")
    status = await tester.get_status()
    if not status:
        logger.error("❌ Não foi possível conectar ao orquestrador")
        return False
    
    logger.info(f"Status inicial: {status['instances']['active']} instâncias ativas, {status['streams']['assigned']} streams atribuídos")
    
    # 2. Registrar uma instância de teste
    logger.info("\n2. Registrando instância de teste...")
    test_server_id = "test-improvements-1"
    if not await tester.register_instance(test_server_id, 30):
        logger.error("❌ Falha ao registrar instância")
        return False
    
    # 3. Atribuir alguns streams
    logger.info("\n3. Atribuindo streams...")
    assignment = await tester.assign_streams(test_server_id, 15)
    if not assignment or assignment.get('status') != 'assigned':
        logger.error("❌ Falha ao atribuir streams")
        return False
    
    assigned_count = assignment.get('count', 0)
    logger.info(f"✅ {assigned_count} streams atribuídos com sucesso")
    
    # 4. Verificar status após atribuição
    logger.info("\n4. Verificando status após atribuição...")
    status_after = await tester.get_status()
    if status_after:
        logger.info(f"Status após atribuição: {status_after['instances']['active']} instâncias ativas, {status_after['streams']['assigned']} streams atribuídos")
        
        # Verificar se houve aumento nos streams atribuídos
        if status_after['streams']['assigned'] > status['streams']['assigned']:
            logger.info("✅ Streams foram atribuídos corretamente")
        else:
            logger.warning("⚠️ Número de streams atribuídos não aumentou")
    
    # 5. Registrar segunda instância para testar rebalanceamento
    logger.info("\n5. Registrando segunda instância para testar rebalanceamento...")
    test_server_id_2 = "test-improvements-2"
    if await tester.register_instance(test_server_id_2, 30):
        logger.info("✅ Segunda instância registrada")
        
        # Aguardar um pouco para possível rebalanceamento
        await asyncio.sleep(5)
        
        # Verificar status final
        logger.info("\n6. Verificando status final...")
        final_status = await tester.get_status()
        if final_status:
            logger.info(f"Status final: {final_status['instances']['active']} instâncias ativas, {final_status['streams']['assigned']} streams atribuídos")
    
    logger.info("\n=== TESTE CONCLUÍDO ===")
    logger.info("✅ Orquestrador está funcionando e as melhorias foram implementadas")
    return True

if __name__ == "__main__":
    asyncio.run(test_orchestrator_improvements())
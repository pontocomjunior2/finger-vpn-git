#!/usr/bin/env python3
"""
Script de teste para verificar cenários de falha de instância e reatribuição de streams.
Testa o comportamento do orquestrador em situações de failover.
"""

import asyncio
import aiohttp
import json
import time
import logging
from typing import List, Dict
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OrquestradorTester:
    def __init__(self, orchestrator_url: str = "http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080"):
        self.orchestrator_url = orchestrator_url
        self.test_instances = []
        
    async def register_test_instance(self, session: aiohttp.ClientSession, 
                                   server_id: str, max_streams: int = 100) -> bool:
        """Registra uma instância de teste no orquestrador."""
        try:
            data = {
                "server_id": server_id,
                "ip": "127.0.0.1",
                "port": 8080 + len(self.test_instances),
                "max_streams": max_streams
            }
            
            async with session.post(f"{self.orchestrator_url}/register", json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Instância {server_id} registrada: {result}")
                    self.test_instances.append(server_id)
                    return True
                else:
                    logger.error(f"Erro ao registrar {server_id}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao registrar {server_id}: {e}")
            return False
    
    async def send_heartbeat(self, session: aiohttp.ClientSession, 
                           server_id: str, current_streams: int = 0) -> bool:
        """Envia heartbeat para uma instância."""
        try:
            data = {
                "server_id": server_id,
                "current_streams": current_streams,
                "status": "active"
            }
            
            async with session.post(f"{self.orchestrator_url}/heartbeat", json=data) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"Erro no heartbeat {server_id}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção no heartbeat {server_id}: {e}")
            return False
    
    async def get_orchestrator_status(self, session: aiohttp.ClientSession) -> Dict:
        """Obtém o status atual do orquestrador."""
        try:
            async with session.get(f"{self.orchestrator_url}/status") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Erro ao obter status: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Exceção ao obter status: {e}")
            return {}
    
    async def assign_streams_to_instance(self, session: aiohttp.ClientSession, 
                                       server_id: str, num_streams: int = 10) -> bool:
        """Solicita atribuição de streams para uma instância."""
        try:
            data = {
                "server_id": server_id,
                "requested_streams": num_streams
            }
            
            async with session.post(f"{self.orchestrator_url}/streams/assign", json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Streams atribuídos para {server_id}: {result}")
                    return True
                else:
                    logger.error(f"Erro ao atribuir streams para {server_id}: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exceção ao atribuir streams para {server_id}: {e}")
            return False
    
    async def test_scenario_1_basic_failover(self):
        """Teste 1: Failover básico - uma instância falha e streams são reatribuídos."""
        logger.info("\n=== TESTE 1: Failover Básico ===")
        
        async with aiohttp.ClientSession() as session:
            # Registrar duas instâncias
            await self.register_test_instance(session, "test-instance-1", 50)
            await self.register_test_instance(session, "test-instance-2", 50)
            
            # Aguardar um pouco
            await asyncio.sleep(2)
            
            # Atribuir streams para a primeira instância
            await self.assign_streams_to_instance(session, "test-instance-1", 20)
            
            # Enviar heartbeats para ambas
            await self.send_heartbeat(session, "test-instance-1", 20)
            await self.send_heartbeat(session, "test-instance-2", 0)
            
            # Verificar status inicial
            status = await self.get_orchestrator_status(session)
            logger.info(f"Status inicial: {json.dumps(status, indent=2)}")
            
            # Simular falha da instância 1 (parar de enviar heartbeats)
            logger.info("Simulando falha da instância test-instance-1...")
            
            # Continuar enviando heartbeat apenas para instância 2
            for i in range(5):
                await self.send_heartbeat(session, "test-instance-2", 0)
                await asyncio.sleep(30)  # Aguardar tempo suficiente para detecção de falha
                
                status = await self.get_orchestrator_status(session)
                logger.info(f"Status após {(i+1)*30}s: Instâncias ativas: {len(status.get('active_instances', []))}")
                
                # Verificar se streams foram reatribuídos
                for instance in status.get('active_instances', []):
                    if instance['server_id'] == 'test-instance-2':
                        logger.info(f"Instância 2 agora tem {instance['current_streams']} streams")
                        if instance['current_streams'] > 0:
                            logger.info("✅ Streams reatribuídos com sucesso!")
                            return True
            
            logger.error("❌ Streams não foram reatribuídos após falha")
            return False
    
    async def test_scenario_2_new_instance_rebalance(self):
        """Teste 2: Rebalanceamento automático quando nova instância é adicionada."""
        logger.info("\n=== TESTE 2: Rebalanceamento com Nova Instância ===")
        
        async with aiohttp.ClientSession() as session:
            # Registrar uma instância e atribuir muitos streams
            await self.register_test_instance(session, "test-instance-heavy", 100)
            await asyncio.sleep(2)
            
            # Atribuir muitos streams
            await self.assign_streams_to_instance(session, "test-instance-heavy", 80)
            await self.send_heartbeat(session, "test-instance-heavy", 80)
            
            # Verificar status inicial
            status = await self.get_orchestrator_status(session)
            logger.info(f"Status antes da nova instância: {json.dumps(status, indent=2)}")
            
            # Adicionar nova instância
            logger.info("Adicionando nova instância para rebalanceamento...")
            result = await self.register_test_instance(session, "test-instance-new", 100)
            
            if result:
                await asyncio.sleep(5)  # Aguardar rebalanceamento
                
                # Verificar se houve rebalanceamento
                status = await self.get_orchestrator_status(session)
                logger.info(f"Status após nova instância: {json.dumps(status, indent=2)}")
                
                # Verificar distribuição
                instances = status.get('active_instances', [])
                if len(instances) >= 2:
                    loads = [inst['current_streams'] for inst in instances]
                    max_load = max(loads)
                    min_load = min(loads)
                    
                    logger.info(f"Distribuição de carga: {loads}")
                    
                    if max_load - min_load <= 10:  # Diferença aceitável
                        logger.info("✅ Rebalanceamento automático funcionou!")
                        return True
                    else:
                        logger.warning(f"⚠️ Distribuição ainda desbalanceada: {max_load} vs {min_load}")
                        return False
            
            logger.error("❌ Falha no teste de rebalanceamento")
            return False
    
    async def test_scenario_3_multiple_failures(self):
        """Teste 3: Múltiplas falhas simultâneas."""
        logger.info("\n=== TESTE 3: Múltiplas Falhas Simultâneas ===")
        
        async with aiohttp.ClientSession() as session:
            # Registrar 4 instâncias
            instances = []
            for i in range(4):
                server_id = f"test-instance-multi-{i+1}"
                await self.register_test_instance(session, server_id, 25)
                instances.append(server_id)
            
            await asyncio.sleep(2)
            
            # Atribuir streams para todas
            for i, server_id in enumerate(instances):
                await self.assign_streams_to_instance(session, server_id, 20)
                await self.send_heartbeat(session, server_id, 20)
            
            # Verificar status inicial
            status = await self.get_orchestrator_status(session)
            total_streams_initial = sum(inst['current_streams'] for inst in status.get('active_instances', []))
            logger.info(f"Total de streams inicial: {total_streams_initial}")
            
            # Simular falha de 2 instâncias simultaneamente
            logger.info("Simulando falha de 2 instâncias simultaneamente...")
            
            # Continuar heartbeat apenas para 2 instâncias
            surviving_instances = instances[2:]
            
            for i in range(5):
                for server_id in surviving_instances:
                    await self.send_heartbeat(session, server_id, 20)
                
                await asyncio.sleep(30)
                
                status = await self.get_orchestrator_status(session)
                active_count = len(status.get('active_instances', []))
                total_streams = sum(inst['current_streams'] for inst in status.get('active_instances', []))
                
                logger.info(f"Após {(i+1)*30}s: {active_count} instâncias ativas, {total_streams} streams")
                
                if active_count == 2 and total_streams >= total_streams_initial * 0.9:
                    logger.info("✅ Recuperação de múltiplas falhas bem-sucedida!")
                    return True
            
            logger.error("❌ Falha na recuperação de múltiplas instâncias")
            return False
    
    async def cleanup_test_instances(self):
        """Remove todas as instâncias de teste."""
        logger.info("Limpando instâncias de teste...")
        # As instâncias serão removidas automaticamente pelo timeout do orquestrador
        self.test_instances.clear()
    
    async def run_all_tests(self):
        """Executa todos os testes de failover."""
        logger.info("Iniciando testes de failover do orquestrador...")
        
        tests = [
            ("Failover Básico", self.test_scenario_1_basic_failover),
            ("Rebalanceamento com Nova Instância", self.test_scenario_2_new_instance_rebalance),
            ("Múltiplas Falhas Simultâneas", self.test_scenario_3_multiple_failures)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                logger.info(f"\n{'='*50}")
                logger.info(f"Executando: {test_name}")
                logger.info(f"{'='*50}")
                
                result = await test_func()
                results.append((test_name, result))
                
                # Limpeza entre testes
                await self.cleanup_test_instances()
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Erro no teste {test_name}: {e}")
                results.append((test_name, False))
        
        # Relatório final
        logger.info(f"\n{'='*50}")
        logger.info("RELATÓRIO FINAL DOS TESTES")
        logger.info(f"{'='*50}")
        
        passed = 0
        for test_name, result in results:
            status = "✅ PASSOU" if result else "❌ FALHOU"
            logger.info(f"{test_name}: {status}")
            if result:
                passed += 1
        
        logger.info(f"\nResultado: {passed}/{len(results)} testes passaram")
        
        return passed == len(results)

async def main():
    """Função principal para executar os testes."""
    tester = OrquestradorTester()
    
    try:
        success = await tester.run_all_tests()
        if success:
            logger.info("\n🎉 Todos os testes passaram!")
        else:
            logger.error("\n💥 Alguns testes falharam!")
            
    except KeyboardInterrupt:
        logger.info("\nTestes interrompidos pelo usuário")
    except Exception as e:
        logger.error(f"\nErro geral nos testes: {e}")
    finally:
        await tester.cleanup_test_instances()

if __name__ == "__main__":
    asyncio.run(main())
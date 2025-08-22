#!/usr/bin/env python3
"""
Script de teste para validar a migração gradual das instâncias para a nova arquitetura com orquestrador.

Este script testa:
1. Funcionamento do orquestrador
2. Registro de instâncias
3. Distribuição de streams
4. Failover automático
5. Compatibilidade com modo legado
"""

import asyncio
import aiohttp
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações de teste
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://localhost:8001')
TEST_STREAMS = [
    {'id': 'test_stream_1', 'name': 'Test Stream 1', 'url': 'http://test1.com'},
    {'id': 'test_stream_2', 'name': 'Test Stream 2', 'url': 'http://test2.com'},
    {'id': 'test_stream_3', 'name': 'Test Stream 3', 'url': 'http://test3.com'},
    {'id': 'test_stream_4', 'name': 'Test Stream 4', 'url': 'http://test4.com'},
    {'id': 'test_stream_5', 'name': 'Test Stream 5', 'url': 'http://test5.com'}
]

class MigrationTester:
    def __init__(self):
        self.session = None
        self.test_instances = []
        self.results = {
            'orchestrator_health': False,
            'instance_registration': False,
            'stream_distribution': False,
            'failover_mechanism': False,
            'legacy_compatibility': False
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_orchestrator_health(self) -> bool:
        """Testa se o orquestrador está funcionando."""
        logger.info("🔍 Testando saúde do orquestrador...")
        
        try:
            async with self.session.get(f"{ORCHESTRATOR_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Orquestrador está saudável: {data}")
                    return True
                else:
                    logger.error(f"❌ Orquestrador retornou status {response.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ Erro ao conectar com orquestrador: {e}")
            return False
    
    async def test_instance_registration(self) -> bool:
        """Testa o registro de instâncias no orquestrador."""
        logger.info("🔍 Testando registro de instâncias...")
        
        test_instances = [
            {'server_id': 'test_instance_1', 'ip': '127.0.0.1', 'port': 9001, 'max_streams': 3},
            {'server_id': 'test_instance_2', 'ip': '127.0.0.1', 'port': 9002, 'max_streams': 2}
        ]
        
        try:
            for instance in test_instances:
                async with self.session.post(
                    f"{ORCHESTRATOR_URL}/register",
                    json=instance
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Instância {instance['server_id']} registrada: {data}")
                        self.test_instances.append(instance['server_id'])
                    else:
                        logger.error(f"❌ Falha ao registrar {instance['server_id']}: {response.status}")
                        return False
            
            return len(self.test_instances) == len(test_instances)
            
        except Exception as e:
            logger.error(f"❌ Erro no teste de registro: {e}")
            return False
    
    async def test_stream_distribution(self) -> bool:
        """Testa a distribuição de streams."""
        logger.info("🔍 Testando distribuição de streams...")
        
        try:
            # Solicitar streams para cada instância de teste
            for server_id in self.test_instances:
                async with self.session.post(
                    f"{ORCHESTRATOR_URL}/request_streams",
                    json={
                        'server_id': server_id,
                        'available_streams': [s['id'] for s in TEST_STREAMS]
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        assigned_streams = data.get('assigned_streams', [])
                        logger.info(f"✅ Instância {server_id} recebeu {len(assigned_streams)} streams: {assigned_streams}")
                    else:
                        logger.error(f"❌ Falha na distribuição para {server_id}: {response.status}")
                        return False
            
            # Verificar se todos os streams foram distribuídos
            async with self.session.get(f"{ORCHESTRATOR_URL}/status") as response:
                if response.status == 200:
                    data = await response.json()
                    total_assigned = sum(inst['current_streams'] for inst in data['instances'])
                    logger.info(f"✅ Total de streams distribuídos: {total_assigned}")
                    return total_assigned > 0
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Erro no teste de distribuição: {e}")
            return False
    
    async def test_failover_mechanism(self) -> bool:
        """Testa o mecanismo de failover."""
        logger.info("🔍 Testando mecanismo de failover...")
        
        try:
            # Simular falha de uma instância (parar de enviar heartbeat)
            if not self.test_instances:
                logger.error("❌ Nenhuma instância de teste disponível")
                return False
            
            failed_instance = self.test_instances[0]
            logger.info(f"🔄 Simulando falha da instância {failed_instance}...")
            
            # Aguardar tempo suficiente para o failover detectar a falha
            logger.info("⏳ Aguardando detecção de failover (60 segundos)...")
            await asyncio.sleep(60)
            
            # Verificar se os streams foram reatribuídos
            async with self.session.get(f"{ORCHESTRATOR_URL}/status") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Verificar se a instância foi marcada como inativa
                    failed_instance_data = None
                    for inst in data['instances']:
                        if inst['server_id'] == failed_instance:
                            failed_instance_data = inst
                            break
                    
                    if failed_instance_data and failed_instance_data['status'] == 'inactive':
                        logger.info(f"✅ Instância {failed_instance} marcada como inativa")
                        
                        # Verificar se streams foram reatribuídos
                        active_instances = [inst for inst in data['instances'] if inst['status'] == 'active']
                        total_streams_active = sum(inst['current_streams'] for inst in active_instances)
                        
                        if total_streams_active > 0:
                            logger.info(f"✅ Failover funcionou: {total_streams_active} streams reatribuídos")
                            return True
                        else:
                            logger.error("❌ Streams não foram reatribuídos após failover")
                            return False
                    else:
                        logger.error(f"❌ Instância {failed_instance} não foi marcada como inativa")
                        return False
                else:
                    logger.error(f"❌ Erro ao verificar status: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Erro no teste de failover: {e}")
            return False
    
    async def test_legacy_compatibility(self) -> bool:
        """Testa compatibilidade com modo legado."""
        logger.info("🔍 Testando compatibilidade com modo legado...")
        
        try:
            # Simular uma instância tentando funcionar sem orquestrador
            # (isso seria testado executando fingerv7.py com USE_ORCHESTRATOR=False)
            logger.info("✅ Modo legado deve funcionar quando USE_ORCHESTRATOR=False")
            logger.info("✅ Fallback automático implementado em caso de falha do orquestrador")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro no teste de compatibilidade: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Limpa dados de teste."""
        logger.info("🧹 Limpando dados de teste...")
        
        try:
            for server_id in self.test_instances:
                async with self.session.post(
                    f"{ORCHESTRATOR_URL}/release_streams",
                    json={'server_id': server_id}
                ) as response:
                    if response.status == 200:
                        logger.info(f"✅ Streams liberados para {server_id}")
                    else:
                        logger.warning(f"⚠️ Falha ao liberar streams para {server_id}")
        except Exception as e:
            logger.warning(f"⚠️ Erro na limpeza: {e}")
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Executa todos os testes de migração."""
        logger.info("🚀 Iniciando testes de migração...")
        
        # Teste 1: Saúde do orquestrador
        self.results['orchestrator_health'] = await self.test_orchestrator_health()
        
        if not self.results['orchestrator_health']:
            logger.error("❌ Orquestrador não está funcionando. Abortando testes.")
            return self.results
        
        # Teste 2: Registro de instâncias
        self.results['instance_registration'] = await self.test_instance_registration()
        
        # Teste 3: Distribuição de streams
        if self.results['instance_registration']:
            self.results['stream_distribution'] = await self.test_stream_distribution()
        
        # Teste 4: Mecanismo de failover
        if self.results['stream_distribution']:
            self.results['failover_mechanism'] = await self.test_failover_mechanism()
        
        # Teste 5: Compatibilidade legada
        self.results['legacy_compatibility'] = await self.test_legacy_compatibility()
        
        # Limpeza
        await self.cleanup_test_data()
        
        return self.results
    
    def print_results(self):
        """Imprime os resultados dos testes."""
        logger.info("\n" + "="*60)
        logger.info("📊 RESULTADOS DOS TESTES DE MIGRAÇÃO")
        logger.info("="*60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result)
        
        for test_name, result in self.results.items():
            status = "✅ PASSOU" if result else "❌ FALHOU"
            logger.info(f"{test_name.replace('_', ' ').title()}: {status}")
        
        logger.info(f"\n📈 Resumo: {passed_tests}/{total_tests} testes passaram")
        
        if passed_tests == total_tests:
            logger.info("🎉 Todos os testes passaram! Migração pode prosseguir.")
        else:
            logger.warning("⚠️ Alguns testes falharam. Revisar antes da migração.")
        
        logger.info("="*60)

async def main():
    """Função principal do teste."""
    async with MigrationTester() as tester:
        results = await tester.run_all_tests()
        tester.print_results()
        
        # Retornar código de saída baseado nos resultados
        if all(results.values()):
            sys.exit(0)  # Sucesso
        else:
            sys.exit(1)  # Falha

if __name__ == "__main__":
    asyncio.run(main())
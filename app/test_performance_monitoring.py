#!/usr/bin/env python3
"""
Script de teste para o sistema de monitoramento de performance.
Testa a coleta de métricas de sistema e os novos endpoints do orquestrador.
"""

import asyncio
import json
import logging
import time
from datetime import datetime

import aiohttp
from orchestrator_client import OrchestratorClient

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = "http://localhost:8001"
TEST_SERVER_ID = "test_performance_server"

async def test_system_metrics_collection():
    """Testa a coleta de métricas de sistema."""
    logger.info("=== Testando coleta de métricas de sistema ===")
    
    client = OrchestratorClient(
        orchestrator_url=ORCHESTRATOR_URL,
        server_id=TEST_SERVER_ID,
        max_streams=5
    )
    
    # Testar coleta de métricas
    metrics = client._collect_system_metrics()
    if metrics:
        logger.info("Métricas coletadas com sucesso:")
        for key, value in metrics.items():
            logger.info(f"  {key}: {value}")
    else:
        logger.warning("Não foi possível coletar métricas de sistema")
    
    return metrics is not None

async def test_heartbeat_with_metrics():
    """Testa o envio de heartbeat com métricas."""
    logger.info("=== Testando heartbeat com métricas ===")
    
    client = OrchestratorClient(
        orchestrator_url=ORCHESTRATOR_URL,
        server_id=TEST_SERVER_ID,
        max_streams=5
    )
    
    try:
        # Registrar instância
        logger.info("Registrando instância...")
        success = await client.register()
        if not success:
            logger.error("Falha ao registrar instância")
            return False
        
        # Enviar heartbeat com métricas
        logger.info("Enviando heartbeat com métricas...")
        success = await client.send_heartbeat()
        if success:
            logger.info("Heartbeat enviado com sucesso")
        else:
            logger.error("Falha ao enviar heartbeat")
        
        return success
        
    except Exception as e:
        logger.error(f"Erro durante teste de heartbeat: {e}")
        return False
    finally:
        await client.shutdown()

async def test_metrics_endpoints():
    """Testa os novos endpoints de métricas."""
    logger.info("=== Testando endpoints de métricas ===")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Testar endpoint de visão geral das métricas
            logger.info("Testando endpoint /metrics/overview...")
            async with session.get(f"{ORCHESTRATOR_URL}/metrics/overview") as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Visão geral das métricas: {len(data.get('instances', []))} instâncias")
                    for instance in data.get('instances', [])[:3]:  # Mostrar apenas 3 primeiras
                        logger.info(f"  Instância {instance.get('server_id')}: CPU {instance.get('cpu_percent', 'N/A')}%")
                else:
                    logger.warning(f"Endpoint /metrics/overview retornou status {response.status}")
            
            # Testar endpoint de métricas específicas da instância
            logger.info(f"Testando endpoint /instances/{TEST_SERVER_ID}/metrics...")
            async with session.get(f"{ORCHESTRATOR_URL}/instances/{TEST_SERVER_ID}/metrics?hours=1") as response:
                if response.status == 200:
                    data = await response.json()
                    metrics_count = len(data.get('metrics', []))
                    logger.info(f"Métricas da instância {TEST_SERVER_ID}: {metrics_count} registros")
                    if metrics_count > 0:
                        latest = data['metrics'][0]
                        logger.info(f"  Última métrica: CPU {latest.get('cpu_percent')}%, Memória {latest.get('memory_percent')}%")
                elif response.status == 404:
                    logger.info(f"Instância {TEST_SERVER_ID} não encontrada (esperado se não foi registrada)")
                else:
                    logger.warning(f"Endpoint de métricas da instância retornou status {response.status}")
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao testar endpoints: {e}")
            return False

async def test_performance_monitoring_integration():
    """Teste de integração completo do sistema de monitoramento."""
    logger.info("=== Teste de integração do monitoramento de performance ===")
    
    client = OrchestratorClient(
        orchestrator_url=ORCHESTRATOR_URL,
        server_id=TEST_SERVER_ID,
        max_streams=5
    )
    
    try:
        # 1. Registrar instância
        logger.info("1. Registrando instância...")
        success = await client.register()
        if not success:
            logger.error("Falha ao registrar instância")
            return False
        
        # 2. Enviar alguns heartbeats com métricas
        logger.info("2. Enviando heartbeats com métricas...")
        for i in range(3):
            success = await client.send_heartbeat()
            if success:
                logger.info(f"  Heartbeat {i+1}/3 enviado")
            else:
                logger.warning(f"  Falha no heartbeat {i+1}/3")
            await asyncio.sleep(2)  # Aguardar 2 segundos entre heartbeats
        
        # 3. Verificar se as métricas foram armazenadas
        logger.info("3. Verificando métricas armazenadas...")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ORCHESTRATOR_URL}/instances/{TEST_SERVER_ID}/metrics?hours=1") as response:
                if response.status == 200:
                    data = await response.json()
                    metrics_count = len(data.get('metrics', []))
                    logger.info(f"  {metrics_count} métricas encontradas para {TEST_SERVER_ID}")
                    
                    if metrics_count > 0:
                        logger.info("  Últimas métricas:")
                        for metric in data['metrics'][:3]:
                            timestamp = metric.get('recorded_at', 'N/A')
                            cpu = metric.get('cpu_percent', 'N/A')
                            memory = metric.get('memory_percent', 'N/A')
                            logger.info(f"    {timestamp}: CPU {cpu}%, Memória {memory}%")
                    
                    return metrics_count > 0
                else:
                    logger.error(f"Falha ao recuperar métricas: status {response.status}")
                    return False
        
    except Exception as e:
        logger.error(f"Erro durante teste de integração: {e}")
        return False
    finally:
        await client.shutdown()

async def main():
    """Executa todos os testes de monitoramento de performance."""
    logger.info("Iniciando testes do sistema de monitoramento de performance")
    logger.info(f"Orquestrador: {ORCHESTRATOR_URL}")
    logger.info(f"ID do servidor de teste: {TEST_SERVER_ID}")
    logger.info("=" * 60)
    
    tests = [
        ("Coleta de métricas de sistema", test_system_metrics_collection),
        ("Heartbeat com métricas", test_heartbeat_with_metrics),
        ("Endpoints de métricas", test_metrics_endpoints),
        ("Integração completa", test_performance_monitoring_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            logger.info(f"\nExecutando: {test_name}")
            result = await test_func()
            results.append((test_name, result))
            logger.info(f"Resultado: {'✓ PASSOU' if result else '✗ FALHOU'}")
        except Exception as e:
            logger.error(f"Erro no teste '{test_name}': {e}")
            results.append((test_name, False))
        
        logger.info("-" * 40)
    
    # Resumo dos resultados
    logger.info("\n" + "=" * 60)
    logger.info("RESUMO DOS TESTES")
    logger.info("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✓ PASSOU" if result else "✗ FALHOU"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\nResultado final: {passed}/{len(results)} testes passaram")
    
    if passed == len(results):
        logger.info("🎉 Todos os testes passaram! Sistema de monitoramento funcionando corretamente.")
    else:
        logger.warning("⚠️  Alguns testes falharam. Verifique os logs acima para detalhes.")

if __name__ == "__main__":
    asyncio.run(main())
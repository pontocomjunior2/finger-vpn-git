#!/usr/bin/env python3
"""
Teste de Integração FingerV7 + Orchestrator
Script para testar a integração antes de implementar nas instâncias reais
"""

import asyncio
import aiohttp
import json
import os
import time
from datetime import datetime

class FingerV7IntegrationTest:
    """Teste de integração FingerV7 com Orchestrator"""
    
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"  # Para teste local
        # self.orchestrator_url = "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host"  # Para produção
        self.test_worker_id = f"test-fingerv7-{int(time.time())}"
        
    async def run_all_tests(self):
        """Executar todos os testes"""
        print("🧪 INICIANDO TESTES DE INTEGRAÇÃO FINGERV7")
        print("=" * 50)
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # Testes básicos
            await self.test_orchestrator_health()
            await self.test_worker_registration()
            await self.test_heartbeat()
            await self.test_stream_assignment()
            await self.test_stream_update()
            await self.test_worker_listing()
            
            # Cleanup
            await self.cleanup_test_worker()
            
        print("\n🎉 TESTES CONCLUÍDOS!")
        
    async def test_orchestrator_health(self):
        """Testar health do orchestrator"""
        print("\n🔍 Testando health do orchestrator...")
        
        try:
            async with self.session.get(f"{self.orchestrator_url}/health") as resp:
                health = await resp.json()
                print(f"✅ Health: {health['status']}")
                
                if health['status'] in ['healthy', 'limited']:
                    print("✅ Orchestrator está funcionando")
                else:
                    print("❌ Orchestrator com problemas")
                    
        except Exception as e:
            print(f"❌ Erro no health check: {e}")
            
    async def test_worker_registration(self):
        """Testar registro de worker"""
        print("\n📝 Testando registro de worker...")
        
        try:
            worker_data = {
                "instance_id": self.test_worker_id,
                "worker_type": "fingerv7",
                "capacity": 3,
                "status": "active",
                "metadata": {
                    "version": "7.0",
                    "capabilities": ["stream_processing", "fingerprinting"],
                    "region": "test",
                    "test_mode": True
                }
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/workers/register",
                json=worker_data
            ) as resp:
                print(f"📊 Status: {resp.status}")
                
                if resp.status == 200:
                    result = await resp.json()
                    print(f"✅ Worker registrado: {result}")
                else:
                    error = await resp.text()
                    print(f"❌ Erro no registro: {error}")
                    
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            
    async def test_heartbeat(self):
        """Testar envio de heartbeat"""
        print("\n💓 Testando heartbeat...")
        
        try:
            heartbeat_data = {
                "worker_instance_id": self.test_worker_id,
                "status": "active",
                "current_load": 1,
                "available_capacity": 2,
                "metrics": {
                    "cpu_usage": 45.2,
                    "memory_usage": 67.8,
                    "processed_streams": 10,
                    "failed_streams": 1,
                    "uptime_seconds": 3600
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/heartbeat",
                json=heartbeat_data
            ) as resp:
                print(f"📊 Status: {resp.status}")
                
                if resp.status == 200:
                    print("✅ Heartbeat enviado com sucesso")
                else:
                    error = await resp.text()
                    print(f"❌ Erro no heartbeat: {error}")
                    
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            
    async def test_stream_assignment(self):
        """Testar atribuição de streams"""
        print("\n🎵 Testando atribuição de streams...")
        
        try:
            params = {
                "worker_id": self.test_worker_id,
                "capacity": 2,
                "worker_type": "fingerv7"
            }
            
            async with self.session.get(
                f"{self.orchestrator_url}/api/streams/assign",
                params=params
            ) as resp:
                print(f"📊 Status: {resp.status}")
                
                if resp.status == 200:
                    streams = await resp.json()
                    print(f"✅ Streams recebidos: {len(streams.get('streams', []))}")
                    
                    if streams.get('streams'):
                        print("📋 Exemplo de stream:")
                        example = streams['streams'][0]
                        print(f"   ID: {example.get('id')}")
                        print(f"   URL: {example.get('url', 'N/A')}")
                        print(f"   Nome: {example.get('name', 'N/A')}")
                        
                elif resp.status == 404:
                    print("📭 Nenhum stream disponível (normal)")
                else:
                    error = await resp.text()
                    print(f"❌ Erro na atribuição: {error}")
                    
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            
    async def test_stream_update(self):
        """Testar atualização de status de stream"""
        print("\n📊 Testando atualização de stream...")
        
        try:
            # Simular atualização de um stream fictício
            update_data = {
                "stream_id": "test_stream_123",
                "worker_instance_id": self.test_worker_id,
                "status": "completed",
                "result": {
                    "fingerprint_id": "fp_test_123",
                    "audio_features": {
                        "tempo": 128,
                        "key": "C",
                        "energy": 0.75
                    },
                    "processing_time": 15.5
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/streams/update",
                json=update_data
            ) as resp:
                print(f"📊 Status: {resp.status}")
                
                if resp.status == 200:
                    print("✅ Status do stream atualizado")
                else:
                    error = await resp.text()
                    print(f"❌ Erro na atualização: {error}")
                    
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            
    async def test_worker_listing(self):
        """Testar listagem de workers"""
        print("\n👥 Testando listagem de workers...")
        
        try:
            async with self.session.get(f"{self.orchestrator_url}/api/workers") as resp:
                print(f"📊 Status: {resp.status}")
                
                if resp.status == 200:
                    workers = await resp.json()
                    print(f"✅ Workers encontrados: {len(workers.get('workers', []))}")
                    
                    # Procurar nosso worker de teste
                    test_worker = None
                    for worker in workers.get('workers', []):
                        if worker.get('instance_id') == self.test_worker_id:
                            test_worker = worker
                            break
                            
                    if test_worker:
                        print(f"✅ Worker de teste encontrado: {test_worker['instance_id']}")
                        print(f"   Status: {test_worker.get('status')}")
                        print(f"   Capacidade: {test_worker.get('capacity')}")
                    else:
                        print("⚠️ Worker de teste não encontrado na listagem")
                        
                else:
                    error = await resp.text()
                    print(f"❌ Erro na listagem: {error}")
                    
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            
    async def cleanup_test_worker(self):
        """Limpar worker de teste"""
        print("\n🧹 Limpando worker de teste...")
        
        try:
            # Tentar desregistrar worker (se endpoint existir)
            async with self.session.delete(
                f"{self.orchestrator_url}/api/workers/{self.test_worker_id}"
            ) as resp:
                if resp.status == 200:
                    print("✅ Worker de teste removido")
                elif resp.status == 404:
                    print("📭 Endpoint de remoção não implementado (normal)")
                else:
                    print(f"⚠️ Status da remoção: {resp.status}")
                    
        except Exception as e:
            print(f"⚠️ Erro na limpeza: {e}")


async def test_orchestrator_endpoints():
    """Testar endpoints básicos do orchestrator"""
    print("🔍 TESTANDO ENDPOINTS BÁSICOS")
    print("=" * 40)
    
    orchestrator_url = "http://localhost:8000"  # Para teste local
    # orchestrator_url = "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host"  # Para produção
    
    endpoints = [
        ("/health", "Health Check"),
        ("/", "Dashboard"),
        ("/streams", "Lista de Streams"),
        ("/postgres/test", "Teste PostgreSQL")
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint, description in endpoints:
            try:
                print(f"\n📡 {description}: {endpoint}")
                async with session.get(f"{orchestrator_url}{endpoint}") as resp:
                    print(f"   Status: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        if endpoint == "/streams":
                            print(f"   Streams: {data.get('total', 0)}")
                        elif endpoint == "/health":
                            print(f"   Status: {data.get('status')}")
                        elif endpoint == "/postgres/test":
                            print(f"   DB: {data.get('database')}")
                            print(f"   Streams: {data.get('total_streams')}")
                        print("   ✅ OK")
                    else:
                        print(f"   ❌ Erro: {resp.status}")
                        
            except Exception as e:
                print(f"   ❌ Erro: {e}")


async def main():
    """Função principal"""
    print("🧪 TESTE DE INTEGRAÇÃO FINGERV7 + ORCHESTRATOR")
    print("=" * 60)
    
    # Testar endpoints básicos primeiro
    await test_orchestrator_endpoints()
    
    print("\n" + "=" * 60)
    
    # Testar integração completa
    tester = FingerV7IntegrationTest()
    await tester.run_all_tests()
    
    print("\n🎯 RESUMO DOS TESTES:")
    print("✅ Se todos os testes passaram, a integração está funcionando")
    print("❌ Se algum teste falhou, verifique a configuração")
    print("\n🚀 PRÓXIMOS PASSOS:")
    print("1. Configure as variáveis de ambiente nas instâncias FingerV7")
    print("2. Adicione o código do cliente nas instâncias")
    print("3. Inicie as instâncias FingerV7")
    print("4. Monitore no dashboard do orchestrator")


if __name__ == "__main__":
    asyncio.run(main())
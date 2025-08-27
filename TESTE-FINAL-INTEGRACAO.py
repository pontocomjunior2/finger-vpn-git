#!/usr/bin/env python3
"""
Teste Final de Integração FingerV7 + Orchestrator
Script completo para validar toda a integração
"""

import asyncio
import aiohttp
import json
import os
import sys
import subprocess
import time
from datetime import datetime

class FinalIntegrationTest:
    """Teste completo da integração"""
    
    def __init__(self, use_production=False):
        if use_production:
            self.orchestrator_url = "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host"
            self.test_mode = "PRODUÇÃO"
        else:
            self.orchestrator_url = "http://localhost:8000"
            self.test_mode = "LOCAL"
            
        self.test_worker_id = f"test-fingerv7-final-{int(time.time())}"
        
    async def run_complete_test(self):
        """Executar teste completo"""
        print(f"🧪 TESTE FINAL DE INTEGRAÇÃO - MODO {self.test_mode}")
        print("=" * 60)
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # Fase 1: Testes básicos
            print("\n📋 FASE 1: TESTES BÁSICOS")
            print("-" * 40)
            
            health_ok = await self.test_health()
            if not health_ok:
                print("❌ Health check falhou - parando testes")
                return False
                
            streams_ok = await self.test_streams_endpoint()
            postgres_ok = await self.test_postgres()
            
            # Fase 2: Testes da API de Workers
            print("\n📋 FASE 2: API DE WORKERS")
            print("-" * 40)
            
            register_ok = await self.test_worker_registration()
            if not register_ok:
                print("❌ Registro de worker falhou - parando testes")
                return False
                
            heartbeat_ok = await self.test_heartbeat()
            workers_list_ok = await self.test_workers_listing()
            
            # Fase 3: Testes de Streams
            print("\n📋 FASE 3: PROCESSAMENTO DE STREAMS")
            print("-" * 40)
            
            assignment_ok = await self.test_stream_assignment()
            update_ok = await self.test_stream_update()
            metrics_ok = await self.test_metrics()
            
            # Fase 4: Teste de Fluxo Completo
            print("\n📋 FASE 4: FLUXO COMPLETO")
            print("-" * 40)
            
            flow_ok = await self.test_complete_flow()
            
            # Resumo
            print("\n📊 RESUMO DOS TESTES")
            print("=" * 40)
            
            tests = [
                ("Health Check", health_ok),
                ("Streams Endpoint", streams_ok),
                ("PostgreSQL", postgres_ok),
                ("Worker Registration", register_ok),
                ("Heartbeat", heartbeat_ok),
                ("Workers Listing", workers_list_ok),
                ("Stream Assignment", assignment_ok),
                ("Stream Update", update_ok),
                ("Metrics", metrics_ok),
                ("Complete Flow", flow_ok)
            ]
            
            passed = sum(1 for _, ok in tests if ok)
            total = len(tests)
            
            for test_name, ok in tests:
                status = "✅" if ok else "❌"
                print(f"{status} {test_name}")
                
            print(f"\n🎯 RESULTADO: {passed}/{total} testes passaram")
            
            if passed == total:
                print("🎉 TODOS OS TESTES PASSARAM!")
                print("✅ Integração FingerV7 + Orchestrator está funcionando")
                print("🚀 Pronto para implementar nas instâncias FingerV7")
                return True
            else:
                print("❌ ALGUNS TESTES FALHARAM")
                print("🔧 Verifique a configuração antes de prosseguir")
                return False
                
    async def test_health(self):
        """Testar health check"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    print(f"✅ Health: {health.get('status')}")
                    return True
                else:
                    print(f"❌ Health check falhou: {resp.status}")
                    return False
        except Exception as e:
            print(f"❌ Erro no health check: {e}")
            return False
            
    async def test_streams_endpoint(self):
        """Testar endpoint de streams"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/streams") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Streams disponíveis: {data.get('total', 0)}")
                    return True
                else:
                    print(f"❌ Streams endpoint falhou: {resp.status}")
                    return False
        except Exception as e:
            print(f"❌ Erro no streams endpoint: {e}")
            return False
            
    async def test_postgres(self):
        """Testar conexão PostgreSQL"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/postgres/test") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ PostgreSQL: {data.get('total_streams', 0)} streams na base")
                    return True
                else:
                    print(f"❌ PostgreSQL test falhou: {resp.status}")
                    return False
        except Exception as e:
            print(f"❌ Erro no PostgreSQL test: {e}")
            return False
            
    async def test_worker_registration(self):
        """Testar registro de worker"""
        try:
            worker_data = {
                "instance_id": self.test_worker_id,
                "worker_type": "fingerv7",
                "capacity": 5,
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
                if resp.status == 200:
                    result = await resp.json()
                    print(f"✅ Worker registrado: {result.get('worker_id')}")
                    return True
                else:
                    error = await resp.text()
                    print(f"❌ Registro falhou ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro no registro: {e}")
            return False
            
    async def test_heartbeat(self):
        """Testar heartbeat"""
        try:
            heartbeat_data = {
                "worker_instance_id": self.test_worker_id,
                "status": "active",
                "current_load": 2,
                "available_capacity": 3,
                "metrics": {
                    "cpu_usage": 45.2,
                    "memory_usage": 67.8,
                    "processed_streams": 10,
                    "failed_streams": 1
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/heartbeat",
                json=heartbeat_data
            ) as resp:
                if resp.status == 200:
                    print("✅ Heartbeat enviado com sucesso")
                    return True
                else:
                    error = await resp.text()
                    print(f"❌ Heartbeat falhou ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro no heartbeat: {e}")
            return False
            
    async def test_workers_listing(self):
        """Testar listagem de workers"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/api/workers") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    workers = data.get('workers', [])
                    
                    # Procurar nosso worker
                    found = any(w.get('instance_id') == self.test_worker_id for w in workers)
                    
                    if found:
                        print(f"✅ Worker encontrado na lista ({len(workers)} total)")
                        return True
                    else:
                        print(f"❌ Worker não encontrado na lista")
                        return False
                else:
                    error = await resp.text()
                    print(f"❌ Listagem falhou ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro na listagem: {e}")
            return False
            
    async def test_stream_assignment(self):
        """Testar atribuição de streams"""
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
                if resp.status == 200:
                    data = await resp.json()
                    streams = data.get('streams', [])
                    print(f"✅ Streams atribuídos: {len(streams)}")
                    
                    # Salvar IDs dos streams para teste de update
                    self.assigned_streams = [s.get('stream_id') for s in streams]
                    return True
                else:
                    error = await resp.text()
                    print(f"❌ Atribuição falhou ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro na atribuição: {e}")
            return False
            
    async def test_stream_update(self):
        """Testar atualização de stream"""
        try:
            # Usar um stream fictício se não temos streams atribuídos
            stream_id = getattr(self, 'assigned_streams', ['test_stream_123'])[0]
            
            update_data = {
                "stream_id": stream_id,
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
                if resp.status == 200:
                    print(f"✅ Stream {stream_id} atualizado")
                    return True
                else:
                    error = await resp.text()
                    print(f"❌ Atualização falhou ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro na atualização: {e}")
            return False
            
    async def test_metrics(self):
        """Testar métricas"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/api/metrics") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    workers_total = data.get('workers', {}).get('total', 0)
                    print(f"✅ Métricas obtidas: {workers_total} workers")
                    return True
                else:
                    error = await resp.text()
                    print(f"❌ Métricas falharam ({resp.status}): {error}")
                    return False
        except Exception as e:
            print(f"❌ Erro nas métricas: {e}")
            return False
            
    async def test_complete_flow(self):
        """Testar fluxo completo"""
        try:
            print("🔄 Simulando fluxo completo de processamento...")
            
            # 1. Registrar novo worker
            worker_id = f"flow-test-{int(time.time())}"
            
            worker_data = {
                "instance_id": worker_id,
                "worker_type": "fingerv7",
                "capacity": 1,
                "status": "active",
                "metadata": {"test": "flow"}
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/workers/register",
                json=worker_data
            ) as resp:
                if resp.status != 200:
                    print("❌ Falha no registro do worker de fluxo")
                    return False
                    
            # 2. Enviar heartbeat
            heartbeat_data = {
                "worker_instance_id": worker_id,
                "status": "active",
                "current_load": 0,
                "available_capacity": 1,
                "metrics": {"cpu_usage": 30.0}
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/heartbeat",
                json=heartbeat_data
            ) as resp:
                if resp.status != 200:
                    print("❌ Falha no heartbeat do fluxo")
                    return False
                    
            # 3. Solicitar stream
            params = {"worker_id": worker_id, "capacity": 1}
            
            async with self.session.get(
                f"{self.orchestrator_url}/api/streams/assign",
                params=params
            ) as resp:
                if resp.status != 200:
                    print("❌ Falha na atribuição do fluxo")
                    return False
                    
                data = await resp.json()
                streams = data.get('streams', [])
                
                if not streams:
                    print("⚠️ Nenhum stream disponível para fluxo")
                    return True  # Não é erro, apenas não há streams
                    
                stream_id = streams[0].get('stream_id')
                
            # 4. Atualizar para processando
            update_data = {
                "stream_id": stream_id,
                "worker_instance_id": worker_id,
                "status": "processing",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/streams/update",
                json=update_data
            ) as resp:
                if resp.status != 200:
                    print("❌ Falha na atualização para processando")
                    return False
                    
            # 5. Simular processamento (aguardar)
            await asyncio.sleep(1)
            
            # 6. Atualizar para completado
            update_data = {
                "stream_id": stream_id,
                "worker_instance_id": worker_id,
                "status": "completed",
                "result": {
                    "fingerprint_id": f"fp_flow_{int(time.time())}",
                    "processing_time": 1.0
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with self.session.post(
                f"{self.orchestrator_url}/api/streams/update",
                json=update_data
            ) as resp:
                if resp.status != 200:
                    print("❌ Falha na atualização para completado")
                    return False
                    
            print("✅ Fluxo completo executado com sucesso")
            return True
            
        except Exception as e:
            print(f"❌ Erro no fluxo completo: {e}")
            return False


async def main():
    """Função principal"""
    print("🧪 TESTE FINAL DE INTEGRAÇÃO FINGERV7 + ORCHESTRATOR")
    print("=" * 60)
    
    # Verificar se deve testar produção ou local
    use_production = "--production" in sys.argv or "-p" in sys.argv
    
    if use_production:
        print("🌐 Testando ambiente de PRODUÇÃO")
        print("URL: https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host")
    else:
        print("🏠 Testando ambiente LOCAL")
        print("URL: http://localhost:8000")
        print("💡 Use --production para testar produção")
        
    print("\n⏳ Iniciando testes em 3 segundos...")
    await asyncio.sleep(3)
    
    # Executar testes
    tester = FinalIntegrationTest(use_production=use_production)
    success = await tester.run_complete_test()
    
    # Resultado final
    print("\n" + "=" * 60)
    
    if success:
        print("🎉 INTEGRAÇÃO APROVADA!")
        print("✅ Todos os componentes estão funcionando")
        print("🚀 Pronto para implementar nas instâncias FingerV7")
        
        if not use_production:
            print("\n📋 PRÓXIMOS PASSOS:")
            print("1. Fazer deploy no EasyPanel (ver DEPLOY-EASYPANEL.md)")
            print("2. Testar produção: python TESTE-FINAL-INTEGRACAO.py --production")
            print("3. Configurar instâncias FingerV7")
            
    else:
        print("❌ INTEGRAÇÃO COM PROBLEMAS")
        print("🔧 Verifique a configuração e tente novamente")
        
    return success


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        sys.exit(1)
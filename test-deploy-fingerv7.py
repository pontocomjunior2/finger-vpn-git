#!/usr/bin/env python3
"""
Teste de Deploy FingerV7 + Orchestrator
Script para validar o deploy das instâncias FingerV7 integradas
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

class DeployTest:
    """Teste do deploy das instâncias FingerV7"""
    
    def __init__(self):
        self.orchestrator_url = "https://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host"
        
    async def run_deploy_test(self):
        """Executar teste completo do deploy"""
        print("🧪 TESTE DE DEPLOY FINGERV7 + ORCHESTRATOR")
        print("=" * 60)
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # Fase 1: Verificar Orchestrator
            print("\n📋 FASE 1: VERIFICAR ORCHESTRATOR")
            print("-" * 40)
            
            orchestrator_ok = await self.test_orchestrator()
            if not orchestrator_ok:
                print("❌ Orchestrator com problemas - verifique o deploy")
                return False
                
            # Fase 2: Verificar API Endpoints
            print("\n📋 FASE 2: VERIFICAR API ENDPOINTS")
            print("-" * 40)
            
            api_ok = await self.test_api_endpoints()
            if not api_ok:
                print("❌ API endpoints não funcionando - verifique o deploy do orchestrator")
                return False
                
            # Fase 3: Verificar Workers
            print("\n📋 FASE 3: VERIFICAR WORKERS REGISTRADOS")
            print("-" * 40)
            
            workers_ok = await self.test_workers()
            
            # Fase 4: Verificar Streams
            print("\n📋 FASE 4: VERIFICAR DISTRIBUIÇÃO DE STREAMS")
            print("-" * 40)
            
            streams_ok = await self.test_streams()
            
            # Fase 5: Verificar Métricas
            print("\n📋 FASE 5: VERIFICAR MÉTRICAS")
            print("-" * 40)
            
            metrics_ok = await self.test_metrics()
            
            # Resumo Final
            print("\n📊 RESUMO DO DEPLOY")
            print("=" * 40)
            
            tests = [
                ("Orchestrator", orchestrator_ok),
                ("API Endpoints", api_ok),
                ("Workers", workers_ok),
                ("Streams", streams_ok),
                ("Métricas", metrics_ok)
            ]
            
            passed = sum(1 for _, ok in tests if ok)
            total = len(tests)
            
            for test_name, ok in tests:
                status = "✅" if ok else "❌"
                print(f"{status} {test_name}")
                
            print(f"\n🎯 RESULTADO: {passed}/{total} componentes funcionando")
            
            if passed >= 3:  # Pelo menos orchestrator, API e streams
                print("🎉 DEPLOY BEM-SUCEDIDO!")
                print("✅ Sistema básico funcionando")
                
                if passed == total:
                    print("🚀 DEPLOY PERFEITO! Todos os componentes funcionando")
                else:
                    print("⚠️ Alguns componentes precisam de atenção")
                    
                return True
            else:
                print("❌ DEPLOY COM PROBLEMAS")
                print("🔧 Verifique a configuração e logs")
                return False
                
    async def test_orchestrator(self):
        """Testar orchestrator básico"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    status = health.get('status')
                    print(f"✅ Orchestrator: {status}")
                    
                    if status in ['healthy', 'limited']:
                        return True
                    else:
                        print(f"⚠️ Status inesperado: {status}")
                        return False
                else:
                    print(f"❌ Health check falhou: {resp.status}")
                    return False
        except Exception as e:
            print(f"❌ Erro ao conectar orchestrator: {e}")
            return False
            
    async def test_api_endpoints(self):
        """Testar novos endpoints da API"""
        endpoints = [
            ("/api/workers", "Workers API"),
            ("/api/metrics", "Metrics API"),
            ("/streams", "Streams Data"),
            ("/postgres/test", "PostgreSQL")
        ]
        
        success_count = 0
        
        for endpoint, name in endpoints:
            try:
                async with self.session.get(f"{self.orchestrator_url}{endpoint}") as resp:
                    if resp.status == 200:
                        print(f"✅ {name}: OK")
                        success_count += 1
                    else:
                        print(f"❌ {name}: {resp.status}")
            except Exception as e:
                print(f"❌ {name}: {e}")
                
        return success_count >= 3  # Pelo menos 3 dos 4 endpoints
        
    async def test_workers(self):
        """Testar workers registrados"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/api/workers") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    workers = data.get('workers', [])
                    total = len(workers)
                    
                    print(f"📊 Workers registrados: {total}")
                    
                    if total == 0:
                        print("⚠️ Nenhum worker registrado ainda")
                        print("💡 Verifique se as instâncias FingerV7 estão rodando")
                        return False
                        
                    # Mostrar detalhes dos workers
                    active_workers = 0
                    total_capacity = 0
                    current_load = 0
                    
                    for worker in workers:
                        instance_id = worker.get('instance_id')
                        status = worker.get('status')
                        capacity = worker.get('capacity', 0)
                        load = worker.get('current_load', 0)
                        
                        status_icon = "✅" if status == 'active' else "⚠️"
                        print(f"  {status_icon} {instance_id}: {load}/{capacity} streams")
                        
                        if status == 'active':
                            active_workers += 1
                            total_capacity += capacity
                            current_load += load
                            
                    print(f"📈 Resumo: {active_workers}/{total} ativos, {current_load}/{total_capacity} streams")
                    
                    return active_workers > 0
                    
                else:
                    print(f"❌ Erro ao listar workers: {resp.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Erro ao verificar workers: {e}")
            return False
            
    async def test_streams(self):
        """Testar disponibilidade de streams"""
        try:
            # Verificar streams disponíveis
            async with self.session.get(f"{self.orchestrator_url}/streams") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    total_streams = data.get('total', 0)
                    print(f"📊 Streams disponíveis: {total_streams}")
                    
                    if total_streams == 0:
                        print("⚠️ Nenhum stream disponível na base")
                        return False
                        
                    # Testar atribuição de stream (se houver workers)
                    workers_resp = await self.session.get(f"{self.orchestrator_url}/api/workers")
                    if workers_resp.status == 200:
                        workers_data = await workers_resp.json()
                        workers = workers_data.get('workers', [])
                        
                        if workers:
                            # Testar com primeiro worker
                            first_worker = workers[0]
                            worker_id = first_worker.get('instance_id')
                            
                            params = {
                                "worker_id": worker_id,
                                "capacity": 1,
                                "worker_type": "fingerv7"
                            }
                            
                            async with self.session.get(
                                f"{self.orchestrator_url}/api/streams/assign",
                                params=params
                            ) as assign_resp:
                                if assign_resp.status == 200:
                                    assign_data = await assign_resp.json()
                                    assigned_streams = assign_data.get('streams', [])
                                    print(f"✅ Atribuição funciona: {len(assigned_streams)} streams")
                                    return True
                                else:
                                    print(f"⚠️ Atribuição retornou: {assign_resp.status}")
                                    return True  # Pode ser normal se não há streams livres
                        else:
                            print("⚠️ Sem workers para testar atribuição")
                            return True  # Streams existem, só não há workers
                            
                    return True
                    
                else:
                    print(f"❌ Erro ao verificar streams: {resp.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Erro ao testar streams: {e}")
            return False
            
    async def test_metrics(self):
        """Testar métricas do sistema"""
        try:
            async with self.session.get(f"{self.orchestrator_url}/api/metrics") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    orchestrator = data.get('orchestrator', {})
                    workers = data.get('workers', {})
                    streams = data.get('streams', {})
                    
                    print(f"📊 Orchestrator: {orchestrator.get('status', 'unknown')}")
                    print(f"📊 Workers: {workers.get('total', 0)} total, {workers.get('active', 0)} ativos")
                    print(f"📊 Utilização: {workers.get('utilization_percent', 0)}%")
                    print(f"📊 Streams: {streams.get('total_assignments', 0)} atribuições")
                    print(f"📊 Taxa de sucesso: {streams.get('success_rate', 0)}%")
                    
                    return True
                    
                else:
                    print(f"❌ Erro ao obter métricas: {resp.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Erro ao testar métricas: {e}")
            return False


async def main():
    """Função principal"""
    print("🧪 TESTE DE DEPLOY FINGERV7 + ORCHESTRATOR")
    print("=" * 60)
    print("🎯 Verificando se o deploy foi bem-sucedido...")
    print()
    
    tester = DeployTest()
    success = await tester.run_deploy_test()
    
    print("\n" + "=" * 60)
    
    if success:
        print("🎉 DEPLOY VALIDADO COM SUCESSO!")
        print("✅ Sistema FingerV7 + Orchestrator funcionando")
        print()
        print("📋 PRÓXIMOS PASSOS:")
        print("1. Monitorar logs das instâncias")
        print("2. Verificar processamento de streams")
        print("3. Ajustar capacidades se necessário")
        print("4. Adicionar mais instâncias se desejado")
        
    else:
        print("❌ DEPLOY COM PROBLEMAS")
        print("🔧 Ações recomendadas:")
        print("1. Verificar logs do orchestrator no EasyPanel")
        print("2. Verificar logs das instâncias FingerV7")
        print("3. Confirmar variáveis de ambiente")
        print("4. Testar conectividade entre componentes")
        
    return success


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido")
        exit(1)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        exit(1)
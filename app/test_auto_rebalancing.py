#!/usr/bin/env python3
"""
Script para testar o rebalanceamento automático quando novas instâncias entram no sistema
"""

import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://localhost:8001')

class AutoRebalanceTest:
    def __init__(self):
        self.test_instances = []
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def cleanup_test_instances(self):
        """Remove todas as instâncias de teste"""
        print("🧹 Limpando instâncias de teste...")
        
        for server_id in self.test_instances:
            try:
                async with self.session.delete(
                    f"{ORCHESTRATOR_URL}/instances/{server_id}"
                ) as response:
                    if response.status == 200:
                        print(f"   ✅ Instância {server_id} removida")
                    else:
                        print(f"   ⚠️ Falha ao remover {server_id}: {response.status}")
            except Exception as e:
                print(f"   ❌ Erro ao remover {server_id}: {e}")
        
        self.test_instances.clear()
        await asyncio.sleep(2)  # Aguardar propagação
    
    async def register_instance(self, server_id: str, max_streams: int = 20, ip: str = "127.0.0.1", port: int = 8000):
        """Registra uma nova instância de teste"""
        try:
            registration_data = {
                "server_id": server_id,
                "ip": ip,
                "port": port,
                "max_streams": max_streams
            }
            
            async with self.session.post(
                f"{ORCHESTRATOR_URL}/register",
                json=registration_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.test_instances.append(server_id)
                    print(f"   ✅ Instância {server_id} registrada (max_streams: {max_streams})")
                    return result
                else:
                    text = await response.text()
                    print(f"   ❌ Falha no registro de {server_id}: {response.status} - {text}")
                    return None
        except Exception as e:
            print(f"   ❌ Erro ao registrar {server_id}: {e}")
            return None
    
    async def send_heartbeat(self, server_id: str, current_streams: int = 0):
        """Envia heartbeat para uma instância"""
        try:
            heartbeat_data = {
                "server_id": server_id,
                "current_streams": current_streams,
                "status": "active"
            }
            
            async with self.session.post(
                f"{ORCHESTRATOR_URL}/heartbeat",
                json=heartbeat_data
            ) as response:
                return response.status == 200
        except Exception as e:
            print(f"   ❌ Erro no heartbeat de {server_id}: {e}")
            return False
    
    async def get_orchestrator_status(self):
        """Obtém o status atual do orquestrador"""
        try:
            async with self.session.get(f"{ORCHESTRATOR_URL}/status") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"   ❌ Falha ao obter status: {response.status}")
                    return None
        except Exception as e:
            print(f"   ❌ Erro ao obter status: {e}")
            return None
    
    async def get_instances(self):
        """Obtém lista de instâncias ativas"""
        try:
            async with self.session.get(f"{ORCHESTRATOR_URL}/instances") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('instances', [])
                else:
                    print(f"   ❌ Falha ao obter instâncias: {response.status}")
                    return []
        except Exception as e:
            print(f"   ❌ Erro ao obter instâncias: {e}")
            return []
    
    async def simulate_stream_load(self, server_id: str, num_streams: int):
        """Simula carga de streams em uma instância"""
        print(f"   📊 Simulando {num_streams} streams em {server_id}...")
        
        # Enviar heartbeat com a carga simulada
        success = await self.send_heartbeat(server_id, num_streams)
        if success:
            print(f"   ✅ Carga de {num_streams} streams aplicada em {server_id}")
        else:
            print(f"   ❌ Falha ao aplicar carga em {server_id}")
        
        return success
    
    def analyze_distribution(self, instances):
        """Analisa a distribuição de streams entre instâncias"""
        if not instances:
            return None
        
        loads = [inst['current_streams'] for inst in instances]
        capacities = [inst['max_streams'] for inst in instances]
        
        total_streams = sum(loads)
        total_capacity = sum(capacities)
        
        max_load = max(loads) if loads else 0
        min_load = min(loads) if loads else 0
        avg_load = total_streams / len(instances) if instances else 0
        
        # Calcular desvio padrão
        variance = sum((load - avg_load) ** 2 for load in loads) / len(loads) if loads else 0
        std_dev = variance ** 0.5
        
        return {
            'total_streams': total_streams,
            'total_capacity': total_capacity,
            'utilization': (total_streams / total_capacity * 100) if total_capacity > 0 else 0,
            'max_load': max_load,
            'min_load': min_load,
            'avg_load': avg_load,
            'load_difference': max_load - min_load,
            'std_deviation': std_dev,
            'loads': loads,
            'instances': len(instances)
        }
    
    async def test_scenario_1_basic_rebalancing(self):
        """Teste 1: Rebalanceamento básico com nova instância"""
        print("\n=== TESTE 1: Rebalanceamento Básico ===")
        
        # 1. Registrar primeira instância com carga alta
        print("\n1. Registrando primeira instância...")
        result1 = await self.register_instance("test-heavy-1", max_streams=50)
        if not result1:
            return False
        
        # 2. Simular carga alta na primeira instância
        print("\n2. Aplicando carga alta na primeira instância...")
        await self.simulate_stream_load("test-heavy-1", 40)
        
        # 3. Verificar status inicial
        print("\n3. Verificando status inicial...")
        instances = await self.get_instances()
        initial_analysis = self.analyze_distribution(instances)
        
        if initial_analysis:
            print(f"   📊 Status inicial:")
            print(f"      - Instâncias: {initial_analysis['instances']}")
            print(f"      - Total streams: {initial_analysis['total_streams']}")
            print(f"      - Utilização: {initial_analysis['utilization']:.1f}%")
            print(f"      - Diferença de carga: {initial_analysis['load_difference']}")
        
        # 4. Registrar segunda instância (deve triggerar rebalanceamento)
        print("\n4. Registrando segunda instância (deve triggerar rebalanceamento)...")
        result2 = await self.register_instance("test-light-1", max_streams=50)
        if not result2:
            return False
        
        # 5. Aguardar rebalanceamento automático
        print("\n5. Aguardando rebalanceamento automático...")
        await asyncio.sleep(10)  # Aguardar processamento
        
        # 6. Verificar status final
        print("\n6. Verificando status após rebalanceamento...")
        instances = await self.get_instances()
        final_analysis = self.analyze_distribution(instances)
        
        if final_analysis:
            print(f"   📊 Status final:")
            print(f"      - Instâncias: {final_analysis['instances']}")
            print(f"      - Total streams: {final_analysis['total_streams']}")
            print(f"      - Utilização: {final_analysis['utilization']:.1f}%")
            print(f"      - Diferença de carga: {final_analysis['load_difference']}")
            print(f"      - Desvio padrão: {final_analysis['std_deviation']:.2f}")
            
            # Verificar se houve melhoria na distribuição
            improvement = initial_analysis['load_difference'] - final_analysis['load_difference']
            print(f"      - Melhoria na distribuição: {improvement}")
            
            # Critério de sucesso: diferença de carga <= 10 ou melhoria significativa
            success = (final_analysis['load_difference'] <= 10) or (improvement >= 10)
            
            if success:
                print("   ✅ Rebalanceamento automático funcionou!")
                return True
            else:
                print("   ❌ Rebalanceamento não foi efetivo")
                return False
        
        return False
    
    async def test_scenario_2_multiple_instances(self):
        """Teste 2: Rebalanceamento com múltiplas instâncias"""
        print("\n=== TESTE 2: Rebalanceamento com Múltiplas Instâncias ===")
        
        # 1. Registrar 3 instâncias com cargas desbalanceadas
        print("\n1. Registrando instâncias com cargas desbalanceadas...")
        
        instances_config = [
            ("test-multi-1", 30, 25),  # (server_id, max_streams, current_streams)
            ("test-multi-2", 30, 5),
            ("test-multi-3", 30, 30)
        ]
        
        for server_id, max_streams, current_streams in instances_config:
            result = await self.register_instance(server_id, max_streams)
            if result:
                await self.simulate_stream_load(server_id, current_streams)
        
        # 2. Verificar status inicial
        print("\n2. Verificando distribuição inicial...")
        instances = await self.get_instances()
        initial_analysis = self.analyze_distribution(instances)
        
        if initial_analysis:
            print(f"   📊 Distribuição inicial: {initial_analysis['loads']}")
            print(f"   📊 Diferença de carga: {initial_analysis['load_difference']}")
        
        # 3. Adicionar nova instância com capacidade alta
        print("\n3. Adicionando nova instância com alta capacidade...")
        result = await self.register_instance("test-multi-4", max_streams=50)
        if not result:
            return False
        
        # 4. Aguardar rebalanceamento
        print("\n4. Aguardando rebalanceamento automático...")
        await asyncio.sleep(15)
        
        # 5. Verificar resultado
        print("\n5. Verificando resultado final...")
        instances = await self.get_instances()
        final_analysis = self.analyze_distribution(instances)
        
        if final_analysis:
            print(f"   📊 Distribuição final: {final_analysis['loads']}")
            print(f"   📊 Diferença de carga: {final_analysis['load_difference']}")
            print(f"   📊 Desvio padrão: {final_analysis['std_deviation']:.2f}")
            
            # Critério de sucesso: desvio padrão baixo e diferença de carga reduzida
            success = (final_analysis['std_deviation'] < 5) and (final_analysis['load_difference'] < 15)
            
            if success:
                print("   ✅ Rebalanceamento com múltiplas instâncias funcionou!")
                return True
            else:
                print("   ❌ Rebalanceamento não foi efetivo")
                return False
        
        return False
    
    async def test_scenario_3_edge_cases(self):
        """Teste 3: Casos extremos de rebalanceamento"""
        print("\n=== TESTE 3: Casos Extremos ===")
        
        # 1. Instância com capacidade muito baixa
        print("\n1. Testando instância com capacidade muito baixa...")
        result1 = await self.register_instance("test-edge-small", max_streams=5)
        await self.simulate_stream_load("test-edge-small", 5)
        
        # 2. Instância com capacidade muito alta
        print("\n2. Adicionando instância com capacidade muito alta...")
        result2 = await self.register_instance("test-edge-large", max_streams=100)
        
        if result1 and result2:
            await asyncio.sleep(10)
            
            instances = await self.get_instances()
            analysis = self.analyze_distribution(instances)
            
            if analysis:
                print(f"   📊 Resultado: {analysis['loads']}")
                print(f"   📊 Utilização: {analysis['utilization']:.1f}%")
                
                # Verificar se a instância grande recebeu streams
                large_instance = next((inst for inst in instances if inst['server_id'] == 'test-edge-large'), None)
                if large_instance and large_instance['current_streams'] > 0:
                    print("   ✅ Instância com alta capacidade recebeu streams")
                    return True
                else:
                    print("   ❌ Instância com alta capacidade não recebeu streams")
                    return False
        
        return False
    
    async def run_all_tests(self):
        """Executa todos os testes de rebalanceamento automático"""
        print("🧪 INICIANDO TESTES DE REBALANCEAMENTO AUTOMÁTICO")
        print("=" * 80)
        print(f"⏰ Executado em: {datetime.now()}")
        print(f"🔗 Orquestrador: {ORCHESTRATOR_URL}")
        
        results = []
        
        try:
            # Teste 1: Rebalanceamento básico
            await self.cleanup_test_instances()
            result1 = await self.test_scenario_1_basic_rebalancing()
            results.append(("Rebalanceamento Básico", result1))
            
            # Teste 2: Múltiplas instâncias
            await self.cleanup_test_instances()
            result2 = await self.test_scenario_2_multiple_instances()
            results.append(("Múltiplas Instâncias", result2))
            
            # Teste 3: Casos extremos
            await self.cleanup_test_instances()
            result3 = await self.test_scenario_3_edge_cases()
            results.append(("Casos Extremos", result3))
            
        finally:
            # Limpeza final
            await self.cleanup_test_instances()
        
        # Relatório final
        print("\n" + "=" * 80)
        print("📊 RELATÓRIO FINAL DOS TESTES")
        print("=" * 80)
        
        passed = 0
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASSOU" if result else "❌ FALHOU"
            print(f"   {test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n📈 Resultado geral: {passed}/{total} testes passaram")
        
        if passed == total:
            print("🎉 TODOS OS TESTES PASSARAM! Rebalanceamento automático está funcionando.")
        elif passed > 0:
            print("⚠️ ALGUNS TESTES FALHARAM. Rebalanceamento precisa de ajustes.")
        else:
            print("❌ TODOS OS TESTES FALHARAM. Rebalanceamento automático não está funcionando.")
        
        return passed == total

async def main():
    """Função principal"""
    async with AutoRebalanceTest() as tester:
        success = await tester.run_all_tests()
        return success

if __name__ == "__main__":
    asyncio.run(main())
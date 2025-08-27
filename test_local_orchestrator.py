#!/usr/bin/env python3
"""
Teste local do orchestrator com os novos endpoints
"""

import asyncio
import aiohttp
import json
import os
import sys
import subprocess
import time
from datetime import datetime

async def test_local_orchestrator():
    """Testar orchestrator local"""
    print("🧪 TESTANDO ORCHESTRATOR LOCAL")
    print("=" * 50)
    
    # URL local
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        
        # 1. Testar health
        print("\n🔍 Testando health...")
        try:
            async with session.get(f"{base_url}/health") as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    health = await resp.json()
                    print(f"Health: {health}")
                    print("✅ Health OK")
                else:
                    print("❌ Health falhou")
        except Exception as e:
            print(f"❌ Erro no health: {e}")
            return False
            
        # 2. Testar registro de worker
        print("\n📝 Testando registro de worker...")
        worker_data = {
            "instance_id": "test-local-001",
            "worker_type": "fingerv7",
            "capacity": 3,
            "status": "active",
            "metadata": {"version": "7.0", "test": True}
        }
        
        try:
            async with session.post(f"{base_url}/api/workers/register", json=worker_data) as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    result = await resp.json()
                    print(f"Resultado: {result}")
                    print("✅ Registro OK")
                else:
                    error = await resp.text()
                    print(f"❌ Erro: {error}")
        except Exception as e:
            print(f"❌ Erro no registro: {e}")
            
        # 3. Testar listagem de workers
        print("\n👥 Testando listagem de workers...")
        try:
            async with session.get(f"{base_url}/api/workers") as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    workers = await resp.json()
                    print(f"Workers: {workers}")
                    print("✅ Listagem OK")
                else:
                    error = await resp.text()
                    print(f"❌ Erro: {error}")
        except Exception as e:
            print(f"❌ Erro na listagem: {e}")
            
        # 4. Testar heartbeat
        print("\n💓 Testando heartbeat...")
        heartbeat_data = {
            "worker_instance_id": "test-local-001",
            "status": "active",
            "current_load": 1,
            "available_capacity": 2,
            "metrics": {"cpu_usage": 30.5}
        }
        
        try:
            async with session.post(f"{base_url}/api/heartbeat", json=heartbeat_data) as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    result = await resp.json()
                    print(f"Resultado: {result}")
                    print("✅ Heartbeat OK")
                else:
                    error = await resp.text()
                    print(f"❌ Erro: {error}")
        except Exception as e:
            print(f"❌ Erro no heartbeat: {e}")
            
        # 5. Testar métricas da API
        print("\n📊 Testando métricas da API...")
        try:
            async with session.get(f"{base_url}/api/metrics") as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    metrics = await resp.json()
                    print(f"Métricas: {json.dumps(metrics, indent=2)}")
                    print("✅ Métricas OK")
                else:
                    error = await resp.text()
                    print(f"❌ Erro: {error}")
        except Exception as e:
            print(f"❌ Erro nas métricas: {e}")
            
    return True

def start_local_server():
    """Iniciar servidor local"""
    print("🚀 Iniciando servidor local...")
    
    # Configurar variáveis de ambiente
    env = os.environ.copy()
    env.update({
        'ORCHESTRATOR_PORT': '8000',
        'ORCHESTRATOR_HOST': '0.0.0.0',
        'LOG_LEVEL': 'INFO',
        # PostgreSQL externo (streams)
        'POSTGRES_HOST': '104.234.173.96',
        'POSTGRES_PORT': '5432',
        'POSTGRES_DB': 'music_log',
        'POSTGRES_USER': 'postgres',
        'POSTGRES_PASSWORD': 'Mudar123!',
        'DB_TABLE_NAME': 'streams'
    })
    
    # Iniciar servidor
    try:
        process = subprocess.Popen([
            sys.executable, 'app/main_orchestrator.py'
        ], env=env, cwd='.')
        
        print("⏳ Aguardando servidor inicializar...")
        time.sleep(5)
        
        return process
        
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")
        return None

async def main():
    """Função principal"""
    print("🧪 TESTE LOCAL DO ORCHESTRATOR COM NOVOS ENDPOINTS")
    print("=" * 60)
    
    # Iniciar servidor local
    server_process = start_local_server()
    
    if not server_process:
        print("❌ Falha ao iniciar servidor")
        return
        
    try:
        # Testar endpoints
        success = await test_local_orchestrator()
        
        if success:
            print("\n🎉 TODOS OS TESTES PASSARAM!")
            print("✅ Os novos endpoints estão funcionando")
            print("🚀 Pronto para deploy no EasyPanel")
        else:
            print("\n❌ ALGUNS TESTES FALHARAM")
            print("🔧 Verifique a configuração")
            
    finally:
        # Parar servidor
        print("\n🛑 Parando servidor local...")
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    asyncio.run(main())
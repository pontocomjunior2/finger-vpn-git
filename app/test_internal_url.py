#!/usr/bin/env python3
"""
Script para testar conectividade com a URL interna do orquestrador no EasyPanel
"""

import asyncio
import aiohttp
import os
from datetime import datetime

# URL interna do Docker
ORCHESTRATOR_URL = "http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080"

async def test_internal_connectivity():
    """Testa conectividade com a URL interna do orquestrador"""
    print(f"🚀 Testando conectividade interna do Docker")
    print(f"🌐 URL interna: {ORCHESTRATOR_URL}")
    print(f"⏰ Timestamp: {datetime.now()}")
    print("=" * 60)
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            
            # Teste 1: Health check
            print("🔍 Teste 1: Health check...")
            try:
                async with session.get(f"{ORCHESTRATOR_URL}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        print(f"✅ Health check OK: {health_data}")
                    else:
                        print(f"⚠️ Health check retornou status {response.status}")
            except Exception as e:
                print(f"❌ Erro no health check: {e}")
            
            # Teste 2: Status do orquestrador
            print("\n🔍 Teste 2: Status do orquestrador...")
            try:
                async with session.get(f"{ORCHESTRATOR_URL}/status") as response:
                    if response.status == 200:
                        status_data = await response.json()
                        print(f"✅ Status OK: {status_data}")
                    else:
                        print(f"⚠️ Status retornou código {response.status}")
            except Exception as e:
                print(f"❌ Erro no status: {e}")
            
            # Teste 3: Registro de instância
            print("\n🔍 Teste 3: Teste de registro...")
            try:
                register_data = {
                    "server_id": "test_internal",
                    "ip": "127.0.0.1",
                    "port": 8000,
                    "max_streams": 5
                }
                async with session.post(f"{ORCHESTRATOR_URL}/register", json=register_data) as response:
                    if response.status == 200:
                        register_result = await response.json()
                        print(f"✅ Registro OK: {register_result}")
                    else:
                        print(f"⚠️ Registro retornou status {response.status}")
            except Exception as e:
                print(f"❌ Erro no registro: {e}")
                
    except Exception as e:
        print(f"❌ Erro geral na conectividade: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Teste de conectividade interna concluído")

if __name__ == "__main__":
    asyncio.run(test_internal_connectivity())
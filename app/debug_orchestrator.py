#!/usr/bin/env python3
"""
Script de debug para testar conectividade com o orquestrador
"""

import asyncio
import logging
import os

import aiohttp
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8080")
SERVER_ID = os.getenv("SERVER_ID", "debug_test")
MAX_STREAMS = int(os.getenv("MAX_STREAMS", "10"))

async def test_orchestrator_connectivity():
    """Testa a conectividade com o orquestrador."""
    
    print(f"🔍 Testando conectividade com orquestrador...")
    print(f"📍 URL: {ORCHESTRATOR_URL}")
    print(f"🆔 SERVER_ID: {SERVER_ID}")
    print(f"📊 MAX_STREAMS: {MAX_STREAMS}")
    print("-" * 50)
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        
        # Teste 1: Health check
        print("\n1️⃣ Testando health check...")
        try:
            async with session.get(f"{ORCHESTRATOR_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Health check OK: {data}")
                else:
                    print(f"❌ Health check falhou: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Erro no health check: {e}")
            return False
        
        # Teste 2: Registro da instância
        print("\n2️⃣ Testando registro da instância...")
        try:
            register_data = {
                "server_id": SERVER_ID,
                "ip": "127.0.0.1",
                "port": 8000,
                "max_streams": MAX_STREAMS
            }
            
            async with session.post(f"{ORCHESTRATOR_URL}/register", json=register_data) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Registro OK: {data}")
                else:
                    error_text = await response.text()
                    print(f"❌ Registro falhou: {response.status} - {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Erro no registro: {e}")
            return False
        
        # Teste 3: Heartbeat
        print("\n3️⃣ Testando heartbeat...")
        try:
            heartbeat_data = {
                "server_id": SERVER_ID,
                "current_streams": 0,
                "status": "active"
            }
            
            async with session.post(f"{ORCHESTRATOR_URL}/heartbeat", json=heartbeat_data) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Heartbeat OK: {data}")
                else:
                    error_text = await response.text()
                    print(f"❌ Heartbeat falhou: {response.status} - {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Erro no heartbeat: {e}")
            return False
        
        # Teste 4: Solicitar streams
        print("\n4️⃣ Testando solicitação de streams...")
        try:
            streams_data = {
                "server_id": SERVER_ID,
                "requested_count": 5
            }
            
            async with session.post(f"{ORCHESTRATOR_URL}/streams/assign", json=streams_data) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Solicitação de streams OK: {data}")
                else:
                    error_text = await response.text()
                    print(f"❌ Solicitação de streams falhou: {response.status} - {error_text}")
        except Exception as e:
            print(f"❌ Erro na solicitação de streams: {e}")
        
        # Teste 5: Status do orquestrador
        print("\n5️⃣ Testando status do orquestrador...")
        try:
            async with session.get(f"{ORCHESTRATOR_URL}/status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Status do orquestrador: {data}")
                else:
                    error_text = await response.text()
                    print(f"❌ Status falhou: {response.status} - {error_text}")
        except Exception as e:
            print(f"❌ Erro ao obter status: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Teste de conectividade concluído!")
    return True

if __name__ == "__main__":
    asyncio.run(test_orchestrator_connectivity())
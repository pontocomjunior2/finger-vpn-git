#!/usr/bin/env python3
"""
Script para verificar se o orquestrador está recebendo conexões da instância 1
"""

import asyncio
import aiohttp
import os
from datetime import datetime

# Configurações
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080')

async def check_orchestrator_status():
    """Verifica o status do orquestrador e instâncias conectadas"""
    try:
        async with aiohttp.ClientSession() as session:
            # Verificar status geral
            print("🔍 Verificando status do orquestrador...")
            async with session.get(f"{ORCHESTRATOR_URL}/status") as response:
                if response.status == 200:
                    status_data = await response.json()
                    print(f"✅ Status do orquestrador: {status_data}")
                    
                    # O status retorna informações agregadas, vamos verificar as instâncias separadamente
                    print(f"📊 Instâncias ativas: {status_data.get('instances', {}).get('active', 0)}")
                    print(f"📊 Total de instâncias: {status_data.get('instances', {}).get('total', 0)}")
                    print(f"📊 Streams atribuídos: {status_data.get('streams', {}).get('assigned', 0)}")
                else:
                    print(f"❌ Erro ao verificar status: {response.status}")
                    
            # Verificar instâncias específicas
            print("\n🔍 Verificando instâncias registradas...")
            async with session.get(f"{ORCHESTRATOR_URL}/instances") as response:
                if response.status == 200:
                    instances_data = await response.json()
                    print(f"📋 Instâncias registradas: {instances_data}")
                else:
                    print(f"❌ Erro ao verificar instâncias: {response.status}")
                    
    except Exception as e:
        print(f"❌ Erro na verificação: {e}")

async def main():
    print(f"🚀 Verificando conexão da instância 1 com o orquestrador")
    print(f"🌐 URL do orquestrador: {ORCHESTRATOR_URL}")
    print(f"⏰ Timestamp: {datetime.now()}")
    print("=" * 60)
    
    await check_orchestrator_status()
    
    print("\n" + "=" * 60)
    print("✅ Verificação concluída")

if __name__ == "__main__":
    asyncio.run(main())
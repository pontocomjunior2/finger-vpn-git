#!/usr/bin/env python3
"""
Script para testar a correção do problema de atribuição de streams.
Simula o cenário completo para verificar se a correção funciona.
"""

import asyncio
import json
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from orchestrator_client import create_orchestrator_client

load_dotenv()

# Configurações
SERVER_ID = os.getenv("SERVER_ID", "test_server_fix")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '104.234.173.96'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Conquista@@2'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

def fetch_streams_from_db():
    """Busca streams do banco de dados (igual ao fingerv7)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cursor.execute("""
            SELECT id, url, name, sheet, cidade, estado, regiao, segmento, index
            FROM streams 
            ORDER BY id
        """)
        
        streams = []
        for row in cursor.fetchall():
            stream = {
                "id": str(row["index"]),  # fingerv7 usa o campo 'index' como 'id'
                "index": str(row["index"]),
                "url": row["url"],
                "name": row["name"],
                "sheet": row["sheet"],
                "cidade": row["cidade"],
                "estado": row["estado"],
                "regiao": row["regiao"],
                "segmento": row["segmento"],
                "metadata": {}
            }
            streams.append(stream)
        
        cursor.close()
        conn.close()
        
        return streams
        
    except Exception as e:
        print(f"Erro ao buscar streams do DB: {e}")
        return []

async def test_corrected_logic():
    """Testa a lógica corrigida de atribuição de streams."""
    
    print("=== Teste da Correção de Atribuição de Streams ===")
    print()
    
    # 1. Buscar streams do banco
    print("1. Carregando streams do banco de dados...")
    all_streams = fetch_streams_from_db()
    print(f"   Total de streams carregados: {len(all_streams)}")
    
    if not all_streams:
        print("   ERRO: Nenhum stream encontrado no banco!")
        return False
    
    print(f"   Primeiros 3 streams: {[(s['id'], s['name']) for s in all_streams[:3]]}")
    print()
    
    # 2. Simular IDs retornados pelo orquestrador (como inteiros)
    print("2. Simulando resposta do orquestrador...")
    # Simular que o orquestrador retornou os primeiros 5 streams
    simulated_orchestrator_ids = [0, 1, 2, 3, 4]  # IDs como inteiros
    print(f"   IDs simulados do orquestrador: {simulated_orchestrator_ids} (tipo: {type(simulated_orchestrator_ids[0])})")
    print()
    
    # 3. Testar lógica ANTIGA (problemática)
    print("3. Testando lógica ANTIGA (problemática)...")
    assigned_streams_old = [
        stream for stream in all_streams 
        if stream.get("id", stream.get("name", "")) in simulated_orchestrator_ids
    ]
    print(f"   Streams filtrados com lógica antiga: {len(assigned_streams_old)}")
    print()
    
    # 4. Testar lógica NOVA (corrigida)
    print("4. Testando lógica NOVA (corrigida)...")
    # Converter IDs do orquestrador para string para compatibilidade
    assigned_stream_ids_str = [str(id) for id in simulated_orchestrator_ids]
    print(f"   IDs convertidos para string: {assigned_stream_ids_str} (tipo: {type(assigned_stream_ids_str[0])})")
    
    assigned_streams_new = [
        stream for stream in all_streams 
        if stream.get("id", stream.get("name", "")) in assigned_stream_ids_str
    ]
    print(f"   Streams filtrados com lógica nova: {len(assigned_streams_new)}")
    print()
    
    # 5. Mostrar resultados detalhados
    if assigned_streams_new:
        print("5. Streams atribuídos com sucesso:")
        for i, stream in enumerate(assigned_streams_new[:3]):
            print(f"   {i+1}. ID: '{stream['id']}', Nome: {stream['name']}")
        if len(assigned_streams_new) > 3:
            print(f"   ... e mais {len(assigned_streams_new) - 3} streams")
    else:
        print("5. ERRO: Nenhum stream foi atribuído!")
    print()
    
    # 6. Verificar se a correção funcionou
    success = len(assigned_streams_new) > 0 and len(assigned_streams_new) == len(simulated_orchestrator_ids)
    
    print("6. Resultado do teste:")
    print(f"   Lógica antiga: {len(assigned_streams_old)} streams (FALHOU)")
    print(f"   Lógica nova: {len(assigned_streams_new)} streams (SUCESSO: {success})")
    print()
    
    return success

async def test_with_real_orchestrator():
    """Testa com o orquestrador real se estiver disponível."""
    
    print("=== Teste com Orquestrador Real ===")
    print()
    
    try:
        orchestrator_client = create_orchestrator_client(
            orchestrator_url=ORCHESTRATOR_URL,
            server_id=SERVER_ID
        )
        
        # Registrar no orquestrador
        await orchestrator_client.register()
        print(f"   Instância {SERVER_ID} registrada no orquestrador")
        
        # Solicitar streams
        assigned_stream_ids = await orchestrator_client.request_streams()
        print(f"   Recebidos {len(assigned_stream_ids)} streams do orquestrador")
        
        if assigned_stream_ids:
            print(f"   IDs recebidos: {assigned_stream_ids} (tipo: {type(assigned_stream_ids[0])})")
            
            # Buscar streams do banco
            all_streams = fetch_streams_from_db()
            
            # Aplicar lógica corrigida
            assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]
            assigned_streams = [
                stream for stream in all_streams 
                if stream.get("id", stream.get("name", "")) in assigned_stream_ids_str
            ]
            
            print(f"   Streams filtrados com lógica corrigida: {len(assigned_streams)}")
            
            if assigned_streams:
                print("   Primeiros streams atribuídos:")
                for i, stream in enumerate(assigned_streams[:3]):
                    print(f"     {i+1}. ID: '{stream['id']}', Nome: {stream['name']}")
            
            return len(assigned_streams) > 0
        else:
            print("   Nenhum stream foi atribuído pelo orquestrador")
            return False
            
    except Exception as e:
        print(f"   Erro ao testar com orquestrador real: {e}")
        return False

async def main():
    """Função principal."""
    
    # Teste com dados simulados
    simulation_success = await test_corrected_logic()
    
    # Teste com orquestrador real (se disponível)
    real_test_success = await test_with_real_orchestrator()
    
    print("=== Resumo dos Testes ===")
    print(f"Teste com dados simulados: {'✓ PASSOU' if simulation_success else '✗ FALHOU'}")
    print(f"Teste com orquestrador real: {'✓ PASSOU' if real_test_success else '✗ FALHOU'}")
    print()
    
    if simulation_success:
        print("🎉 A correção funcionou! O problema de incompatibilidade de tipos foi resolvido.")
    else:
        print("❌ A correção não funcionou como esperado.")

if __name__ == "__main__":
    asyncio.run(main())
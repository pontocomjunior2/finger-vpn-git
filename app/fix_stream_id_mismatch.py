#!/usr/bin/env python3
"""
Script para diagnosticar e corrigir o problema de incompatibilidade de tipos
entre os IDs dos streams retornados pelo orquestrador e os IDs dos streams no fingerv7.
"""

import asyncio
import json
import psycopg2
from orchestrator_client import create_orchestrator_client
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações
SERVER_ID = os.getenv("SERVER_ID", "test_server")
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
    """Busca streams do banco de dados (simulando a função do fingerv7)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(psycopg2.extras.DictCursor)
        
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

async def test_orchestrator_communication():
    """Testa a comunicação com o orquestrador e identifica o problema."""
    
    print("=== Diagnóstico do Problema de Atribuição de Streams ===")
    print()
    
    # 1. Buscar streams do banco de dados
    print("1. Buscando streams do banco de dados...")
    all_streams = fetch_streams_from_db()
    print(f"   Encontrados {len(all_streams)} streams no banco")
    
    if all_streams:
        print(f"   Exemplo de stream do DB: ID='{all_streams[0]['id']}' (tipo: {type(all_streams[0]['id'])})")
        print(f"   Primeiros 5 IDs: {[s['id'] for s in all_streams[:5]]}")
    print()
    
    # 2. Testar comunicação com orquestrador
    print("2. Testando comunicação com orquestrador...")
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
            print(f"   Exemplo de ID do orquestrador: {assigned_stream_ids[0]} (tipo: {type(assigned_stream_ids[0])})")
            print(f"   IDs recebidos: {assigned_stream_ids}")
        print()
        
        # 3. Testar filtragem atual (problemática)
        print("3. Testando filtragem atual (problemática)...")
        assigned_streams_current = [
            stream for stream in all_streams 
            if stream.get("id", stream.get("name", "")) in assigned_stream_ids
        ]
        print(f"   Streams filtrados com lógica atual: {len(assigned_streams_current)}")
        print()
        
        # 4. Testar filtragem corrigida
        print("4. Testando filtragem corrigida...")
        # Converter IDs do orquestrador para string para comparação
        assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]
        
        assigned_streams_fixed = [
            stream for stream in all_streams 
            if stream.get("id", stream.get("name", "")) in assigned_stream_ids_str
        ]
        print(f"   Streams filtrados com lógica corrigida: {len(assigned_streams_fixed)}")
        
        if assigned_streams_fixed:
            print(f"   Exemplo de stream filtrado: {assigned_streams_fixed[0]['name']} (ID: {assigned_streams_fixed[0]['id']})")
        print()
        
        # 5. Análise detalhada
        print("5. Análise detalhada do problema:")
        print(f"   - Orquestrador retorna IDs como: {type(assigned_stream_ids[0]) if assigned_stream_ids else 'N/A'}")
        print(f"   - fingerv7 espera IDs como: {type(all_streams[0]['id']) if all_streams else 'N/A'}")
        print(f"   - Incompatibilidade de tipos causa falha na filtragem")
        print()
        
        # 6. Verificar mapeamento entre campo 'id' da tabela e campo 'index'
        print("6. Verificando mapeamento entre campos 'id' e 'index' da tabela...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, index FROM streams ORDER BY id LIMIT 5")
        
        print("   Mapeamento id -> index:")
        for row in cursor.fetchall():
            db_id, db_index = row
            print(f"   DB id={db_id} -> index='{db_index}'")
        
        cursor.close()
        conn.close()
        print()
        
        return True
        
    except Exception as e:
        print(f"   Erro ao comunicar com orquestrador: {e}")
        return False

def generate_fix():
    """Gera o código corrigido para o fingerv7.py."""
    
    print("=== Solução Proposta ===")
    print()
    print("O problema está na linha 2715 do fingerv7.py:")
    print("ATUAL (problemática):")
    print("    if stream.get('id', stream.get('name', '')) in assigned_stream_ids")
    print()
    print("CORRIGIDA:")
    print("    if stream.get('id', stream.get('name', '')) in [str(id) for id in assigned_stream_ids]")
    print()
    print("OU melhor ainda:")
    print("    # Converter IDs do orquestrador para string")
    print("    assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]")
    print("    assigned_streams = [")
    print("        stream for stream in all_streams ")
    print("        if stream.get('id', stream.get('name', '')) in assigned_stream_ids_str")
    print("    ]")
    print()

async def main():
    """Função principal."""
    success = await test_orchestrator_communication()
    
    if success:
        generate_fix()
        print("Diagnóstico concluído com sucesso!")
    else:
        print("Falha no diagnóstico. Verifique a conexão com o orquestrador.")

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
import os
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

try:
    # Conectar ao banco de dados
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB'),
        port=os.getenv('POSTGRES_PORT')
    )
    
    cursor = conn.cursor()
    
    print("=== Estado atual da tabela stream_locks ===")
    cursor.execute("""
        SELECT stream_id, server_id, heartbeat_at, 
               EXTRACT(EPOCH FROM (NOW() - heartbeat_at))/60 as minutes_ago
        FROM stream_locks 
        ORDER BY stream_id
    """)
    
    rows = cursor.fetchall()
    
    if not rows:
        print("Nenhum lock encontrado na tabela stream_locks")
    else:
        print(f"{'Stream ID':<10} | {'Server ID':<10} | {'Heartbeat':<20} | {'Min Ago':<8}")
        print("-" * 60)
        
        for row in rows:
            stream_id, server_id, heartbeat_at, minutes_ago = row
            print(f"{stream_id:<10} | {server_id:<10} | {heartbeat_at} | {minutes_ago:.1f}")
    
    print(f"\nTotal de locks: {len(rows)}")
    
    # Verificar locks expirados (mais de 2 minutos)
    cursor.execute("""
        SELECT COUNT(*) FROM stream_locks 
        WHERE heartbeat_at < NOW() - INTERVAL '2 minutes'
    """)
    
    expired_count = cursor.fetchone()[0]
    print(f"Locks expirados (>2 min): {expired_count}")
    
    # Verificar distribuição por servidor
    cursor.execute("""
        SELECT server_id, COUNT(*) as lock_count
        FROM stream_locks 
        GROUP BY server_id
        ORDER BY server_id
    """)
    
    server_distribution = cursor.fetchall()
    print("\n=== Distribuição de locks por servidor ===")
    for server_id, count in server_distribution:
        print(f"Servidor {server_id}: {count} locks")
    
    conn.close()
    
except Exception as e:
    print(f"Erro ao consultar banco de dados: {e}")
    import traceback
    traceback.print_exc()
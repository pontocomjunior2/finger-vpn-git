#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Carregar variáveis de ambiente
root_env_file = Path(__file__).parent.parent / ".env"
if root_env_file.exists():
    load_dotenv(root_env_file)
    print(f"Variáveis carregadas de {root_env_file}")

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

try:
    # Conectar ao banco
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    print("\n=== ATRIBUIÇÕES DE STREAMS ===")
    cursor.execute("""
        SELECT server_id, stream_id, status, assigned_at 
        FROM orchestrator_stream_assignments 
        ORDER BY assigned_at DESC
    """)
    
    assignments = cursor.fetchall()
    if assignments:
        print(f"Total de atribuições: {len(assignments)}")
        for server_id, stream_id, status, assigned_at in assignments:
            print(f"Server: {server_id}, Stream: {stream_id}, Status: {status}, Assigned: {assigned_at}")
    else:
        print("Nenhuma atribuição encontrada")
    
    print("\n=== INSTÂNCIAS REGISTRADAS ===")
    cursor.execute("""
        SELECT server_id, ip, port, max_streams, current_streams, status, last_heartbeat 
        FROM orchestrator_instances 
        ORDER BY last_heartbeat DESC
    """)
    
    instances = cursor.fetchall()
    if instances:
        print(f"Total de instâncias: {len(instances)}")
        for server_id, ip, port, max_streams, current_streams, status, last_heartbeat in instances:
            print(f"Server: {server_id}, IP: {ip}:{port}, Streams: {current_streams}/{max_streams}, Status: {status}, Last HB: {last_heartbeat}")
    else:
        print("Nenhuma instância encontrada")
        
except Exception as e:
    print(f"Erro: {e}")
finally:
    if 'conn' in locals():
        conn.close()
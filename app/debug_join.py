#!/usr/bin/env python3
"""
Debug do JOIN entre assignments e instances.
"""

import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
print(f"Variáveis carregadas de {env_path}")

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

print(f"Conectando ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
print(f"Usuário: {DB_CONFIG['user']}")
print(f"Senha: {'*' * len(DB_CONFIG['password'])}")
print()

def debug_join():
    """Debug do JOIN entre tabelas."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("=== DEBUG JOIN ASSIGNMENTS x INSTANCES ===")
        
        # 1. Verificar assignments
        cursor.execute("SELECT * FROM orchestrator_stream_assignments ORDER BY assigned_at DESC")
        assignments = cursor.fetchall()
        print(f"\nAssignments na tabela ({len(assignments)}):")
        for assignment in assignments:
            print(f"  - Stream {assignment['stream_id']} -> {assignment['server_id']} ({assignment['status']})")
        
        # 2. Verificar instances
        cursor.execute("SELECT * FROM orchestrator_instances ORDER BY registered_at DESC")
        instances = cursor.fetchall()
        print(f"\nInstances na tabela ({len(instances)}):")
        for instance in instances:
            print(f"  - {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} ({instance['status']})")
        
        # 3. Verificar server_ids que existem em assignments mas não em instances
        cursor.execute("""
            SELECT DISTINCT osa.server_id
            FROM orchestrator_stream_assignments osa
            LEFT JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE oi.server_id IS NULL
        """)
        orphaned_assignments = cursor.fetchall()
        
        if orphaned_assignments:
            print(f"\n❌ Assignments órfãos (sem instance correspondente):")
            for orphan in orphaned_assignments:
                print(f"  - {orphan['server_id']}")
        else:
            print(f"\n✅ Todos os assignments têm instances correspondentes")
        
        # 4. Testar o JOIN exato do endpoint
        cursor.execute("""
            SELECT osa.stream_id, osa.server_id, osa.assigned_at, osa.status,
                   oi.ip, oi.port
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
            ORDER BY osa.assigned_at DESC
        """)
        
        join_results = cursor.fetchall()
        print(f"\nResultados do JOIN do endpoint ({len(join_results)}):")
        for result in join_results:
            print(f"  - Stream {result['stream_id']} -> {result['server_id']} @ {result['ip']}:{result['port']}")
        
        # 5. Verificar se há assignments ativos
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments WHERE status = 'active'")
        active_assignments = cursor.fetchone()['count']
        print(f"\nAssignments ativos: {active_assignments}")
        
        # 6. Verificar se há instances ativas
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_instances WHERE status = 'active'")
        active_instances = cursor.fetchone()['count']
        print(f"Instances ativas: {active_instances}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro no debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_join()
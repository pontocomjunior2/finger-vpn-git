#!/usr/bin/env python3
"""
Script para sincronizar assignments com os contadores das instances.
"""

import json
import os
import sys

import psycopg2
import psycopg2.extras
import requests
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

ORCHESTRATOR_URL = "http://localhost:8080"

print(f"Conectando ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
print(f"Usuário: {DB_CONFIG['user']}")
print(f"Senha: {'*' * len(DB_CONFIG['password'])}")
print()

def fix_assignments_sync():
    """Corrige sincronização entre assignments e instances."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("=== CORREÇÃO DE SINCRONIZAÇÃO ===")
        
        # 1. Verificar estado atual
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments")
        assignments_count = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT server_id, current_streams, max_streams, status
            FROM orchestrator_instances 
            ORDER BY server_id
        """)
        instances = cursor.fetchall()
        
        print(f"Assignments na tabela: {assignments_count}")
        print(f"Instances encontradas: {len(instances)}")
        
        total_streams_in_instances = sum(instance['current_streams'] for instance in instances)
        print(f"Total de streams nos contadores: {total_streams_in_instances}")
        
        if assignments_count == 0 and total_streams_in_instances > 0:
            print("\n❌ INCONSISTÊNCIA DETECTADA: Contadores indicam streams atribuídos, mas tabela de assignments está vazia")
            
            # Resetar contadores das instances
            print("\n🔄 Resetando contadores das instances...")
            cursor.execute("UPDATE orchestrator_instances SET current_streams = 0")
            conn.commit()
            print("Contadores resetados")
            
            # Reatribuir streams via API
            print("\n🔄 Reatribuindo streams via API...")
            for instance in instances:
                if instance['current_streams'] > 0:
                    server_id = instance['server_id']
                    streams_to_assign = instance['current_streams']
                    
                    print(f"Reatribuindo {streams_to_assign} streams para {server_id}...")
                    
                    try:
                        response = requests.post(
                            f"{ORCHESTRATOR_URL}/streams/assign",
                            json={
                                "server_id": server_id,
                                "requested_count": streams_to_assign
                            },
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            print(f"  ✅ {result.get('count', 0)} streams atribuídos para {server_id}")
                        else:
                            print(f"  ❌ Erro na atribuição para {server_id}: {response.status_code} - {response.text}")
                            
                    except Exception as e:
                        print(f"  ❌ Erro na requisição para {server_id}: {e}")
            
            # Verificar resultado
            print("\n📊 Verificando resultado...")
            cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments")
            new_assignments_count = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT server_id, current_streams
                FROM orchestrator_instances 
                ORDER BY server_id
            """)
            new_instances = cursor.fetchall()
            
            print(f"Assignments após correção: {new_assignments_count}")
            for instance in new_instances:
                print(f"  - {instance['server_id']}: {instance['current_streams']} streams")
            
            if new_assignments_count > 0:
                print("\n✅ Sincronização corrigida com sucesso!")
            else:
                print("\n❌ Problema persiste após correção")
                
        else:
            print("\n✅ Sincronização está correta")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro na correção: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_assignments_sync()
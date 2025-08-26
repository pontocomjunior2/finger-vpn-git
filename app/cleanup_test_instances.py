#!/usr/bin/env python3
"""
Script para limpar todas as instâncias de teste do banco de dados.
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}

def get_db_connection():
    """Conecta ao banco de dados."""
    return psycopg2.connect(**DB_CONFIG)

def cleanup_all_test_instances():
    """Remove todas as instâncias de teste do banco."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        print("🧹 LIMPANDO INSTÂNCIAS DE TESTE")
        print("=" * 50)
        
        # Listar instâncias de teste antes da limpeza
        cursor.execute("""
            SELECT server_id, current_streams, max_streams, status
            FROM orchestrator_instances
            WHERE server_id LIKE 'test%' 
               OR server_id LIKE 'debug%'
               OR server_id LIKE '%test%'
            ORDER BY server_id
        """)
        
        test_instances = cursor.fetchall()
        
        if test_instances:
            print(f"📋 Instâncias de teste encontradas ({len(test_instances)}):")
            for instance in test_instances:
                print(f"  - {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} ({instance['status']})")
            
            # Remover assignments de streams das instâncias de teste
            print("\n🗑️  Removendo assignments de streams...")
            cursor.execute("""
                DELETE FROM orchestrator_stream_assignments
                WHERE server_id LIKE 'test%' 
                   OR server_id LIKE 'debug%'
                   OR server_id LIKE '%test%'
            """)
            
            deleted_assignments = cursor.rowcount
            print(f"   ✅ {deleted_assignments} assignments removidos")
            
            # Remover instâncias de teste
            print("\n🗑️  Removendo instâncias de teste...")
            cursor.execute("""
                DELETE FROM orchestrator_instances
                WHERE server_id LIKE 'test%' 
                   OR server_id LIKE 'debug%'
                   OR server_id LIKE '%test%'
            """)
            
            deleted_instances = cursor.rowcount
            print(f"   ✅ {deleted_instances} instâncias removidas")
            
        else:
            print("✅ Nenhuma instância de teste encontrada")
        
        # Mostrar estado final
        print("\n📊 ESTADO FINAL")
        print("=" * 30)
        
        cursor.execute("""
            SELECT server_id, current_streams, max_streams, status
            FROM orchestrator_instances
            WHERE status = 'active'
            ORDER BY current_streams DESC
        """)
        
        remaining_instances = cursor.fetchall()
        
        if remaining_instances:
            print(f"📋 Instâncias ativas restantes ({len(remaining_instances)}):")
            total_streams = 0
            total_capacity = 0
            
            for instance in remaining_instances:
                print(f"  - {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']}")
                total_streams += instance['current_streams']
                total_capacity += instance['max_streams']
            
            print(f"\n📈 Resumo:")
            print(f"   Total de streams: {total_streams}")
            print(f"   Capacidade total: {total_capacity}")
            print(f"   Utilização: {(total_streams/total_capacity*100):.1f}%")
        else:
            print("❌ Nenhuma instância ativa encontrada")
        
        conn.commit()
        print("\n✅ Limpeza concluída com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro na limpeza: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    cleanup_all_test_instances()
#!/usr/bin/env python3
"""
Script para verificar a estrutura do banco de dados
"""

import os

import psycopg2

# Configurações do banco
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '104.234.173.96'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Conquista@@2'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

def check_tables():
    """Verifica as tabelas do banco de dados"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        
        print("🔍 VERIFICANDO ESTRUTURA DO BANCO DE DADOS")
        print("=" * 60)
        
        # Listar todas as tabelas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"\n📋 Tabelas encontradas ({len(tables)}):")
        for table in tables:
            print(f"   - {table[0]}")
        
        # Verificar tabelas relacionadas ao orquestrador
        orchestrator_tables = [t[0] for t in tables if 'orchestr' in t[0].lower()]
        
        print(f"\n🎯 Tabelas do orquestrador ({len(orchestrator_tables)}):")
        for table in orchestrator_tables:
            print(f"   - {table}")
            
            # Mostrar estrutura da tabela
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            print(f"     Colunas ({len(columns)}):")
            for col_name, data_type, nullable in columns:
                null_info = "NULL" if nullable == 'YES' else "NOT NULL"
                print(f"       - {col_name}: {data_type} ({null_info})")
            print()
        
        # Verificar se existe tabela de streams
        stream_tables = [t[0] for t in tables if 'stream' in t[0].lower()]
        
        if stream_tables:
            print(f"\n📡 Tabelas de streams ({len(stream_tables)}):")
            for table in stream_tables:
                print(f"   - {table}")
        else:
            print(f"\n❌ Nenhuma tabela de streams encontrada")
            print(f"\n💡 Possíveis soluções:")
            print(f"   1. Os streams podem estar armazenados na tabela orchestrator_instances")
            print(f"   2. A tabela de streams pode ter um nome diferente")
            print(f"   3. Os streams podem ser gerenciados apenas em memória")
        
        # Verificar dados da tabela orchestrator_instances
        if 'orchestrator_instances' in [t[0] for t in tables]:
            print(f"\n📊 Dados da tabela orchestrator_instances:")
            cursor.execute("""
                SELECT server_id, current_streams, max_streams, status
                FROM orchestrator_instances 
                WHERE current_streams > 0
                ORDER BY current_streams DESC
                LIMIT 10
            """)
            
            instances = cursor.fetchall()
            print(f"   Instâncias com streams ativos:")
            for server_id, current, max_streams, status in instances:
                print(f"     - {server_id}: {current}/{max_streams} ({status})")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erro ao verificar banco: {e}")

if __name__ == "__main__":
    check_tables()
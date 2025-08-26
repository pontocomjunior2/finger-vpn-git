#!/usr/bin/env python3
"""
Verifica as tabelas existentes relacionadas ao orquestrador.
"""

import os

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

def connect_db():
    """Conecta ao banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        return None

def check_orchestrator_tables():
    """Verifica as tabelas relacionadas ao orquestrador."""
    conn = connect_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        print("=== TABELAS EXISTENTES NO BANCO ===")
        cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print(f"Total de tabelas encontradas: {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        print("\n=== VERIFICANDO TABELAS ESPECÍFICAS ===")
        
        # Verificar se existe tabela de streams
        table_checks = [
            'streams',
            'stream_assignments', 
            'instances',
            'server_instances',
            'orchestrator_instances',
            'distribution_logs',
            'instance_events',
            'heartbeats'
        ]
        
        existing_tables = []
        for table_name in table_checks:
            cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
            """, (table_name,))
            
            exists = cursor.fetchone()[0]
            status = "✅ EXISTE" if exists else "❌ NÃO EXISTE"
            print(f"  {table_name}: {status}")
            
            if exists:
                existing_tables.append(table_name)
        
        print("\n=== ESTRUTURA DAS TABELAS EXISTENTES ===")
        for table_name in existing_tables:
            print(f"\n--- Estrutura da tabela '{table_name}' ---")
            cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = %s
            ORDER BY ordinal_position;
            """, (table_name,))
            
            columns = cursor.fetchall()
            for column in columns:
                col_name, data_type, is_nullable, col_default = column
                nullable = "NULL" if is_nullable == 'YES' else "NOT NULL"
                default = f" DEFAULT {col_default}" if col_default else ""
                print(f"  {col_name}: {data_type} {nullable}{default}")
        
        print("\n=== DADOS DAS TABELAS RELACIONADAS AO ORQUESTRADOR ===")
        
        # Se existe tabela streams, mostrar alguns dados
        if 'streams' in existing_tables:
            print("\n--- Dados da tabela 'streams' ---")
            cursor.execute("SELECT COUNT(*) FROM streams;")
            count = cursor.fetchone()[0]
            print(f"Total de streams: {count}")
            
            if count > 0:
                cursor.execute("""
                SELECT id, name, url 
                FROM streams 
                ORDER BY id 
                LIMIT 5;
                """)
                
                streams = cursor.fetchall()
                print("Primeiros 5 streams:")
                for stream in streams:
                    print(f"  ID {stream[0]}: {stream[1]} - {stream[2]}")
        
        # Se existe tabela de heartbeats ou similar
        for table in ['heartbeats', 'server_instances', 'orchestrator_instances']:
            if table in existing_tables:
                print(f"\n--- Dados da tabela '{table}' ---")
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                print(f"Total de registros: {count}")
                
                if count > 0:
                    cursor.execute(f"SELECT * FROM {table} ORDER BY id LIMIT 3;")
                    records = cursor.fetchall()
                    print("Primeiros registros:")
                    for record in records:
                        print(f"  {record}")
        
    except Exception as e:
        print(f"Erro durante a verificação: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_orchestrator_tables()
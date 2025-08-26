#!/usr/bin/env python3
"""
Verifica a estrutura da tabela orchestrator_stream_assignments.
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

def check_assignments_table():
    """Verifica a estrutura da tabela orchestrator_stream_assignments."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("=== ESTRUTURA DA TABELA orchestrator_stream_assignments ===")
        cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'orchestrator_stream_assignments'
        ORDER BY ordinal_position;
        """)
        
        columns = cursor.fetchall()
        if columns:
            print("Colunas encontradas:")
            for col in columns:
                col_name, data_type, is_nullable, col_default = col
                print(f"  {col_name} ({data_type}) - Nullable: {is_nullable} - Default: {col_default}")
        else:
            print("❌ Tabela 'orchestrator_stream_assignments' não encontrada")
            
            # Verificar se existe alguma tabela similar
            print("\nVerificando tabelas similares...")
            cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name LIKE '%assignment%' OR table_name LIKE '%stream%'
            ORDER BY table_name;
            """)
            
            similar_tables = cursor.fetchall()
            if similar_tables:
                print("Tabelas relacionadas encontradas:")
                for table in similar_tables:
                    print(f"  - {table[0]}")
            else:
                print("Nenhuma tabela relacionada encontrada")
        
        # Verificar dados de exemplo se a tabela existir
        if columns:
            print("\n=== DADOS DE EXEMPLO ===")
            cursor.execute("""
            SELECT * FROM orchestrator_stream_assignments 
            ORDER BY id DESC 
            LIMIT 5;
            """)
            
            sample_data = cursor.fetchall()
            if sample_data:
                print("Últimos 5 registros:")
                for i, row in enumerate(sample_data, 1):
                    print(f"  {i}. {row}")
            else:
                print("Tabela vazia")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_assignments_table()
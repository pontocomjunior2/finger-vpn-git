#!/usr/bin/env python3
"""
Script para verificar a estrutura das tabelas do orquestrador
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def check_table_structure():
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        print("=== Estrutura das Tabelas do Orquestrador ===")
        print()
        
        # Verificar tabela orchestrator_instances
        print("1. Tabela orchestrator_instances:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'orchestrator_instances'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        if columns:
            for col in columns:
                print(f"  - {col['column_name']}: {col['data_type']} ({'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'})")
        else:
            print("  Tabela não encontrada")
        
        print()
        
        # Verificar tabela orchestrator_stream_assignments
        print("2. Tabela orchestrator_stream_assignments:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'orchestrator_stream_assignments'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        if columns:
            for col in columns:
                print(f"  - {col['column_name']}: {col['data_type']} ({'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'})")
        else:
            print("  Tabela não encontrada")
        
        print()
        
        # Verificar dados atuais
        print("3. Dados atuais das instâncias:")
        cursor.execute("SELECT * FROM orchestrator_instances LIMIT 5")
        instances = cursor.fetchall()
        
        if instances:
            for instance in instances:
                print(f"  {dict(instance)}")
        else:
            print("  Nenhuma instância encontrada")
        
        print()
        
        # Verificar assignments
        print("4. Contagem de assignments por instância:")
        cursor.execute("""
            SELECT server_id, COUNT(*) as assignment_count
            FROM orchestrator_stream_assignments 
            GROUP BY server_id
            ORDER BY server_id
        """)
        
        assignments = cursor.fetchall()
        if assignments:
            for assignment in assignments:
                print(f"  Instância {assignment['server_id']}: {assignment['assignment_count']} assignments")
        else:
            print("  Nenhum assignment encontrado")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_table_structure()
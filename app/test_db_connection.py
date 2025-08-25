#!/usr/bin/env python3
"""
Script para testar conexão com banco de dados
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

def test_connection():
    # Carregar .env da raiz
    root_env = Path(__file__).parent.parent / ".env"
    if root_env.exists():
        load_dotenv(root_env)
        print(f"✓ Carregado .env de: {root_env}")
    
    # Mostrar variáveis carregadas
    print("\n=== Variáveis de Ambiente ===")
    print(f"POSTGRES_HOST: {os.getenv('POSTGRES_HOST')}")
    print(f"POSTGRES_USER: {os.getenv('POSTGRES_USER')}")
    print(f"POSTGRES_PASSWORD: {'*' * len(os.getenv('POSTGRES_PASSWORD', ''))}")
    print(f"POSTGRES_DB: {os.getenv('POSTGRES_DB')}")
    print(f"POSTGRES_PORT: {os.getenv('POSTGRES_PORT')}")
    
    # Testar conexão
    try:
        conn_params = {
            'host': os.getenv('POSTGRES_HOST'),
            'database': os.getenv('POSTGRES_DB'),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD'),
            'port': int(os.getenv('POSTGRES_PORT', 5432))
        }
        
        print(f"\n=== Testando Conexão ===")
        print(f"Conectando em: {conn_params['host']}:{conn_params['port']}")
        print(f"Banco: {conn_params['database']}")
        print(f"Usuário: {conn_params['user']}")
        
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Testar query simples
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"\n✓ CONEXÃO SUCESSO!")
        print(f"PostgreSQL: {version}")
        
        # Verificar se tabelas do orquestrador existem
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('orchestrator_instances', 'orchestrator_streams');
        """)
        
        tables = cursor.fetchall()
        print(f"\nTabelas do orquestrador encontradas: {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERRO DE CONEXÃO: {e}")
        return False

if __name__ == "__main__":
    test_connection()
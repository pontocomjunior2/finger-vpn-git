#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def check_database_tables():
    """Verifica as tabelas do banco de dados do orquestrador."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            port=os.getenv('POSTGRES_PORT'),
            database=os.getenv('POSTGRES_DB'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD')
        )
        
        cursor = conn.cursor()
        
        # Verificar tabelas no schema orchestrator
        print("=== VERIFICAÇÃO DE TABELAS ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'orchestrator'
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print(f"Tabelas no schema 'orchestrator': {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Verificar se a tabela streams existe
        if ('streams',) in tables:
            print("\n=== VERIFICAÇÃO DA TABELA STREAMS ===")
            cursor.execute("SELECT COUNT(*) FROM orchestrator.streams;")
            count = cursor.fetchone()[0]
            print(f"Número de streams na tabela: {count}")
            
            # Mostrar estrutura da tabela
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'orchestrator' AND table_name = 'streams'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            print("\nEstrutura da tabela streams:")
            for col in columns:
                print(f"  - {col[0]} ({col[1]}) - Nullable: {col[2]}")
                
            # Verificar se há dados
            if count > 0:
                cursor.execute("SELECT * FROM orchestrator.streams LIMIT 5;")
                rows = cursor.fetchall()
                print("\nPrimeiros 5 registros:")
                for row in rows:
                    print(f"  {row}")
        else:
            print("\n❌ TABELA 'streams' NÃO ENCONTRADA no schema 'orchestrator'")
        
        # Verificar se existe tabela streams sem schema
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'streams' AND table_schema = 'public';
        """)
        
        public_streams = cursor.fetchall()
        if public_streams:
            print("\n=== TABELA STREAMS NO SCHEMA PUBLIC ===")
            cursor.execute("SELECT COUNT(*) FROM public.streams;")
            count = cursor.fetchone()[0]
            print(f"Número de streams na tabela public.streams: {count}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro ao verificar banco de dados: {e}")

if __name__ == "__main__":
    check_database_tables()
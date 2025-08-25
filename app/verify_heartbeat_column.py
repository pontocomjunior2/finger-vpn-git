#!/usr/bin/env python3
"""
Script para verificar e diagnosticar problemas com a coluna heartbeat_at
na tabela stream_locks
"""

import psycopg2
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv(dotenv_path='.env')

DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def main():
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        with conn.cursor() as cursor:
            print("=== DIAGNÓSTICO DA TABELA STREAM_LOCKS ===")
            
            # 1. Verificar se a tabela existe
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'stream_locks'
                )
            """)
            table_exists = cursor.fetchone()[0]
            print(f"1. Tabela stream_locks existe: {table_exists}")
            
            if not table_exists:
                print("ERRO: Tabela stream_locks não existe!")
                return
            
            # 2. Verificar estrutura da tabela
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'stream_locks'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            print("\n2. Estrutura da tabela stream_locks:")
            for col in columns:
                print(f"   - {col[0]} ({col[1]}) - Nullable: {col[2]} - Default: {col[3]}")
            
            # 3. Verificar especificamente a coluna heartbeat_at
            heartbeat_column = [col for col in columns if col[0] == 'heartbeat_at']
            if heartbeat_column:
                print(f"\n3. Coluna heartbeat_at encontrada: {heartbeat_column[0]}")
            else:
                print("\n3. PROBLEMA: Coluna heartbeat_at NÃO encontrada!")
                print("   Tentando adicionar a coluna...")
                
                try:
                    cursor.execute("""
                        ALTER TABLE stream_locks 
                        ADD COLUMN heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                    """)
                    conn.commit()
                    print("   ✓ Coluna heartbeat_at adicionada com sucesso!")
                except Exception as e:
                    print(f"   ✗ Erro ao adicionar coluna: {e}")
                    conn.rollback()
            
            # 4. Testar consulta que estava falhando
            print("\n4. Testando consulta que estava falhando...")
            try:
                cursor.execute("""
                    SELECT server_id FROM stream_locks 
                    WHERE stream_id = %s 
                    AND heartbeat_at > NOW() - INTERVAL '2 minutes'
                """, ('test_stream',))
                result = cursor.fetchall()
                print(f"   ✓ Consulta executada com sucesso! Resultados: {len(result)}")
            except Exception as e:
                print(f"   ✗ Erro na consulta: {e}")
            
            # 5. Verificar dados na tabela
            cursor.execute("SELECT COUNT(*) FROM stream_locks")
            count = cursor.fetchone()[0]
            print(f"\n5. Número de registros na tabela: {count}")
            
            if count > 0:
                cursor.execute("""
                    SELECT stream_id, server_id, heartbeat_at 
                    FROM stream_locks 
                    ORDER BY heartbeat_at DESC 
                    LIMIT 5
                """)
                recent_locks = cursor.fetchall()
                print("   Últimos 5 locks:")
                for lock in recent_locks:
                    print(f"     - Stream: {lock[0]}, Server: {lock[1]}, Heartbeat: {lock[2]}")
            
            # 6. Verificar permissões
            cursor.execute("""
                SELECT has_table_privilege(current_user, 'stream_locks', 'SELECT'),
                       has_table_privilege(current_user, 'stream_locks', 'INSERT'),
                       has_table_privilege(current_user, 'stream_locks', 'UPDATE'),
                       has_table_privilege(current_user, 'stream_locks', 'DELETE')
            """)
            perms = cursor.fetchone()
            print(f"\n6. Permissões do usuário atual:")
            print(f"   - SELECT: {perms[0]}")
            print(f"   - INSERT: {perms[1]}")
            print(f"   - UPDATE: {perms[2]}")
            print(f"   - DELETE: {perms[3]}")
            
        conn.close()
        print("\n=== DIAGNÓSTICO CONCLUÍDO ===")
        
    except Exception as e:
        print(f"Erro durante diagnóstico: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
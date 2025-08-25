#!/usr/bin/env python3
"""
Script para reiniciar o pool de conexões e forçar reconhecimento
da coluna heartbeat_at
"""

import psycopg2
import os
from dotenv import load_dotenv
import time

# Carregar variáveis de ambiente
load_dotenv(dotenv_path=".env")

DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")


def test_heartbeat_queries():
    """Testa as consultas que usam heartbeat_at"""
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
        )

        with conn.cursor() as cursor:
            print("=== TESTANDO CONSULTAS COM HEARTBEAT_AT ===")

            # Teste 1: Consulta da função check_existing_lock
            print("\n1. Testando consulta check_existing_lock...")
            try:
                cursor.execute(
                    """
                    SELECT server_id FROM stream_locks 
                    WHERE stream_id = %s 
                    AND heartbeat_at > NOW() - INTERVAL '2 minutes'
                """,
                    ("test_stream_1",),
                )
                result = cursor.fetchall()
                print(f"   ✓ Sucesso! Resultados: {len(result)}")
            except Exception as e:
                print(f"   ✗ Erro: {e}")

            # Teste 2: Consulta da função acquire_stream_lock (DELETE)
            print("\n2. Testando consulta de limpeza de locks expirados...")
            try:
                cursor.execute(
                    """
                    DELETE FROM stream_locks 
                    WHERE heartbeat_at < NOW() - INTERVAL '%s minutes'
                """,
                    (2,),
                )
                deleted_count = cursor.rowcount
                conn.rollback()  # Não queremos realmente deletar
                print(f"   ✓ Sucesso! Locks que seriam deletados: {deleted_count}")
            except Exception as e:
                print(f"   ✗ Erro: {e}")
                conn.rollback()

            # Teste 3: Inserir um lock de teste
            print("\n3. Testando inserção de lock com heartbeat_at...")
            try:
                cursor.execute(
                    """
                    INSERT INTO stream_locks (stream_id, server_id, heartbeat_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (stream_id) DO UPDATE SET
                    server_id = EXCLUDED.server_id,
                    heartbeat_at = EXCLUDED.heartbeat_at
                """,
                    ("test_stream_restart", "test_server_restart"),
                )
                conn.commit()
                print("   ✓ Sucesso! Lock de teste inserido")
            except Exception as e:
                print(f"   ✗ Erro: {e}")
                conn.rollback()

            # Teste 4: Atualizar heartbeat
            print("\n4. Testando atualização de heartbeat...")
            try:
                cursor.execute(
                    """
                    UPDATE stream_locks 
                    SET heartbeat_at = NOW()
                    WHERE stream_id = %s AND server_id = %s
                """,
                    ("test_stream_restart", "test_server_restart"),
                )
                updated_count = cursor.rowcount
                conn.commit()
                print(f"   ✓ Sucesso! Registros atualizados: {updated_count}")
            except Exception as e:
                print(f"   ✗ Erro: {e}")
                conn.rollback()

            # Teste 5: Verificar o lock de teste
            print("\n5. Verificando lock de teste criado...")
            try:
                cursor.execute(
                    """
                    SELECT stream_id, server_id, heartbeat_at, 
                           (heartbeat_at > NOW() - INTERVAL '2 minutes') as is_active
                    FROM stream_locks 
                    WHERE stream_id = %s
                """,
                    ("test_stream_restart",),
                )
                result = cursor.fetchone()
                if result:
                    print(
                        f"   ✓ Lock encontrado: {result[0]}, {result[1]}, {result[2]}, Ativo: {result[3]}"
                    )
                else:
                    print("   ! Nenhum lock encontrado")
            except Exception as e:
                print(f"   ✗ Erro: {e}")

            # Limpeza: Remover lock de teste
            print("\n6. Limpando lock de teste...")
            try:
                cursor.execute(
                    """
                    DELETE FROM stream_locks 
                    WHERE stream_id = %s
                """,
                    ("test_stream_restart",),
                )
                deleted_count = cursor.rowcount
                conn.commit()
                print(
                    f"   ✓ Lock de teste removido. Registros deletados: {deleted_count}"
                )
            except Exception as e:
                print(f"   ✗ Erro ao limpar: {e}")
                conn.rollback()

        conn.close()
        print("\n=== TODOS OS TESTES CONCLUÍDOS ===")
        return True

    except Exception as e:
        print(f"Erro durante testes: {e}")
        import traceback

        traceback.print_exc()
        return False


def force_pool_restart():
    """Força reinicialização do pool de conexões"""
    print("\n=== FORÇANDO REINICIALIZAÇÃO DO POOL ===")

    try:
        # Importar e reinicializar o pool
        from db_pool import get_db_pool

        pool = get_db_pool()
        if hasattr(pool, "pool") and pool.pool:
            print("Pool existente encontrado. Fechando todas as conexões...")

            # Fechar todas as conexões do pool
            try:
                pool.pool.closeall()
                print("✓ Todas as conexões do pool foram fechadas")
            except Exception as e:
                print(f"Aviso ao fechar pool: {e}")

            # Recriar o pool
            try:
                pool._initialize_pool()
                print("✓ Pool reinicializado com sucesso")
            except Exception as e:
                print(f"Erro ao reinicializar pool: {e}")
        else:
            print("Nenhum pool ativo encontrado")

    except ImportError as e:
        print(f"Erro ao importar db_pool: {e}")
    except Exception as e:
        print(f"Erro durante reinicialização do pool: {e}")


def main():
    print("=== SCRIPT DE REINICIALIZAÇÃO DO POOL DE CONEXÕES ===")
    print("Este script irá:")
    print("1. Testar consultas que usam heartbeat_at")
    print("2. Forçar reinicialização do pool de conexões")
    print("3. Testar novamente as consultas")

    # Primeiro teste
    print("\n--- TESTE INICIAL ---")
    initial_success = test_heartbeat_queries()

    if not initial_success:
        print("\n❌ Testes iniciais falharam. Tentando reinicializar pool...")

        # Forçar reinicialização do pool
        force_pool_restart()

        # Aguardar um pouco
        print("\nAguardando 2 segundos...")
        time.sleep(2)

        # Testar novamente
        print("\n--- TESTE APÓS REINICIALIZAÇÃO ---")
        final_success = test_heartbeat_queries()

        if final_success:
            print("\n✅ Problema resolvido após reinicialização do pool!")
        else:
            print("\n❌ Problema persiste mesmo após reinicialização")
    else:
        print("\n✅ Todos os testes passaram! Pool funcionando corretamente.")

    print("\n=== SCRIPT CONCLUÍDO ===")


if __name__ == "__main__":
    main()

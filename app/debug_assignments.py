#!/usr/bin/env python3

import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
root_env_file = Path(__file__).parent.parent / ".env"
if root_env_file.exists():
    load_dotenv(root_env_file)
    print(f"Variáveis carregadas de {root_env_file}")
else:
    print("Arquivo .env não encontrado")

# Configuração do banco
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
    "database": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "radio_db")),
    "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
    "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "")),
    "port": int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", 5432))),
}

print(
    f"Conectando ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)
print(f"Usuário: {DB_CONFIG['user']}")
print(
    f"Senha: {'*' * len(DB_CONFIG['password']) if DB_CONFIG['password'] else 'VAZIA'}"
)
print()


def debug_assignments():
    """Debug das atribuições de streams."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print("\n=== DEBUG ATRIBUIÇÕES DE STREAMS ===")

        # 1. Verificar se a tabela existe
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orchestrator_stream_assignments'
            ) as table_exists
        """
        )
        result = cursor.fetchone()
        table_exists = result["table_exists"]
        print(f"Tabela orchestrator_stream_assignments existe: {table_exists}")

        if not table_exists:
            print("ERRO: Tabela não existe!")
            return

        # 2. Contar registros na tabela
        cursor.execute("SELECT COUNT(*) as total FROM orchestrator_stream_assignments")
        result = cursor.fetchone()
        total_assignments = result["total"]
        print(f"Total de registros na tabela: {total_assignments}")

        # 3. Listar todos os registros
        cursor.execute(
            """
            SELECT * FROM orchestrator_stream_assignments 
            ORDER BY assigned_at DESC
        """
        )
        assignments = cursor.fetchall()

        if assignments:
            print(f"\nRegistros encontrados ({len(assignments)}):")
            for assignment in assignments:
                print(
                    f"  ID: {assignment['id']}, Stream: {assignment['stream_id']}, "
                    f"Server: {assignment['server_id']}, Status: {assignment['status']}, "
                    f"Assigned: {assignment['assigned_at']}"
                )
        else:
            print("Nenhum registro encontrado na tabela")

        # 4. Verificar instâncias
        cursor.execute(
            """
            SELECT server_id, current_streams, max_streams, status 
            FROM orchestrator_instances
        """
        )
        instances = cursor.fetchall()

        print(f"\n=== INSTÂNCIAS REGISTRADAS ({len(instances)}) ===")
        for instance in instances:
            print(
                f"  Server: {instance['server_id']}, Streams: {instance['current_streams']}/{instance['max_streams']}, "
                f"Status: {instance['status']}"
            )

        # 5. Tentar o JOIN que o endpoint usa
        print("\n=== TESTE DO JOIN DO ENDPOINT ===")
        cursor.execute(
            """
            SELECT osa.stream_id, osa.server_id, osa.assigned_at, osa.status,
                   oi.ip, oi.port
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
            ORDER BY osa.assigned_at DESC
        """
        )

        join_results = cursor.fetchall()
        print(f"Resultados do JOIN: {len(join_results)} registros")

        if join_results:
            for result in join_results:
                print(
                    f"  Stream: {result['stream_id']}, Server: {result['server_id']}, "
                    f"IP: {result['ip']}:{result['port']}, Status: {result['status']}"
                )
        else:
            print("Nenhum resultado do JOIN - pode ser problema de dados")

    except Exception as e:
        print(f"Erro detalhado: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    debug_assignments()

#!/usr/bin/env python3
"""
Teste direto de inserção no banco de dados para debug.
"""

import os
import sys
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
print(f"Variáveis carregadas de {env_path}")

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

print(f"Conectando ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
print(f"Usuário: {DB_CONFIG['user']}")
print(f"Senha: {'*' * len(DB_CONFIG['password'])}")
print()

def test_direct_insert():
    """Testa inserção direta no banco."""
    try:
        # Conectar ao banco
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("=== TESTE DE INSERÇÃO DIRETA ===")
        
        # Verificar autocommit
        print(f"Autocommit: {conn.autocommit}")
        
        # Limpar registros de teste anteriores
        cursor.execute("DELETE FROM orchestrator_stream_assignments WHERE server_id = 'test_server'")
        conn.commit()
        print("Registros de teste anteriores removidos")
        
        # Contar registros antes
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments")
        count_before = cursor.fetchone()['count']
        print(f"Registros antes da inserção: {count_before}")
        
        # Inserir registro de teste
        test_stream_id = 999
        test_server_id = 'test_server'
        
        cursor.execute("""
            INSERT INTO orchestrator_stream_assignments 
            (stream_id, server_id, status)
            VALUES (%s, %s, 'active')
        """, (test_stream_id, test_server_id))
        
        print(f"Inserção executada: stream_id={test_stream_id}, server_id={test_server_id}")
        
        # Verificar se foi inserido (antes do commit)
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments WHERE server_id = %s", (test_server_id,))
        count_after_insert = cursor.fetchone()['count']
        print(f"Registros após inserção (antes commit): {count_after_insert}")
        
        # Commit
        conn.commit()
        print("COMMIT executado")
        
        # Verificar após commit
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments WHERE server_id = %s", (test_server_id,))
        count_after_commit = cursor.fetchone()['count']
        print(f"Registros após commit: {count_after_commit}")
        
        # Verificar total
        cursor.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments")
        total_count = cursor.fetchone()['count']
        print(f"Total de registros na tabela: {total_count}")
        
        # Listar o registro inserido
        cursor.execute("""
            SELECT * FROM orchestrator_stream_assignments 
            WHERE server_id = %s
        """, (test_server_id,))
        
        test_record = cursor.fetchone()
        if test_record:
            print(f"Registro encontrado: {dict(test_record)}")
        else:
            print("ERRO: Registro não encontrado após commit!")
        
        # Testar com nova conexão
        cursor.close()
        conn.close()
        
        print("\n=== TESTE COM NOVA CONEXÃO ===")
        conn2 = psycopg2.connect(**DB_CONFIG)
        cursor2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor2.execute("SELECT COUNT(*) as count FROM orchestrator_stream_assignments WHERE server_id = %s", (test_server_id,))
        count_new_conn = cursor2.fetchone()['count']
        print(f"Registros com nova conexão: {count_new_conn}")
        
        # Limpar registro de teste
        cursor2.execute("DELETE FROM orchestrator_stream_assignments WHERE server_id = %s", (test_server_id,))
        conn2.commit()
        print("Registro de teste removido")
        
        cursor2.close()
        conn2.close()
        
        print("\n=== RESULTADO ===")
        if count_after_commit > 0 and count_new_conn > 0:
            print("✅ Inserção funcionando corretamente")
        else:
            print("❌ Problema com inserção ou persistência")
            
    except Exception as e:
        print(f"Erro no teste: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct_insert()
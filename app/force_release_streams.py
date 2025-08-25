#!/usr/bin/env python3
"""
Script para forçar a liberação de streams de uma instância parada
"""

import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def get_db_connection():
    """Conecta ao banco de dados PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=os.getenv('POSTGRES_PORT'),
        database=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )

def force_release_streams(server_id):
    """Força a liberação de todos os streams de uma instância"""
    print(f"🔧 FORÇANDO LIBERAÇÃO DE STREAMS DA INSTÂNCIA {server_id}\n")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Verificar assignments atuais
        print("1. Verificando assignments atuais...")
        cursor.execute("""
            SELECT COUNT(*) FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'assigned'
        """, (str(server_id),))
        current_assignments = cursor.fetchone()[0]
        print(f"   Assignments ativos: {current_assignments}")
        
        if current_assignments == 0:
            print("   ✅ Nenhum assignment ativo encontrado")
            return
        
        # 2. Liberar todos os assignments
        print("\n2. Liberando todos os assignments...")
        cursor.execute("""
            DELETE FROM orchestrator_stream_assignments 
            WHERE server_id = %s
        """, (str(server_id),))
        deleted_count = cursor.rowcount
        print(f"   ✅ {deleted_count} assignments removidos")
        
        # 3. Resetar contador da instância
        print("\n3. Resetando contador da instância...")
        cursor.execute("""
            UPDATE orchestrator_instances 
            SET current_streams = 0,
                last_heartbeat = %s
            WHERE server_id = %s
        """, (datetime.now(), str(server_id)))
        print(f"   ✅ Contador resetado para 0")
        
        # 4. Verificar estado final
        print("\n4. Verificando estado final...")
        cursor.execute("""
            SELECT current_streams, max_streams, status 
            FROM orchestrator_instances 
            WHERE server_id = %s
        """, (str(server_id),))
        result = cursor.fetchone()
        if result:
            current, max_streams, status = result
            print(f"   Estado final: {current}/{max_streams} streams, status: {status}")
            print(f"   Capacidade disponível: {max_streams - current}")
        
        conn.commit()
        print("\n🎉 LIBERAÇÃO FORÇADA CONCLUÍDA COM SUCESSO!")
        print(f"   ✅ Instância {server_id} pronta para receber novos streams")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERRO: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Forçar liberação da instância 1
    force_release_streams(1)
#!/usr/bin/env python3
"""
Script para corrigir a estrutura da tabela server_heartbeats
Converte server_id de INTEGER para VARCHAR(100)
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Configurações do banco
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def fix_heartbeat_table():
    """Corrige a estrutura da tabela server_heartbeats"""
    try:
        # Conectar ao banco
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        with conn.cursor() as cursor:
            print("Verificando estrutura atual da tabela server_heartbeats...")
            
            # Verificar se a tabela existe e sua estrutura
            cursor.execute("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'server_heartbeats' 
                AND column_name = 'server_id'
            """)
            
            result = cursor.fetchone()
            if result:
                column_name, data_type, max_length = result
                print(f"Coluna server_id encontrada: {data_type}({max_length})")
                
                if data_type == 'integer':
                    print("Detectado server_id como INTEGER. Corrigindo...")
                    
                    # Fazer backup dos dados existentes
                    cursor.execute("SELECT * FROM server_heartbeats")
                    backup_data = cursor.fetchall()
                    print(f"Backup de {len(backup_data)} registros realizado")
                    
                    # Dropar a tabela existente
                    cursor.execute("DROP TABLE IF EXISTS server_heartbeats CASCADE")
                    print("Tabela server_heartbeats removida")
                    
                    # Recriar a tabela com a estrutura correta
                    cursor.execute("""
                        CREATE TABLE server_heartbeats (
                            server_id VARCHAR(100) PRIMARY KEY,
                            last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            status VARCHAR(20) DEFAULT 'ONLINE',
                            ip_address VARCHAR(50),
                            info JSONB
                        )
                    """)
                    print("Tabela server_heartbeats recriada com server_id VARCHAR(100)")
                    
                    # Restaurar dados compatíveis (apenas se server_id for string válida)
                    restored_count = 0
                    for row in backup_data:
                        try:
                            # Converter server_id de integer para string se necessário
                            server_id = str(row[0]) if row[0] is not None else None
                            if server_id and server_id.isdigit():
                                # Se for um número, converter para formato finger_app_X
                                server_id = f"finger_app_{server_id}"
                            
                            cursor.execute("""
                                INSERT INTO server_heartbeats 
                                (server_id, last_heartbeat, status, ip_address, info)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (server_id, row[1], row[2], row[3], row[4]))
                            restored_count += 1
                        except Exception as e:
                            print(f"Erro ao restaurar registro {row}: {e}")
                    
                    print(f"Restaurados {restored_count} registros")
                    
                elif data_type == 'character varying':
                    print("Tabela server_heartbeats já está com a estrutura correta (VARCHAR)")
                else:
                    print(f"Tipo de dados inesperado: {data_type}")
            else:
                print("Tabela server_heartbeats não existe. Criando...")
                cursor.execute("""
                    CREATE TABLE server_heartbeats (
                        server_id VARCHAR(100) PRIMARY KEY,
                        last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        status VARCHAR(20) DEFAULT 'ONLINE',
                        ip_address VARCHAR(50),
                        info JSONB
                    )
                """)
                print("Tabela server_heartbeats criada com estrutura correta")
            
            # Commit das alterações
            conn.commit()
            print("Correção da tabela server_heartbeats concluída com sucesso!")
            
    except Exception as e:
        print(f"Erro ao corrigir tabela server_heartbeats: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    fix_heartbeat_table()
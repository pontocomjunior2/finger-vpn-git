#!/usr/bin/env python3
"""
Script para corrigir o tipo de dados da coluna server_id na tabela stream_locks
Converte de INTEGER para VARCHAR(100) para aceitar IDs de servidor como strings
"""

import psycopg2
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def fix_stream_locks_column():
    """
    Corrige o tipo de dados da coluna server_id na tabela stream_locks
    """
    conn = None
    try:
        # Conectar ao banco
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        cursor = conn.cursor()
        
        # Verificar se a tabela existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'stream_locks'
            )
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            logger.error("Tabela stream_locks não existe!")
            return False
            
        # Verificar o tipo atual da coluna server_id
        cursor.execute("""
            SELECT data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'stream_locks' 
            AND column_name = 'server_id'
        """)
        
        column_info = cursor.fetchone()
        
        if not column_info:
            logger.error("Coluna server_id não encontrada na tabela stream_locks!")
            return False
            
        current_type, max_length = column_info
        logger.info(f"Tipo atual da coluna server_id: {current_type} (max_length: {max_length})")
        
        # Se já for VARCHAR com tamanho adequado, não precisa alterar
        if current_type == 'character varying' and (max_length is None or max_length >= 100):
            logger.info("Coluna server_id já está com o tipo correto (VARCHAR >= 100)")
            return True
            
        # Fazer backup dos dados existentes
        cursor.execute("SELECT stream_id, server_id, heartbeat_at FROM stream_locks")
        backup_data = cursor.fetchall()
        logger.info(f"Backup de {len(backup_data)} registros realizado")
        
        # Limpar a tabela temporariamente
        cursor.execute("DELETE FROM stream_locks")
        logger.info("Tabela stream_locks limpa temporariamente")
        
        # Alterar o tipo da coluna
        cursor.execute("""
            ALTER TABLE stream_locks 
            ALTER COLUMN server_id TYPE VARCHAR(100)
        """)
        logger.info("Tipo da coluna server_id alterado para VARCHAR(100)")
        
        # Restaurar os dados, convertendo server_id para string
        restored_count = 0
        for stream_id, server_id, heartbeat_at in backup_data:
            try:
                # Converter server_id para string se necessário
                server_id_str = str(server_id) if server_id is not None else None
                
                cursor.execute("""
                    INSERT INTO stream_locks (stream_id, server_id, heartbeat_at)
                    VALUES (%s, %s, %s)
                """, (stream_id, server_id_str, heartbeat_at))
                
                restored_count += 1
                
            except Exception as e:
                logger.warning(f"Erro ao restaurar registro {stream_id}: {e}")
                
        logger.info(f"Restaurados {restored_count} de {len(backup_data)} registros")
        
        # Confirmar as alterações
        conn.commit()
        logger.info("Alterações confirmadas com sucesso!")
        
        # Verificar o resultado final
        cursor.execute("""
            SELECT data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'stream_locks' 
            AND column_name = 'server_id'
        """)
        
        final_type, final_max_length = cursor.fetchone()
        logger.info(f"Tipo final da coluna server_id: {final_type} (max_length: {final_max_length})")
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao corrigir coluna server_id: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logger.info("Iniciando correção da coluna server_id na tabela stream_locks...")
    
    success = fix_stream_locks_column()
    
    if success:
        logger.info("Correção concluída com sucesso!")
    else:
        logger.error("Falha na correção da coluna server_id")
        exit(1)
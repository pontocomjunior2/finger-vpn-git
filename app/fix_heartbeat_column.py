#!/usr/bin/env python3
"""
Script para corrigir a coluna heartbeat_at na tabela stream_locks
Este script verifica se a coluna existe e a adiciona se necessário
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

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

def check_and_fix_heartbeat_column():
    """
    Verifica e corrige a coluna heartbeat_at na tabela stream_locks
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
        
        # Verificar se a tabela stream_locks existe
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
            
        # Verificar estrutura atual da tabela
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'stream_locks'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        logger.info("Estrutura atual da tabela stream_locks:")
        for col in columns:
            logger.info(f"  {col[0]} | {col[1]} | Nullable: {col[2]} | Default: {col[3]}")
        
        # Verificar se a coluna heartbeat_at existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'stream_locks' 
                AND column_name = 'heartbeat_at'
            )
        """)
        
        heartbeat_column_exists = cursor.fetchone()[0]
        
        if heartbeat_column_exists:
            logger.info("Coluna heartbeat_at já existe na tabela stream_locks")
            return True
        else:
            logger.info("Coluna heartbeat_at não existe. Adicionando...")
            
            # Adicionar a coluna heartbeat_at
            cursor.execute("""
                ALTER TABLE stream_locks 
                ADD COLUMN heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            """)
            
            # Atualizar registros existentes com timestamp atual
            cursor.execute("""
                UPDATE stream_locks 
                SET heartbeat_at = NOW() 
                WHERE heartbeat_at IS NULL
            """)
            
            conn.commit()
            logger.info("Coluna heartbeat_at adicionada com sucesso!")
            
            # Verificar a estrutura final
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'stream_locks'
                ORDER BY ordinal_position
            """)
            
            final_columns = cursor.fetchall()
            logger.info("Estrutura final da tabela stream_locks:")
            for col in final_columns:
                logger.info(f"  {col[0]} | {col[1]} | Nullable: {col[2]} | Default: {col[3]}")
            
            return True
        
    except Exception as e:
        logger.error(f"Erro ao verificar/corrigir coluna heartbeat_at: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if conn:
            conn.close()

def check_stream_locks_data():
    """
    Verifica alguns dados da tabela stream_locks para debug
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        cursor = conn.cursor()
        
        # Contar registros
        cursor.execute("SELECT COUNT(*) FROM stream_locks")
        count = cursor.fetchone()[0]
        logger.info(f"Total de registros na tabela stream_locks: {count}")
        
        if count > 0:
            # Mostrar alguns registros
            cursor.execute("SELECT * FROM stream_locks LIMIT 5")
            records = cursor.fetchall()
            
            # Obter nomes das colunas
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'stream_locks'
                ORDER BY ordinal_position
            """)
            column_names = [row[0] for row in cursor.fetchall()]
            
            logger.info("Primeiros 5 registros:")
            for i, record in enumerate(records):
                logger.info(f"  Registro {i+1}: {dict(zip(column_names, record))}")
        
    except Exception as e:
        logger.error(f"Erro ao verificar dados da tabela: {e}")
        
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logger.info("Iniciando verificação e correção da coluna heartbeat_at...")
    
    success = check_and_fix_heartbeat_column()
    
    if success:
        logger.info("Verificação/correção concluída com sucesso!")
        logger.info("Verificando dados da tabela...")
        check_stream_locks_data()
    else:
        logger.error("Falha na verificação/correção da coluna heartbeat_at")
        exit(1)
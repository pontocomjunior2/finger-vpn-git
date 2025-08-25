#!/usr/bin/env python3
"""
Script para verificar o acesso à tabela music_log
"""

import os
import psycopg2
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
DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "music_log")

def check_music_log_access():
    """
    Verifica o acesso à tabela music_log consultando os últimos 10 registros
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
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = '{DB_TABLE_NAME}'
            )
        """)
        
        table_exists = cursor.fetchone()[0]
        if not table_exists:
            logger.error(f"A tabela {DB_TABLE_NAME} não existe!")
            return
        
        # Contar registros na tabela
        cursor.execute(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}")
        count = cursor.fetchone()[0]
        logger.info(f"Total de registros na tabela {DB_TABLE_NAME}: {count}")
        
        # Consultar os últimos 100 registros
        cursor.execute(f"""
            SELECT id, date, time, name, artist, song_title, created_at 
            FROM {DB_TABLE_NAME} 
            ORDER BY created_at DESC 
            LIMIT 100
        """)
        
        records = cursor.fetchall()
        logger.info(f"Últimos {len(records)} registros da tabela {DB_TABLE_NAME} (mostrando os 10 mais recentes):")
        
        # Mostrar apenas os 10 primeiros para não sobrecarregar o log
        
        # Mostrar apenas os 10 primeiros registros para não sobrecarregar o log
        for i, record in enumerate(records[:10], 1):
            id, date, time, name, artist, song_title, created_at = record
            logger.info(f"{i}. ID: {id}, Data: {date}, Hora: {time}, Rádio: {name}, Artista: {artist}, Música: {song_title}, Criado em: {created_at}")
        
    except Exception as e:
        logger.error(f"Erro ao acessar a tabela {DB_TABLE_NAME}: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_music_log_access()
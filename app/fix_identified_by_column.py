#!/usr/bin/env python3
"""
Script para corrigir o erro 'value too long for type character varying(10)' 
na coluna identified_by da tabela music_log.

O erro ocorre porque o SERVER_ID 'test_server_corrected' (20 caracteres) 
excede o limite de 10 caracteres da coluna identified_by.
"""

import asyncio
import logging
from typing import Optional

import asyncpg

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações do banco de dados
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dataradio',
    'user': 'postgres',
    'password': 'postgres'
}

DB_TABLE_NAME = 'music_log'

async def get_column_info(conn: asyncpg.Connection, table_name: str, column_name: str) -> Optional[dict]:
    """
    Obtém informações sobre uma coluna específica.
    """
    query = """
    SELECT 
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default
    FROM information_schema.columns 
    WHERE table_name = $1 AND column_name = $2;
    """
    
    result = await conn.fetchrow(query, table_name, column_name)
    if result:
        return dict(result)
    return None

async def fix_identified_by_column():
    """
    Corrige a coluna identified_by alterando de VARCHAR(10) para TEXT.
    """
    try:
        logger.info("Conectando ao banco de dados...")
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            # Verificar informações atuais da coluna
            logger.info(f"Verificando coluna identified_by na tabela {DB_TABLE_NAME}...")
            column_info = await get_column_info(conn, DB_TABLE_NAME, 'identified_by')
            
            if not column_info:
                logger.error(f"Coluna identified_by não encontrada na tabela {DB_TABLE_NAME}")
                return False
            
            logger.info(f"Informações atuais da coluna identified_by:")
            logger.info(f"  - Tipo: {column_info['data_type']}")
            logger.info(f"  - Tamanho máximo: {column_info['character_maximum_length']}")
            logger.info(f"  - Permite NULL: {column_info['is_nullable']}")
            logger.info(f"  - Valor padrão: {column_info['column_default']}")
            
            # Verificar se precisa alterar
            if column_info['data_type'] == 'text':
                logger.info("Coluna identified_by já está configurada como TEXT. Nenhuma alteração necessária.")
                return True
            
            # Alterar coluna para TEXT
            logger.info("Alterando coluna identified_by de VARCHAR(10) para TEXT...")
            alter_query = f"ALTER TABLE {DB_TABLE_NAME} ALTER COLUMN identified_by TYPE TEXT;"
            
            await conn.execute(alter_query)
            logger.info("✅ Coluna identified_by alterada para TEXT com sucesso!")
            
            # Verificar a alteração
            updated_info = await get_column_info(conn, DB_TABLE_NAME, 'identified_by')
            logger.info(f"Informações atualizadas da coluna identified_by:")
            logger.info(f"  - Tipo: {updated_info['data_type']}")
            logger.info(f"  - Tamanho máximo: {updated_info['character_maximum_length']}")
            
            return True
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Erro ao corrigir coluna identified_by: {e}")
        return False

async def test_insert_with_long_server_id():
    """
    Testa inserção com um server_id longo para verificar se o problema foi resolvido.
    """
    try:
        logger.info("Testando inserção com server_id longo...")
        conn = await asyncpg.connect(**DB_CONFIG)
        
        try:
            # Dados de teste com server_id longo
            test_data = {
                'name': 'Teste FM',
                'artist': 'Artista Teste',
                'song_title': 'Música Teste',
                'isrc': 'TEST123456',
                'cidade': 'São Paulo',
                'estado': 'SP',
                'regiao': 'Sudeste',
                'segmento': 'Teste',
                'label': 'Label Teste',
                'genre': 'Pop',
                'identified_by': 'test_server_corrected_muito_longo',  # 34 caracteres
                'date': '2025-08-23',
                'time': '15:30:00'
            }
            
            # Tentar inserir
            insert_query = f"""
            INSERT INTO {DB_TABLE_NAME} 
            (name, artist, song_title, isrc, cidade, estado, regiao, segmento, label, genre, identified_by, date, time)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id;
            """
            
            result = await conn.fetchval(
                insert_query,
                test_data['name'], test_data['artist'], test_data['song_title'],
                test_data['isrc'], test_data['cidade'], test_data['estado'],
                test_data['regiao'], test_data['segmento'], test_data['label'],
                test_data['genre'], test_data['identified_by'], test_data['date'],
                test_data['time']
            )
            
            logger.info(f"✅ Teste de inserção bem-sucedido! ID inserido: {result}")
            
            # Remover o registro de teste
            await conn.execute(f"DELETE FROM {DB_TABLE_NAME} WHERE id = $1", result)
            logger.info("Registro de teste removido.")
            
            return True
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Erro no teste de inserção: {e}")
        return False

async def main():
    """
    Função principal que executa a correção e testes.
    """
    logger.info("=== Iniciando correção da coluna identified_by ===")
    
    # Corrigir a coluna
    success = await fix_identified_by_column()
    if not success:
        logger.error("❌ Falha na correção da coluna identified_by")
        return
    
    # Testar inserção
    test_success = await test_insert_with_long_server_id()
    if test_success:
        logger.info("✅ Correção concluída com sucesso! O problema foi resolvido.")
    else:
        logger.error("❌ Teste de inserção falhou. Pode haver outros problemas.")
    
    logger.info("=== Correção finalizada ===")

if __name__ == "__main__":
    asyncio.run(main())
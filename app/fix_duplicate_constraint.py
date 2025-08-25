#!/usr/bin/env python3
"""
Script para corrigir constraints de duplicatas na tabela music_log
Adiciona constraint UNIQUE que prioriza ISRC para prevenir duplicatas
"""

import asyncio
import logging
import os
from datetime import datetime
import asyncpg
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações do banco de dados
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'music_log'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password')
}

async def check_existing_constraints(conn):
    """Verifica constraints existentes na tabela music_log"""
    query = """
    SELECT conname, pg_get_constraintdef(oid) as definition
    FROM pg_constraint 
    WHERE conrelid = 'music_log'::regclass
    AND contype = 'u';
    """
    
    constraints = await conn.fetch(query)
    logger.info("Constraints UNIQUE existentes:")
    for constraint in constraints:
        logger.info(f"  {constraint['conname']}: {constraint['definition']}")
    
    return constraints

async def check_duplicate_isrc_records(conn):
    """Verifica se existem registros duplicados por ISRC"""
    query = """
    SELECT name, isrc, COUNT(*) as count
    FROM music_log 
    WHERE isrc IS NOT NULL AND isrc != ''
    GROUP BY name, isrc
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT 10;
    """
    
    duplicates = await conn.fetch(query)
    if duplicates:
        logger.warning(f"Encontrados {len(duplicates)} grupos de registros duplicados por ISRC:")
        for dup in duplicates:
            logger.warning(f"  {dup['name']} - ISRC: {dup['isrc']} - {dup['count']} registros")
    else:
        logger.info("Nenhum registro duplicado por ISRC encontrado.")
    
    return duplicates

async def remove_duplicate_records(conn):
    """Remove registros duplicados mantendo apenas o mais recente"""
    logger.info("Removendo registros duplicados por ISRC...")
    
    # Query para identificar e remover duplicatas por ISRC
    query = """
    WITH duplicates AS (
        SELECT id, name, isrc,
               ROW_NUMBER() OVER (
                   PARTITION BY name, isrc 
                   ORDER BY (date || ' ' || time)::timestamp DESC
               ) as rn
        FROM music_log 
        WHERE isrc IS NOT NULL AND isrc != ''
    )
    DELETE FROM music_log 
    WHERE id IN (
        SELECT id FROM duplicates WHERE rn > 1
    );
    """
    
    result = await conn.execute(query)
    deleted_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
    logger.info(f"Removidos {deleted_count} registros duplicados.")
    
    return deleted_count

async def create_isrc_constraint(conn):
    """Cria constraint UNIQUE que prioriza ISRC"""
    logger.info("Criando constraint UNIQUE para ISRC...")
    
    # Primeiro, criar um índice único parcial para registros com ISRC
    create_index_query = """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_music_log_unique_isrc
    ON music_log (name, isrc)
    WHERE isrc IS NOT NULL AND isrc != '';
    """
    
    try:
        await conn.execute(create_index_query)
        logger.info("Índice único para ISRC criado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao criar índice único para ISRC: {e}")
        raise

async def create_fallback_constraint(conn):
    """Cria constraint para registros sem ISRC"""
    logger.info("Criando constraint UNIQUE para registros sem ISRC...")
    
    # Índice único parcial para registros sem ISRC válido
    create_index_query = """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_music_log_unique_no_isrc
    ON music_log (name, artist, song_title, date, time)
    WHERE isrc IS NULL OR isrc = '';
    """
    
    try:
        await conn.execute(create_index_query)
        logger.info("Índice único para registros sem ISRC criado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao criar índice único para registros sem ISRC: {e}")
        raise

async def verify_constraints(conn):
    """Verifica se as constraints foram criadas corretamente"""
    logger.info("Verificando constraints criadas...")
    
    # Verificar índices criados
    query = """
    SELECT indexname, indexdef
    FROM pg_indexes 
    WHERE tablename = 'music_log'
    AND indexname LIKE 'idx_music_log_unique%';
    """
    
    indexes = await conn.fetch(query)
    for index in indexes:
        logger.info(f"Índice: {index['indexname']}")
        logger.info(f"  Definição: {index['indexdef']}")

async def test_duplicate_prevention(conn):
    """Testa se a prevenção de duplicatas está funcionando"""
    logger.info("Testando prevenção de duplicatas...")
    
    test_data = {
        'name': 'TEST_RADIO',
        'artist': 'Test Artist',
        'song_title': 'Test Song',
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M:%S'),
        'identified_by': '999',
        'isrc': 'TEST123456789'
    }
    
    # Tentar inserir o mesmo registro duas vezes
    insert_query = """
    INSERT INTO music_log (name, artist, song_title, date, time, identified_by, isrc)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING id;
    """
    
    try:
        # Primeira inserção
        result1 = await conn.fetchrow(insert_query, *test_data.values())
        logger.info(f"Primeira inserção bem-sucedida: ID {result1['id']}")
        
        # Segunda inserção (deve falhar)
        try:
            result2 = await conn.fetchrow(insert_query, *test_data.values())
            logger.error("ERRO: Segunda inserção não deveria ter sido bem-sucedida!")
        except Exception as e:
            logger.info(f"Segunda inserção corretamente bloqueada: {e}")
        
        # Limpar dados de teste
        await conn.execute("DELETE FROM music_log WHERE name = 'TEST_RADIO'")
        logger.info("Dados de teste removidos.")
        
    except Exception as e:
        logger.error(f"Erro no teste: {e}")

async def main():
    """Função principal"""
    logger.info("Iniciando correção de constraints de duplicatas...")
    
    try:
        # Conectar ao banco de dados
        conn = await asyncpg.connect(**DB_CONFIG)
        logger.info("Conectado ao banco de dados.")
        
        # Verificar constraints existentes
        await check_existing_constraints(conn)
        
        # Verificar duplicatas existentes
        duplicates = await check_duplicate_isrc_records(conn)
        
        # Remover duplicatas se existirem
        if duplicates:
            confirm = input("Deseja remover os registros duplicados? (s/N): ")
            if confirm.lower() == 's':
                await remove_duplicate_records(conn)
            else:
                logger.warning("Duplicatas não removidas. As constraints podem falhar.")
        
        # Criar constraints
        await create_isrc_constraint(conn)
        await create_fallback_constraint(conn)
        
        # Verificar constraints criadas
        await verify_constraints(conn)
        
        # Testar prevenção de duplicatas
        await test_duplicate_prevention(conn)
        
        logger.info("Correção de constraints concluída com sucesso!")
        
    except Exception as e:
        logger.error(f"Erro durante a execução: {e}")
        raise
    finally:
        if 'conn' in locals():
            await conn.close()
            logger.info("Conexão com banco de dados fechada.")

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
Script para corrigir os erros identificados no sistema de fingerprinting:
1. Erro 'value too long for type character varying(10)' - coluna identified_by
2. Erro 'current transaction is aborted, commands ignored until end of transaction block'
3. Erro 'unsupported operand type(s) for -: 'str' and 'int'' no heartbeat

Autor: Sistema de Correção Automática
Data: 2025-08-23
"""

import os
import sys
import psycopg2
import logging
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações do banco de dados
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def get_db_connection():
    """Cria uma conexão com o banco de dados."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

def fix_identified_by_column():
    """Corrige o tamanho da coluna identified_by de VARCHAR(10) para TEXT."""
    logger.info("Iniciando correção da coluna identified_by...")
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            # Verificar se a tabela music_log existe
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'music_log'
                );
            """)
            
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                logger.warning("Tabela music_log não existe. Criando...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS music_log (
                        id SERIAL PRIMARY KEY,
                        name TEXT,
                        artist TEXT,
                        song_title TEXT,
                        date DATE,
                        time TIME,
                        identified_by TEXT,
                        isrc TEXT,
                        cidade TEXT,
                        estado TEXT,
                        regiao TEXT,
                        segmento TEXT,
                        label TEXT,
                        genre TEXT,
                        UNIQUE(name, artist, song_title, date, time)
                    );
                """)
                logger.info("Tabela music_log criada com sucesso.")
            else:
                # Verificar o tipo atual da coluna identified_by
                cursor.execute("""
                    SELECT data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'music_log' 
                    AND column_name = 'identified_by';
                """)
                
                result = cursor.fetchone()
                if result:
                    data_type, max_length = result
                    logger.info(f"Coluna identified_by atual: {data_type}({max_length})")
                    
                    if data_type == 'character varying' and max_length == 10:
                        logger.info("Alterando coluna identified_by de VARCHAR(10) para TEXT...")
                        cursor.execute("""
                            ALTER TABLE music_log 
                            ALTER COLUMN identified_by TYPE TEXT;
                        """)
                        logger.info("Coluna identified_by alterada para TEXT com sucesso.")
                    else:
                        logger.info("Coluna identified_by já está no formato correto.")
                else:
                    logger.info("Adicionando coluna identified_by como TEXT...")
                    cursor.execute("""
                        ALTER TABLE music_log 
                        ADD COLUMN IF NOT EXISTS identified_by TEXT;
                    """)
            
            conn.commit()
            logger.info("Correção da coluna identified_by concluída com sucesso.")
            return True
            
    except Exception as e:
        logger.error(f"Erro ao corrigir coluna identified_by: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def fix_distribution_tables():
    """Corrige problemas nas tabelas de distribuição que causam transações abortadas."""
    logger.info("Iniciando correção das tabelas de distribuição...")
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            # Recriar tabela stream_locks com estrutura correta
            logger.info("Recriando tabela stream_locks...")
            cursor.execute("""
                DROP TABLE IF EXISTS stream_locks CASCADE;
            """)
            
            cursor.execute("""
                CREATE TABLE stream_locks (
                    stream_id VARCHAR(50) PRIMARY KEY,
                    server_id TEXT NOT NULL,
                    acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '2 minutes'
                );
            """)
            
            # Recriar tabela server_heartbeats com estrutura correta
            logger.info("Recriando tabela server_heartbeats...")
            cursor.execute("""
                DROP TABLE IF EXISTS server_heartbeats CASCADE;
            """)
            
            cursor.execute("""
                CREATE TABLE server_heartbeats (
                    server_id TEXT PRIMARY KEY,
                    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status VARCHAR(20) DEFAULT 'ONLINE',
                    ip_address VARCHAR(50),
                    info JSONB
                );
            """)
            
            # Criar índices para melhor performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_stream_locks_expires_at 
                ON stream_locks(expires_at);
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_heartbeats_status 
                ON server_heartbeats(status);
            """)
            
            conn.commit()
            logger.info("Tabelas de distribuição corrigidas com sucesso.")
            return True
            
    except Exception as e:
        logger.error(f"Erro ao corrigir tabelas de distribuição: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_heartbeat_fix_patch():
    """Cria um patch para corrigir o erro de tipo no heartbeat."""
    logger.info("Criando patch para correção do heartbeat...")
    
    patch_content = '''
# PATCH PARA CORREÇÃO DO ERRO DE HEARTBEAT
# Adicionar esta correção na função send_heartbeat() no fingerv7.py

# PROBLEMA: SERVER_ID pode ser string, mas está sendo usado em operação matemática
# LINHA PROBLEMÁTICA (aproximadamente linha 2396):
# (int(s.get("index", 0)) % TOTAL_SERVERS) == (SERVER_ID - 1)

# SOLUÇÃO: Converter SERVER_ID para int quando necessário
# SUBSTITUIR a linha problemática por:

# Garantir que SERVER_ID seja tratado como int para operações matemáticas
try:
    server_id_int = int(SERVER_ID) if isinstance(SERVER_ID, str) and SERVER_ID.isdigit() else 1
except (ValueError, TypeError):
    server_id_int = 1

# Usar server_id_int na operação matemática:
(int(s.get("index", 0)) % TOTAL_SERVERS) == (server_id_int - 1)

# OU ALTERNATIVA MAIS SIMPLES:
# Se SERVER_ID for sempre string, usar hash consistente:
# hash(SERVER_ID) % TOTAL_SERVERS == int(s.get("index", 0)) % TOTAL_SERVERS
'''
    
    try:
        with open('heartbeat_fix_patch.txt', 'w', encoding='utf-8') as f:
            f.write(patch_content)
        logger.info("Patch de correção do heartbeat criado: heartbeat_fix_patch.txt")
        return True
    except Exception as e:
        logger.error(f"Erro ao criar patch: {e}")
        return False

def main():
    """Função principal que executa todas as correções."""
    logger.info("=== INICIANDO CORREÇÕES DO SISTEMA DE FINGERPRINTING ===")
    
    success_count = 0
    total_fixes = 3
    
    # Correção 1: Coluna identified_by
    if fix_identified_by_column():
        success_count += 1
        logger.info("✅ Correção 1/3: Coluna identified_by corrigida")
    else:
        logger.error("❌ Correção 1/3: Falha na correção da coluna identified_by")
    
    # Correção 2: Tabelas de distribuição
    if fix_distribution_tables():
        success_count += 1
        logger.info("✅ Correção 2/3: Tabelas de distribuição corrigidas")
    else:
        logger.error("❌ Correção 2/3: Falha na correção das tabelas de distribuição")
    
    # Correção 3: Patch do heartbeat
    if create_heartbeat_fix_patch():
        success_count += 1
        logger.info("✅ Correção 3/3: Patch do heartbeat criado")
    else:
        logger.error("❌ Correção 3/3: Falha na criação do patch do heartbeat")
    
    logger.info(f"=== CORREÇÕES CONCLUÍDAS: {success_count}/{total_fixes} ===")
    
    if success_count == total_fixes:
        logger.info("🎉 Todas as correções foram aplicadas com sucesso!")
        logger.info("📝 PRÓXIMOS PASSOS:")
        logger.info("   1. Aplicar o patch do heartbeat manualmente no fingerv7.py")
        logger.info("   2. Reiniciar o programa fingerv7.py")
        logger.info("   3. Monitorar os logs para verificar se os erros foram resolvidos")
        return True
    else:
        logger.warning("⚠️  Algumas correções falharam. Verifique os logs acima.")
        return False

if __name__ == "__main__":
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        logger.error("❌ Configurações do banco de dados não encontradas no .env")
        logger.error("   Verifique se as variáveis POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD e POSTGRES_DB estão definidas")
        sys.exit(1)
    
    success = main()
    sys.exit(0 if success else 1)
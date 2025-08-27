import asyncio
import datetime as dt  # Usar alias para evitar conflito com variável datetime
import json
import logging
import os
import platform
import shutil
import signal
import smtplib
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ftplib import FTP, error_perm
from logging.handlers import TimedRotatingFileHandler

import psycopg2
import schedule
from aiohttp import (ClientConnectorError, ClientError, ClientResponseError,
                     ClientTimeout)
from dotenv import load_dotenv
from shazamio import Shazam

try:
    import pytz

    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    # O logger já está configurado aqui
    logger.critical(
        "Biblioteca pytz não encontrada. O tratamento de fuso horário falhará. Instale com: pip install pytz"
    )
    # Considerar sair se pytz for essencial
    # sys.exit(1)
import psycopg2.errors  # Para capturar UniqueViolation
import psycopg2.extras  # Para DictCursor
from async_queue import insert_queue
from db_pool import get_db_pool

# Definir diretório de segmentos global
SEGMENTS_DIR = os.getenv("SEGMENTS_DIR", "C:/DATARADIO/segments")

# Configurar logging para console e arquivo (MOVIDO PARA CIMA)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Formato de log
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: [%(threadName)s] %(message)s"
)  # Adicionado threadName

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler com limpeza a cada 6 horas
SERVER_LOG_FILE = "log.txt"  # Definir nome do arquivo de log aqui
file_handler = TimedRotatingFileHandler(
    SERVER_LOG_FILE, when="H", interval=6, backupCount=1
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Log inicial para confirmar que o logger está configurado
logger.info("Logger configurado.")

# Verificar se Pytz está ausente após configurar o logger
if not HAS_PYTZ:
    logger.critical(
        "Biblioteca pytz não encontrada. O tratamento de fuso horário pode falhar. Instale com: pip install pytz"
    )

# --- Fim da configuração do Logger ---\

# Verificar e criar o diretório de segmentos
if not os.path.exists(SEGMENTS_DIR):
    try:
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        print(f"Diretório de segmentos criado: {SEGMENTS_DIR}")
    except Exception as e:
        print(f"ERRO: Não foi possível criar o diretório de segmentos: {e}")
        # Usar um diretório alternativo se o principal falhar
        SEGMENTS_DIR = "./segments"
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        print(f"Usando diretório alternativo: {SEGMENTS_DIR}")

# Tentar importar psutil, necessário para o heartbeat
try:
    import psutil
except ImportError:
    print(
        "Pacote 'psutil' não encontrado. Execute 'pip install psutil' para habilitar monitoramento completo."
    )

    # Stub de classe para psutil se não estiver instalado
    class PsutilStub:
        def virtual_memory(self):
            return type("obj", (object,), {"percent": 0, "available": 0})

        def cpu_percent(self, interval=0):
            return 0

        def disk_usage(self, path):
            return type("obj", (object,), {"percent": 0, "free": 0})

    psutil = PsutilStub()

# Importações para (S)FTP
from ftplib import FTP

try:
    import pysftp
    from pysftp import CnOpts as pysftpCnOpts  # Importar CnOpts explicitamente

    HAS_PYSFTP = True
except ImportError:
    HAS_PYSFTP = False
    logger.warning(
        "Pacote 'pysftp' não encontrado. O failover SFTP não funcionará. Instale com 'pip install pysftp'."
    )
    pysftpCnOpts = None  # Definir como None se pysftp não estiver disponível
    # Considerar logar um aviso se SFTP for o método escolhido

# Carregar variáveis de ambiente
load_dotenv(dotenv_path=".env")

# Configuração para distribuição de carga entre servidores
SERVER_ID = os.getenv("SERVER_ID", socket.gethostname())  # ID único para cada servidor
USE_ORCHESTRATOR = (
    os.getenv("USE_ORCHESTRATOR", "True").lower() == "true"
)  # Usar orquestrador central
ORCHESTRATOR_URL = os.getenv(
    "ORCHESTRATOR_URL", "http://localhost:8001"
)  # URL do orquestrador
DISTRIBUTE_LOAD = (
    os.getenv("DISTRIBUTE_LOAD", "False").lower() == "true"
)  # Ativar distribuição

# Variáveis legadas para compatibilidade (mantidas para fallback)
TOTAL_SERVERS = int(os.getenv("TOTAL_SERVERS", "1"))  # Número total de servidores
ENABLE_ROTATION = False  # Sempre False
ROTATION_HOURS = 0  # Sempre 0

# Configuração de MAX_STREAMS
MAX_STREAMS = int(
    os.getenv("MAX_STREAMS", "10")
)  # Número máximo de streams por instância

# Importar cliente resiliente do orquestrador se habilitado
orchestrator_client = None

# Debug: Mostrar configurações iniciais
logger.info(f"[INIT] USE_ORCHESTRATOR={USE_ORCHESTRATOR}")
logger.info(f"[INIT] DISTRIBUTE_LOAD={DISTRIBUTE_LOAD}")
logger.info(f"[INIT] ORCHESTRATOR_URL={ORCHESTRATOR_URL}")

if USE_ORCHESTRATOR and DISTRIBUTE_LOAD:
    logger.info("[INIT] Tentando inicializar cliente do orquestrador...")
    try:
        from resilient_worker_client import create_resilient_worker_client

        orchestrator_client = create_resilient_worker_client(
            orchestrator_url=ORCHESTRATOR_URL,
            server_id=SERVER_ID,
            max_streams=MAX_STREAMS,
            circuit_failure_threshold=5,
            circuit_recovery_timeout=60,
            retry_max_attempts=3,
            retry_base_delay=1.0
        )
        logger.info(
            f"Cliente resiliente do orquestrador inicializado: {ORCHESTRATOR_URL} com MAX_STREAMS={MAX_STREAMS}"
        )
    except ImportError as e:
        logger.error(f"Erro ao importar cliente resiliente do orquestrador: {e}")
        logger.warning("Fallback para modo sem orquestrador")
        USE_ORCHESTRATOR = False

# Configurações para identificação e verificação de duplicatas
IDENTIFICATION_DURATION = int(
    os.getenv("IDENTIFICATION_DURATION", "15")
)  # Duração da captura em segundos
DUPLICATE_PREVENTION_WINDOW_SECONDS = int(
    os.getenv("DUPLICATE_PREVENTION_WINDOW_SECONDS", "900")
)  # Nova janela de 15 min

# Configurações do banco de dados PostgreSQL
DB_HOST = os.getenv("POSTGRES_HOST")  # Removido default para forçar configuração
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "music_log")

# Registrar a tabela que está sendo usada
print(f"Configuração da tabela de destino: DB_TABLE_NAME={DB_TABLE_NAME}")

# Configurações de Failover (S)FTP
ENABLE_FAILOVER_SEND = os.getenv("ENABLE_FAILOVER_SEND", "False").lower() == "true"
FAILOVER_METHOD = os.getenv("FAILOVER_METHOD", "SFTP").upper()  # Carrega método
FAILOVER_HOST = os.getenv("FAILOVER_HOST")
_failover_port_str = os.getenv("FAILOVER_PORT")
FAILOVER_PORT = (
    int(_failover_port_str)
    if _failover_port_str and _failover_port_str.isdigit()
    else (22 if FAILOVER_METHOD == "SFTP" else 21)
)
FAILOVER_USER = os.getenv("FAILOVER_USER")
FAILOVER_PASSWORD = os.getenv("FAILOVER_PASSWORD")
FAILOVER_REMOTE_DIR = os.getenv("FAILOVER_REMOTE_DIR")
FAILOVER_SSH_KEY_PATH = os.getenv("FAILOVER_SSH_KEY_PATH")  # Pode ser None

# Caminho para o arquivo JSON contendo os streamings
# STREAMS_FILE removido - não é mais necessário com o orquestrador
# Caminho para o arquivo JSON que armazenará o estado das últimas músicas identificadas
LAST_SONGS_FILE = "last_songs.json"
# Caminho para o arquivo de log local
LOCAL_LOG_FILE = "local_log.json"

# Configurações para o sistema de alerta por e-mail
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "junior@pontocomaudio.net")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "conquista")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "junior@pontocomaudio.net")

# === Funções de Distribuição e Locks ===


def create_distribution_tables():
    """Cria tabelas de controle para distribuição e prevenção de duplicatas"""
    conn = None
    try:
        conn = get_db_pool().pool.getconn()
        with conn.cursor() as cursor:
            # Criar tabela de heartbeats primeiro (referenciada pelas outras tabelas)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS server_heartbeats (
                    server_id VARCHAR(100) PRIMARY KEY,
                    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status VARCHAR(20) DEFAULT 'ONLINE',
                    ip_address VARCHAR(50),
                    info JSONB
                );
            """
            )

            # Tabela de locks distribuídos para streams
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_locks (
                    stream_id VARCHAR(255) PRIMARY KEY,
                    server_id VARCHAR(100) NOT NULL,
                    locked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT fk_server_id FOREIGN KEY (server_id) 
                        REFERENCES server_heartbeats(server_id) ON DELETE CASCADE
                );
            """
            )

            # Tabela de registro de streams processados (para evitar duplicatas)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_ownership (
                    stream_id VARCHAR(255) PRIMARY KEY,
                    server_id VARCHAR(100) NOT NULL,
                    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_processed TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT fk_server_ownership FOREIGN KEY (server_id) 
                        REFERENCES server_heartbeats(server_id) ON DELETE CASCADE
                );
            """
            )

            # Índice para otimizar queries de distribuição
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_stream_locks_server 
                ON stream_locks(server_id);
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_stream_ownership_server 
                ON stream_ownership(server_id);
            """
            )

            # Constraint única para prevenir duplicatas no log
            try:
                cursor.execute(
                    """
                    ALTER TABLE "music_log" 
                    ADD CONSTRAINT unique_song_per_stream_per_minute 
                    UNIQUE (name, song_title, artist, date, time);
                """
                )
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(
                        "Constraint unique_song_per_stream_per_minute já existe"
                    )
                else:
                    raise e

            # Garantir que a coluna heartbeat_at exista na tabela stream_locks
            cursor.execute(
                """
                ALTER TABLE stream_locks 
                ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
            """
            )

            # Corrigir tipo de dados da coluna server_id para VARCHAR(100)
            try:
                cursor.execute(
                    """
                    ALTER TABLE stream_locks 
                    ALTER COLUMN server_id TYPE VARCHAR(100);
                """
                )
                logger.info(
                    "Tipo de dados da coluna server_id corrigido para VARCHAR(100)"
                )
            except Exception as alter_error:
                logger.warning(
                    f"Erro ao alterar tipo da coluna server_id (pode já estar correto): {alter_error}"
                )

            conn.commit()
            logger.info("Tabelas de distribuição criadas/atualizadas com sucesso")
            return True

    except Exception as e:
        logger.error(f"Erro ao criar tabelas de distribuição: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            get_db_pool().pool.putconn(conn)


def consistent_hash(value: str, buckets: int) -> int:
    """
    Implementa consistent hashing para distribuição uniforme de streams
    """
    import hashlib

    if buckets <= 0:
        return 0

    # Usar MD5 para gerar hash consistente
    hash_object = hashlib.md5(value.encode("utf-8"))
    hash_hex = hash_object.hexdigest()

    # Converter para inteiro e mapear para o bucket
    hash_int = int(hash_hex, 16)
    return hash_int % buckets


# Função acquire_stream_lock removida - não é mais necessária com o orquestrador


# Função release_stream_lock removida - não é mais necessária com o orquestrador


# Função assign_stream_ownership removida - não é mais necessária com o orquestrador


# Funções get_assigned_server e check_existing_lock removidas - não são mais necessárias com o orquestrador


def clean_string(text: str) -> str:
    """
    Limpa e normaliza uma string para comparação:
    - Remove acentos
    - Remove caracteres especiais
    - Converte para minúsculas
    - Remove espaços extras
    - Remove palavras comuns que podem variar (Ao Vivo, Remix, etc)
    - Remove parênteses e seu conteúdo
    """
    import re
    import unicodedata

    if not text:
        return ""

    # Remove acentos
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")

    # Remove conteúdo entre parênteses (incluindo os parênteses)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)

    # Remove palavras comuns que podem variar
    common_words = [
        "ao vivo",
        "live",
        "remix",
        "version",
        "feat",
        "ft",
        "featuring",
        "cover",
        "extended",
        "radio edit",
        "original mix",
        "remastered",
        "official",
        "video",
    ]
    for word in common_words:
        text = re.sub(r"\b" + word + r"\b", "", text, flags=re.IGNORECASE)

    # Remove caracteres especiais e mantém apenas letras, números e espaços
    text = re.sub(r"[^\w\s]", "", text)

    # Remove espaços extras e converte para minúsculas
    text = re.sub(r"\s+", " ", text).strip().lower()

    return text


def check_recent_insertion(
    name: str, song_title: str, artist: str, isrc: str = None
) -> bool:
    """
    Verifica se já existe uma inserção recente para este stream/música usando ISRC como identificador principal.
    Se o ISRC não estiver disponível, utiliza a verificação por similaridade de título e artista.

    Utiliza uma abordagem mais robusta para detecção de duplicatas:
    1. Verificação prioritária por ISRC (identificador único internacional)
    2. Normalização avançada de strings como fallback (remoção de parênteses, palavras comuns, etc)
    3. Múltiplos níveis de similaridade (exata, alta, média) para título e artista
    4. Janelas de tempo adaptativas baseadas no nível de similaridade
    5. Cache de resultados para reduzir consultas ao banco
    """
    conn = None
    try:
        conn = get_db_pool().pool.getconn()
        with conn.cursor() as cursor:
            # Aumentar a janela de verificação para capturar mais duplicatas potenciais
            # 7200 segundos = 2 horas (dobro da janela anterior)
            window_start = datetime.now() - timedelta(seconds=7200)

            # Se temos um ISRC válido, usamos ele como critério principal de verificação
            if isrc and isrc != "ISRC não disponível" and isrc.strip() != "":
                cursor.execute(
                    """
                    SELECT id, date, time, song_title, artist, isrc
                    FROM music_log
                    WHERE name = %s
                      AND isrc = %s
                      AND (date + time) >= %s
                    ORDER BY date DESC, time DESC
                    LIMIT 10
                    """,
                    (name, isrc, window_start),
                )

                results = cursor.fetchall()
                if results:
                    # Encontrou duplicata por ISRC
                    first_match = results[0]
                    logger.info(
                        f"Duplicata detectada por ISRC: {isrc} - {song_title} por {artist} em {name} "
                        f"(original: {first_match[3]} por {first_match[4]} em {first_match[1]} {first_match[2]})"
                    )
                    return True

            # Se não temos ISRC ou não encontramos por ISRC, fazemos a verificação por título e artista
            cursor.execute(
                """
                SELECT id, date, time, song_title, artist, isrc
                FROM music_log
                WHERE name = %s
                  AND (date + time) >= %s
                ORDER BY date DESC, time DESC
                LIMIT 50
                """,
                (name, window_start),
            )

            results = cursor.fetchall()
            if not results:
                return False

            # Limpar strings de entrada
            clean_input_title = clean_string(song_title)
            clean_input_artist = clean_string(artist)

            # Verificação de strings vazias após limpeza
            if not clean_input_title or not clean_input_artist:
                logger.warning(
                    f"Strings vazias após limpeza: '{song_title}' -> '{clean_input_title}' | '{artist}' -> '{clean_input_artist}'"
                )
                # Se as strings ficaram vazias após limpeza, usar as originais
                if not clean_input_title:
                    clean_input_title = song_title.lower().strip()
                if not clean_input_artist:
                    clean_input_artist = artist.lower().strip()

            # Verificar cada registro recente com diferentes níveis de similaridade
            for row in results:
                db_id, db_date, db_time, db_title, db_artist = row

                clean_db_title = clean_string(db_title)
                clean_db_artist = clean_string(db_artist)

                # Verificação de strings vazias após limpeza para dados do DB
                if not clean_db_title or not clean_db_artist:
                    if not clean_db_title:
                        clean_db_title = db_title.lower().strip()
                    if not clean_db_artist:
                        clean_db_artist = db_artist.lower().strip()

                # Calcular tempo decorrido a partir de date/time
                record_ts = datetime.combine(db_date, db_time)
                time_diff = (datetime.now() - record_ts).total_seconds()

                # Verificação exata após limpeza (mais rigorosa)
                if (
                    clean_input_title == clean_db_title
                    and clean_input_artist == clean_db_artist
                ):
                    logger.info(
                        f"Duplicata EXATA detectada: {song_title} - {artist} em {name} "
                        f"(ID: {db_id}, criado há {int(time_diff/60)}min atrás - {SERVER_ID})"
                    )
                    return True

                # Cálculo de similaridade de título usando diferentes métodos
                title_exact_match = clean_input_title == clean_db_title
                title_contains = (
                    clean_input_title in clean_db_title
                    or clean_db_title in clean_input_title
                )

                # Verificação de prefixo/sufixo mais robusta
                title_prefix_match = False
                title_suffix_match = False

                if len(clean_input_title) >= 5 and len(clean_db_title) >= 5:
                    # Verificar os primeiros 5 caracteres
                    title_prefix_match = clean_input_title[:5] == clean_db_title[:5]
                    # Verificar os últimos 5 caracteres
                    title_suffix_match = clean_input_title[-5:] == clean_db_title[-5:]

                # Cálculo de similaridade de artista
                artist_exact_match = clean_input_artist == clean_db_artist
                artist_contains = (
                    clean_input_artist in clean_db_artist
                    or clean_db_artist in clean_input_artist
                )

                # Verificação de prefixo para artista
                artist_prefix_match = False
                if len(clean_input_artist) >= 3 and len(clean_db_artist) >= 3:
                    artist_prefix_match = clean_input_artist[:3] == clean_db_artist[:3]

                # Níveis de similaridade
                high_similarity = (
                    title_exact_match
                    or (title_contains and (title_prefix_match or title_suffix_match))
                ) and (artist_exact_match or artist_contains)

                medium_similarity = (
                    title_contains or title_prefix_match or title_suffix_match
                ) and (artist_contains or artist_prefix_match)

                # Ajustar threshold baseado no tempo decorrido e nível de similaridade
                if high_similarity:
                    # Alta similaridade: janela de 120 minutos (7200 segundos)
                    if time_diff < 7200:
                        logger.info(
                            f"Duplicata ALTA SIMILARIDADE detectada: {song_title} - {artist} em {name} "
                            f"(similar a: '{db_title}' - '{db_artist}' criado há {int(time_diff/60)}min atrás - {SERVER_ID})"
                        )
                        return True
                elif medium_similarity:
                    # Média similaridade: janela de 60 minutos (3600 segundos)
                    if time_diff < 3600:
                        logger.info(
                            f"Duplicata MÉDIA SIMILARIDADE detectada: {song_title} - {artist} em {name} "
                            f"(similar a: '{db_title}' - '{db_artist}' criado há {int(time_diff/60)}min atrás - {SERVER_ID})"
                        )
                        return True
                # Baixa similaridade (apenas correspondência parcial): janela de 30 minutos
                elif (title_contains or artist_contains) and time_diff < 1800:
                    logger.info(
                        f"Duplicata BAIXA SIMILARIDADE detectada: {song_title} - {artist} em {name} "
                        f"(similar a: '{db_title}' - '{db_artist}' criado há {int(time_diff/60)}min atrás - {SERVER_ID})"
                    )
                    return True

            return False

    except Exception as e:
        logger.error(f"Erro ao verificar inserção recente: {e}")
        return False
    finally:
        if conn:
            get_db_pool().pool.putconn(conn)


# === Fim das Funções de Distribuição ===

# Configurar logging para console e arquivo (REMOVIDO DAQUI)

# Registrar informações sobre as variáveis de ambiente carregadas
logger.info("=== Iniciando script com as seguintes configurações ===")
logger.info(f"SERVER_ID: {SERVER_ID} (tipo: {type(SERVER_ID).__name__})")
logger.info(f"TOTAL_SERVERS: {TOTAL_SERVERS} (tipo: {type(TOTAL_SERVERS).__name__})")
logger.info(f"DISTRIBUTE_LOAD: {DISTRIBUTE_LOAD}")
logger.info("Sistema de distribuição: Hashing consistente ativado")
logger.info(f"DB_TABLE_NAME: {DB_TABLE_NAME}")
logger.info(f"ENABLE_FAILOVER_SEND: {ENABLE_FAILOVER_SEND}")
logger.info(f"FAILOVER_METHOD: {FAILOVER_METHOD}")
logger.info(f"FAILOVER_HOST: {FAILOVER_HOST}")
logger.info(f"FAILOVER_PORT: {FAILOVER_PORT}")
logger.info(f"FAILOVER_USER: {FAILOVER_USER}")
logger.info(f"FAILOVER_REMOTE_DIR: {FAILOVER_REMOTE_DIR}")
logger.info(f"FAILOVER_SSH_KEY_PATH: {FAILOVER_SSH_KEY_PATH}")
logger.info("======================================================")


# --- Função para Envio de Arquivo via Failover (FTP/SFTP) ---
async def send_file_via_failover(local_file_path, stream_index):
    """Envia um arquivo para o servidor de failover configurado (FTP ou SFTP)."""
    if not ENABLE_FAILOVER_SEND:
        logger.debug("Envio para failover desabilitado nas configurações.")
        return

    if not all([FAILOVER_HOST, FAILOVER_USER, FAILOVER_PASSWORD, FAILOVER_REMOTE_DIR]):
        logger.error(
            "Configurações de failover incompletas no .env. Impossível enviar arquivo."
        )
        return

    if stream_index is None:
        logger.error(
            "Índice do stream não fornecido. Não é possível nomear o arquivo de failover."
        )
        return

    # Criar um nome de arquivo único no servidor remoto
    timestamp_str = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_filename = (
        f"{stream_index}_{timestamp_str}_{os.path.basename(local_file_path)}"
    )
    # Usar os.path.join e depois replace para garantir compatibilidade entre OS no caminho remoto
    remote_path = os.path.join(FAILOVER_REMOTE_DIR, remote_filename).replace("\\", "/")

    logger.info(
        f"Tentando enviar {local_file_path} para failover via {FAILOVER_METHOD} em {FAILOVER_HOST}:{FAILOVER_PORT}"
    )
    logger.debug(f"Caminho remoto: {remote_path}")

    try:
        if FAILOVER_METHOD == "SFTP":
            if not HAS_PYSFTP:
                logger.error(
                    "SFTP selecionado, mas a biblioteca pysftp não está instalada."
                )
                return

            cnopts = pysftpCnOpts()
            # Ignorar verificação da chave do host (menos seguro, mas evita problemas de configuração inicial)
            # Considere configurar known_hosts para produção
            cnopts.hostkeys = None

            # Definir kwargs para conexão SFTP
            sftp_kwargs = {
                "host": FAILOVER_HOST,
                "port": FAILOVER_PORT,
                "username": FAILOVER_USER,
                "cnopts": cnopts,
            }
            if FAILOVER_SSH_KEY_PATH and os.path.exists(FAILOVER_SSH_KEY_PATH):
                sftp_kwargs["private_key"] = FAILOVER_SSH_KEY_PATH
                sftp_kwargs["private_key_pass"] = (
                    FAILOVER_PASSWORD  # Senha da chave, se houver
                )
                logger.debug("Usando chave SSH para autenticação SFTP.")
            else:
                sftp_kwargs["password"] = FAILOVER_PASSWORD
                logger.debug("Usando senha para autenticação SFTP.")

            # Usar asyncio.to_thread para a operação sftp bloqueante
            await asyncio.to_thread(
                _sftp_upload_sync, sftp_kwargs, local_file_path, remote_path
            )

        elif FAILOVER_METHOD == "FTP":
            # Usar asyncio.to_thread para operações de FTP bloqueantes
            await asyncio.to_thread(_ftp_upload_sync, local_file_path, remote_path)

        else:
            logger.error(
                f"Método de failover desconhecido: {FAILOVER_METHOD}. Use 'FTP' ou 'SFTP'."
            )

    except Exception as e:
        logger.error(
            f"Erro ao enviar arquivo via {FAILOVER_METHOD} para {FAILOVER_HOST}: {e}",
            exc_info=True,
        )


# Função auxiliar bloqueante para SFTP (para ser usada com asyncio.to_thread)
def _sftp_upload_sync(sftp_kwargs, local_file_path, remote_path):
    # A conexão SFTP é feita dentro do 'with' que agora está nesta função síncrona
    with pysftp.Connection(**sftp_kwargs) as sftp:
        logger.info(f"Conectado ao SFTP: {FAILOVER_HOST}")
        remote_dir = os.path.dirname(remote_path)
        # Garantir que o diretório remoto exista (opcional, mas útil)
        try:
            sftp.makedirs(remote_dir)
            logger.debug(f"Diretório remoto {remote_dir} verificado/criado.")
        except OSError as e:
            # Ignora erro se o diretório já existe, mas loga outros erros
            if "Directory already exists" not in str(e):
                logger.warning(
                    f"Não foi possível criar/verificar diretório SFTP {remote_dir}: {e}"
                )

        sftp.put(local_file_path, remote_path)
        logger.info(
            f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via SFTP para {remote_dir}"
        )


# Função auxiliar bloqueante para FTP (para ser usada com asyncio.to_thread)
def _ftp_upload_sync(local_file_path, remote_path):
    ftp = None
    try:
        ftp = FTP()
        ftp.connect(FAILOVER_HOST, FAILOVER_PORT, timeout=30)  # Timeout de 30s
        ftp.login(FAILOVER_USER, FAILOVER_PASSWORD)
        logger.info(f"Conectado ao FTP: {FAILOVER_HOST}")

        # Tentar criar diretórios recursivamente (simples)
        remote_dir = os.path.dirname(remote_path)
        dirs_to_create = remote_dir.strip("/").split(
            "/"
        )  # Remover barras inicial/final e dividir
        current_dir = ""
        for d in dirs_to_create:
            if not d:
                continue
            current_dir = (
                f"{current_dir}/{d}" if current_dir else f"/{d}"
            )  # Construir caminho absoluto
            try:
                ftp.mkd(current_dir)
                logger.debug(f"Diretório FTP criado: {current_dir}")
            except error_perm as e:
                if not e.args[0].startswith(
                    "550"
                ):  # Ignorar erro "já existe" ou "permissão negada" (pode já existir)
                    logger.warning(
                        f"Não foi possível criar diretório FTP {current_dir}: {e}"
                    )
                # else:
                #     logger.debug(f"Diretório FTP já existe ou permissão negada para criar: {current_dir}")

        # Mudar para o diretório final (se existir)
        try:
            ftp.cwd(remote_dir)
            logger.debug(f"Mudado para diretório FTP: {remote_dir}")
        except error_perm as e:
            logger.error(
                f"Não foi possível mudar para o diretório FTP {remote_dir}: {e}. Upload pode falhar."
            )
            # Considerar lançar o erro ou retornar se o diretório é essencial
            # raise # Re-lança o erro se não conseguir mudar para o diretório
            return  # Ou simplesmente retorna se não conseguir mudar

        with open(local_file_path, "rb") as fp:
            ftp.storbinary(f"STOR {os.path.basename(remote_path)}", fp)
        logger.info(
            f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via FTP para {remote_dir}"
        )

    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass  # Ignorar erros ao fechar


# --- Fim das Funções de Failover ---


# Verificar se a tabela de logs existe (RESTAURADO)
def check_log_table():
    logger.info(
        f"Verificando se a tabela de logs '{DB_TABLE_NAME}' existe no banco de dados..."
    )
    lock_id = 12345  # ID de bloqueio arbitrário para esta operação específica

    try:
        with get_db_pool().get_connection_sync() as conn:
            # Forçar autocommit para que DDL não deixe a sessão em estado abortado
            prev_autocommit = getattr(conn, "autocommit", False)
            try:
                conn.autocommit = True
            except Exception:
                prev_autocommit = False

            # Salvar lock_timeout e statement_timeout atuais e aumentar temporariamente para DDL
            prev_lock_timeout = None
            prev_statement_timeout = None
            try:
                with conn.cursor() as c:
                    c.execute("SHOW lock_timeout")
                    prev_lock_timeout = c.fetchone()[0]
                    c.execute("SHOW statement_timeout")
                    prev_statement_timeout = c.fetchone()[0]
                    c.execute("SET lock_timeout = '300000'")  # 5min
                    c.execute("SET statement_timeout = '300000'")  # 5min para DDL
            except Exception as e:
                logger.warning(f"Não foi possível ajustar timeouts: {e}")

            lock_acquired = False
            try:
                logger.debug("Tentando adquirir advisory lock...")
                # Tentar obter um bloqueio consultivo (sem aguardar)
                with conn.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
                    lock_acquired = cursor.fetchone()[0]
                logger.debug(f"Lock adquirido: {lock_acquired}")

                if not lock_acquired:
                    logger.warning(
                        "Não foi possível obter o bloqueio para verificação da tabela. Outro processo pode estar em execução."
                    )
                    return False

                logger.debug("Iniciando criação da tabela IF NOT EXISTS...")
                # Criar tabela se não existir (sem checagem prévia para reduzir janelas de corrida)
                create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {DB_TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    time TIME NOT NULL,
    name VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    song_title VARCHAR(255) NOT NULL,
    isrc VARCHAR(50),
    cidade VARCHAR(100),
    estado VARCHAR(50),
    regiao VARCHAR(50),
    segmento VARCHAR(100),
    label VARCHAR(255),
    genre VARCHAR(100),
    identified_by VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
                """
                with conn.cursor() as cursor:
                    cursor.execute(create_table_sql)
                logger.debug("Criação da tabela concluída.")

                logger.debug("Adicionando coluna identified_by IF NOT EXISTS...")
                # Garantir coluna 'identified_by'
                with conn.cursor() as cursor:
                    add_sql = (
                        f"ALTER TABLE {DB_TABLE_NAME} "
                        "ADD COLUMN IF NOT EXISTS identified_by VARCHAR(10);"
                    )
                    cursor.execute(add_sql)
                logger.debug("Adição de coluna identified_by concluída.")

                logger.debug("Removendo coluna identified_by_server IF EXISTS...")
                # Remover coluna obsoleta 'identified_by_server' se existir
                with conn.cursor() as cursor:
                    drop_sql = (
                        f"ALTER TABLE {DB_TABLE_NAME} "
                        "DROP COLUMN IF EXISTS identified_by_server;"
                    )
                    cursor.execute(drop_sql)
                logger.debug("Remoção de coluna identified_by_server concluída.")

                logger.info(
                    f"Tabela de logs '{DB_TABLE_NAME}' verificada/ajustada com sucesso!"
                )
                logger.debug("Verificação da tabela concluída com sucesso.")
                return True

            except psycopg2.errors.LockNotAvailable as e:
                logger.warning(
                    f"Operação atingiu lock_timeout durante DDL/verificação: {e}"
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
                return False
            except Exception as e:
                logger.error(
                    f"Erro ao verificar/criar tabela de logs: {e}", exc_info=True
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
                return False
            finally:
                logger.debug("Restaurando timeouts...")
                # Restaurar timeouts anteriores
                try:
                    with conn.cursor() as c:
                        if prev_lock_timeout is not None:
                            c.execute(f"SET lock_timeout = '{prev_lock_timeout}'")
                        if prev_statement_timeout is not None:
                            c.execute(
                                f"SET statement_timeout = '{prev_statement_timeout}'"
                            )
                except Exception as e:
                    logger.debug(f"Falha ao restaurar timeouts: {e}")
                else:
                    logger.debug("Timeouts restaurados.")

                # Liberar o bloqueio consultivo
                try:
                    if lock_acquired:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                except Exception as unlock_err:
                    logger.warning(
                        f"Falha ao liberar advisory lock {lock_id}: {unlock_err}"
                    )

                # Restaurar autocommit original
                try:
                    conn.autocommit = prev_autocommit
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Erro ao verificar tabela de logs: {e}", exc_info=True)
        return False


# Fila para enviar ao Shazamio (RESTAURADO)
shazam_queue = asyncio.Queue()

# Variável para controlar o último heartbeat enviado (RESTAURADO)
last_heartbeat_time = 0
HEARTBEAT_INTERVAL_SECS = 60  # Enviar heartbeat a cada 1 minuto

# Variável global para controle da pausa do Shazam (RESTAURADO)
shazam_pause_until_timestamp = 0.0

# Variável global para armazenar last_songs
last_songs = {}


# Classe StreamConnectionTracker (RESTAURADO)
class StreamConnectionTracker:
    def __init__(self):
        self.connection_errors = {}  # Stores stream_name: error_timestamp
        self.error_counts = {}  # Stores stream_name: consecutive_error_count

    def record_error(self, stream_name):
        """Records the timestamp of the first consecutive error for a stream."""
        if stream_name not in self.connection_errors:
            self.connection_errors[stream_name] = time.time()
            self.error_counts[stream_name] = 1
            logger.debug(f"Registrado primeiro erro de conexão para: {stream_name}")
        else:
            # Incrementar contador de erros consecutivos
            self.error_counts[stream_name] = self.error_counts.get(stream_name, 0) + 1
            logger.debug(
                f"Erro consecutivo #{self.error_counts[stream_name]} para: {stream_name}"
            )

    def clear_error(self, stream_name):
        """Clears the error status for a stream if it was previously recorded."""
        if stream_name in self.connection_errors:
            del self.connection_errors[stream_name]
            logger.debug(f"Erro de conexão limpo para: {stream_name}")
        if stream_name in self.error_counts:
            del self.error_counts[stream_name]
            logger.debug(f"Contador de erros limpo para: {stream_name}")

    def get_error_count(self, stream_name):
        """Returns the number of consecutive errors for a stream."""
        return self.error_counts.get(stream_name, 0)

    def check_persistent_errors(self, threshold_minutes=10):
        """Checks for streams that have been failing for longer than the threshold."""
        current_time = time.time()
        persistent_errors = []
        threshold_seconds = threshold_minutes * 60
        for stream_name, error_time in list(
            self.connection_errors.items()
        ):  # Iterate over a copy
            if (current_time - error_time) > threshold_seconds:
                persistent_errors.append(stream_name)
                # Optionally remove from dict once alerted to prevent repeated alerts immediately
                # del self.connection_errors[stream_name]
        if persistent_errors:
            logger.debug(
                f"Erros persistentes encontrados (> {threshold_minutes} min): {persistent_errors}"
            )
        return persistent_errors


connection_tracker = StreamConnectionTracker()  # Instanciar o tracker (RESTAURADO)


# Função para conectar ao banco de dados PostgreSQL usando pool
def connect_db():
    """
    Função de compatibilidade que usa o pool de conexões.
    DEPRECATED: Use get_db_pool().get_connection() diretamente para novos códigos.
    """
    try:
        # Validar se as configurações essenciais existem
        if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
            missing = []
            if not DB_HOST:
                missing.append("POSTGRES_HOST")
            if not DB_USER:
                missing.append("POSTGRES_USER")
            if not DB_PASSWORD:
                missing.append("POSTGRES_PASSWORD")
            if not DB_NAME:
                missing.append("POSTGRES_DB")

            error_msg = f"Configurações de banco de dados incompletas. Faltando: {', '.join(missing)}"
            logger.error(error_msg)
            return None

        # Usar o pool de conexões em vez de criar conexão direta
        logger.debug(
            f"Obtendo conexão do pool para PostgreSQL: {DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

        # Retornar uma conexão do pool (sem context manager para compatibilidade)
        conn = get_db_pool().pool.getconn()
        if conn:
            # Testar se a conexão está válida
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            logger.debug("Conexão do pool obtida com sucesso!")
            return conn
        else:
            logger.error("Não foi possível obter conexão do pool")
            return None

    except psycopg2.OperationalError as e:
        error_msg = f"Erro operacional ao conectar ao banco: {e}"
        logger.error(error_msg)
        return None
    except Exception as e:
        error_msg = f"Erro ao conectar ao banco de dados: {e}"
        logger.error(error_msg)
        return None


# Função para retornar conexão ao pool
def close_db_connection(conn):
    """
    Retorna a conexão ao pool em vez de fechá-la.
    Use esta função em vez de conn.close() quando usar connect_db().
    """
    if conn:
        try:
            get_db_pool().pool.putconn(conn)
        except Exception as e:
            logger.error(f"Erro ao retornar conexão ao pool: {e}")


# Função para calcular o deslocamento de rotação com base no tempo
# calculate_rotation_offset - Função depreciada, removida em favor de hashing consistente


# Função para buscar streams do banco de dados
def fetch_streams_from_db():
    """
    Busca a configuração dos streams do banco de dados PostgreSQL.
    Retorna a lista de streams ou None em caso de erro.
    """
    try:
        with get_db_pool().get_connection_sync() as conn:
            with conn.cursor() as cursor:
                # Verificar se a tabela streams existe
                cursor.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'streams')"
                )
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    logger.error("A tabela 'streams' não existe no banco de dados!")
                    return None

                # Buscar todos os streams ordenados por index
                cursor.execute(
                    "SELECT url, name, sheet, cidade, estado, regiao, segmento, index FROM streams ORDER BY index"
                )
                rows = cursor.fetchall()

                streams = []
                for row in rows:
                    stream = {
                        "url": row[0],
                        "name": row[1],
                        "sheet": row[2],
                        "cidade": row[3],
                        "estado": row[4],
                        "regiao": row[5],
                        "segmento": row[6],
                        "index": str(row[7]),
                        "id": str(row[7]),  # Adicionar campo 'id' baseado no index
                        "metadata": {},  # Adicionar campo metadata vazio
                    }
                    streams.append(stream)

                logger.info(f"Carregados {len(streams)} streams do banco de dados.")
                return streams

    except Exception as e:
        logger.error(f"Erro ao buscar streams do banco de dados: {e}")
        return None


# Função para salvar streams no arquivo JSON local
# Função save_streams_to_json removida - não é mais necessária com o orquestrador


# Função para carregar os streamings do banco de dados PostgreSQL
def load_streams():
    """
    Carrega a configuração dos streams apenas do banco de dados.
    Retorna apenas a lista de streams.
    """
    streams_from_db = fetch_streams_from_db()  # Busca do DB

    if streams_from_db is not None:
        logger.info("Streams carregados com sucesso do banco de dados.")
        return streams_from_db  # Retorna apenas a lista de streams
    else:
        logger.critical(
            "Falha ao carregar streams do banco de dados. "
            "Não há fonte de streams disponível."
        )
        return []


# Função para carregar o estado das últimas músicas identificadas
def load_last_songs():
    logger.debug("Iniciando a função load_last_songs()")
    try:
        if os.path.exists(LAST_SONGS_FILE):
            with open(LAST_SONGS_FILE, "r", encoding="utf-8") as f:
                last_songs = json.load(f)
                logger.info(f"{len(last_songs)} últimas músicas carregadas.")
                return last_songs
        else:
            return {}
    except Exception as e:
        logger.error(f"Erro ao carregar o arquivo de estado das últimas músicas: {e}")
        return {}


# Função para salvar o estado das últimas músicas identificadas
def save_last_songs(last_songs):
    logger.debug("Iniciando a função save_last_songs()")
    try:
        with open(LAST_SONGS_FILE, "w", encoding="utf-8") as f:
            json.dump(last_songs, f, indent=4, ensure_ascii=False)
        logger.info(f"Arquivo de estado {LAST_SONGS_FILE} salvo.")
    except IOError as e:
        logger.error(f"Erro ao salvar estado em {LAST_SONGS_FILE}: {e}")


# Função para carregar o log local
def load_local_log():
    logger.debug("Iniciando a função load_local_log()")
    try:
        if os.path.exists(LOCAL_LOG_FILE):
            with open(LOCAL_LOG_FILE, "r", encoding="utf-8") as f:
                local_log = json.load(f)
                logger.info(f"{len(local_log)} entradas carregadas do log local.")
                return local_log
        else:
            return []
    except Exception as e:
        logger.error(f"Erro ao carregar o log local: {e}")
        return []


# Função para salvar o log local
def save_local_log(local_log):
    logger.debug("Iniciando a função save_local_log()")
    try:
        with open(LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(local_log, f, ensure_ascii=False)
        logger.info(f"Log local {LOCAL_LOG_FILE} salvo.")
    except IOError as e:
        logger.error(f"Erro ao salvar log local em {LOCAL_LOG_FILE}: {e}")


# Função para apagar o log local
def clear_local_log():
    logger.debug("Iniciando a função clear_local_log()")
    try:
        with open(LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        logger.info("Log local limpo.")
    except IOError as e:
        logger.error(f"Erro ao limpar o log local {LOCAL_LOG_FILE}: {e}")


# Função para verificar duplicidade na log local
def is_duplicate_in_log(song_title, artist, name):
    logger.debug("Iniciando a função is_duplicate_in_log()")
    local_log = load_local_log()
    for entry in local_log:
        if (
            entry["song_title"] == song_title
            and entry["artist"] == artist
            and entry["name"] == name
        ):
            return True
    return False


# Função para converter a data e hora ISO 8601 para dd/mm/yyyy e HH:MM:SS
def convert_iso8601_to_datetime(iso_date):
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
    except Exception as e:
        logger.error(f"Erro ao converter a data e hora: {e}")
        return iso_date, iso_date


# Função para monitorar periodicamente o banco de dados para atualizações nos streams
# Função monitor_streams_file removida - não é mais necessária com o orquestrador


# Função para capturar o áudio do streaming ao vivo e salvar um segmento temporário
async def capture_stream_segment(name, url, duration=None):
    # Agora a decisão de processar ou não é feita pelo sistema de bloqueio distribuído

    # Usar configuração global se não especificado
    if duration is None:
        duration = IDENTIFICATION_DURATION

    output_dir = SEGMENTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir, f"{name}_segment.mp3"
    )  # Sempre o mesmo arquivo
    try:
        logger.debug(f"URL do stream: {url}")
        # Remover a verificação prévia da URL com requests
        # Remover o parâmetro -headers
        command = [
            "ffmpeg",
            "-y",
            "-i",
            url,
            "-t",
            str(duration),
            "-ac",
            "1",
            "-ar",
            "44100",
            "-b:a",
            "192k",
            "-acodec",
            "libmp3lame",
            output_path,
        ]
        logger.info(f"Capturando segmento de {duration} segundos do stream {name}...")
        logger.debug(f"Comando FFmpeg: {' '.join(command)}")

        # Usar o timeout otimizado
        capture_timeout = (
            duration + 15
        )  # 15 segundos a mais do que a duração desejada (otimizado)

        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=capture_timeout
        )

        if process.returncode != 0:
            stderr_text = (
                stderr.decode(errors="ignore") if stderr else "Sem saída de erro"
            )
            logger.error(f"Erro ao capturar o stream {url}: {stderr_text}")
            connection_tracker.record_error(name)  # Registra o erro
            return None
        else:
            # Verificar se o arquivo foi criado e tem um tamanho razoável
            if (
                os.path.exists(output_path) and os.path.getsize(output_path) > 1000
            ):  # Mais de 1KB
                logger.info(
                    f"Segmento de {duration} segundos capturado com sucesso para {name}."
                )
                connection_tracker.clear_error(
                    name
                )  # Limpa o erro se a captura for bem-sucedida
                return output_path
            else:
                logger.error(f"Arquivo de saída vazio ou muito pequeno para {name}.")
                connection_tracker.record_error(name)
                return None
    except asyncio.TimeoutError:
        logger.error(
            f"Tempo esgotado para capturar o stream {url} após {capture_timeout}s"
        )
        connection_tracker.record_error(name)  # Registra o erro
        if "process" in locals():
            process.kill()
        return None
    except Exception as e:
        logger.error(f"Erro ao capturar o stream {url}: {str(e)}")
        logger.error(f"Tipo de erro: {type(e).__name__}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        connection_tracker.record_error(name)  # Registra o erro
        return None


# Função para verificar duplicatas no banco de dados (MODIFICADA)
async def _internal_is_duplicate_in_db(cursor, now_tz, name, artist, song_title):
    # Recebe datetime timezone-aware (now_tz)
    # --- Log Detalhado Início ---
    logger.debug(f"[_internal_is_duplicate] Iniciando verificação para:")
    logger.debug(f"  Stream: {name}")
    logger.debug(f"  Artista: {artist}")
    logger.debug(f"  Título: {song_title}")
    logger.debug(f"  Timestamp Atual (TZ): {now_tz}")  # Log do timestamp TZ-aware
    logger.debug(f"  Janela (s): {DUPLICATE_PREVENTION_WINDOW_SECONDS}")
    # --- Fim Log Detalhado ---

    try:
        # Calcular o início da janela de verificação usando o timestamp TZ-aware
        start_window_tz = now_tz - timedelta(
            seconds=DUPLICATE_PREVENTION_WINDOW_SECONDS
        )
        # Extrair data e hora (como objetos date e time) para a query
        start_date = start_window_tz.date()
        start_time = start_window_tz.time()

        # --- Log Detalhado Cálculo Janela ---
        logger.debug(f"  Início Janela (TZ): {start_window_tz}")
        logger.debug(f"  Data Início Janela: {start_date}")
        logger.debug(f"  Hora Início Janela: {start_time}")
        # --- Fim Log Detalhado ---

        result = None
        try:
            # Usar apenas a abordagem de comparação separada (mais robusta)
            query = f"""
            SELECT id, date, time FROM {DB_TABLE_NAME}
                WHERE name = %s AND artist = %s AND song_title = %s
                AND (date > %s OR (date = %s AND time >= %s))
            LIMIT 1
            """
            params = (name, artist, song_title, start_date, start_date, start_time)
            # --- Log Detalhado Query ---
            logger.debug(f"  Executando Query (DATE/TIME): {query.strip()}")
            logger.debug(f"  Parâmetros Query: {params}")
            # --- Fim Log Detalhado ---

            # Executar a operação de banco de dados em um thread
            def db_query():
                try:
                    cursor.execute(query, params)
                    return cursor.fetchone()
                except Exception as e_query_thread:
                    # Logar o erro aqui também, pois pode não ser propagado corretamente
                    logger.error(
                        f"[_internal_is_duplicate] Erro dentro do thread db_query: {e_query_thread}"
                    )
                    raise  # Re-lança para ser pego pelo bloco except externo

            result = await asyncio.to_thread(db_query)

            if result:
                logger.debug(
                    f"  Query encontrou resultado: ID={result[0]}, Data={result[1]}, Hora={result[2]}"
                )
            else:
                logger.debug(f"  Query não encontrou resultado.")

        except Exception as e_query:
            logger.error(
                f"[_internal_is_duplicate] Erro ao executar query de duplicidade (possivelmente no to_thread): {e_query}",
                exc_info=True,
            )
            # --- Log Detalhado Erro Query ---
            logger.debug(
                f"[_internal_is_duplicate] Retornando False devido a erro na query."
            )
            # --- Fim Log Detalhado ---
            return False  # Assume não duplicata se a query falhar

        is_duplicate = result is not None
        # --- Log Detalhado Resultado Final ---
        if is_duplicate:
            logger.info(
                f"[_internal_is_duplicate] Duplicata ENCONTRADA para {song_title} - {artist} em {name} (ID={result[0]} às {result[1]} {result[2]})."
            )
            logger.debug(f"[_internal_is_duplicate] Retornando True.")
        else:
            logger.info(
                f"[_internal_is_duplicate] Nenhuma duplicata ENCONTRADA para {song_title} - {artist} em {name} na janela de tempo."
            )  # Mais claro
            logger.debug(f"[_internal_is_duplicate] Retornando False.")
        # --- Fim Log Detalhado ---
        return is_duplicate

    except Exception as e_geral:
        logger.error(
            f"[_internal_is_duplicate] Erro GERAL ao verificar duplicatas: {e_geral}",
            exc_info=True,
        )
        # --- Log Detalhado Erro Geral ---
        logger.debug(f"[_internal_is_duplicate] Retornando False devido a erro geral.")
        # --- Fim Log Detalhado ---
        return False  # Assume não duplicata em caso de erro na verificação


# Função para inserir dados no banco de dados usando fila assíncrona
async def insert_data_to_db(entry_base, now_tz):
    """
    Adiciona uma tarefa de inserção à fila assíncrona.
    Retorna True se a tarefa foi adicionada com sucesso à fila.
    """
    song_title = entry_base["song_title"]
    artist = entry_base["artist"]
    name = entry_base["name"]
    isrc = entry_base.get("isrc", None)

    logger.debug(
        f"insert_data_to_db: Adicionando à fila: {song_title} - {artist} em {name} (ISRC: {isrc})"
    )

    try:
        # Verificar se já existe uma inserção recente para esta música neste stream
        # Usando ISRC como identificador principal quando disponível
        is_recent_duplicate = await asyncio.to_thread(
            check_recent_insertion, name, song_title, artist, isrc
        )

        if is_recent_duplicate:
            logger.info(
                f"insert_data_to_db: Inserção ignorada - duplicata recente detectada para {song_title} - {artist} em {name}"
            )
            return False

        # Formatar dados para inserção
        date_str = now_tz.strftime("%Y-%m-%d")
        time_str = now_tz.strftime("%H:%M:%S")

        entry = entry_base.copy()
        entry["date"] = date_str
        entry["time"] = time_str
        entry["identified_by"] = str(SERVER_ID)

        # Adicionar à fila assíncrona
        await insert_queue.add_insert_task(entry)

        logger.info(
            f"insert_data_to_db: Tarefa adicionada à fila com sucesso: {song_title} - {artist} ({name})"
        )
        return True

    except Exception as e:
        logger.error(
            f"insert_data_to_db: Erro ao adicionar tarefa à fila ({song_title} - {artist}): {e}",
            exc_info=True,
        )

        # Enviar alerta por e-mail em caso de erro crítico
        try:
            subject = "Alerta: Erro ao Adicionar Tarefa à Fila de Inserção"
            body = f"O servidor {SERVER_ID} encontrou um erro ao adicionar uma tarefa à fila de inserção.\n\nErro: {e}\nDados: {entry_base}"
            send_email_alert(subject, body)
        except Exception as email_err:
            logger.error(f"Erro ao enviar e-mail de alerta: {email_err}")

        return False


# Função para atualizar o log local e chamar a inserção no DB
async def update_local_log(
    stream, song_title, artist, timestamp, isrc=None, label=None, genre=None
):
    # ... (Criação de date_str, time_str, stream_name - igual a antes) ...
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H:%M:%S")
    stream_name = stream["name"]
    logger.debug(
        f"update_local_log: Preparando {song_title} - {artist} em {stream_name}"
    )

    # ... (Carregamento do log local - igual a antes) ...
    local_log = []
    try:
        if os.path.exists(LOCAL_LOG_FILE):
            with open(LOCAL_LOG_FILE, "r", encoding="utf-8") as f:
                local_log = json.load(f)
    except json.JSONDecodeError:
        logger.warning("Arquivo de log local corrompido ou vazio. Criando um novo.")
    except Exception as e:
        logger.error(f"Erro ao carregar log local: {e}")

    # Cria a nova entrada
    new_entry = {
        "date": date_str,
        "time": time_str,
        "name": stream_name,
        "artist": artist,
        "song_title": song_title,
        "isrc": isrc,
        "cidade": stream.get("cidade", ""),
        "estado": stream.get("estado", ""),
        "regiao": stream.get("regiao", ""),
        "segmento": stream.get("segmento", ""),
        "label": label,
        "genre": genre,
        "identified_by": str(SERVER_ID),
    }

    # Tenta inserir no banco de dados (a função insert_data_to_db agora faz a checagem de duplicidade)
    inserted_successfully = await insert_data_to_db(
        new_entry, timestamp.replace(tzinfo=timezone.utc)
    )

    if inserted_successfully:
        logger.info(
            f"update_local_log: Inserção de {song_title} - {artist} bem-sucedida. Atualizando log local."
        )
        # Adiciona ao log local apenas se inserido com sucesso no DB
        local_log.append(new_entry)
        local_log = local_log[-1000:]  # Mantém tamanho gerenciável

        # Salva o log local atualizado
        try:
            with open(LOCAL_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(local_log, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar log local: {e}")

        return True  # Indica que foi uma nova inserção bem-sucedida
    else:
        # A inserção falhou (seja por duplicidade ou erro)
        # O log da falha já foi feito dentro de insert_data_to_db
        logger.info(
            f"update_local_log: Inserção de {song_title} - {artist} falhou ou foi ignorada (duplicata/erro). Log local não atualizado."
        )
        return False


# Função para processar um único stream
async def process_stream(stream, last_songs):
    logger.debug("Iniciando a função process_stream()")
    url = stream["url"]
    name = stream["name"]
    # Use stream index or name as the key for tracking
    stream_key = stream.get("index", name)
    previous_segment = None
    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            logger.info(f"Processando streaming: {name} (ciclo {cycle_count})")

            current_segment_path = await capture_stream_segment(
                name, url, duration=None
            )

            if current_segment_path is None:
                # Registrar erro no tracker
                connection_tracker.record_error(stream_key)
                failure_count = connection_tracker.get_error_count(stream_key)

                wait_time = 5  # Tempo de espera reduzido
                if failure_count > 3:
                    wait_time = 15  # Tempo de espera após falhas reduzido

                logger.error(
                    f"Falha ao capturar segmento do streaming {name} ({stream_key}). Falha #{failure_count}. Tentando novamente em {wait_time} segundos..."
                )
                await asyncio.sleep(wait_time)
                continue
            else:
                # Limpar erros no tracker em caso de sucesso
                connection_tracker.clear_error(stream_key)

            # Se a captura foi bem-sucedida, prosseguir com o Shazam
            await shazam_queue.put((current_segment_path, stream, last_songs))
            await shazam_queue.join()  # Esperar o item ser processado antes do próximo ciclo

            logger.info(
                f"Aguardando 45 segundos para o próximo ciclo do stream {name} ({stream_key})..."
            )
            await asyncio.sleep(45)  # Intervalo de captura de segmentos (otimizado)

    except asyncio.CancelledError:
        logger.info(f"Task do stream {name} ({stream_key}) foi cancelada.")
        raise  # Re-raise para permitir cancelamento limpo
    except Exception as e:
        logger.error(f"Erro inesperado no processamento do stream {name}: {e}")


def send_email_alert(subject, body):
    """
    Função de alerta por e-mail desabilitada.
    Apenas registra o alerta nos logs ao invés de enviar e-mail.
    """
    logger.warning(f"ALERTA DE E-MAIL (DESABILITADO): {subject}")
    logger.warning(f"Conteúdo do alerta: {body}")
    # Comentado para evitar erros de autenticação:
    # message = MIMEMultipart()
    # message["From"] = ALERT_EMAIL
    # message["To"] = RECIPIENT_EMAIL
    # message["Subject"] = subject
    # message.attach(MIMEText(body, "plain"))
    #
    # try:
    #     with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    #         server.login(ALERT_EMAIL, ALERT_EMAIL_PASSWORD)
    #         server.send_message(message)
    #     logger.info("E-mail de alerta enviado com sucesso.")
    # except Exception as e:
    #     logger.error(f"Erro ao enviar e-mail de alerta: {e}")


async def check_and_alert_persistent_errors():
    while True:
        await asyncio.sleep(600)  # Verifica a cada 10 minutos
        persistent_errors = connection_tracker.check_persistent_errors()
        if persistent_errors:
            subject = "Alerta: Erros de Conexão Persistentes em Streams de Rádio"
            body = f"Os seguintes streams estão com erros de conexão há mais de 10 minutos:\n\n"
            for stream in persistent_errors:
                body += f"- {stream}\n"
            body += "\nPor favor, verifique esses streams o mais rápido possível."

            send_email_alert(subject, body)
            logger.warning(
                f"Alerta enviado para erros persistentes: {persistent_errors}"
            )


# Função para sincronizar o arquivo JSON local com o banco de dados
# Função sync_json_with_db removida - não é mais necessária com o orquestrador


# Função schedule_json_sync removida - não é mais necessária com o orquestrador


# Função para verificar se é hora de recarregar os streams devido à rotação
# Função legada de rotação - depreciada, agora usa hashing consistente
async def check_rotation_schedule():
    # Sistema de rotação baseado em tempo foi removido
    # Agora usa hashing consistente para distribuição estável
    return False


# Classe para gerenciar rate limiting do Shazam
class ShazamRateLimiter:
    def __init__(self, max_requests_per_minute=20, pause_duration=120):
        self.max_requests_per_minute = max_requests_per_minute
        self.pause_duration = pause_duration  # em segundos
        self.request_timestamps = []
        self.pause_until_timestamp = 0.0
        self.consecutive_429_count = 0
        self.lock = asyncio.Lock()

    async def wait_if_needed(self):
        async with self.lock:
            current_time = time.time()

            # Verificar se está em pausa
            if current_time < self.pause_until_timestamp:
                remaining_pause = self.pause_until_timestamp - current_time
                return False, dt.datetime.fromtimestamp(
                    self.pause_until_timestamp
                ).strftime("%H:%M:%S")

            # Limpar timestamps antigos (mais de 60 segundos)
            self.request_timestamps = [
                ts for ts in self.request_timestamps if current_time - ts < 60
            ]

            # Verificar se excedeu o limite de requisições por minuto
            if len(self.request_timestamps) >= self.max_requests_per_minute:
                # Calcular tempo até que uma requisição saia da janela de 1 minuto
                oldest_timestamp = min(self.request_timestamps)
                wait_time = (
                    60 - (current_time - oldest_timestamp) + 0.1
                )  # +0.1s de margem

                if wait_time > 0:
                    logger.info(
                        f"Rate limit preventivo: aguardando {wait_time:.2f}s antes da próxima requisição Shazam"
                    )
                    await asyncio.sleep(wait_time)

            # Registrar nova requisição
            self.request_timestamps.append(time.time())
            return True, None

    def record_success(self):
        self.consecutive_429_count = 0  # Resetar contador de erros 429 consecutivos

    def record_429_error(self):
        self.consecutive_429_count += 1
        current_time = time.time()

        # Aumentar o tempo de pausa exponencialmente com base no número de erros 429 consecutivos
        pause_time = min(
            self.pause_duration * (2 ** (self.consecutive_429_count - 1)), 1800
        )  # Máximo de 30 minutos
        self.pause_until_timestamp = current_time + pause_time

        logger.warning(
            f"Erro 429 consecutivo #{self.consecutive_429_count}. Pausando Shazam por {pause_time}s (até {dt.datetime.fromtimestamp(self.pause_until_timestamp).strftime('%H:%M:%S')})"
        )
        return pause_time


# Função worker para identificar música usando Shazamio (MODIFICADA)
async def identify_song_shazamio(shazam):
    global last_request_time
    # Criar instância do rate limiter
    rate_limiter = ShazamRateLimiter(max_requests_per_minute=15, pause_duration=120)

    # Definir o fuso horário uma vez fora do loop usando pytz
    target_tz = None
    if HAS_PYTZ:
        try:
            target_tz = pytz.timezone("America/Sao_Paulo")
            logger.info(
                f"Fuso horário definido (via pytz) para verificação de duplicatas: America/Sao_Paulo"
            )
        except pytz.exceptions.UnknownTimeZoneError:
            logger.critical(
                f"Erro ao definir fuso horário 'America/Sao_Paulo' com pytz: Zona desconhecida. Verifique o nome."
            )
            sys.exit(1)
        except Exception as tz_err:
            logger.critical(
                f"Erro ao definir fuso horário 'America/Sao_Paulo' com pytz: {tz_err}. Saindo."
            )
            sys.exit(1)
    else:
        # Se pytz não foi importado, sair (já logado criticamente na importação)
        logger.critical(
            "pytz não está disponível. Impossível continuar com tratamento de fuso horário."
        )
        sys.exit(1)

    while True:
        file_path, stream, last_songs = await shazam_queue.get()
        stream_index = stream.get("index")  # Obter índice aqui para uso posterior

        # Verificar se o arquivo existe (pode ter sido pulado na captura ou já removido)
        if file_path is None:
            logger.info(
                f"Arquivo de segmento para o stream {stream['name']} não foi capturado. Pulando identificação."
            )
            shazam_queue.task_done()
            continue

        # Verificar se o arquivo ainda existe no sistema de arquivos
        if not os.path.exists(file_path):
            logger.warning(
                f"Arquivo de segmento {file_path} não existe mais (possivelmente já processado por outra tarefa). Pulando identificação."
            )
            shazam_queue.task_done()
            continue

        identification_attempted = False
        out = None  # Inicializar fora do loop de retentativa

        # --- Verificar com o rate limiter se podemos prosseguir ---
        can_proceed, pause_until = await rate_limiter.wait_if_needed()
        if not can_proceed:
            logger.info(
                f"Shazam em pausa devido a erro 429 anterior (até {pause_until}). Enviando {os.path.basename(file_path)} diretamente para failover."
            )
            if ENABLE_FAILOVER_SEND:
                asyncio.create_task(send_file_via_failover(file_path, stream_index))
        else:
            # --- Tentar identificação se não estiver em pausa ---
            identification_attempted = True
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"Identificando música no arquivo {file_path} (tentativa {attempt + 1}/{max_retries})..."
                    )
                    out = await asyncio.wait_for(
                        shazam.recognize(file_path), timeout=10
                    )
                    last_request_time = time.time()
                    rate_limiter.record_success()  # Registrar sucesso para o rate limiter

                    if "track" in out:
                        break
                    else:
                        logger.info(
                            "Nenhuma música identificada (resposta vazia do Shazam)."
                        )
                        break

                except ClientResponseError as e_resp:
                    if e_resp.status == 429:
                        # Usar o rate limiter para gerenciar a pausa
                        rate_limiter.record_429_error()
                        if ENABLE_FAILOVER_SEND:
                            asyncio.create_task(
                                send_file_via_failover(file_path, stream_index)
                            )
                        break
                    else:
                        wait_time = 2**attempt
                        logger.error(
                            f"Erro HTTP {e_resp.status} do Shazam (tentativa {attempt + 1}/{max_retries}): {e_resp}. Esperando {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                except (ClientConnectorError, asyncio.TimeoutError) as e_conn:
                    wait_time = 2**attempt
                    logger.error(
                        f"Erro de conexão/timeout com Shazam (tentativa {attempt + 1}/{max_retries}): {e_conn}. Esperando {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                except Exception as e_gen:
                    logger.error(
                        f"Erro inesperado ao identificar a música (tentativa {attempt + 1}/{max_retries}): {e_gen}",
                        exc_info=True,
                    )
                    break
            else:
                if identification_attempted:
                    logger.error(
                        f"Falha na identificação de {os.path.basename(file_path)} após {max_retries} tentativas (sem erro 429 ou erro genérico)."
                    )

        # --- Processar resultado (se houve identificação e não estava em pausa) ---
        if identification_attempted and out and "track" in out:
            track = out["track"]
            title = track["title"]
            artist = track["subtitle"]
            isrc = track.get("isrc", "ISRC não disponível")
            label = None
            genre = None
            # ... (extração de label/genre) ...
            if "sections" in track:
                for section in track["sections"]:
                    if section["type"] == "SONG":
                        for metadata in section["metadata"]:
                            if metadata["title"] == "Label":
                                label = metadata["text"]
            if "genres" in track:
                genre = track["genres"].get("primary", None)

            logger.info(
                f"Música identificada: {title} por {artist} (ISRC: {isrc}, Gravadora: {label}, Gênero: {genre})"
            )

            # Obter timestamp atual COM FUSO HORÁRIO
            now_tz = dt.datetime.now(target_tz)

            # Criar dicionário base SEM date/time
            entry_base = {
                "name": stream["name"],
                "artist": artist,
                "song_title": title,
                "isrc": isrc,
                "cidade": stream.get("cidade", ""),
                "estado": stream.get("estado", ""),
                "regiao": stream.get("regiao", ""),
                "segmento": stream.get("segmento", ""),
                "label": label,
                "genre": genre,
                "identified_by": str(SERVER_ID),
            }

            # Chamar insert_data_to_db, que fará a verificação e a inserção
            inserted = await insert_data_to_db(entry_base, now_tz)

            if (
                inserted
            ):  # Salvar last_songs apenas se a inserção foi BEM-SUCEDIDA (não duplicata)
                last_songs[stream["name"]] = (title, artist)
                save_last_songs(last_songs)

        # --- Limpeza do arquivo local ---
        # ... (código de limpeza existente) ...
        if os.path.exists(file_path):
            try:
                await asyncio.to_thread(os.remove, file_path)
                logger.debug(f"Arquivo de segmento local {file_path} removido.")
            except Exception as e_remove:
                logger.error(
                    f"Erro ao remover arquivo de segmento {file_path}: {e_remove}"
                )

        shazam_queue.task_done()


# Variáveis globais para controle de finalização
shutdown_event = asyncio.Event()
active_tasks = set()


# Função para lidar com sinais de finalização (CTRL+C, etc.)
def handle_shutdown_signal(sig, frame):
    logger.info(
        f"Sinal de finalização recebido ({sig}). Iniciando o encerramento controlado..."
    )
    shutdown_event.set()


# Registrar o handler para os sinais
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


# Função para monitorar shutdown e cancelar tarefas
async def monitor_shutdown():
    await shutdown_event.wait()
    logger.info("Cancelando todas as tarefas ativas...")

    # CORREÇÃO CRÍTICA: Liberar streams imediatamente ao parar a instância
    global STREAMS
    if orchestrator_client:
        try:
            # Usar o método shutdown do cliente resiliente que libera streams automaticamente
            logger.info("Executando shutdown do cliente resiliente do orquestrador")
            await orchestrator_client.shutdown()
            STREAMS = []
            logger.info("[SHUTDOWN] Cliente resiliente encerrado e streams liberados")
        except Exception as e:
            logger.error(f"Erro ao executar shutdown do cliente resiliente: {e}")

    # Cancelar todas as tarefas ativas
    for task in active_tasks:
        if not task.done():
            task.cancel()

    # Aguardar até 5 segundos para as tarefas serem canceladas
    if active_tasks:
        try:
            await asyncio.wait(active_tasks, timeout=5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro ao aguardar cancelamento de tarefas: {e}")

    logger.info("Processo de finalização concluído.")


# Função para adicionar uma tarefa ao conjunto de tarefas ativas
def register_task(task):
    active_tasks.add(task)
    # Remover tarefas concluídas para evitar vazamentos de memória
    done_tasks = {t for t in active_tasks if t.done()}
    active_tasks.difference_update(done_tasks)
    return task


# Função para enviar heartbeat para o banco de dados
async def send_heartbeat():
    global last_heartbeat_time
    current_time = time.time()

    # Limitar heartbeats
    if current_time - last_heartbeat_time < HEARTBEAT_INTERVAL_SECS:
        return

    last_heartbeat_time = current_time
    conn = None

    try:
        # Coletar informações do sistema (fora do thread DB)
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        mem_info = await asyncio.to_thread(psutil.virtual_memory)
        cpu_percent = await asyncio.to_thread(
            psutil.cpu_percent, interval=1
        )  # Interval pode ser bloqueante
        disk_info = await asyncio.to_thread(psutil.disk_usage, "/")

        # Garantir que SERVER_ID seja tratado como int para operações matemáticas
        try:
            server_id_int = (
                int(SERVER_ID)
                if isinstance(SERVER_ID, str) and SERVER_ID.isdigit()
                else 1
            )
        except (ValueError, TypeError):
            server_id_int = 1

        # Informações para o banco de dados
        info = {
            "hostname": hostname,
            "platform": platform.platform(),
            "cpu_percent": cpu_percent,
            "memory_percent": mem_info.percent,
            "memory_available_mb": round(mem_info.available / (1024 * 1024), 2),
            "disk_percent": disk_info.percent,
            "disk_free_gb": round(disk_info.free / (1024 * 1024 * 1024), 2),
            "processing_streams": len(
                [
                    s
                    for s in STREAMS
                    if s.get(
                        "processed_by_server",
                        (int(s.get("index", 0)) % TOTAL_SERVERS) == (server_id_int - 1),
                    )
                ]
            ),
            "total_streams": len(STREAMS),
            "python_version": platform.python_version(),
        }
        info_json = json.dumps(info)

        # --- Operações de DB em thread separada ---
        def db_heartbeat_operations():
            try:
                with get_db_pool().get_connection_sync() as conn:
                    with conn.cursor() as cursor:
                        # Verificar/Criar tabela
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS server_heartbeats (
                                server_id VARCHAR(100) PRIMARY KEY,
                                last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                                status VARCHAR(20) DEFAULT 'ONLINE',
                                ip_address VARCHAR(50),
                                info JSONB
                            );
                        """
                        )

                        # Atualizar o heartbeat
                        cursor.execute(
                            """
                            INSERT INTO server_heartbeats (server_id, last_heartbeat, status, ip_address, info)
                            VALUES (%s, NOW(), 'ONLINE', %s, %s::jsonb)
                            ON CONFLICT (server_id) 
                            DO UPDATE SET 
                                last_heartbeat = NOW(),
                                status = 'ONLINE',
                                ip_address = EXCLUDED.ip_address,
                                info = EXCLUDED.info;
                        """,
                            (SERVER_ID, ip_address, info_json),
                        )  # Usa a variável info_json

                        conn.commit()
                        logger.debug(f"Heartbeat enviado para o servidor {SERVER_ID}")
            except Exception as db_err:
                logger.error(f"Erro DB em send_heartbeat [thread]: {db_err}")

        # Executar operações DB no thread
        await asyncio.to_thread(db_heartbeat_operations)

    except Exception as e:
        logger.error(
            f"Erro ao coletar informações do sistema ou executar DB thread em send_heartbeat: {e}"
        )
    finally:
        # Conexão já é retornada ao pool na função db_heartbeat_operations
        pass


# Função para verificar status de outros servidores
async def check_servers_status():
    # Intervalos e limites
    CHECK_INTERVAL_SECS = 300
    OFFLINE_THRESHOLD_SECS = 600
    conn = None

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECS)

            # --- Operações DB em thread separada ---
            def db_check_status_operations():
                _offline_servers_data = []
                _online_servers_data = []
                _send_alert = False  # Flag para indicar se o alerta deve ser enviado

                try:
                    with get_db_pool().get_connection_sync() as conn:
                        with conn.cursor() as cursor:
                            # Verificar se a tabela existe
                            cursor.execute(
                                """
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_name = 'server_heartbeats'
                                );
                            """
                            )

                            if not cursor.fetchone()[0]:
                                logger.warning(
                                    "check_servers_status [thread]: Tabela de heartbeats não existe."
                                )
                                return [], [], False

                            # Marcar servidores offline
                            cursor.execute(
                                """
                                UPDATE server_heartbeats
                                SET status = 'OFFLINE'
                                WHERE last_heartbeat < NOW() - INTERVAL '%s seconds'
                                AND status = 'ONLINE'
                                RETURNING server_id, last_heartbeat;
                            """,
                                (OFFLINE_THRESHOLD_SECS,),
                            )

                            _offline_servers_data = cursor.fetchall()
                            conn.commit()  # Commit da atualização de status

                            if _offline_servers_data:
                                server_ids = [row[0] for row in _offline_servers_data]
                                logger.warning(
                                    f"check_servers_status [thread]: Servidores marcados como OFFLINE: {server_ids}"
                                )
                                # Definir flag para enviar alerta se este for o servidor 1
                                if SERVER_ID == "1":
                                    _send_alert = True

                            # Obter estatísticas dos servidores online
                            cursor.execute(
                                """
                                SELECT server_id, last_heartbeat, ip_address, info
                                FROM server_heartbeats
                                WHERE status = 'ONLINE'
                                ORDER BY server_id;
                            """
                            )
                            _online_servers_data = cursor.fetchall()

                        return _offline_servers_data, _online_servers_data, _send_alert

                except Exception as db_err:
                    logger.error(f"Erro DB em check_servers_status [thread]: {db_err}")
                    # Retorna listas vazias e sem alerta
                    return [], [], False

            # Executar operações DB no thread
            offline_servers, online_servers, send_alert = await asyncio.to_thread(
                db_check_status_operations
            )

            # Processar resultados fora do thread
            if offline_servers and send_alert:
                # Servidores detectados como offline E este servidor deve alertar
                server_ids = [row[0] for row in offline_servers]
                last_heartbeats = [row[1] for row in offline_servers]
                servers_info = "\n".join(
                    [
                        f"Servidor {sid}: Último heartbeat em {lh}"
                        for sid, lh in zip(server_ids, last_heartbeats)
                    ]
                )

                subject = "ALERTA: Servidores de Identificação OFFLINE"
                body = f"""Foram detectados servidores offline no sistema de identificação musical.

Servidores offline:
{servers_info}

O que fazer:
1. Verificar se os servidores estão operacionais
2. Verificar logs de erro
3. Reiniciar os servidores offline se necessário
4. Se um servidor não for retornar, considere ajustar TOTAL_SERVERS={TOTAL_SERVERS-len(server_ids)} e reiniciar os demais

Este é um alerta automático enviado pelo servidor {SERVER_ID}.
"""
                send_email_alert(subject, body)
                logger.info(f"Alerta de servidores offline enviado por e-mail")

            if online_servers:
                logger.info(
                    f"Servidores online: {len(online_servers)} de {TOTAL_SERVERS}"
                )
                for row in online_servers:
                    server_id, last_hb, ip, info_json = row
                    if info_json:
                        try:
                            info = (
                                json.loads(info_json)
                                if isinstance(info_json, str)
                                else info_json
                            )
                            streams_info = f"Processando {info.get('processing_streams', '?')} streams"
                            sys_info = f"CPU: {info.get('cpu_percent', '?')}%, Mem: {info.get('memory_percent', '?')}%"
                            logger.debug(
                                f"Servidor {server_id} ({ip}): {streams_info}, {sys_info}"
                            )
                        except Exception as json_err:
                            logger.warning(
                                f"Erro ao processar info JSON do servidor {server_id}: {json_err}"
                            )
                            logger.debug(
                                f"Servidor {server_id} ({ip}): Último heartbeat em {last_hb} (info JSON inválido)"
                            )
                    else:
                        logger.debug(
                            f"Servidor {server_id} ({ip}): Último heartbeat em {last_hb} (sem info JSON)"
                        )

        except Exception as e:
            logger.error(f"Erro no loop principal de check_servers_status: {e}")
        # Conexão é retornada ao pool na função db_check_status_operations


# Variável global para controlar o tempo da última solicitação
last_request_time = 0


# Função principal para processar todos os streams
async def main():
    logger.debug("Iniciando a função main()")
    logger.info(
        f"Configurações de distribuição carregadas do .env: SERVER_ID={SERVER_ID}, TOTAL_SERVERS={TOTAL_SERVERS}"
    )
    logger.info(
        f"Distribuição de carga: {DISTRIBUTE_LOAD}, Rotação: {ENABLE_ROTATION}, Horas de rotação: {ROTATION_HOURS}"
    )

    # Inicializar a fila assíncrona de inserções
    try:
        await insert_queue.start_worker()
        logger.info("Fila assíncrona de inserções inicializada com sucesso")
    except Exception as e_queue:
        logger.error(f"Erro ao inicializar fila assíncrona: {e_queue}")
        sys.exit(1)

    # Verificar se a tabela de logs existe e criar se necessário (executar em thread)
    try:
        table_ok = await asyncio.to_thread(check_log_table)
        if not table_ok:
            logger.warning(
                "A verificação/criação da tabela de logs falhou. Tentando prosseguir mesmo assim, mas podem ocorrer erros."
            )
    except Exception as e_check_table:
        logger.error(f"Erro ao executar check_log_table em thread: {e_check_table}")
        logger.warning("Prosseguindo sem verificação da tabela de logs.")

    # Criar tabelas de controle de distribuição e locks
    try:
        await asyncio.to_thread(create_distribution_tables)
        logger.info("Tabelas de controle de distribuição criadas com sucesso")
    except Exception as e_dist:
        logger.error(f"Erro ao criar tabelas de distribuição: {e_dist}")

    # Criar instância do Shazam para reconhecimento
    shazam = Shazam()

    global STREAMS
    STREAMS = load_streams()

    if not STREAMS:
        logger.error(
            "Não foi possível carregar os streamings. Verifique a configuração do banco de dados ou o arquivo JSON local."
        )
        sys.exit(1)

    last_songs = load_last_songs()
    tasks = []

    # Inicializar fila para processamento
    global shazam_queue
    shazam_queue = asyncio.Queue()

    # Registrar informações sobre a distribuição de carga
    if DISTRIBUTE_LOAD:
        logger.info(
            f"Modo de distribuição de carga ativado: Servidor {SERVER_ID} de {TOTAL_SERVERS}"
        )
        if ENABLE_ROTATION:
            logger.info(f"Rotação de rádios ativada: a cada {ROTATION_HOURS} horas")
            rotation_offset = calculate_rotation_offset()
            logger.info(f"Offset de rotação atual: {rotation_offset}")

        # Calcular e exibir quantos streams cada servidor está processando
        streams_per_server = {}
        total_streams = len(STREAMS)
        for i in range(1, TOTAL_SERVERS + 1):
            streams_for_this_server = len(
                [
                    s
                    for s in STREAMS
                    if s.get(
                        "processed_by_server",
                        (int(s.get("index", 0)) % TOTAL_SERVERS) == (i - 1),
                    )
                ]
            )
            streams_per_server[i] = streams_for_this_server

        logger.info(f"Distribuição de streams por servidor: {streams_per_server}")
        logger.info(
            f"Este servidor ({SERVER_ID}) processará {streams_per_server.get(SERVER_ID, 0)} de {total_streams} streams"
        )
    else:
        logger.info(
            "Modo de distribuição de carga desativado. Processando todos os streams."
        )

    async def reload_streams():
        global STREAMS, last_songs
        all_streams = load_streams()
        last_songs = load_last_songs()  # Carregar last_songs
        logger.info("Streams recarregados.")
        if "update_streams_in_db" in globals():
            update_streams_in_db(
                all_streams
            )  # Atualiza o banco de dados com as rádios do arquivo

        # Usar apenas o orquestrador para distribuição de streams
        assigned_streams = []
        
        # Debug: Mostrar status das variáveis de configuração
        logger.info(f"[DEBUG] DISTRIBUTE_LOAD={DISTRIBUTE_LOAD}, USE_ORCHESTRATOR={USE_ORCHESTRATOR}, orchestrator_client={'Inicializado' if orchestrator_client else 'None'}")
        logger.info(f"[DEBUG] ORCHESTRATOR_URL={ORCHESTRATOR_URL}")
        
        if DISTRIBUTE_LOAD and USE_ORCHESTRATOR and orchestrator_client:
            try:
                # Registrar instância no orquestrador
                await orchestrator_client.register()
                logger.info(f"Instância {SERVER_ID} registrada no orquestrador")

                # Solicitar streams do orquestrador
                assigned_stream_ids = await orchestrator_client.request_streams()
                logger.info(
                    f"Recebidos {len(assigned_stream_ids)} streams do orquestrador"
                )

                # Converter IDs do orquestrador para string para compatibilidade
                assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]

                # Filtrar streams atribuídos (usando 'index')
                assigned_streams = [
                    stream
                    for stream in all_streams
                    if stream.get("index", "") in assigned_stream_ids_str
                ]

                logger.info(
                    f"Processando {len(assigned_streams)} streams atribuídos pelo orquestrador"
                )

            except Exception as e:
                logger.error(f"Erro ao comunicar com orquestrador: {e}")
                logger.error("Sistema de distribuição requer orquestrador funcional")
                assigned_streams = []  # Não processar streams se orquestrador falhar
        else:
            # Modo sem distribuição - processar todos os streams
            assigned_streams = all_streams
            logger.info(
                "Modo de distribuição desativado - processando todos os streams"
            )

        # Cancelar todas as tarefas existentes
        for task in tasks:
            if not task.done():
                task.cancel()
        # Criar novas tarefas para os streams recarregados
        tasks.clear()
        for stream in assigned_streams:
            task = asyncio.create_task(process_stream(stream, last_songs))
            register_task(task)
            tasks.append(task)
        logger.info(
            f"{len(tasks)} tasks criadas para {len(assigned_streams)} streams atribuídos."
        )
        STREAMS = assigned_streams

        # Nota: Cliente resiliente gerencia contagem de streams internamente
        logger.info(f"[RELOAD] Streams carregados: {len(STREAMS)}")

    # CORREÇÃO: Chamar reload_streams() para garantir distribuição correta na inicialização
    if DISTRIBUTE_LOAD:
        logger.info("Executando distribuição inicial de streams...")
        await reload_streams()
        logger.info("Distribuição inicial de streams concluída.")
    else:
        # Criar tarefas para todos os streams quando distribuição está desativada
        for stream in STREAMS:
            task = asyncio.create_task(process_stream(stream, last_songs))
            register_task(task)
            tasks.append(task)
        logger.info(f"{len(tasks)} tasks criadas para todos os {len(STREAMS)} streams.")

        # Nota: Cliente resiliente gerencia contagem de streams internamente

    # Criar e registrar todas as tarefas necessárias
    # monitor_task removida - não é mais necessária com o orquestrador
    shazam_task = register_task(asyncio.create_task(identify_song_shazamio(shazam)))
    shutdown_monitor_task = register_task(asyncio.create_task(monitor_shutdown()))

    # Adicionar tarefas de heartbeat e monitoramento de servidores
    heartbeat_task = register_task(asyncio.create_task(heartbeat_loop()))
    server_monitor_task = register_task(asyncio.create_task(check_servers_status()))

    # Adicionar tarefa de heartbeat do orquestrador se habilitado
    orchestrator_heartbeat_task = None
    orchestrator_sync_task = None
    orchestrator_alerts_task = None
    if USE_ORCHESTRATOR and orchestrator_client and DISTRIBUTE_LOAD:
        orchestrator_heartbeat_task = register_task(
            asyncio.create_task(orchestrator_heartbeat_loop())
        )
        logger.info("Tarefa de heartbeat do orquestrador iniciada")

        # Adicionar tarefa de sincronização dinâmica do orquestrador
        orchestrator_sync_task = register_task(
            asyncio.create_task(orchestrator_sync_loop())
        )
        logger.info("Tarefa de sincronização dinâmica do orquestrador iniciada")

        # Adicionar tarefa de alertas do orquestrador
        orchestrator_alerts_task = register_task(
            asyncio.create_task(orchestrator_alerts_loop())
        )
        logger.info("Tarefa de alertas do orquestrador iniciada")

    if "send_data_to_db" in globals():
        send_data_task = register_task(asyncio.create_task(send_data_to_db()))
        tasks_to_gather = [
            shazam_task,
            send_data_task,
            shutdown_monitor_task,
            heartbeat_task,
            server_monitor_task,
        ]
    else:
        tasks_to_gather = [
            shazam_task,
            shutdown_monitor_task,
            heartbeat_task,
            server_monitor_task,
        ]

    # Adicionar tarefas do orquestrador se disponíveis
    if orchestrator_heartbeat_task:
        tasks_to_gather.append(orchestrator_heartbeat_task)
    if orchestrator_sync_task:
        tasks_to_gather.append(orchestrator_sync_task)
    if orchestrator_alerts_task:
        tasks_to_gather.append(orchestrator_alerts_task)

    alert_task = register_task(asyncio.create_task(check_and_alert_persistent_errors()))
    # json_sync_task removida - não é mais necessária com o orquestrador

    tasks_to_gather.extend([alert_task])

    # Adicionar tarefa para verificar a rotação de streams
    if DISTRIBUTE_LOAD and ENABLE_ROTATION:
        rotation_task = register_task(asyncio.create_task(check_rotation_schedule()))
        tasks.append(rotation_task)

    # Adicionar tasks de streams apenas se não foram adicionadas anteriormente
    # Isso evita a criação duplicada de tasks
    if tasks:
        logger.info(f"Adicionando {len(tasks)} tasks de streams existentes ao gather")
        tasks_to_gather.extend(tasks)

    try:
        await asyncio.gather(*tasks_to_gather, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("Tarefas principais canceladas devido ao encerramento do programa.")
    except Exception as e:
        logger.error(f"Erro durante execução principal: {e}")
    finally:
        logger.info("Finalizando aplicação...")
        # Liberar streams e zerar contagem em caso de finalização inesperada
        if USE_ORCHESTRATOR and DISTRIBUTE_LOAD and orchestrator_client:
            try:
                if orchestrator_client.assigned_streams:
                    logger.info(
                        f"Liberando {len(orchestrator_client.assigned_streams)} streams atribuídos durante finalização"
                    )
                    await orchestrator_client.release_streams(
                        list(orchestrator_client.assigned_streams)
                    )
                logger.info("Streams liberados durante finalização")
            except Exception as release_error:
                logger.error(
                    f"Erro ao liberar streams durante finalização: {release_error}"
                )
        # Limpar lista global de streams
        STREAMS.clear()
        logger.info("Lista global de streams limpa durante finalização")


def stop_and_restart():
    """Função para parar e reiniciar o script."""
    logger.info("Reiniciando o script...")
    # Liberar streams antes de reiniciar
    if USE_ORCHESTRATOR and DISTRIBUTE_LOAD and orchestrator_client:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if orchestrator_client.assigned_streams:
                logger.info(
                    f"Liberando {len(orchestrator_client.assigned_streams)} streams antes do restart"
                )
                loop.run_until_complete(
                    orchestrator_client.release_streams(
                        list(orchestrator_client.assigned_streams)
                    )
                )
            logger.info("Streams liberados antes do restart")
        except Exception as release_error:
            logger.error(f"Erro ao liberar streams antes do restart: {release_error}")
    # Limpar lista global de streams
    global STREAMS
    STREAMS.clear()
    logger.info("Lista global de streams limpa antes do restart")
    os.execv(sys.executable, ["python"] + sys.argv)


# Função de loop para enviar heartbeats periodicamente
async def heartbeat_loop():
    """Envia heartbeats periódicos para o banco de dados."""
    while True:
        try:
            await send_heartbeat()
        except Exception as e:
            logger.error(f"Erro no loop de heartbeat: {e}")
        finally:
            # Aguardar até o próximo intervalo
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECS)


async def orchestrator_heartbeat_loop():
    """
    Loop de heartbeat aprimorado para manter comunicação com o orquestrador central
    Inclui verificação de consistência automática
    """
    logger.info("Iniciando loop de heartbeat aprimorado do orquestrador")

    while not shutdown_event.is_set():
        try:
            if orchestrator_client:
                # Enviar heartbeat usando cliente resiliente
                success = await orchestrator_client.send_heartbeat()

                if success:
                    logger.debug(f"Heartbeat enviado com sucesso - Instância {SERVER_ID}")
                else:
                    logger.warning(f"[HEARTBEAT] Falha no heartbeat - pode estar em modo local")
                    
                # Verificar status do cliente para detectar modo local
                health_status = await orchestrator_client.health_check()
                if health_status.get('local_mode_active'):
                    logger.info(f"[HEARTBEAT] Cliente em modo local - continuando operação")
                elif not health_status.get('orchestrator_available'):
                    logger.warning(f"[HEARTBEAT] Orquestrador indisponível - ativando modo local")

        except Exception as e:
            logger.error(f"Erro no heartbeat aprimorado do orquestrador: {e}")
            import traceback

            logger.error(f"[HEARTBEAT] Traceback: {traceback.format_exc()}")

        finally:
            # Aguardar 30 segundos antes do próximo heartbeat
            await asyncio.sleep(30)


async def orchestrator_sync_loop():
    """Loop para sincronização dinâmica de streams com o orquestrador a cada 3 segundos."""
    global STREAMS, tasks, last_songs
    last_assigned_streams = set()

    logger.info("Iniciando loop de sincronização dinâmica do orquestrador")

    while not shutdown_event.is_set():
        try:
            logger.info("[SYNC] Executando ciclo de sincronização dinâmica")

            if orchestrator_client:
                logger.info(f"[SYNC] orchestrator_client existe: {orchestrator_client}")
                # Verificar se o atributo is_registered existe
                if hasattr(orchestrator_client, 'is_registered'):
                    logger.info(f"[SYNC] is_registered: {orchestrator_client.is_registered}")
                else:
                    logger.warning("[SYNC] Atributo is_registered não encontrado, definindo como False")
                    orchestrator_client.is_registered = False

                if hasattr(orchestrator_client, 'is_registered') and orchestrator_client.is_registered:
                    logger.info(
                        "[SYNC] Cliente do orquestrador registrado, solicitando streams"
                    )

                    # Solicitar streams atuais do orquestrador
                    current_assigned_stream_ids = (
                        await orchestrator_client.request_streams()
                    )
                    current_assigned_streams = set(current_assigned_stream_ids)

                    logger.info(
                        f"[SYNC] Streams recebidos do orquestrador: {current_assigned_streams}"
                    )
                    logger.info(f"[SYNC] Streams anteriores: {last_assigned_streams}")

                    # Verificar se houve mudanças nos assignments
                    if current_assigned_streams != last_assigned_streams:
                        logger.info(
                            f"[SYNC] Mudança detectada nos assignments: {len(current_assigned_streams)} streams atribuídos"
                        )

                        # Recarregar streams dinamicamente
                        await reload_streams_dynamic(current_assigned_stream_ids)
                        last_assigned_streams = current_assigned_streams

                        logger.info(
                            f"[SYNC] Sincronização dinâmica concluída: {len(STREAMS)} streams ativos"
                        )
                    else:
                        logger.info(
                            f"[SYNC] Nenhuma mudança nos assignments: {len(current_assigned_streams)} streams"
                        )
                else:
                    is_registered_status = getattr(orchestrator_client, 'is_registered', False)
                    logger.info(
                        f"[SYNC] Cliente do orquestrador não registrado. is_registered={is_registered_status}"
                    )
            else:
                logger.info("[SYNC] orchestrator_client é None")

            logger.info("[SYNC] Aguardando 3 segundos antes da próxima verificação")
            await asyncio.sleep(
                3
            )  # Verificar a cada 3 segundos para resposta mais rápida

        except asyncio.CancelledError:
            logger.info("[SYNC] Loop de sincronização do orquestrador cancelado")
            break
        except Exception as e:
            logger.error(f"[SYNC] Erro no loop de sincronização do orquestrador: {e}")
            import traceback

            logger.error(f"[SYNC] Traceback: {traceback.format_exc()}")

            # Registrar erro no sistema de alertas
            if orchestrator_client:
                orchestrator_client.record_operation_result("sync_loop", False, str(e))

            await asyncio.sleep(
                5
            )  # Aguardar menos tempo em caso de erro para recuperação mais rápida


async def orchestrator_alerts_loop():
    """Loop para verificação periódica de alertas e geração de relatórios."""
    logger.info("Iniciando loop de verificação de alertas do orquestrador")

    while not shutdown_event.is_set():
        try:
            if orchestrator_client and hasattr(orchestrator_client, 'is_registered') and orchestrator_client.is_registered:
                # Obter resumo de alertas das últimas 24 horas
                alert_summary = orchestrator_client.get_alert_summary(hours=24)

                if alert_summary.get("total_alerts", 0) > 0:
                    logger.warning(
                        f"[ALERTS] Resumo de alertas (24h): {alert_summary['total_alerts']} alertas"
                    )

                    # Log detalhado dos alertas por tipo
                    for alert_type, count in alert_summary.get(
                        "alerts_by_type", {}
                    ).items():
                        logger.warning(f"[ALERTS] {alert_type}: {count} ocorrências")

                    # Log dos alertas mais recentes
                    recent_alerts = alert_summary.get("recent_alerts", [])
                    if recent_alerts:
                        logger.warning(
                            f"[ALERTS] Últimos {len(recent_alerts)} alertas:"
                        )
                        for alert in recent_alerts[
                            -5:
                        ]:  # Mostrar apenas os 5 mais recentes
                            logger.warning(
                                f"[ALERTS]   - {alert['timestamp']}: {alert['type']} - {alert['message']} ({alert['severity']})"
                            )

                    # Verificar se há padrões críticos
                    if alert_summary.get("critical_patterns", 0) > 0:
                        logger.error(
                            f"[ALERTS] CRÍTICO: {alert_summary['critical_patterns']} padrões críticos detectados!"
                        )

                        # Enviar alerta por email para padrões críticos
                        try:
                            subject = f"[CRÍTICO] Padrões de erro detectados - Instância {SERVER_ID}"
                            body = f"""Padrões críticos de erro detectados na instância {SERVER_ID}:

Resumo de alertas (24h):
- Total de alertas: {alert_summary['total_alerts']}
- Padrões críticos: {alert_summary['critical_patterns']}

Alertas por tipo:
{chr(10).join([f'- {t}: {c}' for t, c in alert_summary.get('alerts_by_type', {}).items()])}

Últimos alertas:
{chr(10).join([f'- {a["timestamp"]}: {a["type"]} - {a["message"]}' for a in recent_alerts[-3:]])}

Verifique o sistema imediatamente."""
                            send_email_alert(subject, body)
                            logger.info(f"[ALERTS] Email de alerta crítico enviado")
                        except Exception as email_err:
                            logger.error(
                                f"[ALERTS] Erro ao enviar email de alerta crítico: {email_err}"
                            )
                else:
                    logger.debug(f"[ALERTS] Nenhum alerta nas últimas 24 horas")

            # Verificar alertas a cada 5 minutos
            await asyncio.sleep(300)

        except asyncio.CancelledError:
            logger.info("[ALERTS] Loop de verificação de alertas cancelado")
            break
        except Exception as e:
            logger.error(f"[ALERTS] Erro no loop de verificação de alertas: {e}")
            await asyncio.sleep(60)  # Aguardar 1 minuto em caso de erro


async def handle_stream_change_notification(change_type, stream_data=None):
    """Handle notificações em tempo real de mudanças de streams.

    Args:
        change_type: Tipo de mudança ('assignment_changed', 'stream_updated', 'stream_added', 'stream_removed')
        stream_data: Dados do stream (opcional, dependendo do tipo de mudança)
    """
    try:
        logger.info(f"Notificação de mudança recebida: {change_type}")

        if change_type == "assignment_changed":
            # Forçar sincronização imediata
            if orchestrator_client and hasattr(orchestrator_client, 'is_registered') and orchestrator_client.is_registered:
                current_assigned_stream_ids = (
                    await orchestrator_client.request_streams()
                )
                await reload_streams_dynamic(current_assigned_stream_ids)
                logger.info(
                    "Sincronização imediata concluída devido a mudança de assignment"
                )

        elif change_type in ["stream_updated", "stream_added", "stream_removed"]:
            # Recarregar todos os streams do banco de dados
            if orchestrator_client and hasattr(orchestrator_client, 'is_registered') and orchestrator_client.is_registered:
                current_assigned_stream_ids = (
                    await orchestrator_client.request_streams()
                )
                await reload_streams_dynamic(current_assigned_stream_ids)
                logger.info(f"Streams recarregados devido a {change_type}")

    except Exception as e:
        logger.error(f"Erro ao processar notificação de mudança: {e}")


async def reload_streams_dynamic(assigned_stream_ids):
    """Recarrega streams dinamicamente sem reinicializar todo o sistema."""
    global STREAMS, tasks, last_songs

    try:
        logger.info(
            f"[RELOAD_DYNAMIC] Iniciando reload dinâmico com {len(assigned_stream_ids)} streams atribuídos: {assigned_stream_ids}"
        )

        # Carregar todos os streams disponíveis
        all_streams = load_streams()
        if not all_streams:
            logger.error("[RELOAD_DYNAMIC] Falha ao carregar streams do banco de dados")
            return

        logger.info(
            f"[RELOAD_DYNAMIC] {len(all_streams)} streams carregados do banco de dados"
        )

        # Converter IDs para string para compatibilidade
        assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]

        # Filtrar streams atribuídos
        new_assigned_streams = [
            stream
            for stream in all_streams
            if stream.get("index", "") in assigned_stream_ids_str
        ]

        logger.info(
            f"[RELOAD_DYNAMIC] {len(new_assigned_streams)} streams filtrados para esta instância"
        )

        # Identificar streams que precisam ser removidos
        current_stream_ids = {stream.get("index", "") for stream in STREAMS}
        new_stream_ids = {stream.get("index", "") for stream in new_assigned_streams}

        streams_to_remove = current_stream_ids - new_stream_ids
        streams_to_add = new_stream_ids - current_stream_ids

        logger.info(f"[RELOAD_DYNAMIC] Análise de mudanças:")
        logger.info(f"[RELOAD_DYNAMIC]   - Streams atuais: {current_stream_ids}")
        logger.info(f"[RELOAD_DYNAMIC]   - Novos streams: {new_stream_ids}")
        logger.info(f"[RELOAD_DYNAMIC]   - Para remover: {streams_to_remove}")
        logger.info(f"[RELOAD_DYNAMIC]   - Para adicionar: {streams_to_add}")

        # Cancelar tarefas de streams removidos
        if streams_to_remove:
            logger.info(
                f"[RELOAD_DYNAMIC] Removendo {len(streams_to_remove)} streams: {streams_to_remove}"
            )
            tasks_to_cancel = []
            for i, task in enumerate(tasks):
                if i < len(STREAMS):
                    stream_id = STREAMS[i].get("index", "")
                    if stream_id in streams_to_remove:
                        tasks_to_cancel.append(task)
                        logger.debug(
                            f"[RELOAD_DYNAMIC] Marcando tarefa do stream {stream_id} para cancelamento"
                        )

            logger.info(f"[RELOAD_DYNAMIC] Cancelando {len(tasks_to_cancel)} tarefas")
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
                    logger.debug(f"[RELOAD_DYNAMIC] Tarefa cancelada")
                if task in tasks:
                    tasks.remove(task)

        # Adicionar tarefas para novos streams
        if streams_to_add:
            logger.info(
                f"[RELOAD_DYNAMIC] Adicionando {len(streams_to_add)} novos streams: {streams_to_add}"
            )
            for stream in new_assigned_streams:
                stream_id = stream.get("index", "")
                if stream_id in streams_to_add:
                    stream_name = stream.get("name", "Unknown")
                    stream_url = stream.get("url", "Unknown")
                    logger.debug(
                        f"[RELOAD_DYNAMIC] Criando tarefa para stream {stream_id} ({stream_name}) - URL: {stream_url}"
                    )
                    task = asyncio.create_task(process_stream(stream, last_songs))
                    register_task(task)
                    tasks.append(task)
                    logger.debug(
                        f"[RELOAD_DYNAMIC] Tarefa criada e registrada para stream {stream_id}"
                    )

        # Atualizar lista global de streams
        STREAMS = new_assigned_streams

        # CORREÇÃO CRÍTICA: Sincronizar current_streams com orchestrator_client
        if orchestrator_client:
            logger.info(
                f"[RELOAD_DYNAMIC] Streams atualizados: {len(STREAMS)}"
            )

        logger.info(
            f"Sincronização dinâmica concluída: {len(STREAMS)} streams ativos, "
            f"{len(streams_to_remove)} removidos, {len(streams_to_add)} adicionados"
        )

    except Exception as e:
        logger.error(f"Erro durante sincronização dinâmica: {e}")
        # Em caso de erro, fazer reload completo como fallback
        logger.info("Executando reload completo como fallback...")
        # Recarregar last_songs antes do fallback
        last_songs = load_last_songs()
        await reload_streams()


# Ponto de entrada
if __name__ == "__main__":
    # Configurar temporizador para reinício a cada 30 minutos
    schedule.every(30).minutes.do(stop_and_restart)

    # Iniciar thread para verificar o schedule
    def run_schedule():
        while True:
            try:  # try precisa do bloco indentado
                schedule.run_pending()
            except Exception as e:
                logger.error(f"Erro no thread de schedule: {e}")
            # Mover sleep para fora do try/except para sempre ocorrer
            time.sleep(60)  # Verificar a cada minuto

    schedule_thread = threading.Thread(target=run_schedule)
    schedule_thread.daemon = (
        True  # Thread será encerrada quando o programa principal terminar
    )
    schedule_thread.start()

    # Bloco try/except/finally principal corretamente indentado
    try:
        # Executar o loop principal
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Programa interrompido pelo usuário (KeyboardInterrupt)")
        shutdown_event.set()  # Aciona o evento de shutdown
    except Exception as e:
        logger.critical(f"Erro crítico: {e}", exc_info=True)
        shutdown_event.set()  # Aciona o evento de shutdown em caso de erro crítico

        # Enviar e-mail de alerta para erro crítico
        try:
            subject = "Erro Crítico no Servidor de Identificação"
            body = f"O servidor {SERVER_ID} encontrou um erro crítico e precisou ser encerrado.\\n\\nErro: {e}\\n\\nPor favor, verifique os logs para mais detalhes."
            send_email_alert(subject, body)
        except Exception as email_err:
            logger.error(
                f"Não foi possível enviar e-mail de alerta para erro crítico: {email_err}"
            )
    finally:
        logger.info("Aplicação encerrando...")

        # Graceful shutdown - liberar streams do orquestrador
        if USE_ORCHESTRATOR and orchestrator_client and DISTRIBUTE_LOAD:
            try:
                asyncio.run(orchestrator_client.release_all_streams())
                logger.info("Streams liberados no orquestrador durante shutdown")
            except Exception as e:
                logger.error(f"Erro ao liberar streams durante shutdown: {e}")

        # Encerrar a fila assíncrona de inserções
        try:
            # Usar asyncio.run() para executar a operação assíncrona no contexto síncrono
            asyncio.run(insert_queue.stop_worker())
            logger.info("Fila assíncrona de inserções encerrada com sucesso")
        except Exception as e_queue_stop:
            logger.error(f"Erro ao encerrar fila assíncrona: {e_queue_stop}")

        # Garantir que todas as tarefas sejam canceladas no encerramento
        if "active_tasks" in globals() and active_tasks:
            logger.info(f"Tentando cancelar {len(active_tasks)} tarefas ativas...")
            # Aciona o evento de shutdown novamente para garantir que o monitor o veja
            shutdown_event.set()
            # Aguarda um pouco para o monitor_shutdown iniciar o cancelamento
            time.sleep(1)

            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.info("Nenhum loop de eventos em execução para cancelar tarefas.")

            if loop and not loop.is_closed():
                # Dar tempo para as tarefas serem canceladas
                # A função monitor_shutdown já aguarda asyncio.wait
                # Apenas esperamos que ela termine (ou timeout)
                for task in active_tasks:  # Indentação correta do for loop
                    if not task.done():
                        task.cancel()
                try:  # try/except corretamente indentado
                    # Espera por um tempo curto para o cancelamento ocorrer
                    # Não usar loop.run_until_complete aqui pois o loop principal já foi encerrado
                    # e pode causar erros
                    # Basta confiar que as tarefas foram sinalizadas para cancelar
                    logger.info("Tarefas sinalizadas para cancelamento.")
                except asyncio.CancelledError:
                    logger.info("Cancelamento durante a finalização.")
                except Exception as e:
                    logger.error(f"Erro ao finalizar tarefas pendentes: {e}")
            else:
                logger.info(
                    "Loop de eventos não está ativo ou fechado, pulando cancelamento de tarefas."
                )

        logger.info("Aplicação encerrada.")
    sys.exit(0)

import subprocess
import psycopg2
import time
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from shazamio import Shazam
from aiohttp import ClientConnectorError, ClientResponseError, ClientTimeout, ClientError
import asyncio
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import schedule
import threading
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import signal
import socket
import platform
from ftplib import FTP, error_perm
import socket
import datetime as dt # Usar alias para evitar conflito com variÃ¡vel datetime
import redis.asyncio as redis  # Novo: cliente Redis assÃ­ncrono
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    # O logger jÃ¡ estÃ¡ configurado aqui
    logger.critical("Biblioteca pytz nÃ£o encontrada. O tratamento de fuso horÃ¡rio falharÃ¡. Instale com: pip install pytz")
    # Considerar sair se pytz for essencial
    # sys.exit(1)
import psycopg2.errors # Para capturar UniqueViolation
import psycopg2.extras # Para DictCursor

# Definir diretÃ³rio de segmentos global
SEGMENTS_DIR = os.getenv('SEGMENTS_DIR', 'C:/DATARADIO/segments')

# Configurar logging para console e arquivo (MOVIDO PARA CIMA)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Formato de log
formatter = logging.Formatter('%(asctime)s %(levelname)s: [%(threadName)s] %(message)s') # Adicionado threadName

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler com limpeza a cada 6 horas
SERVER_LOG_FILE = 'log.txt' # Definir nome do arquivo de log aqui
file_handler = TimedRotatingFileHandler(SERVER_LOG_FILE, when='H', interval=6, backupCount=1)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Log inicial para confirmar que o logger estÃ¡ configurado
logger.info("Logger configurado.")

# Verificar se Pytz estÃ¡ ausente apÃ³s configurar o logger
if not HAS_PYTZ:
     logger.critical("Biblioteca pytz nÃ£o encontrada. O tratamento de fuso horÃ¡rio pode falhar. Instale com: pip install pytz")

# --- Fim da configuraÃ§Ã£o do Logger ---\

# Verificar e criar o diretÃ³rio de segmentos
if not os.path.exists(SEGMENTS_DIR):
    try:
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        logger.info(f"DiretÃ³rio de segmentos criado: {SEGMENTS_DIR}")
    except Exception as e:
        logger.error(f"ERRO: NÃ£o foi possÃ­vel criar o diretÃ³rio de segmentos: {e}")
        try:
            SEGMENTS_DIR = './segments'
            os.makedirs(SEGMENTS_DIR, exist_ok=True)
            logger.info(f"Usando diretÃ³rio alternativo: {SEGMENTS_DIR}")
        except Exception as fallback_e:
            logger.critical(f"Falha crÃ­tica: NÃ£o foi possÃ­vel criar diretÃ³rio de segmentos: {fallback_e}")
            sys.exit(1)

# Tentar importar psutil, necessÃ¡rio para o heartbeat
try:
    import psutil
except ImportError:
    logger.warning("Pacote 'psutil' nÃ£o encontrado. Execute 'pip install psutil' para habilitar monitoramento completo.")
    
    # Stub de classe para psutil se nÃ£o estiver instalado
    class PsutilStub:
        def virtual_memory(self): return type('obj', (object,), {'percent': 0, 'available': 0})
        def cpu_percent(self, interval=0): return 0
        def disk_usage(self, path): return type('obj', (object,), {'percent': 0, 'free': 0})
    
    psutil = PsutilStub()

# ImportaÃ§Ãµes para (S)FTP
from ftplib import FTP
try:
    import pysftp
    from pysftp import CnOpts as pysftpCnOpts # Importar CnOpts explicitamente
    HAS_PYSFTP = True
except ImportError:
    HAS_PYSFTP = False
    logger.warning("Pacote 'pysftp' nÃ£o encontrado. O failover SFTP nÃ£o funcionarÃ¡. Instale com 'pip install pysftp'.")
    pysftpCnOpts = None # Definir como None se pysftp nÃ£o estiver disponÃ­vel
    # Considerar logar um aviso se SFTP for o mÃ©todo escolhido

# Carregar variÃ¡veis de ambiente
load_dotenv()

# ConfiguraÃ§Ã£o Redis (opcional) - com prefixo smf: para isolamento
REDIS_URL = os.getenv("REDIS_URL")
REDIS_CHANNEL = os.getenv("REDIS_CHANNEL", "smf:server_heartbeats")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "smf:server")
REDIS_HEARTBEAT_TTL_SECS = int(os.getenv("REDIS_HEARTBEAT_TTL_SECS", "120"))

_redis_client: "redis.Redis | None" = None

async def get_redis_client() -> "redis.Redis | None":
    """Inicializa e retorna o cliente Redis, ou None se nÃ£o configurado/falhar."""
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Checagem rÃ¡pida de conexÃ£o
            await _redis_client.ping()
            logger.info("Redis conectado com sucesso para Songmetrix Finger.")
        except Exception as e:
            logger.error(f"Falha ao conectar no Redis: {e}")
            _redis_client = None
    return _redis_client

async def publish_redis_heartbeat(info: dict) -> None:
    """Publica heartbeat via Redis (Pub/Sub + presenÃ§a com TTL) usando prefixo smf:."""
    client = await get_redis_client()
    if not client:
        logger.debug("publish_redis_heartbeat: Redis nÃ£o configurado, ignorando")
        return
    try:
        # Atualiza presenÃ§a com TTL usando prefixo smf:
        presence_key = f"{REDIS_KEY_PREFIX}:{SERVER_ID}"  # ex: smf:server:1
        value = json.dumps({
            "server_id": SERVER_ID,
            "last_ts": int(time.time()),
            "ip_address": info.get("ip_address"),
            "processing_streams": info.get("processing_streams", 0),
            "processing_stream_names": info.get("processing_stream_names", []),
        })
        # SETEX com TTL
        await client.set(presence_key, value, ex=REDIS_HEARTBEAT_TTL_SECS)

        # Publicar mensagem de heartbeat no canal com prefixo smf:
        msg = {
            "type": "heartbeat",
            "server_id": SERVER_ID,
            "ts": int(time.time()),
            "processing_streams": info.get("processing_streams"),
            "processing_stream_names": info.get("processing_stream_names", []),
            "cpu_percent": info.get("cpu_percent"),
            "memory_percent": info.get("memory_percent"),
            "ip_address": info.get("ip_address"),
        }
        await client.publish(REDIS_CHANNEL, json.dumps(msg))  # canal: smf:server_heartbeats
        logger.debug(f"publish_redis_heartbeat: publicado no Redis (canal={REDIS_CHANNEL}, key={presence_key}, TTL={REDIS_HEARTBEAT_TTL_SECS}s)")
    except redis.RedisError as e:
        logger.warning(f"publish_redis_heartbeat: erro Redis especÃ­fico: {e}")
    except (TypeError, OverflowError) as e:
        logger.error(f"publish_redis_heartbeat: erro JSON ao serializar dados: {e}")
    except Exception as e:
        logger.error(f"publish_redis_heartbeat: falha inesperada ao publicar no Redis: {e}")

async def get_redis_online_servers() -> list[int]:
    """ObtÃ©m lista de servidores online diretamente do Redis usando prefixo smf:."""
    client = await get_redis_client()
    if not client:
        return []
    try:
        # Buscar todas as chaves de presenÃ§a com prefixo smf:server:*
        pattern = f"{REDIS_KEY_PREFIX}:*"  # smf:server:*
        keys = await client.keys(pattern)
        server_ids = []
        for key in keys:
            try:
                # Extrair server_id da chave (ex: smf:server:1 -> 1)
                server_id = int(key.split(":")[-1])
                server_ids.append(server_id)
            except (ValueError, IndexError):
                continue
        return sorted(server_ids)
    except Exception as e:
        logger.error(f"get_redis_online_servers: erro ao consultar Redis: {e}")
        return []

# ConfiguraÃ§Ã£o para distribuiÃ§Ã£o de carga entre servidores
SERVER_ID = int(os.getenv('SERVER_ID', '1'))  # ID Ãºnico para cada servidor (convertido para inteiro)
TOTAL_SERVERS = int(os.getenv('TOTAL_SERVERS', '1'))  # NÃºmero total de servidores
DISTRIBUTE_LOAD = os.getenv('DISTRIBUTE_LOAD', 'False').lower() == 'true'  # Ativar distribuiÃ§Ã£o
ROTATION_HOURS = int(os.getenv('ROTATION_HOURS', '24'))  # Horas para rotaÃ§Ã£o de rÃ¡dios (padrÃ£o: 24h)
ENABLE_ROTATION = os.getenv('ENABLE_ROTATION', 'False').lower() == 'true'  # Ativar rodÃ­zio de rÃ¡dios

# Validar SERVER_ID (nÃ£o altere o SERVER_ID real; use um ID efetivo sÃ³ para distribuiÃ§Ã£o)
if DISTRIBUTE_LOAD and (SERVER_ID < 1 or SERVER_ID > TOTAL_SERVERS):
    logger.warning(f"AVISO: SERVER_ID invÃ¡lido ({SERVER_ID}). Deve estar entre 1 e {TOTAL_SERVERS}.")
    logger.warning("Manteremos SERVER_ID para logs/identificaÃ§Ã£o e usaremos 1 apenas para distribuiÃ§Ã£o.")
    EFFECTIVE_SERVER_ID = 1
else:
    EFFECTIVE_SERVER_ID = SERVER_ID

# ConfiguraÃ§Ãµes para identificaÃ§Ã£o e verificaÃ§Ã£o de duplicatas
IDENTIFICATION_DURATION = int(os.getenv('IDENTIFICATION_DURATION', '15'))  # DuraÃ§Ã£o da captura em segundos
DUPLICATE_PREVENTION_WINDOW_SECONDS = int(os.getenv('DUPLICATE_PREVENTION_WINDOW_SECONDS', '900')) # Nova janela de 15 min
NUM_SHAZAM_WORKERS = int(os.getenv('NUM_SHAZAM_WORKERS', '4'))  # NÃºmero de tarefas de identificaÃ§Ã£o simultÃ¢neas

# ConfiguraÃ§Ãµes do banco de dados PostgreSQL
DB_HOST = os.getenv('POSTGRES_HOST')  # Removido default para forÃ§ar configuraÃ§Ã£o
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')
DB_NAME = os.getenv('POSTGRES_DB')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_TABLE_NAME = os.getenv('DB_TABLE_NAME', 'music_log')

# Registrar a tabela que estÃ¡ sendo usada
logger.info(f"ConfiguraÃ§Ã£o da tabela de destino: DB_TABLE_NAME={DB_TABLE_NAME}")

# ConfiguraÃ§Ãµes de Failover (S)FTP
ENABLE_FAILOVER_SEND = os.getenv('ENABLE_FAILOVER_SEND', 'False').lower() == 'true'
FAILOVER_METHOD = os.getenv('FAILOVER_METHOD', 'SFTP').upper()  # Carrega mÃ©todo
FAILOVER_HOST = os.getenv('FAILOVER_HOST')
_failover_port_str = os.getenv('FAILOVER_PORT')
FAILOVER_PORT = int(_failover_port_str) if _failover_port_str and _failover_port_str.isdigit() else (22 if FAILOVER_METHOD == 'SFTP' else 21)
FAILOVER_USER = os.getenv('FAILOVER_USER')
FAILOVER_PASSWORD = os.getenv('FAILOVER_PASSWORD')
FAILOVER_REMOTE_DIR = os.getenv('FAILOVER_REMOTE_DIR')
FAILOVER_SSH_KEY_PATH = os.getenv('FAILOVER_SSH_KEY_PATH')  # Pode ser None

# Caminho para o arquivo JSON contendo os streamings
STREAMS_FILE = 'streams.json'
# Caminho para o arquivo JSON que armazenarÃ¡ o estado das Ãºltimas mÃºsicas identificadas
LAST_SONGS_FILE = 'last_songs.json'
# Caminho para o arquivo de log local
LOCAL_LOG_FILE = 'local_log.json'

# ConfiguraÃ§Ãµes para o sistema de alerta por e-mail
ALERT_EMAIL = os.getenv('ALERT_EMAIL', "junior@pontocomaudio.net")
ALERT_EMAIL_PASSWORD = os.getenv('ALERT_EMAIL_PASSWORD', "conquista")
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', "junior@pontocomaudio.net")

# Configurar logging para console e arquivo (REMOVIDO DAQUI)

# Registrar informaÃ§Ãµes sobre as variÃ¡veis de ambiente carregadas
logger.info("=== Iniciando script com as seguintes configuraÃ§Ãµes ===")
logger.info(f"SERVER_ID: {SERVER_ID} (tipo: {type(SERVER_ID).__name__})")
logger.info(f"TOTAL_SERVERS: {TOTAL_SERVERS} (tipo: {type(TOTAL_SERVERS).__name__})")
logger.info(f"DISTRIBUTE_LOAD: {DISTRIBUTE_LOAD}")
logger.info(f"ENABLE_ROTATION: {ENABLE_ROTATION}")
logger.info(f"ROTATION_HOURS: {ROTATION_HOURS}")
logger.info(f"DB_TABLE_NAME: {DB_TABLE_NAME}")
logger.info(f"ENABLE_FAILOVER_SEND: {ENABLE_FAILOVER_SEND}")
logger.info(f"FAILOVER_METHOD: {FAILOVER_METHOD}")
logger.info(f"FAILOVER_HOST: {FAILOVER_HOST}")
logger.info(f"FAILOVER_PORT: {FAILOVER_PORT}")
logger.info(f"FAILOVER_USER: {FAILOVER_USER}")
logger.info(f"FAILOVER_REMOTE_DIR: {FAILOVER_REMOTE_DIR}")
logger.info(f"FAILOVER_SSH_KEY_PATH: {FAILOVER_SSH_KEY_PATH}")
logger.info(f"EFFECTIVE_SERVER_ID (distribuiÃ§Ã£o): {EFFECTIVE_SERVER_ID}")
logger.info("======================================================")

# --- FunÃ§Ã£o para Envio de Arquivo via Failover (FTP/SFTP) ---
async def send_file_via_failover(local_file_path, stream_index):
    """Envia um arquivo para o servidor de failover configurado (FTP ou SFTP)."""
    if not ENABLE_FAILOVER_SEND:
        logger.debug("Envio para failover desabilitado nas configuraÃ§Ãµes.")
        return

    if not all([FAILOVER_HOST, FAILOVER_USER, FAILOVER_PASSWORD, FAILOVER_REMOTE_DIR]):
        logger.error("ConfiguraÃ§Ãµes de failover incompletas no .env. ImpossÃ­vel enviar arquivo.")
        return

    if stream_index is None:
        logger.error("Ãndice do stream nÃ£o fornecido. NÃ£o Ã© possÃ­vel nomear o arquivo de failover.")
        return

    # Criar um nome de arquivo Ãºnico no servidor remoto
    timestamp_str = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_filename = f"{stream_index}_{timestamp_str}_{os.path.basename(local_file_path)}"
    # Usar os.path.join e depois replace para garantir compatibilidade entre OS no caminho remoto
    remote_path = os.path.join(FAILOVER_REMOTE_DIR, remote_filename).replace("\\", "/")

    logger.info(f"Tentando enviar {local_file_path} para failover via {FAILOVER_METHOD} em {FAILOVER_HOST}:{FAILOVER_PORT}")
    logger.debug(f"Caminho remoto: {remote_path}")

    try:
        if FAILOVER_METHOD == 'SFTP':
            if not HAS_PYSFTP:
                logger.error("SFTP selecionado, mas a biblioteca pysftp nÃ£o estÃ¡ instalada.")
                return

            cnopts = pysftpCnOpts()
            # Ignorar verificaÃ§Ã£o da chave do host (menos seguro, mas evita problemas de configuraÃ§Ã£o inicial)
            # Considere configurar known_hosts para produÃ§Ã£o
            cnopts.hostkeys = None

            # Definir kwargs para conexÃ£o SFTP
            sftp_kwargs = {
                'host': FAILOVER_HOST,
                'port': FAILOVER_PORT,
                'username': FAILOVER_USER,
                'cnopts': cnopts
            }
            if FAILOVER_SSH_KEY_PATH and os.path.exists(FAILOVER_SSH_KEY_PATH):
                sftp_kwargs['private_key'] = FAILOVER_SSH_KEY_PATH
                sftp_kwargs['private_key_pass'] = FAILOVER_PASSWORD # Senha da chave, se houver
                logger.debug("Usando chave SSH para autenticaÃ§Ã£o SFTP.")
            else:
                sftp_kwargs['password'] = FAILOVER_PASSWORD
                logger.debug("Usando senha para autenticaÃ§Ã£o SFTP.")

            # Usar asyncio.to_thread para a operaÃ§Ã£o sftp bloqueante
            await asyncio.to_thread(_sftp_upload_sync, sftp_kwargs, local_file_path, remote_path)

        elif FAILOVER_METHOD == 'FTP':
            # Usar asyncio.to_thread para operaÃ§Ãµes de FTP bloqueantes
            await asyncio.to_thread(_ftp_upload_sync, local_file_path, remote_path)

        else:
            logger.error(f"MÃ©todo de failover desconhecido: {FAILOVER_METHOD}. Use 'FTP' ou 'SFTP'.")

    except Exception as e:
        logger.error(f"Erro ao enviar arquivo via {FAILOVER_METHOD} para {FAILOVER_HOST}: {e}", exc_info=True)

# FunÃ§Ã£o auxiliar bloqueante para SFTP (para ser usada com asyncio.to_thread)
def _sftp_upload_sync(sftp_kwargs, local_file_path, remote_path):
    # A conexÃ£o SFTP Ã© feita dentro do 'with' que agora estÃ¡ nesta funÃ§Ã£o sÃ­ncrona
    with pysftp.Connection(**sftp_kwargs) as sftp:
        logger.info(f"Conectado ao SFTP: {FAILOVER_HOST}")
        remote_dir = os.path.dirname(remote_path)
        # Garantir que o diretÃ³rio remoto exista (opcional, mas Ãºtil)
        try:
            sftp.makedirs(remote_dir)
            logger.debug(f"DiretÃ³rio remoto {remote_dir} verificado/criado.")
        except OSError as e:
             # Ignora erro se o diretÃ³rio jÃ¡ existe, mas loga outros erros
             if "Directory already exists" not in str(e):
                  logger.warning(f"NÃ£o foi possÃ­vel criar/verificar diretÃ³rio SFTP {remote_dir}: {e}")

        sftp.put(local_file_path, remote_path)
        logger.info(f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via SFTP para {remote_dir}")

# FunÃ§Ã£o auxiliar bloqueante para FTP (para ser usada com asyncio.to_thread)
def _ftp_upload_sync(local_file_path, remote_path):
    ftp = None
    try:
        ftp = FTP()
        ftp.connect(FAILOVER_HOST, FAILOVER_PORT, timeout=30) # Timeout de 30s
        ftp.login(FAILOVER_USER, FAILOVER_PASSWORD)
        logger.info(f"Conectado ao FTP: {FAILOVER_HOST}")

        # Tentar criar diretÃ³rios recursivamente (simples)
        remote_dir = os.path.dirname(remote_path)
        dirs_to_create = remote_dir.strip('/').split('/') # Remover barras inicial/final e dividir
        current_dir = ''
        for d in dirs_to_create:
            if not d: continue
            current_dir = f'{current_dir}/{d}' if current_dir else f'/{d}' # Construir caminho absoluto
            try:
                ftp.mkd(current_dir)
                logger.debug(f"DiretÃ³rio FTP criado: {current_dir}")
            except error_perm as e:
                if not e.args[0].startswith('550'): # Ignorar erro "jÃ¡ existe" ou "permissÃ£o negada" (pode jÃ¡ existir)
                    logger.warning(f"NÃ£o foi possÃ­vel criar diretÃ³rio FTP {current_dir}: {e}")
                # else:
                #     logger.debug(f"DiretÃ³rio FTP jÃ¡ existe ou permissÃ£o negada para criar: {current_dir}")

        # Mudar para o diretÃ³rio final (se existir)
        try:
            ftp.cwd(remote_dir)
            logger.debug(f"Mudado para diretÃ³rio FTP: {remote_dir}")
        except error_perm as e:
            logger.error(f"NÃ£o foi possÃ­vel mudar para o diretÃ³rio FTP {remote_dir}: {e}. Upload pode falhar.")
            # Considerar lanÃ§ar o erro ou retornar se o diretÃ³rio Ã© essencial
            # raise # Re-lanÃ§a o erro se nÃ£o conseguir mudar para o diretÃ³rio
            return # Ou simplesmente retorna se nÃ£o conseguir mudar

        with open(local_file_path, 'rb') as fp:
            ftp.storbinary(f'STOR {os.path.basename(remote_path)}', fp)
        logger.info(f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via FTP para {remote_dir}")

    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass # Ignorar erros ao fechar

# --- Fim das FunÃ§Ãµes de Failover ---

# Verificar se a tabela de logs existe (RESTAURADO)
async def check_log_table():
    logger.info(f"Verificando se a tabela de logs '{DB_TABLE_NAME}' existe no banco de dados...")
    conn = None # Initialize conn to None
    try:
        conn = await connect_db()
        if not conn:
            logger.error("NÃ£o foi possÃ­vel conectar ao banco de dados para verificar a tabela de logs.")
            return False

        with conn.cursor() as cursor:
            # Verificar se a tabela existe
            cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{DB_TABLE_NAME}')")
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                logger.error(f"A tabela de logs '{DB_TABLE_NAME}' nÃ£o existe no banco de dados!")
                # Listar tabelas disponÃ­veis
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                tables = [row[0] for row in cursor.fetchall()]
                logger.info(f"Tabelas disponÃ­veis no banco: {tables}")

                # Criar tabela automaticamente para evitar erros
                try:
                    logger.info(f"Tentando criar a tabela '{DB_TABLE_NAME}' automaticamente...")
                    # Corrigir a formataÃ§Ã£o da string SQL multi-linha
                    create_table_sql = """
CREATE TABLE {} (
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
                    """.format(DB_TABLE_NAME) # Usar .format() para inserir o nome da tabela
                    cursor.execute(create_table_sql)
                    conn.commit()
                    logger.info(f"Tabela '{DB_TABLE_NAME}' criada com sucesso!")
                    return True
                except Exception as e:
                    logger.error(f"Erro ao criar a tabela '{DB_TABLE_NAME}': {e}")
                    logger.info("Considere criar a tabela manualmente com o seguinte comando SQL:")
                    # logger.info(create_table_sql) # Don't log potentially large SQL
                    return False
            else:
                # Verificar as colunas da tabela (garantir indentaÃ§Ã£o correta aqui)
                cursor.execute(f"SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = '{DB_TABLE_NAME}'")
                columns_info = {row[0].lower(): {'type': row[1], 'default': row[2]} for row in cursor.fetchall()}
                logger.info(f"Tabela '{DB_TABLE_NAME}' existe com as seguintes colunas: {list(columns_info.keys())}")
                columns = list(columns_info.keys())

                # --- Ajuste da coluna 'identified_by' --- (garantir indentaÃ§Ã£o correta)
                col_identified_by = 'identified_by'

                if col_identified_by in columns:
                    # (LÃ³gica interna do if permanece a mesma, verificar indentaÃ§Ã£o)
                    # ... (cÃ³digo existente dentro do if col_identified_by...)
                    current_info = columns_info[col_identified_by]
                    needs_alter = False
                    alter_parts = []
                    if not current_info['type'].startswith('character varying') or '(10)' not in current_info['type']:
                        alter_parts.append(f"ALTER COLUMN {col_identified_by} TYPE VARCHAR(10)")
                        needs_alter = True
                    if current_info['default'] is not None:
                         if 'null::' not in str(current_info['default']).lower():
                             alter_parts.append(f"ALTER COLUMN {col_identified_by} DROP DEFAULT")
                             needs_alter = True

                    if needs_alter:
                        try:
                            alter_sql = f"ALTER TABLE {DB_TABLE_NAME} { ', '.join(alter_parts) };"
                            logger.info(f"Alterando coluna '{col_identified_by}': {alter_sql}")
                            cursor.execute(alter_sql)
                            conn.commit()
                            logger.info(f"Coluna '{col_identified_by}' alterada com sucesso.")
                        except Exception as e:
                            logger.error(f"Erro ao alterar coluna '{col_identified_by}': {e}")
                            conn.rollback()
                else:
                     # (LÃ³gica interna do else permanece a mesma, verificar indentaÃ§Ã£o)
                    # ... (cÃ³digo existente dentro do else para adicionar coluna) ...
                    try:
                        logger.info(f"Adicionando coluna '{col_identified_by}' (VARCHAR(10)) Ã  tabela '{DB_TABLE_NAME}'...")
                        add_sql = f"ALTER TABLE {DB_TABLE_NAME} ADD COLUMN {col_identified_by} VARCHAR(10);"
                        cursor.execute(add_sql)
                        conn.commit()
                        logger.info(f"Coluna '{col_identified_by}' adicionada com sucesso.")
                        columns.append(col_identified_by) # Adiciona Ã  lista local
                    except Exception as e:
                        logger.error(f"Erro ao adicionar coluna '{col_identified_by}': {e}")
                        conn.rollback()

                # --- RemoÃ§Ã£o da coluna 'identified_by_server' --- (garantir indentaÃ§Ã£o correta)
                col_to_remove = 'identified_by_server'
                if col_to_remove in columns:
                    # (LÃ³gica interna do if permanece a mesma, verificar indentaÃ§Ã£o)
                    # ... (cÃ³digo existente dentro do if col_to_remove...) ...
                    try:
                        logger.info(f"Removendo coluna obsoleta '{col_to_remove}' da tabela '{DB_TABLE_NAME}'...")
                        drop_sql = f"ALTER TABLE {DB_TABLE_NAME} DROP COLUMN {col_to_remove};"
                        cursor.execute(drop_sql)
                        conn.commit()
                        logger.info(f"Coluna '{col_to_remove}' removida com sucesso.")
                        columns.remove(col_to_remove) # Remove da lista local
                    except Exception as e:
                        logger.error(f"Erro ao remover coluna '{col_to_remove}': {e}")
                        conn.rollback()

                # Verificar colunas essenciais (garantir indentaÃ§Ã£o correta)
                required_columns = ['date', 'time', 'name', 'artist', 'song_title']
                missing_columns = [col for col in required_columns if col not in columns]

                if missing_columns:
                    logger.error(f"A tabela '{DB_TABLE_NAME}' existe, mas nÃ£o possui as colunas necessÃ¡rias: {missing_columns}")
                    return False # Este return estÃ¡ dentro do else, estÃ¡ correto

                # Mostrar algumas linhas da tabela para diagnÃ³stico (garantir indentaÃ§Ã£o correta)
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}")
                    count = cursor.fetchone()[0]
                    logger.info(f"A tabela '{DB_TABLE_NAME}' contÃ©m {count} registros.")
                except Exception as e:
                    logger.error(f"Erro ao consultar dados da tabela '{DB_TABLE_NAME}': {e}")

                logger.info(f"Tabela de logs '{DB_TABLE_NAME}' verificada com sucesso!")
                return True # Este return estÃ¡ dentro do else, estÃ¡ correto

    except Exception as e:
        logger.error(f"Erro ao verificar tabela de logs: {e}", exc_info=True) # Add exc_info
        return False
    finally:
        if conn:
            conn.close()

# Fila para enviar ao Shazamio (RESTAURADO)
shazam_queue = asyncio.Queue(maxsize=100)  # Limitar tamanho da fila para evitar uso excessivo de memÃ³ria

# VariÃ¡vel para controlar o Ãºltimo heartbeat enviado (RESTAURADO)
last_heartbeat_time = 0
HEARTBEAT_INTERVAL_SECS = 60  # Enviar heartbeat a cada 1 minuto

# VariÃ¡vel global para controle da pausa do Shazam (RESTAURADO)
shazam_pause_until_timestamp = 0.0

# ValidaÃ§Ã£o crÃ­tica de configuraÃ§Ã£o
if REDIS_HEARTBEAT_TTL_SECS <= HEARTBEAT_INTERVAL_SECS:
    logger.warning(f"CONFIGURAÃ‡ÃƒO CRÃTICA: REDIS_HEARTBEAT_TTL_SECS ({REDIS_HEARTBEAT_TTL_SECS}s) deve ser maior que HEARTBEAT_INTERVAL_SECS ({HEARTBEAT_INTERVAL_SECS}s)!")
    logger.warning(f"RecomendaÃ§Ã£o: Configure REDIS_HEARTBEAT_TTL_SECS={HEARTBEAT_INTERVAL_SECS * 2} ou maior no .env")
    REDIS_HEARTBEAT_TTL_SECS = max(HEARTBEAT_INTERVAL_SECS * 2, 120)  # Garantir margem de seguranÃ§a
    logger.info(f"TTL ajustado automaticamente para {REDIS_HEARTBEAT_TTL_SECS}s para evitar expiraÃ§Ãµes prematuras")

# Classe StreamConnectionTracker (RESTAURADO)
class StreamConnectionTracker:
    def __init__(self):
        self.connection_errors = {} # Stores stream_name: error_timestamp
        self.error_counts = {}  # Novo: contagem de falhas consecutivas por stream

    def record_error(self, stream_name):
        """Records the timestamp of the first consecutive error for a stream."""
        if stream_name not in self.connection_errors:
            self.connection_errors[stream_name] = time.time()
            logger.debug(f"Registrado primeiro erro de conexÃ£o para: {stream_name}")
        # Incrementar contagem de falhas consecutivas
        self.error_counts[stream_name] = self.error_counts.get(stream_name, 0) + 1

    def clear_error(self, stream_name):
        """Clears the error status for a stream if it was previously recorded."""
        if stream_name in self.connection_errors:
            del self.connection_errors[stream_name]
            logger.debug(f"Erro de conexÃ£o limpo para: {stream_name}")
        # Zerar/Remover contagem de falhas na limpeza
        if stream_name in self.error_counts:
            del self.error_counts[stream_name]

    def check_persistent_errors(self, threshold_minutes=10):
        """Checks for streams that have been failing for longer than the threshold."""
        current_time = time.time()
        persistent_errors = []
        threshold_seconds = threshold_minutes * 60
        for stream_name, error_time in list(self.connection_errors.items()): # Iterate over a copy
            if (current_time - error_time) > threshold_seconds:
                persistent_errors.append(stream_name)
                # Optionally remove from dict once alerted to prevent repeated alerts immediately
                # del self.connection_errors[stream_name]
        if persistent_errors:
             logger.debug(f"Erros persistentes encontrados (> {threshold_minutes} min): {persistent_errors}")
        return persistent_errors

    def get_error_count(self, stream_name) -> int:
        """Retorna a contagem de falhas consecutivas para o stream."""
        return self.error_counts.get(stream_name, 0)

connection_tracker = StreamConnectionTracker() # Instanciar o tracker (RESTAURADO)

# FunÃ§Ã£o para conectar ao banco de dados PostgreSQL
async def connect_db():
    """
    Conecta ao banco de dados PostgreSQL usando asyncio.to_thread 
    para evitar bloqueio do event loop.
    
    Returns:
        psycopg2.connection: ConexÃ£o com o banco de dados ou None em caso de erro
    """
    # ValidaÃ§Ã£o das variÃ¡veis de ambiente necessÃ¡rias
    required_vars = [DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]
    missing_vars = [var for var in required_vars if not var]
    
    if missing_vars:
        logger.error("VariÃ¡veis de ambiente de banco de dados nÃ£o configuradas.")
        logger.error("Verifique: POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB")
        return None
    
    def _connect_sync():
        """FunÃ§Ã£o sÃ­ncrona para conectar ao banco de dados"""
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT
            )
            return conn
        except psycopg2.OperationalError as e:
            logger.error(f"Erro de conexÃ£o com o banco de dados: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao conectar ao banco de dados: {e}")
            return None
    
    try:
        # Executar conexÃ£o em thread separada para nÃ£o bloquear event loop
        conn = await asyncio.to_thread(_connect_sync)
        if conn:
            logger.debug("ConexÃ£o com banco de dados estabelecida com sucesso")
        return conn
    except Exception as e:
        logger.error(f"Erro ao executar conexÃ£o assÃ­ncrona com o banco: {e}")
        return None

# FunÃ§Ã£o para calcular o deslocamento de rotaÃ§Ã£o com base no tempo
def calculate_rotation_offset():
    if not ENABLE_ROTATION:
        return 0
    
    # Calcular quantas rotaÃ§Ãµes jÃ¡ ocorreram desde o inÃ­cio do tempo (1/1/1970)
    hours_since_epoch = int(time.time() / 3600)  # Converter segundos para horas
    rotations = hours_since_epoch // ROTATION_HOURS
    
    # O deslocamento Ã© o nÃºmero de rotaÃ§Ãµes mÃ³dulo o nÃºmero total de servidores
    offset = rotations % TOTAL_SERVERS
    
    logger.info(f"Calculado deslocamento de rotaÃ§Ã£o: {offset} (apÃ³s {rotations} rotaÃ§Ãµes)")
    return offset

# FunÃ§Ã£o para buscar streams do banco de dados
async def fetch_streams_from_db():
    """
    Busca a configuraÃ§Ã£o dos streams do banco de dados PostgreSQL.
    Retorna a lista de streams ou None em caso de erro.
    """
    conn = None
    try:
        conn = await connect_db()
        if not conn:
            logger.warning("NÃ£o foi possÃ­vel conectar ao banco de dados para buscar streams.")
            return None
        
        with conn.cursor() as cursor:
            # Verificar se a tabela streams existe
            cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'streams')")
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                logger.error("A tabela 'streams' nÃ£o existe no banco de dados!")
                return None
            
            # Buscar todos os streams ordenados por index
            cursor.execute("SELECT url, name, sheet, cidade, estado, regiao, segmento, index FROM streams ORDER BY index")
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
                    "metadata": {}  # Adicionar campo metadata vazio
                }
                streams.append(stream)
            
            logger.info(f"Carregados {len(streams)} streams do banco de dados.")
            return streams
            
    except Exception as e:
        logger.error(f"Erro ao buscar streams do banco de dados: {e}")
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_err:
                logger.error(f"Erro ao fechar conexÃ£o do banco de dados: {close_err}")

# FunÃ§Ã£o para salvar streams no arquivo JSON local
def save_streams_to_json(streams):
    """
    Salva a lista de streams no arquivo JSON local como backup.
    """
    try:
        with open(STREAMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(streams, f, ensure_ascii=False, indent=2)
        logger.info(f"Streams salvos com sucesso no arquivo JSON local: {STREAMS_FILE}")
    except Exception as e:
        logger.error(f"Erro ao salvar streams no arquivo JSON {STREAMS_FILE}: {e}")

# FunÃ§Ã£o para carregar os streamings do banco de dados PostgreSQL
async def load_streams():
    """
    Carrega a configuraÃ§Ã£o dos streams. Prioriza o banco de dados,
    usa o JSON local como fallback e atualiza o JSON apÃ³s sucesso no DB.
    Retorna apenas a lista de streams.
    """
    streams_from_db = await fetch_streams_from_db()  # Tenta buscar do DB primeiro

    if streams_from_db is not None:
        logger.info("Streams carregados com sucesso do banco de dados.")
        save_streams_to_json(streams_from_db)  # Atualiza o JSON local como backup
        return streams_from_db  # Retorna apenas a lista de streams

    # Fallback: Tentar carregar do JSON local se o DB falhar
    logger.warning(
        f"Falha ao carregar do DB ou DB nÃ£o configurado. "
        f"Tentando carregar do arquivo de fallback: {STREAMS_FILE}"
    )
    if os.path.exists(STREAMS_FILE):
        try:
            with open(STREAMS_FILE, 'r', encoding='utf-8') as f:
                streams_from_json = json.load(f)

            if isinstance(streams_from_json, list):  # Verificar se Ã© uma lista
                # Validar estrutura bÃ¡sica (opcional, mas recomendado)
                valid_streams = []
                seen_ids = set()
                for stream in streams_from_json:
                    # ValidaÃ§Ã£o mais robusta
                    stream_id_val = stream.get('id')  # Obter ID para validaÃ§Ã£o
                    if (
                        isinstance(stream, dict)
                        and stream_id_val is not None  # ID nÃ£o pode ser None
                        and 'name' in stream
                        and 'url' in stream
                        and str(stream_id_val) not in seen_ids  # Evitar IDs duplicados
                    ):
                        stream_id_str = str(stream_id_val)  # Normalizar para string

                        # Garantir que 'metadata' exista e seja um dict
                        if 'metadata' not in stream or not isinstance(stream['metadata'], dict):
                            if 'metadata' in stream:
                                logger.warning(
                                    f"Corrigindo campo 'metadata' invÃ¡lido para stream ID {stream_id_str} no JSON."
                                )
                            stream['metadata'] = {}

                        # Atualizar o ID no dicionÃ¡rio para ser string se necessÃ¡rio
                        stream['id'] = stream_id_str
                        valid_streams.append(stream)
                        seen_ids.add(stream_id_str)
                    else:
                        logger.warning(
                            f"Stream invÃ¡lido, sem ID, ou ID duplicado ({stream_id_val}) "
                            f"encontrado e ignorado no JSON: {stream}"
                        )

                if not valid_streams:
                    logger.error(
                        f"Nenhum stream vÃ¡lido encontrado no arquivo JSON de fallback: {STREAMS_FILE}"
                    )
                    return []

                logger.info(
                    f"Carregados {len(valid_streams)} streams vÃ¡lidos do arquivo JSON de fallback."
                )
                return valid_streams  # Retorna apenas a lista de streams
            else:
                logger.error(
                    f"ConteÃºdo do arquivo JSON ({STREAMS_FILE}) nÃ£o Ã© uma lista vÃ¡lida."
                )
                return []  # Retorna lista vazia

        except (IOError, json.JSONDecodeError) as e:
            logger.error(
                f"Erro ao carregar ou parsear streams do arquivo JSON {STREAMS_FILE}: {e}",
                exc_info=True,
            )
            return []  # Retorna lista vazia
        except Exception as e:
            logger.error(
                f"Erro inesperado ao carregar streams do JSON {STREAMS_FILE}: {e}",
                exc_info=True,
            )
            return []
    else:
        logger.critical(
            f"Falha ao carregar do DB e arquivo JSON de fallback {STREAMS_FILE} nÃ£o encontrado. "
            f"NÃ£o hÃ¡ fonte de streams disponÃ­vel."
        )
        # send_email_alert("Erro CrÃ­tico - Sem Fonte de Streams", f"Falha ao conectar ao DB e o arquivo {STREAMS_FILE} nÃ£o existe.")
        return []

# FunÃ§Ã£o para carregar o estado das Ãºltimas mÃºsicas identificadas
def load_last_songs():
    logger.debug("Iniciando a funÃ§Ã£o load_last_songs()")
    try:
        if os.path.exists(LAST_SONGS_FILE):
            with open(LAST_SONGS_FILE, 'r', encoding='utf-8') as f:
                last_songs = json.load(f)
                logger.info(f"{len(last_songs)} Ãºltimas mÃºsicas carregadas.")
                return last_songs
        else:
            return {}
    except Exception as e:
        logger.error(f"Erro ao carregar o arquivo de estado das Ãºltimas mÃºsicas: {e}")
        return {}

# FunÃ§Ã£o para salvar o estado das Ãºltimas mÃºsicas identificadas
def save_last_songs(last_songs):
    logger.debug("Iniciando a funÃ§Ã£o save_last_songs()")
    try:
        with open(LAST_SONGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_songs, f, indent=4, ensure_ascii=False)
        logger.info(f"Arquivo de estado {LAST_SONGS_FILE} salvo.")
    except IOError as e:
        logger.error(f"Erro ao salvar estado em {LAST_SONGS_FILE}: {e}")

# FunÃ§Ã£o para carregar o log local
def load_local_log():
    logger.debug("Iniciando a funÃ§Ã£o load_local_log()")
    try:
        if os.path.exists(LOCAL_LOG_FILE):
            with open(LOCAL_LOG_FILE, 'r', encoding='utf-8') as f:
                local_log = json.load(f)
                logger.info(f"{len(local_log)} entradas carregadas do log local.")
                return local_log
        else:
            return []
    except Exception as e:
        logger.error(f"Erro ao carregar o log local: {e}")
        return []

# FunÃ§Ã£o para salvar o log local
def save_local_log(local_log):
    logger.debug("Iniciando a funÃ§Ã£o save_local_log()")
    try:
        with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(local_log, f, ensure_ascii=False)
        logger.info(f"Log local {LOCAL_LOG_FILE} salvo.")
    except IOError as e:
        logger.error(f"Erro ao salvar log local em {LOCAL_LOG_FILE}: {e}")

# FunÃ§Ã£o para apagar o log local
def clear_local_log():
    logger.debug("Iniciando a funÃ§Ã£o clear_local_log()")
    try:
        with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)
        logger.info("Log local limpo.")
    except IOError as e:
        logger.error(f"Erro ao limpar o log local {LOCAL_LOG_FILE}: {e}")

# FunÃ§Ã£o para verificar duplicidade na log local
def is_duplicate_in_log(song_title, artist, name):
    logger.debug("Iniciando a funÃ§Ã£o is_duplicate_in_log()")
    local_log = load_local_log()
    for entry in local_log:
        if entry["song_title"] == song_title and entry["artist"] == artist and entry["name"] == name:
            return True
    return False

# FunÃ§Ã£o para converter a data e hora ISO 8601 para dd/mm/yyyy e HH:MM:SS
def convert_iso8601_to_datetime(iso_date):
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
    except Exception as e:
        logger.error(f"Erro ao converter a data e hora: {e}")
        return iso_date, iso_date

# FunÃ§Ã£o para monitorar periodicamente o banco de dados para atualizaÃ§Ãµes nos streams
async def monitor_streams_file(callback):
    logger.debug("Iniciando a funÃ§Ã£o monitor_streams_file()")
    last_streams_count = 0
    last_check_time = 0
    check_interval = 300  # Verificar a cada 5 minutos (300 segundos)
    
    while True:
        try:
            current_time = time.time()
            # Verificar apenas a cada intervalo definido
            if current_time - last_check_time >= check_interval:
                conn = await connect_db()
                if conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) FROM streams")
                        current_count = cursor.fetchone()[0]
                        # Se o nÃºmero de streams mudou, recarregar
                        if current_count != last_streams_count:
                            logger.info(f"MudanÃ§a detectada no nÃºmero de streams: {last_streams_count} -> {current_count}")
                            last_streams_count = current_count
                            callback()
                    conn.close()
                last_check_time = current_time
            
            await asyncio.sleep(60)  # Verificar a cada minuto se Ã© hora de checar o banco
        except Exception as e:
            logger.error(f"Erro ao monitorar streams no banco de dados: {e}")
            await asyncio.sleep(60)  # Esperar um minuto antes de tentar novamente


def sanitize_filename(name: str) -> str:
    """Sanitiza nomes para uso seguro em sistemas de arquivos."""
    invalid_chars = '<>:"/\\|?*'
    table = str.maketrans({ch: '_' for ch in invalid_chars})
    safe = name.translate(table)
    # Substitui caracteres de controle/fora do ASCII bÃ¡sico
    safe = ''.join(c if 32 <= ord(c) < 127 else '_' for c in safe)
    # Remove espaÃ§os/pontos finais problemÃ¡ticos no Windows
    safe = safe.strip().rstrip('.')
    return safe[:120] if len(safe) > 120 else safe

# FunÃ§Ã£o para capturar o Ã¡udio do streaming ao vivo e salvar um segmento temporÃ¡rio
async def capture_stream_segment(name, url, duration=None, processed_by_server=True):
    # Se o stream nÃ£o for processado por este servidor, retornar None
    if not processed_by_server:
        logger.info(f"Pulando captura do stream {name} pois nÃ£o Ã© processado por este servidor.")
        return None
    
    # Usar configuraÃ§Ã£o global se nÃ£o especificado
    if duration is None:
        duration = IDENTIFICATION_DURATION
        
    output_dir = SEGMENTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_name = sanitize_filename(name)
    # Nome Ãºnico por captura para evitar concorrÃªncia e sobrescrita
    timestamp_str = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    unique_suffix = uuid.uuid4().hex[:6]
    output_filename = f"{safe_name}_{timestamp_str}_{unique_suffix}.mp3"
    output_path = os.path.join(output_dir, output_filename)
    try:
        logger.debug(f"URL do stream: {url}")
        # Remover a verificaÃ§Ã£o prÃ©via da URL com requests
        # Remover o parÃ¢metro -headers
        command = [
            'ffmpeg', '-y', '-i', url,
            '-t', str(duration), '-ac', '1', '-ar', '44100', '-b:a', '192k', '-acodec', 'libmp3lame', output_path
        ]
        logger.info(f"Capturando segmento de {duration} segundos do stream {name}...")
        logger.debug(f"Comando FFmpeg: {' '.join(command)}")
        
        # Usar o timeout aumentado
        capture_timeout = duration + 30  # 30 segundos a mais do que a duraÃ§Ã£o desejada
        
        process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=capture_timeout)
        
        if process.returncode != 0:
            stderr_text = stderr.decode(errors='ignore') if stderr else "Sem saÃ­da de erro"
            logger.error(f"Erro ao capturar o stream {url}: {stderr_text}")
            connection_tracker.record_error(name)  # Registra o erro
            return None
        else:
            # Verificar se o arquivo foi criado e tem um tamanho razoÃ¡vel
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:  # Mais de 1KB
                logger.info(f"Segmento de {duration} segundos capturado com sucesso para {name}.")
                connection_tracker.clear_error(name)  # Limpa o erro se a captura for bem-sucedida
                return output_path
            else:
                logger.error(f"Arquivo de saÃ­da vazio ou muito pequeno para {name}.")
                connection_tracker.record_error(name)
                return None
    except asyncio.TimeoutError:
        logger.error(f"Tempo esgotado para capturar o stream {url} apÃ³s {capture_timeout}s")
        connection_tracker.record_error(name)  # Registra o erro
        if 'process' in locals():
            process.kill()
        return None
    except Exception as e:
        logger.error(f"Erro ao capturar o stream {url}: {str(e)}")
        logger.error(f"Tipo de erro: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        connection_tracker.record_error(name)  # Registra o erro
        return None

# FunÃ§Ã£o para verificar duplicatas no banco de dados (MODIFICADA)
async def _internal_is_duplicate_in_db(cursor, now_tz, name, artist, song_title):
    # Recebe datetime timezone-aware (now_tz)
    # --- Log Detalhado InÃ­cio ---
    logger.debug(f"[_internal_is_duplicate] Iniciando verificaÃ§Ã£o para:")
    logger.debug(f"  Stream: {name}")
    logger.debug(f"  Artista: {artist}")
    logger.debug(f"  TÃ­tulo: {song_title}")
    logger.debug(f"  Timestamp Atual (TZ): {now_tz}") # Log do timestamp TZ-aware
    logger.debug(f"  Janela (s): {DUPLICATE_PREVENTION_WINDOW_SECONDS}")
    # --- Fim Log Detalhado ---

    try:
        # Calcular o inÃ­cio da janela de verificaÃ§Ã£o usando o timestamp TZ-aware
        start_window_tz = now_tz - timedelta(seconds=DUPLICATE_PREVENTION_WINDOW_SECONDS)
        # Extrair data e hora (como objetos date e time) para a query
        start_date = start_window_tz.date()
        start_time = start_window_tz.time()

        # --- Log Detalhado CÃ¡lculo Janela ---
        logger.debug(f"  InÃ­cio Janela (TZ): {start_window_tz}")
        logger.debug(f"  Data InÃ­cio Janela: {start_date}")
        logger.debug(f"  Hora InÃ­cio Janela: {start_time}")
        # --- Fim Log Detalhado ---

        result = None
        try:
            # Usar apenas a abordagem de comparaÃ§Ã£o separada (mais robusta)
            query = f"""
            SELECT id, date, time FROM {DB_TABLE_NAME}
                WHERE name = %s AND artist = %s AND song_title = %s
                AND (date > %s OR (date = %s AND time >= %s))
            LIMIT 1
            """
            params = (name, artist, song_title, start_date, start_date, start_time)
            # --- Log Detalhado Query ---
            logger.debug(f"  Executando Query (DATE/TIME): {query.strip()}")
            logger.debug(f"  ParÃ¢metros Query: {params}")
            # --- Fim Log Detalhado ---
            
            # Executar a operaÃ§Ã£o de banco de dados em um thread
            def db_query():
                try:
                    cursor.execute(query, params)
                    return cursor.fetchone()
                except Exception as e_query_thread:
                    # Logar o erro aqui tambÃ©m, pois pode nÃ£o ser propagado corretamente
                    logger.error(f"[_internal_is_duplicate] Erro dentro do thread db_query: {e_query_thread}")
                    raise # Re-lanÃ§a para ser pego pelo bloco except externo
            
            result = await asyncio.to_thread(db_query)

            if result:
                 logger.debug(f"  Query encontrou resultado: ID={result[0]}, Data={result[1]}, Hora={result[2]}")
            else:
                 logger.debug(f"  Query nÃ£o encontrou resultado.")

        except Exception as e_query:
             logger.error(f"[_internal_is_duplicate] Erro ao executar query de duplicidade (possivelmente no to_thread): {e_query}", exc_info=True)
             # --- Log Detalhado Erro Query ---
             logger.debug(f"[_internal_is_duplicate] Retornando False devido a erro na query.")
             # --- Fim Log Detalhado ---
             return False # Assume nÃ£o duplicata se a query falhar

        is_duplicate = result is not None
        # --- Log Detalhado Resultado Final ---
        if is_duplicate:
            logger.info(f"[_internal_is_duplicate] Duplicata ENCONTRADA para {song_title} - {artist} em {name} (ID={result[0]} Ã s {result[1]} {result[2]}).")
            logger.debug(f"[_internal_is_duplicate] Retornando True.")
        else:
            logger.info(f"[_internal_is_duplicate] Nenhuma duplicata ENCONTRADA para {song_title} - {artist} em {name} na janela de tempo.") # Mais claro
            logger.debug(f"[_internal_is_duplicate] Retornando False.")
        # --- Fim Log Detalhado ---
        return is_duplicate

    except Exception as e_geral:
        logger.error(f"[_internal_is_duplicate] Erro GERAL ao verificar duplicatas: {e_geral}", exc_info=True)
        # --- Log Detalhado Erro Geral ---
        logger.debug(f"[_internal_is_duplicate] Retornando False devido a erro geral.")
        # --- Fim Log Detalhado ---
        return False # Assume nÃ£o duplicata em caso de erro na verificaÃ§Ã£o

# FunÃ§Ã£o para inserir dados no banco de dados (MODIFICADA)
async def insert_data_to_db(entry_base, now_tz):
    # Recebe dicionÃ¡rio base e timestamp TZ-aware
    song_title = entry_base['song_title']
    artist = entry_base['artist']
    name = entry_base['name']
    logger.debug(f"insert_data_to_db: Iniciando processo para {song_title} - {artist} em {name}")

    def db_insert_operations():
        _conn = None
        _success = False
        try:
            # Esta funÃ§Ã£o serÃ¡ executada em thread separada, entÃ£o podemos usar connect_db sÃ­ncrono
            _conn = psycopg2.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT
            )
            
            if not _conn:
                logger.error("insert_data_to_db [thread]: NÃ£o foi possÃ­vel conectar ao DB.")
                return False

            with _conn.cursor() as cursor:
                # 1) Verificar se a tabela existe
                cursor.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                    (DB_TABLE_NAME,),
                )
                if not cursor.fetchone()[0]:
                    logger.error(
                        f"insert_data_to_db [thread]: A tabela '{DB_TABLE_NAME}' "
                        "nÃ£o existe! InserÃ§Ã£o falhou."
                    )
                    return False

                # 2) VerificaÃ§Ã£o de duplicidade (na mesma thread/cursor)
                start_window_tz = now_tz - timedelta(
                    seconds=DUPLICATE_PREVENTION_WINDOW_SECONDS
                )
                start_date = start_window_tz.date()
                start_time = start_window_tz.time()

                dup_query = f"""
                    SELECT 1 FROM {DB_TABLE_NAME}
                    WHERE name = %s AND artist = %s AND song_title = %s
                      AND (date > %s OR (date = %s AND time >= %s))
                    LIMIT 1
                """
                dup_params = (
                    name,
                    artist,
                    song_title,
                    start_date,
                    start_date,
                    start_time,
                )
                logger.debug(
                    f"  [thread] Verificando duplicidade (DATE/TIME): {dup_query.strip()}"
                )
                logger.debug(f"  [thread] ParÃ¢metros duplicidade: {dup_params}")

                cursor.execute(dup_query, dup_params)
                if cursor.fetchone():
                    logger.info(
                        f"insert_data_to_db [thread]: InserÃ§Ã£o ignorada, duplicata "
                        f"encontrada para {song_title} - {artist} em {name}."
                    )
                    return False

                # 3) Preparar dados para inserÃ§Ã£o
                date_str = now_tz.strftime('%Y-%m-%d')
                time_str = now_tz.strftime('%H:%M:%S')
                logger.debug(
                    f"  [thread] Formatado para INSERT: date='{date_str}', time='{time_str}'"
                )

                entry = entry_base.copy()
                entry["date"] = date_str
                entry["time"] = time_str

                logger.debug(
                    "insert_data_to_db [thread]: identified_by(entry)='%s', "
                    "SERVER_ID='%s', EFFECTIVE_SERVER_ID='%s'",
                    entry.get("identified_by"),
                    str(SERVER_ID),
                    str(EFFECTIVE_SERVER_ID),
                )

                values = (
                    entry["date"],
                    entry["time"],
                    entry["name"],
                    entry["artist"],
                    entry["song_title"],
                    entry.get("isrc", ""),
                    entry.get("cidade", ""),
                    entry.get("estado", ""),
                    entry.get("regiao", ""),
                    entry.get("segmento", ""),
                    entry.get("label", ""),
                    entry.get("genre", ""),
                    entry.get("identified_by", str(SERVER_ID)),
                )
                logger.debug(f"insert_data_to_db [thread]: Valores para inserÃ§Ã£o: {values}")

                insert_query = f"""
                    INSERT INTO {DB_TABLE_NAME}
                        (date, time, name, artist, song_title, isrc,
                         cidade, estado, regiao, segmento, label, genre, identified_by)
                    VALUES
                        (%s, %s, %s, %s, %s, %s,
                         %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """

                try:
                    cursor.execute(insert_query, values)
                    inserted_row = cursor.fetchone()
                    if inserted_row:
                        _conn.commit()
                        logger.info(
                            "insert_data_to_db [thread]: Dados inseridos com sucesso: "
                            f"ID={inserted_row[0]}, {song_title} - {artist} ({name})"
                        )
                        _success = True
                    else:
                        logger.error(
                            "insert_data_to_db [thread]: InserÃ§Ã£o falhou ou nÃ£o retornou ID "
                            f"para {song_title} - {artist}."
                        )
                        _conn.rollback()
                        _success = False

                except psycopg2.errors.UniqueViolation as e_unique:
                    _conn.rollback()
                    logger.warning(
                        "insert_data_to_db [thread]: InserÃ§Ã£o falhou devido a "
                        f"violaÃ§Ã£o UNIQUE: {e_unique}"
                    )
                    _success = False
                except Exception as e_insert:
                    _conn.rollback()
                    logger.error(
                        "insert_data_to_db [thread]: Erro GERAL ao inserir dados "
                        f"({song_title} - {artist}): {e_insert}"
                    )
                    _success = False
                    # Re-lanÃ§ar para ser capturado fora e disparar alerta
                    raise e_insert
                    
            return _success

        except Exception as e_db:
            logger.error(
                f"insert_data_to_db [thread]: Erro no DB (cursor/execuÃ§Ã£o): {e_db}"
            )
            if _conn:
                try:
                    _conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if _conn:
                try:
                    _conn.close()
                except Exception as cl_err:
                    logger.error(f"Erro ao fechar conexÃ£o DB em thread: {cl_err}")

    # Executar operaÃ§Ãµes de banco em thread separada
    try:
        success = await asyncio.to_thread(db_insert_operations)
        
        if not success:
            logger.info("Enviando alerta de e-mail por falha na inserÃ§Ã£o (nÃ£o duplicata)")
            subject = "Alerta: Erro ao Inserir Dados no Banco de Dados"
            body = (
                f"O servidor {SERVER_ID} encontrou um erro GERAL ao inserir dados "
                f"na tabela {DB_TABLE_NAME}. Verifique os logs.\nDados: {entry_base}"
            )
            send_email_alert(subject, body)
            
        return success
        
    except Exception as e:
        logger.error(
            f"insert_data_to_db: Erro INESPERADO ({song_title} - {artist}): {e}",
            exc_info=True,
        )
        return False

# FunÃ§Ã£o para atualizar o log local e chamar a inserÃ§Ã£o no DB
async def update_local_log(stream, song_title, artist, timestamp, isrc=None, label=None, genre=None):
    # ... (CriaÃ§Ã£o de date_str, time_str, stream_name - igual a antes) ...
    date_str = timestamp.strftime('%Y-%m-%d')
    time_str = timestamp.strftime('%H:%M:%S')
    stream_name = stream['name']
    logger.debug(f"update_local_log: Preparando {song_title} - {artist} em {stream_name}")

    logger.debug(
        "update_local_log: using identified_by='%s' (SERVER_ID), EFFECTIVE_SERVER_ID='%s'",
        str(SERVER_ID), str(EFFECTIVE_SERVER_ID)
    )

    # ... (Carregamento do log local - igual a antes) ...
    local_log = []
    try:
        if os.path.exists(LOCAL_LOG_FILE):
            with open(LOCAL_LOG_FILE, 'r', encoding='utf-8') as f:
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
        "identified_by": str(SERVER_ID) 
    }

    # Tenta inserir no banco de dados (a funÃ§Ã£o insert_data_to_db agora faz a checagem de duplicidade)
    inserted_successfully = await insert_data_to_db(new_entry, timestamp.replace(tzinfo=timezone.utc))
        
    if inserted_successfully:
        logger.info(f"update_local_log: InserÃ§Ã£o de {song_title} - {artist} bem-sucedida. Atualizando log local.")
        # Adiciona ao log local apenas se inserido com sucesso no DB
        local_log.append(new_entry)
        local_log = local_log[-1000:] # MantÃ©m tamanho gerenciÃ¡vel
            
        # Salva o log local atualizado
        try:
            with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_log, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar log local: {e}")
            
        return True # Indica que foi uma nova inserÃ§Ã£o bem-sucedida
    else:
        # A inserÃ§Ã£o falhou (seja por duplicidade ou erro)
        # O log da falha jÃ¡ foi feito dentro de insert_data_to_db
        logger.info(f"update_local_log: InserÃ§Ã£o de {song_title} - {artist} falhou ou foi ignorada (duplicata/erro). Log local nÃ£o atualizado.")
        return False 

# Modificar funÃ§Ã£o process_stream para usar distribuiÃ§Ã£o dinÃ¢mica
async def process_stream(stream, last_songs):
    logger.debug("Iniciando a funÃ§Ã£o process_stream()")
    url = stream['url']
    name = stream['name']
    # Use stream index or name as the key for tracking
    stream_key = stream.get('index', name)
    stream_index = stream.get('index', 0)
    previous_segment = None

    while True:
        logger.info(f"Processando streaming: {name}")
        
        # Verificar dinamicamente se este stream deve ser processado por este servidor
        try:
            # Garantir que o Ã­ndice seja inteiro para distribuiÃ§Ã£o
            try:
                stream_index_int = int(stream_index)
            except Exception:
                stream_index_int = 0
            processed_by_server = await should_process_stream_dynamic(stream_index_int, SERVER_ID)
        except Exception as e:
            logger.error(f"Erro ao verificar distribuiÃ§Ã£o dinÃ¢mica para {name}: {e}")
            # Fallback para lÃ³gica estÃ¡tica SOMENTE em caso de erro
            try:
                server_id = int(EFFECTIVE_SERVER_ID)
                total = int(TOTAL_SERVERS) if int(TOTAL_SERVERS) > 0 else 1
                idx = int(stream.get('index', 0)) if str(stream.get('index', '0')).isdigit() else 0
                processed_by_server = (idx % total == (server_id - 1))
            except Exception as fe:
                logger.error(f"Fallback estÃ¡tico falhou para {name}: {fe}. Assumindo processamento local.")
                processed_by_server = True
        
        # Verificar se este stream estÃ¡ sendo processado por este servidor
        if not processed_by_server:
            logger.info(
                f"Stream {name} ({stream_key}) nÃ£o Ã© processado por este servidor. "
                f"Verificando novamente (rebalance-aware) em atÃ© 60 segundos."
            )
            await wait_for_rebalance_or_timeout(60)
            continue

        current_segment_path = await capture_stream_segment(
            name, url, duration=None, processed_by_server=processed_by_server
        )

        if current_segment_path is None:
            # Registrar erro no tracker
            connection_tracker.record_error(stream_key) 
            failure_count = connection_tracker.get_error_count(stream_key)
            
            wait_time = 10  # Default wait time
            if failure_count > 3:
                wait_time = 30 # Increased wait time after 3 failures
                
            logger.error(
                f"Falha ao capturar segmento do streaming {name} ({stream_key}). "
                f"Falha #{failure_count}. Tentando novamente em atÃ© {wait_time} segundos..."
            )
            await wait_for_rebalance_or_timeout(wait_time)
            continue
        else:
            # Limpar erros no tracker em caso de sucesso
            connection_tracker.clear_error(stream_key)

        # Se a captura foi bem-sucedida, enfileirar sem aguardar processamento
        await shazam_queue.put((current_segment_path, stream, last_songs))
        logger.debug(f"Segmento enfileirado para identificaÃ§Ã£o: {current_segment_path}")

        logger.info(
            f"Aguardando atÃ© 60 segundos (rebalance-aware) para o prÃ³ximo ciclo do stream "
            f"{name} ({stream_key})..."
        )
        await wait_for_rebalance_or_timeout(60)

def send_email_alert(subject, body):
    """
    FunÃ§Ã£o de alerta por e-mail desabilitada.
    Apenas registra o alerta nos logs ao invÃ©s de enviar e-mail.
    """
    logger.warning(f"ALERTA DE E-MAIL (DESABILITADO): {subject}")
    logger.warning(f"ConteÃºdo do alerta: {body}")
    # Comentado para evitar erros de autenticaÃ§Ã£o:
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
            subject = "Alerta: Erros de ConexÃ£o Persistentes em Streams de RÃ¡dio"
            body = f"Os seguintes streams estÃ£o com erros de conexÃ£o hÃ¡ mais de 10 minutos:\n\n"
            for stream in persistent_errors:
                body += f"- {stream}\n"
            body += "\nPor favor, verifique esses streams o mais rÃ¡pido possÃ­vel."
            
            send_email_alert(subject, body)
            logger.warning(f"Alerta enviado para erros persistentes: {persistent_errors}")

# FunÃ§Ã£o para sincronizar o arquivo JSON local com o banco de dados
async def sync_json_with_db():
    logger.debug("Iniciando a funÃ§Ã£o sync_json_with_db()")
    conn = None
    rows = None
    try:
        # OperaÃ§Ãµes de DB em thread separada
        async def db_operations():
            _conn = await connect_db()
            if not _conn:
                return None, None # Retorna None para conn e rows se a conexÃ£o falhar
            try:
                with _conn.cursor() as _cursor:
                    _cursor.execute("SELECT url, name, sheet, cidade, estado, regiao, segmento, index FROM streams ORDER BY index")
                    _rows = _cursor.fetchall()
                return _conn, _rows # Retorna a conexÃ£o e as linhas
            except Exception as db_err:
                logger.error(f"Erro DB em sync_json_with_db (operaÃ§Ãµes cursor): {db_err}")
                return _conn, None # Retorna a conexÃ£o (para fechar) e None para rows
            # O finally nÃ£o Ã© necessÃ¡rio aqui, pois o close serÃ¡ chamado fora

        conn, rows = await db_operations()

        if conn and rows is not None: # Checar se rows nÃ£o Ã© None
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
                    "index": str(row[7])
                }
                streams.append(stream)
            
            # Aplicar distribuiÃ§Ã£o de carga dinÃ¢mica se ativada (apenas para visualizaÃ§Ã£o no arquivo JSON)
            if DISTRIBUTE_LOAD and len(streams) > 0:
                try:
                    # Obter servidores online dinamicamente
                    online_servers = await get_online_server_ids()
                    active_servers_count = len(online_servers)
                    
                    logger.info(f"sync_json_with_db: Aplicando distribuiÃ§Ã£o dinÃ¢mica com {active_servers_count} servidores online: {online_servers}")
                    
                    # Marcar quais streams sÃ£o processados por este servidor
                    for i, stream_item in enumerate(streams):
                        stream_index = int(stream_item.get('index', i))
                        should_process = await should_process_stream_dynamic(stream_index, SERVER_ID, online_servers)
                        stream_item['processed_by_server'] = should_process
                        stream_item['assigned_to_servers'] = online_servers  # Para debug/informaÃ§Ã£o
                        stream_item['total_active_servers'] = active_servers_count
                        
                except Exception as dyn_err:
                    logger.error(f"Erro ao aplicar distribuiÃ§Ã£o dinÃ¢mica em sync_json_with_db: {dyn_err}")
                    # Fallback para lÃ³gica estÃ¡tica
                    server_id = int(SERVER_ID)
                    if server_id >= 1 and server_id <= TOTAL_SERVERS:
                        for i, stream_item in enumerate(streams):
                            stream_item['processed_by_server'] = (i % TOTAL_SERVERS == (EFFECTIVE_SERVER_ID - 1))
                            stream_item['distribution_mode'] = 'static_fallback'
            
            # Salvar os streams no arquivo JSON local (operaÃ§Ã£o de I/O sÃ­ncrona)
            try:
                with open(STREAMS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(streams, f, ensure_ascii=False, indent=2)
                logger.info(f"Arquivo JSON local sincronizado com sucesso. {len(streams)} streams salvos.")
            except Exception as file_err:
                logger.error(f"Erro ao salvar arquivo JSON local em sync_json_with_db: {file_err}")

        elif conn is None:
             logger.error("NÃ£o foi possÃ­vel conectar ao banco de dados para sincronizar o arquivo JSON local.")
        else: # conn existe, mas rows Ã© None (erro no cursor)
             logger.error("Erro ao buscar dados do banco para sincronizar o arquivo JSON local.")
             
    except Exception as e:
        logger.error(f"Erro geral ao sincronizar o arquivo JSON local com o banco de dados: {e}")
    finally:
        if conn:
            try:
                # Fechar conexÃ£o em thread separada
                await asyncio.to_thread(conn.close)
            except Exception as close_err:
                logger.error(f"Erro ao fechar conexÃ£o DB em sync_json_with_db: {close_err}")

# FunÃ§Ã£o para agendar a sincronizaÃ§Ã£o periÃ³dica do arquivo JSON
async def schedule_json_sync():
    logger.info("Iniciando agendamento de sincronizaÃ§Ã£o do arquivo JSON local")
    while True:
        await sync_json_with_db()  # Sincroniza imediatamente na inicializaÃ§Ã£o
        await asyncio.sleep(3600)  # Aguarda 1 hora (3600 segundos) antes da prÃ³xima sincronizaÃ§Ã£o

# FunÃ§Ã£o para verificar se Ã© hora de recarregar os streams devido Ã  rotaÃ§Ã£o
async def check_rotation_schedule():
    if not (DISTRIBUTE_LOAD and ENABLE_ROTATION):
        return False  # NÃ£o fazer nada se a rotaÃ§Ã£o nÃ£o estiver ativada
    
    logger.info("Iniciando monitoramento de rotaÃ§Ã£o de streams")
    last_rotation_offset = calculate_rotation_offset()
    
    while True:
        await asyncio.sleep(60)  # Verificar a cada minuto
        current_rotation_offset = calculate_rotation_offset()
        
        if current_rotation_offset != last_rotation_offset:
            logger.info(f"Detectada mudanÃ§a na rotaÃ§Ã£o: {last_rotation_offset} -> {current_rotation_offset}")
            last_rotation_offset = current_rotation_offset
            
            # Recarregar streams com a nova rotaÃ§Ã£o
            global STREAMS
            STREAMS = load_streams()
            logger.info(f"Streams recarregados devido Ã  rotaÃ§Ã£o. Agora processando {len(STREAMS)} streams.")
            
            # Atualizar as tarefas (isso serÃ¡ chamado na funÃ§Ã£o main)
            return True
        
        return False

# FunÃ§Ã£o worker para identificar mÃºsica usando Shazamio (MODIFICADA)
async def identify_song_shazamio(shazam):
    global last_request_time, shazam_pause_until_timestamp
    # Definir o fuso horÃ¡rio uma vez fora do loop usando pytz
    target_tz = None
    if HAS_PYTZ:
        try:
            target_tz = pytz.timezone("America/Sao_Paulo")
            logger.info(
                "Fuso horÃ¡rio definido (via pytz) para verificaÃ§Ã£o de duplicatas: "
                "America/Sao_Paulo"
            )
        except pytz.exceptions.UnknownTimeZoneError:
            logger.critical(
                "Erro ao definir fuso horÃ¡rio 'America/Sao_Paulo' com pytz: "
                "Zona desconhecida. Verifique o nome."
            )
            sys.exit(1)
        except Exception as tz_err:
            logger.critical(
                f"Erro ao definir fuso horÃ¡rio 'America/Sao_Paulo' com pytz: {tz_err}. "
                "Saindo."
            )
            sys.exit(1)
    else:
        # Se pytz nÃ£o foi importado, sair (jÃ¡ logado criticamente na importaÃ§Ã£o)
        logger.critical(
            "pytz nÃ£o estÃ¡ disponÃ­vel. ImpossÃ­vel continuar com tratamento de fuso horÃ¡rio."
        )
        sys.exit(1)

    while True:
        file_path, stream, last_songs = await shazam_queue.get()
        stream_index = stream.get("index")  # Obter Ã­ndice aqui para uso posterior
        
        try:
            # Verificar se o arquivo existe (pode ter sido pulado na captura)
            if file_path is None:
                logger.info(
                    f"Arquivo de segmento para o stream {stream['name']} nÃ£o foi capturado. "
                    "Pulando identificaÃ§Ã£o."
                )
                continue

            identification_attempted = False
            out = None  # Inicializar fora do loop de retentativa

            # --- Verificar se o Shazam estÃ¡ em pausa ---
            current_time_check = time.time()
            if current_time_check < shazam_pause_until_timestamp:
                logger.info(
                    "Shazam em pausa devido a erro 429 anterior "
                    f"(atÃ© {dt.datetime.fromtimestamp(shazam_pause_until_timestamp).strftime('%H:%M:%S')}). "
                    f"Enviando {os.path.basename(file_path)} diretamente para failover."
                )
                if ENABLE_FAILOVER_SEND:
                    asyncio.create_task(send_file_via_failover(file_path, stream_index))
            else:
                # --- Tentar identificaÃ§Ã£o se nÃ£o estiver em pausa ---
                identification_attempted = True
                # ... (loop de retentativas com tratamento de erro 429 e failover) ...
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        # ... (cÃ³digo do try existente: esperar, logar, shazam.recognize) ...
                        current_time = time.time()
                        time_since_last_request = current_time - last_request_time
                        if time_since_last_request < 1:
                            await asyncio.sleep(1 - time_since_last_request)

                        # Verificar se o arquivo ainda existe antes de chamar o Shazam
                        if not os.path.exists(file_path):
                            logger.error(
                                f"Arquivo de segmento nÃ£o encontrado no momento da "
                                f"identificaÃ§Ã£o: {file_path}"
                            )
                            break

                        logger.info(
                            f"Identificando mÃºsica no arquivo {file_path} "
                            f"(tentativa {attempt + 1}/{max_retries})..."
                        )
                        out = await asyncio.wait_for(
                            shazam.recognize(file_path), timeout=10
                        )
                        last_request_time = time.time()

                        if "track" in out:
                            break
                        else:
                            logger.info(
                                "Nenhuma mÃºsica identificada (resposta vazia do Shazam)."
                            )
                            break

                    except ClientResponseError as e_resp:
                        # ... (tratamento erro 429 com pausa e failover) ...
                        if e_resp.status == 429:
                            logger.warning(
                                "Erro 429 (Too Many Requests) do Shazam detectado. "
                                "Pausando Shazam por 2 minutos."
                            )
                            shazam_pause_until_timestamp = time.time() + 120
                            if ENABLE_FAILOVER_SEND:
                                asyncio.create_task(
                                    send_file_via_failover(file_path, stream_index)
                                )
                            break
                        else:
                            wait_time = 2**attempt
                            logger.error(
                                f"Erro HTTP {e_resp.status} do Shazam "
                                f"(tentativa {attempt + 1}/{max_retries}): {e_resp}. "
                                f"Esperando {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                    except (ClientConnectorError, asyncio.TimeoutError) as e_conn:
                        # ... (tratamento erro conexÃ£o/timeout) ...
                        wait_time = 2**attempt
                        logger.error(
                            "Erro de conexÃ£o/timeout com Shazam "
                            f"(tentativa {attempt + 1}/{max_retries}): {e_conn}. "
                            f"Esperando {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    except Exception as e_gen:
                        # ... (tratamento erro genÃ©rico) ...
                        logger.error(
                            "Erro inesperado ao identificar a mÃºsica "
                            f"(tentativa {attempt + 1}/{max_retries}): {e_gen}",
                            exc_info=True,
                        )
                        break
                else:
                    if identification_attempted:
                        logger.error(
                            "Falha na identificaÃ§Ã£o de "
                            f"{os.path.basename(file_path)} apÃ³s {max_retries} tentativas "
                            "(sem erro 429 ou erro genÃ©rico)."
                        )

            # --- Processar resultado (se houve identificaÃ§Ã£o e nÃ£o estava em pausa) ---
            if identification_attempted and out and "track" in out:
                track = out["track"]
                title = track["title"]
                artist = track["subtitle"]
                isrc = track.get("isrc", "ISRC nÃ£o disponÃ­vel")
                label = None
                genre = None
                # ... (extraÃ§Ã£o de label/genre) ...
                if "sections" in track:
                    for section in track["sections"]:
                        if section["type"] == "SONG":
                            for metadata in section["metadata"]:
                                if metadata["title"] == "Label":
                                    label = metadata["text"]
                if "genres" in track:
                    genre = track["genres"].get("primary", None)

                logger.info(
                    f"MÃºsica identificada: {title} por {artist} "
                    f"(ISRC: {isrc}, Gravadora: {label}, GÃªnero: {genre})"
                )

                # Obter timestamp atual COM FUSO HORÃRIO
                now_tz = dt.datetime.now(target_tz)

                # Criar dicionÃ¡rio base SEM date/time
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

                # Chamar insert_data_to_db, que farÃ¡ a verificaÃ§Ã£o e a inserÃ§Ã£o
                inserted = await insert_data_to_db(entry_base, now_tz)

                if inserted:  # Salvar last_songs apenas se inserÃ§Ã£o foi bem-sucedida
                    last_songs[stream["name"]] = (title, artist)
                    save_last_songs(last_songs)

            # --- Limpeza do arquivo local ---
            # ... (cÃ³digo de limpeza existente) ...
            if os.path.exists(file_path):
                try:
                    await asyncio.to_thread(os.remove, file_path)
                    logger.debug(f"Arquivo de segmento local {file_path} removido.")
                except Exception as e_remove:
                    logger.error(
                        f"Erro ao remover arquivo de segmento {file_path}: {e_remove}"
                    )

        finally:
            # GARANTIR que task_done seja sempre chamado
            shazam_queue.task_done()

# VariÃ¡veis globais para controle de finalizaÃ§Ã£o
shutdown_event = asyncio.Event()
active_tasks = set()

# FunÃ§Ã£o para lidar com sinais de finalizaÃ§Ã£o (CTRL+C, etc.)
def handle_shutdown_signal(sig, frame):
    logger.info(f"Sinal de finalizaÃ§Ã£o recebido ({sig}). Iniciando o encerramento controlado...")
    shutdown_event.set()

# Registrar o handler para os sinais
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# FunÃ§Ã£o para monitorar shutdown e cancelar tarefas
async def monitor_shutdown():
    await shutdown_event.wait()
    logger.info("Cancelando todas as tarefas ativas...")
    
    # Cancelar todas as tarefas ativas
    for task in active_tasks:
        if not task.done():
            task.cancel()
    
    # Aguardar atÃ© 5 segundos para as tarefas serem canceladas
    if active_tasks:
        try:
            await asyncio.wait(active_tasks, timeout=5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro ao aguardar cancelamento de tarefas: {e}")
    
    logger.info("Processo de finalizaÃ§Ã£o concluÃ­do.")

# FunÃ§Ã£o para adicionar uma tarefa ao conjunto de tarefas ativas
def register_task(task):
    active_tasks.add(task)
    # Remover tarefas concluÃ­das para evitar vazamentos de memÃ³ria
    done_tasks = {t for t in active_tasks if t.done()}
    active_tasks.difference_update(done_tasks)
    return task

# FunÃ§Ã£o para enviar heartbeat para o banco de dados
async def send_heartbeat():
    global last_heartbeat_time
    current_time = time.time()

    # Limitar heartbeats
    if current_time - last_heartbeat_time < HEARTBEAT_INTERVAL_SECS:
        return
    
    last_heartbeat_time = current_time
    conn = None
    
    try:
        # Coletar informaÃ§Ãµes do sistema (fora do thread DB)
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        mem_info = await asyncio.to_thread(psutil.virtual_memory)
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=1) # Interval pode ser bloqueante
        disk_info = await asyncio.to_thread(psutil.disk_usage, '/')
        
        # Calcular streams processados dinamicamente
        try:
            processing_streams_count = 0
            for stream in STREAMS:
                stream_index = stream.get('index', 0)
                if await should_process_stream_dynamic(stream_index, EFFECTIVE_SERVER_ID):
                    processing_streams_count += 1
        except Exception as calc_err:
            logger.error(f"Erro ao calcular streams processados dinamicamente: {calc_err}")
            # Fallback para lÃ³gica estÃ¡tica
            processing_streams_count = len([s for s in STREAMS if s.get('processed_by_server', 
                                                                       (int(s.get('index', 0)) % TOTAL_SERVERS) == (EFFECTIVE_SERVER_ID - 1))])
        
        # NOVO: nomes dos streams processados
        try:
            processing_stream_names = await get_streams_processed_names()
            logger.debug(f"send_heartbeat: processing_stream_names({len(processing_stream_names)}): {processing_stream_names[:10]}")
        except Exception as e:
            logger.exception("send_heartbeat: falha ao obter nomes de streams: %s", e)
            processing_stream_names = []

        # NOVO: detectar VPN
        vpn_info = await asyncio.to_thread(detect_vpn)

        # NOVO: Ãºltimos erros do log
        recent_errors = await asyncio.to_thread(get_recent_errors, 5, 400)
        
        # Criar diagnÃ³sticos adicionais
        diagnostics = {
            "streams_loaded": len(STREAMS) if STREAMS else 0,
            "processing_names_count": len(processing_stream_names),
            "distribution_mode": str(globals().get("DISTRIBUTION_MODE") or "unknown"),
            "distribute_load": str(globals().get("DISTRIBUTE_LOAD") or "unknown"),
            "instance_id": str(globals().get("INSTANCE_ID") or "unknown"),
        }
        
        # InformaÃ§Ãµes para o banco de dados
        info = {
            "hostname": platform.node(),
            "platform": platform.system(),
            "cpu_percent": cpu_percent,
            "memory_percent": mem_info.percent,
            "memory_available_mb": round(mem_info.available / (1024 * 1024), 2),
            "disk_percent": disk_info.percent,
            "disk_free_gb": round(disk_info.free / (1024 * 1024 * 1024), 2),
            "processing_streams": processing_streams_count,
            "total_streams": len(STREAMS),
            "distribution_mode": "dynamic" if DISTRIBUTE_LOAD else "static",
            "static_total_servers": TOTAL_SERVERS,
            "cached_active_servers": len(_cached_online_servers) if _cached_online_servers else 0,
            "python_version": platform.python_version(),
            "processing_stream_names": processing_stream_names,
            "vpn": vpn_info,
            "recent_errors": recent_errors,
            "ip_address": ip_address,
            "diagnostics": diagnostics,
        }
        logger.debug("send_heartbeat: diagnostics=%s", diagnostics)
        
        # Novo: publicar em Redis para presenÃ§a e tempo real (nÃ£o bloqueante do fluxo atual)
        try:
            await publish_redis_heartbeat(info)
        except Exception as e:
            logger.debug(f"send_heartbeat: publish_redis_heartbeat falhou: {e}")
        
        # --- OperaÃ§Ãµes de DB --- 
        async def db_heartbeat_operations():
            _conn = None
            try:
                _conn = await connect_db()
                if not _conn:
                    logger.error("send_heartbeat [thread]: NÃ£o foi possÃ­vel conectar ao DB.")
                    return None # Retorna None se conexÃ£o falhar

                with _conn.cursor() as cursor:
                    # Verificar/Criar tabela
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS server_heartbeats (
                            server_id INTEGER PRIMARY KEY,
                            last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            status VARCHAR(20) DEFAULT 'ONLINE',
                            ip_address VARCHAR(50),
                            info JSONB
                        );
                    """)
                    
                    # Atualizar o heartbeat
                    cursor.execute("""
                        INSERT INTO server_heartbeats (server_id, last_heartbeat, status, ip_address, info)
                        VALUES (%s, NOW(), 'ONLINE', %s, %s)
                        ON CONFLICT (server_id) DO UPDATE SET
                            last_heartbeat = NOW(),
                            status = 'ONLINE',
                            ip_address = EXCLUDED.ip_address,
                            info = EXCLUDED.info;
                    """, (SERVER_ID, ip_address, json.dumps(info)))
                    
                    _conn.commit()
                    logger.debug(f"Heartbeat enviado para o servidor {SERVER_ID} (processando {processing_streams_count} streams)")
                return _conn # Retorna a conexÃ£o para ser fechada fora
            except Exception as db_err:
                logger.error(f"Erro DB em send_heartbeat [thread]: {db_err}")
                if _conn: _conn.rollback() # Tentar rollback
                return _conn # Retorna a conexÃ£o (possivelmente None) para tentar fechar

        # Executar operaÃ§Ãµes DB
        conn = await db_heartbeat_operations()
        
    except Exception as e:
        logger.error(f"Erro ao coletar informaÃ§Ãµes do sistema ou executar DB thread em send_heartbeat: {e}")
        # Publicar heartbeat via Redis se disponÃ­vel mesmo com erro no DB
        try:
            await publish_redis_heartbeat(info)
        except Exception as redis_err:
            logger.warning(f"Erro ao publicar heartbeat via Redis apÃ³s falha no DB: {redis_err}")
    finally:
        if conn:
            try:
                await asyncio.to_thread(conn.close)
            except Exception as close_err:
                 logger.error(f"Erro ao fechar conexÃ£o DB em send_heartbeat: {close_err}")

# FunÃ§Ã£o para verificar status de outros servidores
async def check_servers_status():
    # Intervalos e limites
    CHECK_INTERVAL_SECS = 300
    OFFLINE_THRESHOLD_SECS = 600
    conn = None
    
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECS)
            
            # --- OperaÃ§Ãµes DB --- 
            async def db_check_status_operations():
                _conn = None
                _offline_servers_data = []
                _online_servers_data = []
                _send_alert = False # Flag para indicar se o alerta deve ser enviado
                
                try:
                    _conn = await connect_db()
                    if not _conn:
                        logger.error("check_servers_status [thread]: NÃ£o foi possÃ­vel conectar ao DB.")
                        return _conn, [], [], False # conn, offline, online, send_alert

                    with _conn.cursor() as cursor:
                        # Verificar se a tabela existe
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = 'server_heartbeats'
                            );
                        """)
                        
                        if not cursor.fetchone()[0]:
                            logger.warning("check_servers_status [thread]: Tabela de heartbeats nÃ£o existe.")
                            return _conn, [], [], False
                        
                        # Marcar servidores offline
                        cursor.execute("""
                            UPDATE server_heartbeats
                            SET status = 'OFFLINE'
                            WHERE last_heartbeat < NOW() - INTERVAL '%s seconds'
                            AND status = 'ONLINE'
                            RETURNING server_id, last_heartbeat;
                        """, (OFFLINE_THRESHOLD_SECS,))
                        
                        _offline_servers_data = cursor.fetchall()
                        _conn.commit() # Commit da atualizaÃ§Ã£o de status
                        
                        if _offline_servers_data:
                            server_ids = [row[0] for row in _offline_servers_data]
                            logger.warning(f"check_servers_status [thread]: Servidores marcados como OFFLINE: {server_ids}")
                            # Definir flag para enviar alerta se este for o servidor 1
                            if SERVER_ID == 1:
                                _send_alert = True
                        
                        # Obter estatÃ­sticas dos servidores online
                        cursor.execute("""
                            SELECT server_id, last_heartbeat, ip_address, info
                            FROM server_heartbeats
                            WHERE status = 'ONLINE'
                            ORDER BY server_id;
                        """)
                        _online_servers_data = cursor.fetchall()
                    
                    return _conn, _offline_servers_data, _online_servers_data, _send_alert
                
                except Exception as db_err:
                    logger.error(f"Erro DB em check_servers_status [thread]: {db_err}")
                    if _conn: _conn.rollback()
                    # Retorna a conexÃ£o para fechar, mas listas vazias e sem alerta
                    return _conn, [], [], False 

            # Executar operaÃ§Ãµes DB
            conn, offline_servers, online_servers, send_alert = await db_check_status_operations()

            # Processar resultados fora do thread
            if offline_servers and send_alert:
                # Servidores detectados como offline E este servidor deve alertar
                server_ids = [row[0] for row in offline_servers]
                last_heartbeats = [row[1] for row in offline_servers]
                servers_info = "\n".join([f"Servidor {sid}: Ãšltimo heartbeat em {lh}" 
                                          for sid, lh in zip(server_ids, last_heartbeats)])
                
                subject = "ALERTA: Servidores de IdentificaÃ§Ã£o OFFLINE"
                body = f"""Foram detectados servidores offline no sistema de identificaÃ§Ã£o musical.

Servidores offline:
{servers_info}

O que fazer:
1. Verificar se os servidores estÃ£o operacionais
2. Verificar logs de erro
3. Reiniciar os servidores offline se necessÃ¡rio
4. Se um servidor nÃ£o for retornar, considere ajustar TOTAL_SERVERS={TOTAL_SERVERS-len(server_ids)} e reiniciar os demais

Este Ã© um alerta automÃ¡tico enviado pelo servidor {SERVER_ID}.
"""
                send_email_alert(subject, body)
                logger.info(f"Alerta de servidores offline enviado por e-mail")
            
            if online_servers:
                logger.info(f"Servidores online: {len(online_servers)} de {TOTAL_SERVERS}")
                for row in online_servers:
                    server_id, last_hb, ip, info_json = row
                    if info_json:
                        try:
                            info = json.loads(info_json) if isinstance(info_json, str) else info_json
                            streams_info = f"Processando {info.get('processing_streams', '?')} streams"
                            sys_info = f"CPU: {info.get('cpu_percent', '?')}%, Mem: {info.get('memory_percent', '?')}%"
                            logger.debug(f"Servidor {server_id} ({ip}): {streams_info}, {sys_info}")
                        except Exception as json_err:
                            logger.warning(f"Erro ao processar info JSON do servidor {server_id}: {json_err}")
                            logger.debug(f"Servidor {server_id} ({ip}): Ãšltimo heartbeat em {last_hb} (info JSON invÃ¡lido)")
                    else:
                         logger.debug(f"Servidor {server_id} ({ip}): Ãšltimo heartbeat em {last_hb} (sem info JSON)")
                
        except Exception as e:
            logger.error(f"Erro no loop principal de check_servers_status: {e}")
        finally:
            if conn:
                try:
                    await asyncio.to_thread(conn.close)
                    conn = None # Garantir que nÃ£o tentarÃ¡ fechar novamente
                except Exception as close_err:
                     logger.error(f"Erro ao fechar conexÃ£o DB em check_servers_status: {close_err}")

# VariÃ¡vel global para controlar o tempo da Ãºltima solicitaÃ§Ã£o
last_request_time = 0

# VariÃ¡veis globais para cache de servidores dinÃ¢micos
_last_dynamic_check = 0
_cached_online_servers = []
_cached_active_servers_count = 1
DYNAMIC_CACHE_TTL = 120  # Cache por 2 minutos
OFFLINE_THRESHOLD_SECS = 600  # Janela para considerar servidor online (manter em sincronia com check_servers_status)

# Evento global de rebalanceamento
REBALANCE_EVENT = asyncio.Event()

async def watch_online_servers_redis(poll_interval_secs: int = 5):
    """
    Observa heartbeats via Redis para manter lista de servidores online em tempo real.
    Usa prefixo smf: para isolamento. Atualiza cache e dispara REBALANCE_EVENT.
    """
    client = await get_redis_client()
    if not client:
        logger.warning("watch_online_servers_redis: Redis indisponÃ­vel, abortando watcher.")
        return

    last_seen: dict[int, float] = {}  # server_id -> timestamp

    # Semeadura inicial a partir das chaves de presenÃ§a jÃ¡ existentes
    try:
        global _cached_online_servers, _last_dynamic_check
        pattern = f"{REDIS_KEY_PREFIX}:*"  # smf:server:*
        keys = await client.keys(pattern)
        now_ts = time.time()
        for key in keys:
            try:
                sid = int(key.split(":")[-1])
            except (ValueError, IndexError):
                continue
            try:
                ttl = await client.ttl(key)  # segundos restantes
            except Exception:
                ttl = -1
            if ttl is None or ttl < 0:
                # Sem TTL definido ou erro ao obter: considere como visto agora
                last_seen[sid] = now_ts
            else:
                # ReconstrÃ³i o last_seen com base no TTL restante
                last_seen[sid] = max(
                    0.0,
                    now_ts - (REDIS_HEARTBEAT_TTL_SECS - ttl)
                )
        online_now = sorted([
            sid for sid, ts in last_seen.items()
            if (now_ts - ts) < REDIS_HEARTBEAT_TTL_SECS
        ])
        _cached_online_servers = online_now
        _last_dynamic_check = now_ts
        try:
            REBALANCE_EVENT.set()
        except Exception:
            pass
        logger.info(f"Watcher Redis semeado com servidores online iniciais: {online_now}")
        # Janela curta para acordar corrotinas e, em seguida, limpar o evento
        try:
            await asyncio.sleep(1)
            REBALANCE_EVENT.clear()
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"watch_online_servers_redis: falha ao semear estado inicial: {e}")

    # Assinar canal com prefixo smf:
    pubsub = client.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)  # smf:server_heartbeats
    logger.info(f"Watcher Redis iniciado (canal={REDIS_CHANNEL}, poll={poll_interval_secs}s).")

    async def reader():
        """LÃª mensagens do canal Redis e atualiza last_seen."""
        try:
            async for message in pubsub.listen():
                if not message or message.get("type") != "message":
                    continue
                try:
                    data = json.loads(message.get("data", "{}"))
                    if data.get("type") == "heartbeat":
                        sid = int(data.get("server_id"))
                        last_seen[sid] = time.time()
                        logger.debug(f"Redis heartbeat recebido de servidor {sid}")
                except Exception as e:
                    logger.debug(f"watch_online_servers_redis: erro ao processar msg: {e}")
        except Exception as e:
            logger.error(f"watch_online_servers_redis: erro no loop PubSub: {e}")

    async def evaluator():
        """Avalia periodicamente quais servidores estÃ£o online e atualiza cache."""
        global _cached_online_servers, _last_dynamic_check
        while True:
            try:
                now_ts = time.time()
                online_now = sorted([
                    sid for sid, ts in last_seen.items()
                    if (now_ts - ts) < REDIS_HEARTBEAT_TTL_SECS
                ])
                
                if online_now != _cached_online_servers:
                    _cached_online_servers = online_now
                    _last_dynamic_check = now_ts
                    try:
                        REBALANCE_EVENT.set()
                    except Exception:
                        pass
                    logger.info(f"Redis watcher: servidores online atualizados: {online_now}")
                    # Janela curta para acordar corrotinas e, em seguida, limpar o evento
                    await asyncio.sleep(1)
                    try:
                        REBALANCE_EVENT.clear()
                    except Exception:
                        pass
                    
                # Log periÃ³dico de diagnÃ³stico
                if len(last_seen) > 0:
                    logger.debug(f"Redis watcher: last_seen={dict(list(last_seen.items())[:5])}, online_now={online_now}")
                    
            except Exception as e:
                logger.error(f"watch_online_servers_redis.evaluator: {e}")
            await asyncio.sleep(poll_interval_secs)

    # Rodar leitor e avaliador em paralelo
    reader_task = asyncio.create_task(reader())
    evaluator_task = asyncio.create_task(evaluator())
    try:
        await asyncio.gather(reader_task, evaluator_task)
    finally:
        try:
            await pubsub.unsubscribe(REDIS_CHANNEL)
            await pubsub.close()
        except Exception:
            pass

# === INÃCIO: Helpers para Dashboard: VPN, Erros e Streams Ativos ===
import socket  # Adicionar novamente para garantir disponibilidade
def detect_vpn() -> dict:
    """
    Detecta uso de VPN com heurÃ­sticas simples via interfaces de rede e env vars.
    Retorna um dict:
      {
        "in_use": bool,
        "interface": Optional[str],
        "type": Optional[str]  # "wireguard" | "openvpn" | "unknown"
      }
    """
    try:
        import psutil as _ps
        ifaces_stats = _ps.net_if_stats()
        ifaces_addrs = _ps.net_if_addrs()
        candidates = []

        for iface_name, stats in ifaces_stats.items():
            lname = iface_name.lower()
            # HeurÃ­stica: interfaces tÃ­picas de VPN
            if any(token in lname for token in ("tun", "wg", "vpn", "tap")) and stats.isup:
                # Verifica se possui endereÃ§o IPv4 (nÃ£o loopback)
                addrs = ifaces_addrs.get(iface_name, [])
                has_ipv4 = any(
                    (getattr(a, "family", None) == socket.AF_INET) or str(getattr(a, "family", None)).endswith("AF_INET")
                    for a in addrs
                )
                if has_ipv4:
                    candidates.append(iface_name)

        if candidates:
            picked = candidates[0]
            l = picked.lower()
            if "wg" in l:
                return {"in_use": True, "interface": picked, "type": "wireguard"}
            if "tun" in l or "tap" in l:
                return {"in_use": True, "interface": picked, "type": "openvpn"}
            return {"in_use": True, "interface": picked, "type": "unknown"}

        # Fallback: variÃ¡veis de ambiente
        vpn_type = os.getenv("VPN_TYPE") or os.getenv("VPN_SERVICE_PROVIDER")
        if vpn_type:
            return {"in_use": True, "interface": None, "type": vpn_type.lower()}
        if os.getenv("OPENVPN_USER") or os.getenv("OPENVPN_PASSWORD"):
            return {"in_use": True, "interface": None, "type": "openvpn"}

        return {"in_use": False, "interface": None, "type": None}
    except Exception:
        # Em caso de erro, nÃ£o bloquear o heartbeat
        return {"in_use": False, "interface": None, "type": None}


async def get_streams_processed_names() -> list:
    """
    Retorna lista com os nomes dos streams processados por esta instÃ¢ncia,
    com base na lÃ³gica dinÃ¢mica should_process_stream_dynamic.
    """
    names = []
    try:
        total_streams = len(STREAMS) if STREAMS else 0
        if total_streams == 0:
            logger.warning("get_streams_processed_names: STREAMS nÃ£o carregados ou vazios")
            return []

        for s in STREAMS:
            try:
                idx = s.get("index", 0)
                if await should_process_stream_dynamic(idx, EFFECTIVE_SERVER_ID):
                    names.append(s.get("name") or s.get("url") or f"id:{s.get('id')}")
            except Exception as e:
                logger.exception(
                    "get_streams_processed_names: erro ao decidir processamento para stream id=%s name=%s: %s",
                    s.get("id"),
                    s.get("name"),
                    e,
                )

        logger.info(
            "get_streams_processed_names: total_streams=%d, selecionados=%d",
            total_streams,
            len(names),
        )
        return names
    except Exception as e:
        logger.exception("get_streams_processed_names: erro inesperado: %s", e)
        return []


def get_recent_errors(max_entries: int = 5, tail_lines: int = 400) -> list:
    """
    LÃª o arquivo de log e extrai atÃ© 'max_entries' erros mais recentes (ERROR/CRITICAL).
    tail_lines: nÃºmero de linhas finais do arquivo a analisar (heurÃ­stica para ser leve).
    Retorna lista de dicts: [{"timestamp": str, "level": str, "message": str}, ...]
    """
    results = []
    try:
        path = SERVER_LOG_FILE  # jÃ¡ definido no topo como 'log.txt'
        if not os.path.exists(path):
            return results

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-tail_lines:]

        # Formato do formatter: '%(asctime)s %(levelname)s: [%(threadName)s] %(message)s'
        for line in reversed(lines):
            # Pegamos os nÃ­veis de severidade tipicamente usados
            if " ERROR:" in line or " CRITICAL:" in line:
                # Tente extrair as partes, mas deixe robusto
                # Ex: "2025-08-16 10:01:23,123 ERROR: [ThreadX] Mensagem"
                try:
                    # timestamp = inÃ­cio atÃ© o primeiro " "
                    # nÃ­vel = depois do espaÃ§o atÃ© ":"
                    # mensagem = depois de "] "
                    parts = line.strip().split(" ", 2)
                    if len(parts) >= 3:
                        ts = f"{parts[0]} {parts[1].rstrip(':')}".strip()
                        rest = parts[2]
                    else:
                        ts = ""
                        rest = line.strip()

                    level = "ERROR" if " ERROR:" in line else "CRITICAL"
                    # Tente eliminar o prefixo "[thread] "
                    msg = rest
                    brk = rest.find("] ")
                    if brk != -1:
                        msg = rest[brk + 2 :]
                    # Limite mÃ¡ximo de mensagens coletadas
                    results.append({"timestamp": ts, "level": level, "message": msg})
                    if len(results) >= max_entries:
                        break
                except Exception:
                    # Se parsing falhar, empilha simples
                    results.append({"timestamp": "", "level": "ERROR", "message": line.strip()})
                    if len(results) >= max_entries:
                        break
    except Exception:
        # Silenciosamente ignore
        return results
    return results
# === FIM: Helpers para Dashboard ===

# Estado conhecido de servidores online (para detecÃ§Ã£o de mudanÃ§as)
_last_known_online_servers = []

# FunÃ§Ã£o para obter servidores online baseado em heartbeats
async def get_online_server_ids(force_refresh=False):
    """
    Consulta a tabela server_heartbeats para obter lista de servidores online.
    Retorna lista de server_ids que estÃ£o com status 'ONLINE' e heartbeat recente.
    Se force_refresh=True, ignora o cache.
    """
    global _last_dynamic_check, _cached_online_servers

    current_time = time.time()
    # Usar cache se permitido e ainda vÃ¡lido
    if not force_refresh and (current_time - _last_dynamic_check < DYNAMIC_CACHE_TTL) and _cached_online_servers:
        return _cached_online_servers

    try:
        async def db_get_online_servers():
            _conn = await connect_db()
            if not _conn:
                logger.warning("get_online_server_ids: NÃ£o foi possÃ­vel conectar ao DB. Usando configuraÃ§Ã£o estÃ¡tica.")
                return [SERVER_ID]  # Fallback para servidor atual

            try:
                with _conn.cursor() as cursor:
                    # Verificar se tabela existe
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'server_heartbeats'
                        );
                    """)
                    if not cursor.fetchone()[0]:
                        logger.debug("get_online_server_ids: Tabela heartbeats nÃ£o existe. Usando configuraÃ§Ã£o estÃ¡tica.")
                        return [SERVER_ID]

                    # Obter servidores online
                    cursor.execute("""
                        SELECT server_id 
                        FROM server_heartbeats 
                        WHERE status = 'ONLINE' 
                        AND last_heartbeat > NOW() - INTERVAL '%s seconds'
                        ORDER BY server_id;
                    """, (OFFLINE_THRESHOLD_SECS,))
                    rows = cursor.fetchall()
                    online = [row[0] for row in rows] if rows else []
                    return online or [SERVER_ID]
            except Exception as db_err:
                logger.error(f"Erro DB em get_online_server_ids: {db_err}")
                return [SERVER_ID]  # Fallback
            finally:
                try:
                    _conn.close()
                except Exception as close_err:
                    logger.error(f"Erro ao fechar conexÃ£o em get_online_server_ids (inner): {close_err}")

        # Executa a consulta e obtÃ©m diretamente a lista de servidores online
        online_servers = await db_get_online_servers()

        # Atualizar cache
        _cached_online_servers = online_servers
        _last_dynamic_check = current_time

        logger.debug(f"get_online_server_ids: Servidores online: {online_servers}")
        return online_servers

    except Exception as e:
        logger.error(f"Erro ao obter servidores online: {e}")
        return [SERVER_ID]  # Fallback para servidor atual

# FunÃ§Ã£o para obter nÃºmero de servidores ativos dinamicamente
async def get_active_servers_count():
    """
    Retorna o nÃºmero de servidores atualmente online e ativos.
    Se nÃ£o conseguir determinar dinamicamente, retorna TOTAL_SERVERS estÃ¡tico.
    """
    global _cached_active_servers_count

    try:
        online_servers = await get_online_server_ids()
        active_count = len(online_servers)

        # ValidaÃ§Ã£o: pelo menos 1 servidor (o atual) deve estar ativo
        if active_count < 1:
            logger.warning("get_active_servers_count: Nenhum servidor detectado como online. Usando fallback.")
            active_count = 1

        _cached_active_servers_count = active_count
        logger.debug(f"get_active_servers_count: {active_count} servidores ativos detectados")
        return active_count

    except Exception as e:
        logger.error(f"Erro ao obter contagem de servidores ativos: {e}")
        # Fallback para configuraÃ§Ã£o estÃ¡tica
        return TOTAL_SERVERS

# FunÃ§Ã£o auxiliar: aguardar rebalanceamento ou timeout
async def wait_for_rebalance_or_timeout(timeout_secs: int):
    """
    Aguarda atÃ© o REBALANCE_EVENT ser disparado ou atÃ© atingir timeout.
    NÃ£o limpa o evento global aqui (limpeza centralizada no watcher).
    """
    try:
        await asyncio.wait_for(REBALANCE_EVENT.wait(), timeout=timeout_secs)
    except asyncio.TimeoutError:
        pass

# Watcher de servidores online que dispara o gatilho de rebalanceamento
async def monitor_online_servers(poll_interval_secs: int = 30):
    """
    Observa a lista de servidores online ignorando cache, e dispara rebalanceamento
    quando detectar mudanÃ§as (entrada/saÃ­da de servidores).
    """
    global _last_known_online_servers, _cached_active_servers_count, _cached_online_servers, _last_dynamic_check
    # Inicializar estado conhecido
    try:
        _last_known_online_servers = await get_online_server_ids(force_refresh=True)
    except Exception:
        _last_known_online_servers = [SERVER_ID]
    
    logger.info(
        f"monitor_online_servers: inicial online={_last_known_online_servers} "
        f"(poll={poll_interval_secs}s)"
    )
    
    while True:
        try:
            online_now = await get_online_server_ids(force_refresh=True)
            if set(online_now) != set(_last_known_online_servers):
                logger.info(
                    f"Rebalanceamento: mudanÃ§a detectada na lista de servidores online. "
                    f"antes={_last_known_online_servers} agora={online_now}"
                )
                # Atualiza caches imediata/explicitamente
                _cached_active_servers_count = max(1, len(online_now))
                # Dispara o evento para acordar as corrotinas
                REBALANCE_EVENT.set()
                
                # Atualiza o estado conhecido e o cache
                _last_known_online_servers = online_now
                # Manter o cache interno coerente com a mudanÃ§a
                _cached_online_servers = online_now
                _last_dynamic_check = time.time()
                
                # Pequena janela para todas as tasks acordarem
                await asyncio.sleep(1)
                # Limpar o evento para permitir novos rebalanceamentos futuros
                REBALANCE_EVENT.clear()
        except Exception as e:
            logger.error(f"monitor_online_servers: erro ao monitorar servidores online: {e}")
        
        await asyncio.sleep(poll_interval_secs)

# FunÃ§Ã£o para calcular se um stream deve ser processado por este servidor (dinÃ¢mico)
async def should_process_stream_dynamic(stream_index, server_id, online_servers=None):
    """
    Determina se um stream deve ser processado por este servidor baseado na distribuiÃ§Ã£o dinÃ¢mica.
    """
    if not DISTRIBUTE_LOAD:
        return True
    
    try:
        # Durante um rebalanceamento, forÃ§ar refresh da lista de online
        if online_servers is None:
            if REBALANCE_EVENT.is_set():
                online_servers = await get_online_server_ids(force_refresh=True)
            else:
                online_servers = await get_online_server_ids()
        
        # Se nÃ£o hÃ¡ servidores online ou apenas este servidor
        if not online_servers or len(online_servers) == 1:
            return True
        
        # Verificar se o servidor atual estÃ¡ na lista de online
        if server_id not in online_servers:
            logger.warning(f"Servidor atual ({server_id}) nÃ£o estÃ¡ na lista de servidores online: {online_servers}")
            return True  # Processar por seguranÃ§a
        
        # DistribuiÃ§Ã£o por mÃ³dulo baseada apenas em servidores online
        online_servers_sorted = sorted(online_servers)
        server_position = online_servers_sorted.index(server_id)
        total_online = len(online_servers_sorted)
        
        should_process = (int(stream_index) % total_online) == server_position
        
        logger.debug(
            f"should_process_stream_dynamic: stream_index={stream_index}, "
            f"server_id={server_id}, position={server_position}, "
            f"total_online={total_online}, should_process={should_process}"
        )
        
        return should_process
        
    except Exception as e:
        logger.error(f"Erro em should_process_stream_dynamic: {e}")
        # Fallback para lÃ³gica estÃ¡tica
        effective_id = EFFECTIVE_SERVER_ID if server_id == SERVER_ID else server_id
        return (int(stream_index) % TOTAL_SERVERS) == (effective_id - 1)

# FunÃ§Ã£o principal para processar todos os streams
async def main():
    logger.debug("Iniciando a funÃ§Ã£o main()")
    logger.info(f"ConfiguraÃ§Ãµes de distribuiÃ§Ã£o carregadas do .env: SERVER_ID={SERVER_ID}, TOTAL_SERVERS={TOTAL_SERVERS}")
    logger.info(f"DistribuiÃ§Ã£o de carga: {DISTRIBUTE_LOAD}, RotaÃ§Ã£o: {ENABLE_ROTATION}, Horas de rotaÃ§Ã£o: {ROTATION_HOURS}")
    
    # Verificar se a tabela de logs existe e criar se necessÃ¡rio
    try:
        table_ok = await check_log_table()
        if not table_ok:
            logger.warning("A verificaÃ§Ã£o/criaÃ§Ã£o da tabela de logs falhou. Tentando prosseguir mesmo assim, mas podem ocorrer erros.")
    except Exception as e_check_table:
         logger.error(f"Erro ao executar check_log_table: {e_check_table}")
         logger.warning("Prosseguindo sem verificaÃ§Ã£o da tabela de logs.")

    # Criar instÃ¢ncia do Shazam para reconhecimento
    shazam = Shazam()
    
    global STREAMS
    STREAMS = await load_streams()
    
    if not STREAMS:
        logger.error("NÃ£o foi possÃ­vel carregar os streamings. Verifique a configuraÃ§Ã£o do banco de dados ou o arquivo JSON local.")
        sys.exit(1)
        
    last_songs = load_last_songs()
    tasks = []
    
    # Inicializar fila para processamento
    global shazam_queue
    shazam_queue = asyncio.Queue(maxsize=100)  # Limitar tamanho da fila para evitar uso excessivo de memÃ³ria
    
    # Registrar informaÃ§Ãµes sobre a distribuiÃ§Ã£o de carga
    if DISTRIBUTE_LOAD:
        logger.info(f"Modo de distribuiÃ§Ã£o de carga DINÃ‚MICA ativado: Servidor {SERVER_ID}")
        logger.info(f"TOTAL_SERVERS estÃ¡tico configurado: {TOTAL_SERVERS}")
        
        # Obter informaÃ§Ãµes dinÃ¢micas de servidores
        try:
            online_servers = await get_online_server_ids()
            active_count = len(online_servers)
            logger.info(f"Servidores online detectados: {online_servers} (total: {active_count})")

            # VALIDAÃ‡ÃƒO CRÃTICA: Alertar sobre discrepÃ¢ncia entre configuraÃ§Ã£o e realidade
            if active_count != TOTAL_SERVERS:
                logger.warning("=" * 80)
                logger.warning("DISCREPÃ‚NCIA CRÃTICA DETECTADA:")
                logger.warning(f"TOTAL_SERVERS configurado: {TOTAL_SERVERS}")
                logger.warning(f"Servidores realmente online: {active_count} ({online_servers})")
                logger.warning("Esta discrepÃ¢ncia pode causar distribuiÃ§Ã£o de carga inadequada!")
                logger.warning("RecomendaÃ§Ã£o: Verifique se todos os servidores estÃ£o funcionando ou")
                logger.warning(f"ajuste TOTAL_SERVERS para {active_count} no arquivo .env")
                logger.warning("=" * 80)

        except Exception as e:
            logger.error(f"Erro ao obter servidores online: {e}")
            online_servers = [SERVER_ID]
            active_count = 1
            logger.warning(f"Fallback: Assumindo apenas este servidor ({SERVER_ID}) estÃ¡ online")
        
        if ENABLE_ROTATION:
            logger.info(f"RotaÃ§Ã£o de rÃ¡dios ativada: a cada {ROTATION_HOURS} horas")
            rotation_offset = calculate_rotation_offset()
            logger.info(f"Offset de rotaÃ§Ã£o atual: {rotation_offset}")
        
        # Calcular e exibir quantos streams cada servidor estÃ¡ processando (dinÃ¢mico)
        streams_per_server = {}
        total_streams = len(STREAMS)
        
        try:
            for server_id in online_servers:
                streams_for_this_server = 0
                for stream in STREAMS:
                    stream_index = stream.get('index', 0)
                    if await should_process_stream_dynamic(stream_index, server_id, online_servers):
                        streams_for_this_server += 1
                streams_per_server[server_id] = streams_for_this_server
        except Exception as calc_err:
            logger.error(f"Erro ao calcular distribuiÃ§Ã£o dinÃ¢mica: {calc_err}")
            # Fallback para lÃ³gica estÃ¡tica
            for i in range(1, TOTAL_SERVERS + 1):
                effective_id = EFFECTIVE_SERVER_ID if i == SERVER_ID else i
                streams_for_this_server = len([s for s in STREAMS if s.get('processed_by_server', 
                                                                          (int(s.get('index', 0)) % TOTAL_SERVERS) == (effective_id - 1))])
                streams_per_server[i] = streams_for_this_server
            
        logger.info(f"DistribuiÃ§Ã£o DINÃ‚MICA de streams por servidor: {streams_per_server}")
        logger.info(f"Este servidor ({SERVER_ID}) processarÃ¡ {streams_per_server.get(SERVER_ID, 0)} de {total_streams} streams")
        
        # Informar sobre diferenÃ§as entre configuraÃ§Ã£o estÃ¡tica e dinÃ¢mica
        static_streams_for_current = len([s for s in STREAMS if (int(s.get('index', 0)) % TOTAL_SERVERS) == (EFFECTIVE_SERVER_ID - 1)])
        dynamic_streams_for_current = streams_per_server.get(SERVER_ID, 0)
        if static_streams_for_current != dynamic_streams_for_current:
            logger.info(f"DIFERENÃ‡A DETECTADA: ConfiguraÃ§Ã£o estÃ¡tica processaria {static_streams_for_current} streams, "
                       f"distribuiÃ§Ã£o dinÃ¢mica processarÃ¡ {dynamic_streams_for_current} streams")
    else:
        logger.info("Modo de distribuiÃ§Ã£o de carga desativado. Processando todos os streams.")

    async def reload_streams():
        global STREAMS
        STREAMS = await load_streams()
        logger.info("Streams recarregados.")
        if 'update_streams_in_db' in globals():
            update_streams_in_db(STREAMS)  # Atualiza o banco de dados com as rÃ¡dios do arquivo
        # Cancelar todas as tarefas existentes
        for task in tasks:
            if not task.done():
                task.cancel()
        # Criar novas tarefas para os streams recarregados
        tasks.clear()
        # Apenas adicionar tarefas para streams que devem ser processados por este servidor
        for stream in STREAMS:
            task = asyncio.create_task(process_stream(stream, last_songs))
            register_task(task)  # Registrar para controle de finalizaÃ§Ã£o
            tasks.append(task)
        logger.info(f"{len(tasks)} tasks criadas para os novos streams.")

    # Iniciar heartbeat IMEDIATAMENTE apÃ³s carregar streams
    if DISTRIBUTE_LOAD:
        logger.info("Iniciando heartbeat imediato para registro no Redis...")
        try:
            # Enviar heartbeat inicial antes de qualquer task
            await send_heartbeat()
        except Exception as e:
            logger.error(f"Falha no heartbeat inicial: {e}")
    
    # Criar e registrar todas as tarefas necessÃ¡rias
    async def reload_streams_wrapper():
        await reload_streams()
    
    monitor_task = register_task(asyncio.create_task(monitor_streams_file(reload_streams_wrapper)))
    logger.info(f"Iniciando pool de {NUM_SHAZAM_WORKERS} workers de identificaÃ§Ã£o do Shazam...")
    shazam_workers = []
    for _ in range(NUM_SHAZAM_WORKERS):
        worker_task = asyncio.create_task(identify_song_shazamio(shazam))
        register_task(worker_task)
        shazam_workers.append(worker_task)
    shutdown_monitor_task = register_task(asyncio.create_task(monitor_shutdown()))
    
    # Adicionar tarefas de heartbeat e monitoramento de servidores
    heartbeat_task = register_task(asyncio.create_task(heartbeat_loop()))
    server_monitor_task = register_task(asyncio.create_task(check_servers_status()))
    
    # Iniciar watcher de servidores online APÃ“S heartbeat inicial
    if DISTRIBUTE_LOAD:
        try:
            if REDIS_URL:
                # Pequeno delay para garantir que o heartbeat inicial foi enviado
                await asyncio.sleep(1)
                online_servers_watcher_task = register_task(
                    asyncio.create_task(watch_online_servers_redis(poll_interval_secs=5))
                )
                logger.info("Watcher de servidores online via Redis iniciado (tempo real, prefixo smf:).")
            else:
                online_servers_watcher_task = register_task(
                    asyncio.create_task(monitor_online_servers(poll_interval_secs=30))
                )
                logger.info("Watcher de servidores online iniciado (poll=30s via DB).")
        except Exception as e:
            logger.error(f"Falha ao iniciar watcher de servidores online: {e}")
    
    if 'send_data_to_db' in globals():
        send_data_task = register_task(asyncio.create_task(send_data_to_db()))
        tasks_to_gather = [monitor_task, shutdown_monitor_task, heartbeat_task, server_monitor_task]
        tasks_to_gather.extend(shazam_workers)
        tasks_to_gather.append(send_data_task)
    else:
        tasks_to_gather = [monitor_task, shutdown_monitor_task, heartbeat_task, server_monitor_task]
        tasks_to_gather.extend(shazam_workers)
    
    # Adicionar o watcher de servidores online Ã s tarefas se foi iniciado
    if DISTRIBUTE_LOAD and 'online_servers_watcher_task' in locals():
        tasks_to_gather.append(online_servers_watcher_task)
    
    alert_task = register_task(asyncio.create_task(check_and_alert_persistent_errors()))
    json_sync_task = register_task(asyncio.create_task(schedule_json_sync()))
    
    tasks_to_gather.extend([alert_task, json_sync_task])
    
    # Adicionar tarefa para verificar a rotaÃ§Ã£o de streams
    if DISTRIBUTE_LOAD and ENABLE_ROTATION:
        rotation_task = register_task(asyncio.create_task(check_rotation_schedule()))
        tasks.append(rotation_task)
    
    # Adicionar tarefas para processar os streams
    for stream in STREAMS:
        stream_task = register_task(asyncio.create_task(process_stream(stream, last_songs)))
        tasks.append(stream_task)
    
    tasks_to_gather.extend(tasks)
    
    try:
        await asyncio.gather(*tasks_to_gather, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("Tarefas principais canceladas devido ao encerramento do programa.")
    except Exception as e:
        logger.error(f"Erro durante execuÃ§Ã£o principal: {e}")
    finally:
        logger.info("Finalizando aplicaÃ§Ã£o...")

def stop_and_restart():
    """FunÃ§Ã£o para parar e reiniciar o script."""
    logger.info("Reiniciando o script...")
    os.execv(sys.executable, ['python'] + sys.argv)

# FunÃ§Ã£o de loop para enviar heartbeats periodicamente
async def heartbeat_loop():
    """Envia heartbeats periÃ³dicos para o banco de dados."""
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECS)
            await send_heartbeat()
        except Exception as e:
            logger.error(f"Erro no loop de heartbeat: {e}")

# Ponto de entrada
if __name__ == '__main__':
    # Configurar temporizador para reinÃ­cio a cada 30 minutos
    schedule.every(30).minutes.do(stop_and_restart)

    # Iniciar thread para verificar o schedule
    def run_schedule():
        while True:
            try: # try precisa do bloco indentado
                schedule.run_pending()
            except Exception as e:
                logger.error(f"Erro no thread de schedule: {e}")
            # Mover sleep para fora do try/except para sempre ocorrer
            time.sleep(60)  # Verificar a cada minuto
        
    schedule_thread = threading.Thread(target=run_schedule)
    schedule_thread.daemon = True  # Thread serÃ¡ encerrada quando o programa principal terminar
    schedule_thread.start()

    # Bloco try/except/finally principal corretamente indentado
    try:
        # Executar o loop principal
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Programa interrompido pelo usuÃ¡rio (KeyboardInterrupt)")
        shutdown_event.set() # Aciona o evento de shutdown
    except Exception as e:
        logger.critical(f"Erro crÃ­tico: {e}", exc_info=True)
        shutdown_event.set() # Aciona o evento de shutdown em caso de erro crÃ­tico
        
        # Enviar e-mail de alerta para erro crÃ­tico
        try:
            subject = "Erro CrÃ­tico no Servidor de IdentificaÃ§Ã£o"
            body = f"O servidor {SERVER_ID} encontrou um erro crÃ­tico e precisou ser encerrado.\n\nErro: {e}\n\nPor favor, verifique os logs para mais detalhes."
            send_email_alert(subject, body)
        except Exception as email_err:
            logger.error(f"NÃ£o foi possÃ­vel enviar e-mail de alerta para erro crÃ­tico: {email_err}")
    finally:
        logger.info("AplicaÃ§Ã£o encerrando...")
        # Garantir que todas as tarefas sejam canceladas no encerramento
        if 'active_tasks' in globals() and active_tasks:
            logger.info(f"Tentando cancelar {len(active_tasks)} tarefas ativas...")
            # Aciona o evento de shutdown novamente para garantir que o monitor o veja
            shutdown_event.set() 
            # Aguarda um pouco para o monitor_shutdown iniciar o cancelamento
            time.sleep(1)
            
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.info("Nenhum loop de eventos em execuÃ§Ã£o para cancelar tarefas.")

            if loop and not loop.is_closed():
                # Dar tempo para as tarefas serem canceladas
                # A funÃ§Ã£o monitor_shutdown jÃ¡ aguarda asyncio.wait
                # Apenas esperamos que ela termine (ou timeout)
                for task in active_tasks: # IndentaÃ§Ã£o correta do for loop
                    if not task.done():
                        task.cancel()
                try: # try/except corretamente indentado
                    # Espera por um tempo curto para o cancelamento ocorrer
                    # NÃ£o usar loop.run_until_complete aqui pois o loop principal jÃ¡ foi encerrado
                    # e pode causar erros
                    # Basta confiar que as tarefas foram sinalizadas para cancelar
                    logger.info("Tarefas sinalizadas para cancelamento.")
                except asyncio.CancelledError:
                    logger.info("Cancelamento durante a finalizaÃ§Ã£o.")
                except Exception as e:
                    logger.error(f"Erro ao finalizar tarefas pendentes: {e}")
            else:
                 logger.info("Loop de eventos nÃ£o estÃ¡ ativo ou fechado, pulando cancelamento de tarefas.")
        
        # Fechar conexÃ£o Redis ao finalizar
        if _redis_client:
            try:
                asyncio.run(_redis_client.aclose())
                logger.info("ConexÃ£o Redis fechada.")
            except Exception as redis_close_err:
                logger.error(f"Erro ao fechar conexÃ£o Redis: {redis_close_err}")
                 
        logger.info("AplicaÃ§Ã£o encerrada.")
        sys.exit(0)
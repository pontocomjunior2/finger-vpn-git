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
import datetime as dt # Usar alias para evitar conflito com variável datetime
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    # O logger já está configurado aqui
    logger.critical("Biblioteca pytz não encontrada. O tratamento de fuso horário falhará. Instale com: pip install pytz")
    # Considerar sair se pytz for essencial
    # sys.exit(1)
import psycopg2.errors # Para capturar UniqueViolation

# Definir diretório de segmentos global
SEGMENTS_DIR = os.getenv('SEGMENTS_DIR', 'C:/DATARADIO/segments')

# Configurar logging para console e arquivo (MOVIDO PARA CIMA)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Formato de log
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler com limpeza a cada 6 horas
SERVER_LOG_FILE = 'log.txt' # Definir nome do arquivo de log aqui
file_handler = TimedRotatingFileHandler(SERVER_LOG_FILE, when='H', interval=6, backupCount=1)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
# --- Fim da configuração do Logger ---

# Verificar e criar o diretório de segmentos
if not os.path.exists(SEGMENTS_DIR):
    try:
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        print(f"Diretório de segmentos criado: {SEGMENTS_DIR}")
    except Exception as e:
        print(f"ERRO: Não foi possível criar o diretório de segmentos: {e}")
        # Usar um diretório alternativo se o principal falhar
        SEGMENTS_DIR = './segments'
        os.makedirs(SEGMENTS_DIR, exist_ok=True)
        print(f"Usando diretório alternativo: {SEGMENTS_DIR}")

# Tentar importar psutil, necessário para o heartbeat
try:
    import psutil
except ImportError:
    print("Pacote 'psutil' não encontrado. Execute 'pip install psutil' para habilitar monitoramento completo.")
    
    # Stub de classe para psutil se não estiver instalado
    class PsutilStub:
        def virtual_memory(self): return type('obj', (object,), {'percent': 0, 'available': 0})
        def cpu_percent(self, interval=0): return 0
        def disk_usage(self, path): return type('obj', (object,), {'percent': 0, 'free': 0})
    
    psutil = PsutilStub()

# Importações para (S)FTP
from ftplib import FTP
try:
    import pysftp
    from pysftp import CnOpts as pysftpCnOpts # Importar CnOpts explicitamente
    HAS_PYSFTP = True
except ImportError:
    HAS_PYSFTP = False
    logger.warning("Pacote 'pysftp' não encontrado. O failover SFTP não funcionará. Instale com 'pip install pysftp'.")
    pysftpCnOpts = None # Definir como None se pysftp não estiver disponível
    # Considerar logar um aviso se SFTP for o método escolhido

# Carregar variáveis de ambiente
load_dotenv()

# Configuração para distribuição de carga entre servidores
SERVER_ID = int(os.getenv('SERVER_ID', '1'))  # ID único para cada servidor (convertido para inteiro)
TOTAL_SERVERS = int(os.getenv('TOTAL_SERVERS', '1'))  # Número total de servidores
DISTRIBUTE_LOAD = os.getenv('DISTRIBUTE_LOAD', 'False').lower() == 'true'  # Ativar distribuição
ROTATION_HOURS = int(os.getenv('ROTATION_HOURS', '24'))  # Horas para rotação de rádios (padrão: 24h)
ENABLE_ROTATION = os.getenv('ENABLE_ROTATION', 'False').lower() == 'true'  # Ativar rodízio de rádios

# Validar SERVER_ID
if DISTRIBUTE_LOAD and (SERVER_ID < 1 or SERVER_ID > TOTAL_SERVERS):
    print(f"AVISO: SERVER_ID inválido ({SERVER_ID}). Deve estar entre 1 e {TOTAL_SERVERS}.")
    print(f"Ajustando SERVER_ID para 1 automaticamente.")
    SERVER_ID = 1  # Ajustar automaticamente para um valor válido em vez de processar todos os streams

# Configurações para identificação e verificação de duplicatas
IDENTIFICATION_DURATION = int(os.getenv('IDENTIFICATION_DURATION', '15'))  # Duração da captura em segundos
DUPLICATE_PREVENTION_WINDOW_SECONDS = int(os.getenv('DUPLICATE_PREVENTION_WINDOW_SECONDS', '900')) # Nova janela de 15 min

# Configurações do banco de dados PostgreSQL
DB_HOST = os.getenv('POSTGRES_HOST')  # Removido default para forçar configuração
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')
DB_NAME = os.getenv('POSTGRES_DB')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_TABLE_NAME = os.getenv('DB_TABLE_NAME', 'music_log')

# Registrar a tabela que está sendo usada
print(f"Configuração da tabela de destino: DB_TABLE_NAME={DB_TABLE_NAME}")

# Configurações de Failover (S)FTP
ENABLE_FAILOVER_SEND = os.getenv('ENABLE_FAILOVER_SEND', 'False').lower() == 'true'
FAILOVER_METHOD = os.getenv('FAILOVER_METHOD', 'SFTP').upper()  # Carrega método
FAILOVER_HOST = os.getenv('FAILOVER_HOST')
_failover_port_str = os.getenv('FAILOVER_PORT')
FAILOVER_PORT = int(_failover_port_str) if _failover_port_str and _failover_port_str.isdigit() else (22 if FAILOVER_METHOD == 'SFTP' else 21)
FAILOVER_USER = os.getenv('FAILOVER_USER')
FAILOVER_PASSWORD = os.getenv('FAILOVER_PASSWORD')
FAILOVER_REMOTE_DIR = os.getenv('FAILOVER_REMOTE_DIR')
FAILOVER_SSH_KEY_PATH = os.getenv('FAILOVER_SSH_KEY_PATH')  # Pode ser None

# Caminho para o arquivo JSON contendo os streamings
STREAMS_FILE = 'streams.json'
# Caminho para o arquivo JSON que armazenará o estado das últimas músicas identificadas
LAST_SONGS_FILE = 'last_songs.json'
# Caminho para o arquivo de log local
LOCAL_LOG_FILE = 'local_log.json'

# Configurações para o sistema de alerta por e-mail
ALERT_EMAIL = os.getenv('ALERT_EMAIL', "junior@pontocomaudio.net")
ALERT_EMAIL_PASSWORD = os.getenv('ALERT_EMAIL_PASSWORD', "conquista")
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', "junior@pontocomaudio.net")

# Configurar logging para console e arquivo (REMOVIDO DAQUI)

# Registrar informações sobre as variáveis de ambiente carregadas
logger.info("=== Iniciando script com as seguintes configurações ===")
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
logger.info("======================================================")

# --- Função para Envio de Arquivo via Failover (FTP/SFTP) ---
async def send_file_via_failover(local_file_path, stream_index):
    """Envia um arquivo para o servidor de failover configurado (FTP ou SFTP)."""
    if not ENABLE_FAILOVER_SEND:
        logger.debug("Envio para failover desabilitado nas configurações.")
        return

    if not all([FAILOVER_HOST, FAILOVER_USER, FAILOVER_PASSWORD, FAILOVER_REMOTE_DIR]):
        logger.error("Configurações de failover incompletas no .env. Impossível enviar arquivo.")
        return

    if stream_index is None:
        logger.error("Índice do stream não fornecido. Não é possível nomear o arquivo de failover.")
        return

    # Criar um nome de arquivo único no servidor remoto
    timestamp_str = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    remote_filename = f"{stream_index}_{timestamp_str}_{os.path.basename(local_file_path)}"
    # Usar os.path.join e depois replace para garantir compatibilidade entre OS no caminho remoto
    remote_path = os.path.join(FAILOVER_REMOTE_DIR, remote_filename).replace("\\", "/")

    logger.info(f"Tentando enviar {local_file_path} para failover via {FAILOVER_METHOD} em {FAILOVER_HOST}:{FAILOVER_PORT}")
    logger.debug(f"Caminho remoto: {remote_path}")

    try:
        if FAILOVER_METHOD == 'SFTP':
            if not HAS_PYSFTP:
                logger.error("SFTP selecionado, mas a biblioteca pysftp não está instalada.")
                return

            cnopts = pysftpCnOpts()
            # Ignorar verificação da chave do host (menos seguro, mas evita problemas de configuração inicial)
            # Considere configurar known_hosts para produção
            cnopts.hostkeys = None

            # Definir kwargs para conexão SFTP
            sftp_kwargs = {
                'host': FAILOVER_HOST,
                'port': FAILOVER_PORT,
                'username': FAILOVER_USER,
                'cnopts': cnopts
            }
            if FAILOVER_SSH_KEY_PATH and os.path.exists(FAILOVER_SSH_KEY_PATH):
                sftp_kwargs['private_key'] = FAILOVER_SSH_KEY_PATH
                sftp_kwargs['private_key_pass'] = FAILOVER_PASSWORD # Senha da chave, se houver
                logger.debug("Usando chave SSH para autenticação SFTP.")
            else:
                sftp_kwargs['password'] = FAILOVER_PASSWORD
                logger.debug("Usando senha para autenticação SFTP.")

            # Usar asyncio.to_thread para a operação sftp bloqueante
            await asyncio.to_thread(_sftp_upload_sync, sftp_kwargs, local_file_path, remote_path)

        elif FAILOVER_METHOD == 'FTP':
            # Usar asyncio.to_thread para operações de FTP bloqueantes
            await asyncio.to_thread(_ftp_upload_sync, local_file_path, remote_path)

        else:
            logger.error(f"Método de failover desconhecido: {FAILOVER_METHOD}. Use 'FTP' ou 'SFTP'.")

    except Exception as e:
        logger.error(f"Erro ao enviar arquivo via {FAILOVER_METHOD} para {FAILOVER_HOST}: {e}", exc_info=True)

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
                  logger.warning(f"Não foi possível criar/verificar diretório SFTP {remote_dir}: {e}")

        sftp.put(local_file_path, remote_path)
        logger.info(f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via SFTP para {remote_dir}")

# Função auxiliar bloqueante para FTP (para ser usada com asyncio.to_thread)
def _ftp_upload_sync(local_file_path, remote_path):
    ftp = None
    try:
        ftp = FTP()
        ftp.connect(FAILOVER_HOST, FAILOVER_PORT, timeout=30) # Timeout de 30s
        ftp.login(FAILOVER_USER, FAILOVER_PASSWORD)
        logger.info(f"Conectado ao FTP: {FAILOVER_HOST}")

        # Tentar criar diretórios recursivamente (simples)
        remote_dir = os.path.dirname(remote_path)
        dirs_to_create = remote_dir.strip('/').split('/') # Remover barras inicial/final e dividir
        current_dir = ''
        for d in dirs_to_create:
            if not d: continue
            current_dir = f'{current_dir}/{d}' if current_dir else f'/{d}' # Construir caminho absoluto
            try:
                ftp.mkd(current_dir)
                logger.debug(f"Diretório FTP criado: {current_dir}")
            except error_perm as e:
                if not e.args[0].startswith('550'): # Ignorar erro "já existe" ou "permissão negada" (pode já existir)
                    logger.warning(f"Não foi possível criar diretório FTP {current_dir}: {e}")
                # else:
                #     logger.debug(f"Diretório FTP já existe ou permissão negada para criar: {current_dir}")

        # Mudar para o diretório final (se existir)
        try:
            ftp.cwd(remote_dir)
            logger.debug(f"Mudado para diretório FTP: {remote_dir}")
        except error_perm as e:
            logger.error(f"Não foi possível mudar para o diretório FTP {remote_dir}: {e}. Upload pode falhar.")
            # Considerar lançar o erro ou retornar se o diretório é essencial
            # raise # Re-lança o erro se não conseguir mudar para o diretório
            return # Ou simplesmente retorna se não conseguir mudar

        with open(local_file_path, 'rb') as fp:
            ftp.storbinary(f'STOR {os.path.basename(remote_path)}', fp)
        logger.info(f"Arquivo {os.path.basename(remote_path)} enviado com sucesso via FTP para {remote_dir}")

    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass # Ignorar erros ao fechar

# --- Fim das Funções de Failover ---

# Verificar se a tabela de logs existe (RESTAURADO)
def check_log_table():
    logger.info(f"Verificando se a tabela de logs '{DB_TABLE_NAME}' existe no banco de dados...")
    conn = None # Initialize conn to None
    try:
        conn = connect_db()
        if not conn:
            logger.error("Não foi possível conectar ao banco de dados para verificar a tabela de logs.")
            return False

        with conn.cursor() as cursor:
            # Verificar se a tabela existe
            cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{DB_TABLE_NAME}')")
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                logger.error(f"A tabela de logs '{DB_TABLE_NAME}' não existe no banco de dados!")
                # Listar tabelas disponíveis
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                tables = [row[0] for row in cursor.fetchall()]
                logger.info(f"Tabelas disponíveis no banco: {tables}")

                # Criar tabela automaticamente para evitar erros
                try:
                    logger.info(f"Tentando criar a tabela '{DB_TABLE_NAME}' automaticamente...")
                    # Corrigir a formatação da string SQL multi-linha
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
                # Verificar as colunas da tabela (garantir indentação correta aqui)
                cursor.execute(f"SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = '{DB_TABLE_NAME}'")
                columns_info = {row[0].lower(): {'type': row[1], 'default': row[2]} for row in cursor.fetchall()}
                logger.info(f"Tabela '{DB_TABLE_NAME}' existe com as seguintes colunas: {list(columns_info.keys())}")
                columns = list(columns_info.keys())

                # --- Ajuste da coluna 'identified_by' --- (garantir indentação correta)
                col_identified_by = 'identified_by'

                if col_identified_by in columns:
                    # (Lógica interna do if permanece a mesma, verificar indentação)
                    # ... (código existente dentro do if col_identified_by...)
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
                     # (Lógica interna do else permanece a mesma, verificar indentação)
                    # ... (código existente dentro do else para adicionar coluna) ...
                    try:
                        logger.info(f"Adicionando coluna '{col_identified_by}' (VARCHAR(10)) à tabela '{DB_TABLE_NAME}'...")
                        add_sql = f"ALTER TABLE {DB_TABLE_NAME} ADD COLUMN {col_identified_by} VARCHAR(10);"
                        cursor.execute(add_sql)
                        conn.commit()
                        logger.info(f"Coluna '{col_identified_by}' adicionada com sucesso.")
                        columns.append(col_identified_by) # Adiciona à lista local
                    except Exception as e:
                        logger.error(f"Erro ao adicionar coluna '{col_identified_by}': {e}")
                        conn.rollback()

                # --- Remoção da coluna 'identified_by_server' --- (garantir indentação correta)
                col_to_remove = 'identified_by_server'
                if col_to_remove in columns:
                    # (Lógica interna do if permanece a mesma, verificar indentação)
                    # ... (código existente dentro do if col_to_remove...) ...
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

                # Verificar colunas essenciais (garantir indentação correta)
                required_columns = ['date', 'time', 'name', 'artist', 'song_title']
                missing_columns = [col for col in required_columns if col not in columns]

                if missing_columns:
                    logger.error(f"A tabela '{DB_TABLE_NAME}' existe, mas não possui as colunas necessárias: {missing_columns}")
                    return False # Este return está dentro do else, está correto

                # Mostrar algumas linhas da tabela para diagnóstico (garantir indentação correta)
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}")
                    count = cursor.fetchone()[0]
                    logger.info(f"A tabela '{DB_TABLE_NAME}' contém {count} registros.")
                except Exception as e:
                    logger.error(f"Erro ao consultar dados da tabela '{DB_TABLE_NAME}': {e}")

                logger.info(f"Tabela de logs '{DB_TABLE_NAME}' verificada com sucesso!")
                return True # Este return está dentro do else, está correto

    except Exception as e:
        logger.error(f"Erro ao verificar tabela de logs: {e}", exc_info=True) # Add exc_info
        return False
    finally:
        if conn:
            conn.close()

# Fila para enviar ao Shazamio (RESTAURADO)
shazam_queue = asyncio.Queue()

# Variável para controlar o último heartbeat enviado (RESTAURADO)
last_heartbeat_time = 0
HEARTBEAT_INTERVAL_SECS = 60  # Enviar heartbeat a cada 1 minuto

# Variável global para controle da pausa do Shazam (RESTAURADO)
shazam_pause_until_timestamp = 0.0

# Classe StreamConnectionTracker (RESTAURADO)
class StreamConnectionTracker:
    def __init__(self):
        self.connection_errors = {} # Stores stream_name: error_timestamp

    def record_error(self, stream_name):
        """Records the timestamp of the first consecutive error for a stream."""
        if stream_name not in self.connection_errors:
            self.connection_errors[stream_name] = time.time()
            logger.debug(f"Registrado primeiro erro de conexão para: {stream_name}")

    def clear_error(self, stream_name):
        """Clears the error status for a stream if it was previously recorded."""
        if stream_name in self.connection_errors:
            del self.connection_errors[stream_name]
            logger.debug(f"Erro de conexão limpo para: {stream_name}")

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

connection_tracker = StreamConnectionTracker() # Instanciar o tracker (RESTAURADO)

# Função para conectar ao banco de dados PostgreSQL
def connect_db():
    try:
        # Validar se as configurações essenciais existem
        if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
            missing = []
            if not DB_HOST: missing.append("POSTGRES_HOST")
            if not DB_USER: missing.append("POSTGRES_USER") 
            if not DB_PASSWORD: missing.append("POSTGRES_PASSWORD")
            if not DB_NAME: missing.append("POSTGRES_DB")
            
            error_msg = f"Configurações de banco de dados incompletas. Faltando: {', '.join(missing)}"
            logger.error(error_msg)
            # send_email_alert("Erro: Configurações de Banco de Dados Incompletas", error_msg)
            return None
            
        # Mostrar informações de conexão (sem a senha)
        logger.info(f"Conectando ao banco PostgreSQL: {DB_HOST}:{DB_PORT}/{DB_NAME} (usuário: {DB_USER})")
        
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            connect_timeout=10  # Timeout de 10 segundos para a conexão
        )
        logger.debug("Conexão ao banco de dados estabelecida com sucesso!")
        return conn
    except psycopg2.OperationalError as e:
        # Erro operacional (servidor inacessível, credenciais incorretas, etc.)
        error_msg = f"Erro operacional ao conectar ao banco: {e}"
        logger.error(error_msg)
        # send_email_alert("Alerta: Falha na Conexão com o Banco de Dados", 
        #                  f"O servidor {SERVER_ID} não conseguiu se conectar ao banco de dados PostgreSQL em {DB_HOST}:{DB_PORT}.\\n\\nErro: {e}")
        return None
    except Exception as e:
        # Outros erros
        error_msg = f"Erro ao conectar ao banco de dados: {e}"
        logger.error(error_msg)
        # send_email_alert("Alerta: Falha na Conexão com o Banco de Dados", 
        #                  f"O servidor {SERVER_ID} não conseguiu se conectar ao banco de dados PostgreSQL em {DB_HOST}:{DB_PORT}.\\n\\nErro: {e}")
        return None

# Função para calcular o deslocamento de rotação com base no tempo
def calculate_rotation_offset():
    if not ENABLE_ROTATION:
        return 0
    
    # Calcular quantas rotações já ocorreram desde o início do tempo (1/1/1970)
    hours_since_epoch = int(time.time() / 3600)  # Converter segundos para horas
    rotations = hours_since_epoch // ROTATION_HOURS
    
    # O deslocamento é o número de rotações módulo o número total de servidores
    offset = rotations % TOTAL_SERVERS
    
    logger.info(f"Calculado deslocamento de rotação: {offset} (após {rotations} rotações)")
    return offset

# Função para carregar os streamings do banco de dados PostgreSQL
def load_streams():
    logger.debug("Iniciando a função load_streams() - Buscando do PostgreSQL")
    logger.info(f"Configurações de distribuição: SERVER_ID={SERVER_ID}, TOTAL_SERVERS={TOTAL_SERVERS}, DISTRIBUTE_LOAD={DISTRIBUTE_LOAD}, ENABLE_ROTATION={ENABLE_ROTATION}")
    logger.info(f"Conexão BD: HOST={DB_HOST}, DB={DB_NAME}, USER={DB_USER}, PORT={DB_PORT}")
    streams = []
    try:
        conn = connect_db()
        if conn:
            with conn.cursor() as cursor:
                # Testar se a tabela existe antes de consultar
                cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'streams')")
                table_exists = cursor.fetchone()[0]
                
                if not table_exists:
                    logger.error("A tabela 'streams' não existe no banco de dados!")
                    # Tentar encontrar tabelas disponíveis
                    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                    tables = [row[0] for row in cursor.fetchall()]
                    logger.info(f"Tabelas disponíveis no banco: {tables}")
                    
                cursor.execute("SELECT url, name, sheet, cidade, estado, regiao, segmento, index FROM streams ORDER BY index")
                rows = cursor.fetchall()
                
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
            conn.close()
        else:
            logger.error("Não foi possível conectar ao banco de dados. Tentando carregar do arquivo local.")
            # Fallback para o arquivo JSON local se não conseguir conectar ao banco
            try:
                with open(STREAMS_FILE, 'r', encoding='utf-8') as f:
                    streams = json.load(f)
                logger.info(f"Streams carregados do arquivo local como fallback.")
            except Exception as e:
                logger.error(f"Erro ao carregar o arquivo JSON local: {e}")
    except Exception as e:
        logger.error(f"Erro ao carregar streams do banco de dados: {e}")
        # Fallback para o arquivo JSON local em caso de erro
        try:
            with open(STREAMS_FILE, 'r', encoding='utf-8') as f:
                streams = json.load(f)
            logger.info(f"Streams carregados do arquivo local como fallback após erro no banco.")
        except Exception as e:
            logger.error(f"Erro ao carregar o arquivo JSON local: {e}")
    
    # Aplicar distribuição de carga se ativada
    if DISTRIBUTE_LOAD and TOTAL_SERVERS > 1:
        server_id = SERVER_ID  # Já é um inteiro, não precisa converter
        if server_id < 1 or server_id > TOTAL_SERVERS:
            logger.warning(f"SERVER_ID inválido ({server_id}). Deve estar entre 1 e {TOTAL_SERVERS}. Usando todos os streams.")
        else:
            # Calcular o deslocamento de rotação
            rotation_offset = calculate_rotation_offset()
            
            # Aplicar o deslocamento ao SERVER_ID para implementar a rotação
            effective_server_id = ((server_id - 1 + rotation_offset) % TOTAL_SERVERS) + 1
            
            if ENABLE_ROTATION:
                logger.info(f"Rotação ativada: SERVER_ID original {server_id}, SERVER_ID efetivo {effective_server_id}")
            
            # Distribuir streams entre servidores com o SERVER_ID efetivo
            distributed_streams = []
            
            # Garantir que a distribuição não falhe mesmo se houver inconsistências
            try:
                # Usar uma tabela de controle no banco de dados para garantir exclusividade
                conn = connect_db()
                if conn:
                    # Primeiro, atualizar ou inserir registros de controle para este servidor
                    with conn.cursor() as cursor:
                        for i, stream in enumerate(streams):
                            stream_index = int(stream['index'])
                            # Determinar qual servidor deve processar este stream
                            target_server = (stream_index % TOTAL_SERVERS) + 1
                            # Ajustar com base na rotação
                            target_server = ((target_server - 1 + rotation_offset) % TOTAL_SERVERS) + 1
                            
                            if target_server == effective_server_id:
                                # Este servidor deve processar este stream
                                stream['processed_by_server'] = True
                                distributed_streams.append(stream)
                            else:
                                stream['processed_by_server'] = False
                    conn.close()
            except Exception as e:
                logger.error(f"Erro ao aplicar distribuição de carga no banco: {e}")
                # Fallback para método simples original em caso de erro
                distributed_streams = []
                for i, stream in enumerate(streams):
                    if i % TOTAL_SERVERS == (effective_server_id - 1):
                        stream['processed_by_server'] = True
                        distributed_streams.append(stream)
                    else:
                        stream['processed_by_server'] = False
            
            logger.info(f"Distribuição de carga ativada: Servidor {server_id}/{TOTAL_SERVERS} " +
                       f"(efetivo: {effective_server_id}) - " +
                       f"Processando {len(distributed_streams)}/{len(streams)} streams")
            streams = distributed_streams
    
    logger.info(f"{len(streams)} streams carregados no total.")
    return streams

# Função para carregar o estado das últimas músicas identificadas
def load_last_songs():
    logger.debug("Iniciando a função load_last_songs()")
    try:
        if os.path.exists(LAST_SONGS_FILE):
            with open(LAST_SONGS_FILE, 'r', encoding='utf-8') as f:
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
        with open(LAST_SONGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_songs, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar o estado das últimas músicas: {e}")

# Função para carregar o log local
def load_local_log():
    logger.debug("Iniciando a função load_local_log()")
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

# Função para salvar o log local
def save_local_log(local_log):
    logger.debug("Iniciando a função save_local_log()")
    try:
        with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(local_log, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar o log local: {e}")

# Função para apagar o log local
def clear_local_log():
    logger.debug("Iniciando a função clear_local_log()")
    try:
        with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)
        logger.info("Log local limpo.")
    except Exception as e:
        logger.error(f"Erro ao limpar o log local: {e}")

# Função para verificar duplicidade na log local
def is_duplicate_in_log(song_title, artist, name):
    logger.debug("Iniciando a função is_duplicate_in_log()")
    local_log = load_local_log()
    for entry in local_log:
        if entry["song_title"] == song_title and entry["artist"] == artist and entry["name"] == name:
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
async def monitor_streams_file(callback):
    logger.debug("Iniciando a função monitor_streams_file()")
    last_streams_count = 0
    last_check_time = 0
    check_interval = 300  # Verificar a cada 5 minutos (300 segundos)
    
    while True:
        try:
            current_time = time.time()
            # Verificar apenas a cada intervalo definido
            if current_time - last_check_time >= check_interval:
                conn = connect_db()
                if conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) FROM streams")
                        current_count = cursor.fetchone()[0]
                        
                        # Se o número de streams mudou, recarregar
                        if current_count != last_streams_count:
                            logger.info(f"Mudança detectada no número de streams: {last_streams_count} -> {current_count}")
                            last_streams_count = current_count
                            callback()
                    conn.close()
                last_check_time = current_time
            
            await asyncio.sleep(60)  # Verificar a cada minuto se é hora de checar o banco
        except Exception as e:
            logger.error(f"Erro ao monitorar streams no banco de dados: {e}")
            await asyncio.sleep(60)  # Esperar um minuto antes de tentar novamente

# Função para capturar o áudio do streaming ao vivo e salvar um segmento temporário
async def capture_stream_segment(name, url, duration=None, processed_by_server=True):
    # Se o stream não for processado por este servidor, retornar None
    if not processed_by_server:
        logger.info(f"Pulando captura do stream {name} pois não é processado por este servidor.")
        return None
    
    # Usar configuração global se não especificado
    if duration is None:
        duration = IDENTIFICATION_DURATION
        
    output_dir = SEGMENTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{name}_segment.mp3')  # Sempre o mesmo arquivo
    try:
        logger.debug(f"URL do stream: {url}")
        # Remover a verificação prévia da URL com requests
        # Remover o parâmetro -headers
        command = [
            'ffmpeg', '-y', '-i', url,
            '-t', str(duration), '-ac', '1', '-ar', '44100', '-b:a', '192k', '-acodec', 'libmp3lame', output_path
        ]
        logger.info(f"Capturando segmento de {duration} segundos do stream {name}...")
        logger.debug(f"Comando FFmpeg: {' '.join(command)}")
        
        # Usar o timeout aumentado
        capture_timeout = duration + 30  # 30 segundos a mais do que a duração desejada
        
        process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=capture_timeout)
        
        if process.returncode != 0:
            stderr_text = stderr.decode(errors='ignore') if stderr else "Sem saída de erro"
            logger.error(f"Erro ao capturar o stream {url}: {stderr_text}")
            connection_tracker.record_error(name)  # Registra o erro
            return None
        else:
            # Verificar se o arquivo foi criado e tem um tamanho razoável
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:  # Mais de 1KB
                logger.info(f"Segmento de {duration} segundos capturado com sucesso para {name}.")
                connection_tracker.clear_error(name)  # Limpa o erro se a captura for bem-sucedida
                return output_path
            else:
                logger.error(f"Arquivo de saída vazio ou muito pequeno para {name}.")
                connection_tracker.record_error(name)
                return None
    except asyncio.TimeoutError:
        logger.error(f"Tempo esgotado para capturar o stream {url} após {capture_timeout}s")
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

# Função para verificar duplicatas no banco de dados (MODIFICADA)
async def _internal_is_duplicate_in_db(cursor, now_tz, name, artist, song_title):
    # Recebe datetime timezone-aware (now_tz)
    # --- Log Detalhado Início ---
    logger.debug(f"[_internal_is_duplicate] Iniciando verificação para:")
    logger.debug(f"  Stream: {name}")
    logger.debug(f"  Artista: {artist}")
    logger.debug(f"  Título: {song_title}")
    logger.debug(f"  Timestamp Atual (TZ): {now_tz}") # Log do timestamp TZ-aware
    logger.debug(f"  Janela (s): {DUPLICATE_PREVENTION_WINDOW_SECONDS}")
    # --- Fim Log Detalhado ---

    try:
        # Calcular o início da janela de verificação usando o timestamp TZ-aware
        start_window_tz = now_tz - timedelta(seconds=DUPLICATE_PREVENTION_WINDOW_SECONDS)
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
            cursor.execute(query, params)
            result = cursor.fetchone()
            if result:
                 logger.debug(f"  Query encontrou resultado: ID={result[0]}, Data={result[1]}, Hora={result[2]}")
            else:
                 logger.debug(f"  Query não encontrou resultado.")

        except Exception as e_query:
             logger.error(f"[_internal_is_duplicate] Erro ao executar query de duplicidade: {e_query}", exc_info=True)
             # --- Log Detalhado Erro Query ---
             logger.debug(f"[_internal_is_duplicate] Retornando False devido a erro na query.")
             # --- Fim Log Detalhado ---
             return False # Assume não duplicata se a query falhar

        is_duplicate = result is not None
        # --- Log Detalhado Resultado Final ---
        if is_duplicate:
            logger.info(f"[_internal_is_duplicate] Duplicata ENCONTRADA para {song_title} - {artist} em {name} (ID={result[0]} às {result[1]} {result[2]}).")
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
        return False # Assume não duplicata em caso de erro na verificação

# Função para inserir dados no banco de dados (MODIFICADA)
async def insert_data_to_db(entry_base, now_tz):
    # Recebe dicionário base e timestamp TZ-aware
    song_title = entry_base['song_title']
    artist = entry_base['artist']
    name = entry_base['name']
    logger.debug(f"insert_data_to_db: Iniciando processo para {song_title} - {artist} em {name}")

    conn = None
    try:
        conn = connect_db()
        if not conn:
            logger.error("insert_data_to_db: Não foi possível conectar ao DB.")
            return False # Falha na inserção

        # Logs detalhados para debugging do bug identified_by
        logger.info(f"DEBUG INSERT - SERVER_ID sendo usado: {SERVER_ID} (tipo: {type(SERVER_ID)})")
        logger.info(f"DEBUG INSERT - entry_base: {entry_base}")

        with conn.cursor() as cursor:
            # PASSO 1: Verificar duplicidade DENTRO da transação usando now_tz
            is_duplicate = await _internal_is_duplicate_in_db(cursor, now_tz, name, artist, song_title)

            if is_duplicate:
                logger.info(f"insert_data_to_db: Inserção ignorada, duplicata encontrada (verificação de janela) para {song_title} - {artist} em {name}.")
                return False # Indica que não inseriu (duplicata pela janela de tempo)

            # PASSO 2: Formatar date/time strings e Inserir se não for duplicata
            # Usar date/time do entry_base se presentes; caso contrário, usar now_tz
            date_str = entry_base.get("date") or now_tz.strftime('%Y-%m-%d')
            time_str = entry_base.get("time") or now_tz.strftime('%H:%M:%S')
            logger.debug(f"  Formatado para INSERT: date='{date_str}', time='{time_str}'")

            # Verificar se a tabela existe (redundante se check_log_table funcionou, mas seguro)
            cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{DB_TABLE_NAME}')")
            if not cursor.fetchone()[0]:
                logger.error(f"insert_data_to_db: A tabela '{DB_TABLE_NAME}' não existe! Inserção falhou.")
                return False

            # Garantir que identified_by use o SERVER_ID correto
            identified_by_value = str(SERVER_ID)
            logger.info(f"DEBUG INSERT - identified_by_value definido como: '{identified_by_value}'")

            # Preparar valores para inserção
            # Garantir que a ordem corresponde à query SQL
            values = (
                date_str,
                time_str, 
                entry_base.get("name"),
                entry_base.get("artist"),
                entry_base.get("song_title"),
                entry_base.get("isrc", ""),
                entry_base.get("cidade", ""),
                entry_base.get("estado", ""),
                entry_base.get("regiao", ""),
                entry_base.get("segmento", ""),
                entry_base.get("label", ""),
                entry_base.get("genre", ""),
                identified_by_value  # Usar variável explícita em vez de entry.get()
            )
            
            logger.info(f"DEBUG INSERT - Valores sendo inseridos: {values}")

            # Query SQL (verificar ordem das colunas)
            insert_sql = f'''
                INSERT INTO {DB_TABLE_NAME} (date, time, name, artist, song_title, isrc, cidade, estado, regiao, segmento, label, genre, identified_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id -- Retorna o ID para confirmação
            '''
            try:
                cursor.execute(insert_sql, values)
                inserted_id = cursor.fetchone()

                if inserted_id:
                    conn.commit() # Commit SÓ SE a inserção foi bem-sucedida
                    logger.info(f"insert_data_to_db: Dados inseridos com sucesso: ID={inserted_id[0]}, {song_title} - {artist} ({name})")
                    logger.info(f"Dados inseridos com sucesso no DB - identified_by='{identified_by_value}' para SERVER_ID={SERVER_ID}")
                    return True # Indica que inseriu com sucesso
                else:
                    # Isso não deveria acontecer normalmente se a query está correta e não houve erro
                    logger.error(f"insert_data_to_db: Inserção falhou ou não retornou ID para {song_title} - {artist}.")
                    conn.rollback() # Garante rollback se algo estranho ocorreu
                    return False

            except psycopg2.errors.UniqueViolation as e_unique:
                # Capturar erro específico de violação da constraint UNIQUE
                conn.rollback() # Importante fazer rollback
                logger.warning(f"insert_data_to_db: Inserção falhou devido a violação de constraint UNIQUE (duplicata exata no mesmo segundo detectada pelo DB): {e_unique}")
                return False # Indica que não inseriu (duplicata exata)

            except Exception as e_insert:
                # Outros erros durante a inserção
                conn.rollback()
                logger.error(f"insert_data_to_db: Erro GERAL ao inserir dados ({song_title} - {artist}): {e_insert}", exc_info=True)
                logger.error(f"DEBUG INSERT - SERVER_ID durante erro: {SERVER_ID}")
                # Enviar alerta para erros GERAIS de inserção
                subject = "Alerta: Erro ao Inserir Dados no Banco de Dados"
                body = f"O servidor {SERVER_ID} encontrou um erro GERAL ao inserir dados na tabela {DB_TABLE_NAME}. Erro: {e_insert}\nDados: {entry_base}"
                send_email_alert(subject, body)
                return False # Indica falha na inserção

    except Exception as e:
        # Erros na conexão ou fora do bloco with cursor
        logger.error(f"insert_data_to_db: Erro INESPERADO fora da transação ({song_title} - {artist}): {e}", exc_info=True)
        logger.error(f"DEBUG INSERT - SERVER_ID durante erro: {SERVER_ID}")
        if conn:
            try: conn.rollback()
            except Exception as rb_err: logger.error(f"Erro no rollback externo: {rb_err}")
        return False # Indica falha na inserção
    finally:
        if conn:
            try: conn.close()
            except Exception as cl_err: logger.error(f"Erro ao fechar conexão: {cl_err}")

# Função para atualizar o log local e chamar a inserção no DB
async def update_local_log(stream, song_title, artist, timestamp, isrc=None, label=None, genre=None):
    # ... (Criação de date_str, time_str, stream_name - igual a antes) ...
    date_str = timestamp.strftime('%Y-%m-%d')
    time_str = timestamp.strftime('%H:%M:%S')
    stream_name = stream['name']
    logger.debug(f"update_local_log: Preparando {song_title} - {artist} em {stream_name}")

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
    
    # Debug do SERVER_ID usado no log local
    logger.info(f"DEBUG LOCAL_LOG - SERVER_ID sendo usado: {SERVER_ID}")
    
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
    
    logger.info(f"DEBUG LOCAL_LOG - Entry created with identified_by='{new_entry['identified_by']}'")

    # Tenta inserir no banco de dados (a função insert_data_to_db agora faz a checagem de duplicidade)
    inserted_successfully = await insert_data_to_db(new_entry, timestamp.replace(tzinfo=timezone.utc))
        
    if inserted_successfully:
        logger.info(f"update_local_log: Inserção de {song_title} - {artist} bem-sucedida. Atualizando log local.")
        # Adiciona ao log local apenas se inserido com sucesso no DB
        local_log.append(new_entry)
        local_log = local_log[-1000:] # Mantém tamanho gerenciável
            
        # Salva o log local atualizado
        try:
            with open(LOCAL_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_log, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar log local: {e}")
            logger.error(f"DEBUG LOCAL_LOG - SERVER_ID durante erro: {SERVER_ID}")
            
        return True # Indica que foi uma nova inserção bem-sucedida
    else:
        # A inserção falhou (seja por duplicidade ou erro)
        # O log da falha já foi feito dentro de insert_data_to_db
        logger.info(f"update_local_log: Inserção de {song_title} - {artist} falhou ou foi ignorada (duplicata/erro). Log local não atualizado.")
        logger.error(f"DEBUG LOCAL_LOG - SERVER_ID durante falha: {SERVER_ID}")
        return False 

# Função para processar um único stream
async def process_stream(stream, last_songs):
    logger.debug("Iniciando a função process_stream()")
    url = stream['url']
    name = stream['name']
    processed_by_server = stream.get('processed_by_server', True)
    previous_segment = None

    while True:
        logger.info(f"Processando streaming: {name}")
        # Verificar se este stream está sendo processado por este servidor
        if not processed_by_server:
            logger.info(f"Stream {name} não é processado por este servidor. Verificando novamente em 60 segundos.")
            await asyncio.sleep(60)  # Aguardar antes de verificar novamente
            continue

        current_segment_path = await capture_stream_segment(name, url, duration=None, processed_by_server=processed_by_server)

        if current_segment_path is None:
            logger.error(f"Falha ao capturar segmento do streaming {name}. Tentando novamente...")
            await asyncio.sleep(10)
            continue

        await shazam_queue.put((current_segment_path, stream, last_songs))
        await shazam_queue.join()

        logger.info(f"Aguardando 60 segundos para o próximo ciclo do stream {name}...")
        await asyncio.sleep(60)  # Intervalo de captura de segmentos

def send_email_alert(subject, body):
    message = MIMEMultipart()
    message["From"] = ALERT_EMAIL
    message["To"] = RECIPIENT_EMAIL
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(ALERT_EMAIL, ALERT_EMAIL_PASSWORD)
            server.send_message(message)
        logger.info("E-mail de alerta enviado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail de alerta: {e}")

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
            logger.warning(f"Alerta enviado para erros persistentes: {persistent_errors}")

# Função para sincronizar o arquivo JSON local com o banco de dados
async def sync_json_with_db():
    logger.debug("Iniciando a função sync_json_with_db()")
    try:
        conn = connect_db()
        if conn:
            with conn.cursor() as cursor:
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
                        "index": str(row[7])
                    }
                    streams.append(stream)
                
                # Aplicar distribuição de carga se ativada (apenas para visualização no arquivo JSON)
                if DISTRIBUTE_LOAD and TOTAL_SERVERS > 1:
                    server_id = int(SERVER_ID)
                    if server_id >= 1 and server_id <= TOTAL_SERVERS:
                        # Marcar quais streams são processados por este servidor
                        for i, stream in enumerate(streams):
                            stream['processed_by_server'] = (i % TOTAL_SERVERS == (server_id - 1))
                
                # Salvar os streams no arquivo JSON local
                with open(STREAMS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(streams, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Arquivo JSON local sincronizado com sucesso. {len(streams)} streams salvos.")
            conn.close()
        else:
            logger.error("Não foi possível conectar ao banco de dados para sincronizar o arquivo JSON local.")
    except Exception as e:
        logger.error(f"Erro ao sincronizar o arquivo JSON local com o banco de dados: {e}")

# Função para agendar a sincronização periódica do arquivo JSON
async def schedule_json_sync():
    logger.info("Iniciando agendamento de sincronização do arquivo JSON local")
    while True:
        await sync_json_with_db()  # Sincroniza imediatamente na inicialização
        await asyncio.sleep(3600)  # Aguarda 1 hora (3600 segundos) antes da próxima sincronização

# Função para verificar se é hora de recarregar os streams devido à rotação
async def check_rotation_schedule():
    if not (DISTRIBUTE_LOAD and ENABLE_ROTATION):
        return False  # Não fazer nada se a rotação não estiver ativada
    
    logger.info("Iniciando monitoramento de rotação de streams")
    last_rotation_offset = calculate_rotation_offset()
    
    while True:
        await asyncio.sleep(60)  # Verificar a cada minuto
        current_rotation_offset = calculate_rotation_offset()
        
        if current_rotation_offset != last_rotation_offset:
            logger.info(f"Detectada mudança na rotação: {last_rotation_offset} -> {current_rotation_offset}")
            last_rotation_offset = current_rotation_offset
            
            # Recarregar streams com a nova rotação
            global STREAMS
            STREAMS = load_streams()
            logger.info(f"Streams recarregados devido à rotação. Agora processando {len(STREAMS)} streams.")
            
            # Atualizar as tarefas (isso será chamado na função main)
            return True
        
        return False

# Função worker para identificar música usando Shazamio (MODIFICADA)
async def identify_song_shazamio(shazam):
    global last_request_time, shazam_pause_until_timestamp
    # Definir o fuso horário uma vez fora do loop usando pytz
    target_tz = None
    if HAS_PYTZ:
        try:
            target_tz = pytz.timezone("America/Sao_Paulo")
            logger.info(f"Fuso horário definido (via pytz) para verificação de duplicatas: America/Sao_Paulo")
        except pytz.exceptions.UnknownTimeZoneError:
             logger.critical(f"Erro ao definir fuso horário 'America/Sao_Paulo' com pytz: Zona desconhecida. Verifique o nome.")
             sys.exit(1)
        except Exception as tz_err:
             logger.critical(f"Erro ao definir fuso horário 'America/Sao_Paulo' com pytz: {tz_err}. Saindo.")
             sys.exit(1)
    else:
        # Se pytz não foi importado, sair (já logado criticamente na importação)
        logger.critical("pytz não está disponível. Impossível continuar com tratamento de fuso horário.")
        sys.exit(1)

    while True:
        file_path, stream, last_songs = await shazam_queue.get()
        stream_index = stream.get('index') # Obter índice aqui para uso posterior

        # Verificar se o arquivo existe (pode ter sido pulado na captura)
        if file_path is None:
            logger.info(f"Arquivo de segmento para o stream {stream['name']} não foi capturado. Pulando identificação.")
            shazam_queue.task_done()
            continue

        identification_attempted = False
        out = None # Inicializar fora do loop de retentativa

        # --- Verificar se o Shazam está em pausa --- 
        current_time_check = time.time()
        if current_time_check < shazam_pause_until_timestamp:
            logger.info(f"Shazam em pausa devido a erro 429 anterior (até {dt.datetime.fromtimestamp(shazam_pause_until_timestamp).strftime('%H:%M:%S')}). Enviando {os.path.basename(file_path)} diretamente para failover.")
            if ENABLE_FAILOVER_SEND:
                asyncio.create_task(send_file_via_failover(file_path, stream_index))
        else:
            # --- Tentar identificação se não estiver em pausa ---
            identification_attempted = True
            # ... (loop de retentativas com tratamento de erro 429 e failover) ...
            max_retries = 5
            for attempt in range(max_retries):
                 try:
                     # ... (código do try existente: esperar, logar, shazam.recognize) ...
                     current_time = time.time()
                     time_since_last_request = current_time - last_request_time
                     if time_since_last_request < 1:
                         await asyncio.sleep(1 - time_since_last_request)
                     
                     logger.info(f"Identificando música no arquivo {file_path} (tentativa {attempt + 1}/{max_retries})...")
                     out = await asyncio.wait_for(shazam.recognize(file_path), timeout=10)
                     last_request_time = time.time()

                     if 'track' in out:
                         break 
                     else:
                         logger.info("Nenhuma música identificada (resposta vazia do Shazam).")
                         break 

                 except ClientResponseError as e_resp:
                     # ... (tratamento erro 429 com pausa e failover) ...
                     if e_resp.status == 429:
                         logger.warning(f"Erro 429 (Too Many Requests) do Shazam detectado. Pausando Shazam por 2 minutos.")
                         shazam_pause_until_timestamp = time.time() + 120
                         if ENABLE_FAILOVER_SEND:
                             asyncio.create_task(send_file_via_failover(file_path, stream_index))
                         break 
                     else:
                         wait_time = 2 ** attempt
                         logger.error(f"Erro HTTP {e_resp.status} do Shazam (tentativa {attempt + 1}/{max_retries}): {e_resp}. Esperando {wait_time}s...")
                         await asyncio.sleep(wait_time)
                 except (ClientConnectorError, asyncio.TimeoutError) as e_conn:
                      # ... (tratamento erro conexão/timeout) ...
                     wait_time = 2 ** attempt
                     logger.error(f"Erro de conexão/timeout com Shazam (tentativa {attempt + 1}/{max_retries}): {e_conn}. Esperando {wait_time}s...")
                     await asyncio.sleep(wait_time)
                 except Exception as e_gen:
                      # ... (tratamento erro genérico) ...
                     logger.error(f"Erro inesperado ao identificar a música (tentativa {attempt + 1}/{max_retries}): {e_gen}", exc_info=True)
                     break 
            else: 
                 if identification_attempted:
                    logger.error(f"Falha na identificação de {os.path.basename(file_path)} após {max_retries} tentativas (sem erro 429 ou erro genérico).")

        # --- Processar resultado (se houve identificação e não estava em pausa) ---
        if identification_attempted and out and 'track' in out:
            track = out['track']
            title = track['title']
            artist = track['subtitle']
            isrc = track.get('isrc', 'ISRC não disponível')
            label = None
            genre = None
            # ... (extração de label/genre) ...
            if 'sections' in track:
                for section in track['sections']:
                    if section['type'] == 'SONG':
                        for metadata in section['metadata']:
                            if metadata['title'] == 'Label':
                                label = metadata['text']
            if 'genres' in track:
                genre = track['genres'].get('primary', None)

            logger.info(f"Música identificada: {title} por {artist} (ISRC: {isrc}, Gravadora: {label}, Gênero: {genre})")

            # Obter timestamp atual COM FUSO HORÁRIO
            now_tz = dt.datetime.now(target_tz)

            # Criar dicionário base SEM date/time
            entry_base = {
                 "name": stream['name'], "artist": artist, "song_title": title,
                 "isrc": isrc, "cidade": stream.get("cidade", ""), "estado": stream.get("estado", ""),
                 "regiao": stream.get("regiao", ""), "segmento": stream.get("segmento", ""),
                 "label": label, "genre": genre, "identified_by": str(SERVER_ID)
             }

            # Chamar insert_data_to_db, que fará a verificação e a inserção
            inserted = await insert_data_to_db(entry_base, now_tz)

            if inserted: # Salvar last_songs apenas se a inserção foi BEM-SUCEDIDA (não duplicata)
                last_songs[stream['name']] = (title, artist)
                save_last_songs(last_songs)

        # --- Limpeza do arquivo local --- 
        # ... (código de limpeza existente) ...
        if os.path.exists(file_path):
            try:
                await asyncio.to_thread(os.remove, file_path)
                logger.debug(f"Arquivo de segmento local {file_path} removido.")
            except Exception as e_remove:
                logger.error(f"Erro ao remover arquivo de segmento {file_path}: {e_remove}")
                
        shazam_queue.task_done()

# Variáveis globais para controle de finalização
shutdown_event = asyncio.Event()
active_tasks = set()

# Função para lidar com sinais de finalização (CTRL+C, etc.)
def handle_shutdown_signal(sig, frame):
    logger.info(f"Sinal de finalização recebido ({sig}). Iniciando o encerramento controlado...")
    shutdown_event.set()

# Registrar o handler para os sinais
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

# Função para monitorar shutdown e cancelar tarefas
async def monitor_shutdown():
    await shutdown_event.wait()
    logger.info("Cancelando todas as tarefas ativas...")
    
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

# Função para obter nomes dos streams processados por este servidor
async def get_streams_processed_names() -> list:
    """
    Retorna uma lista dos nomes dos streams que esta instância deve processar,
    com base na lógica de distribuição estática utilizada neste script (Windows).
    """
    try:
        if not STREAMS:
            logger.warning("get_streams_processed_names: STREAMS não carregados ou vazios")
            return []
        
        processed_names = []
        for idx, stream in enumerate(STREAMS):
            try:
                if DISTRIBUTE_LOAD and TOTAL_SERVERS > 1:
                    should_process = (idx % TOTAL_SERVERS) == (SERVER_ID - 1)
                else:
                    should_process = True

                if should_process:
                    processed_names.append(stream.get('name', f"Stream_{idx}"))
            except Exception as e:
                logger.error(
                    "get_streams_processed_names: erro ao decidir processamento para stream id=%s name=%s: %s",
                    idx, stream.get('name', 'UNKNOWN'), e
                )

        logger.debug(
            "get_streams_processed_names: total_streams=%d, selecionados=%d",
            len(STREAMS), len(processed_names)
        )
        return processed_names
    except Exception as e:
        logger.exception("get_streams_processed_names: erro inesperado: %s", e)
        return []

# Função para enviar heartbeat para o banco de dados
async def send_heartbeat():
    global last_heartbeat_time
    current_time = time.time()

    # Limitar heartbeats para não sobrecarregar o banco
    if current_time - last_heartbeat_time < HEARTBEAT_INTERVAL_SECS:
        return
    
    last_heartbeat_time = current_time
    
    try:
        # Obter lista de nomes dos streams processados
        processing_stream_names = await get_streams_processed_names()

        # Logs de debug para ver o estado exato no momento do heartbeat
        logger.info(f"DEBUG HEARTBEAT - SERVER_ID atual: {SERVER_ID}")
        logger.info(f"DEBUG HEARTBEAT - DISTRIBUTE_LOAD: {DISTRIBUTE_LOAD}")
        logger.info(f"DEBUG HEARTBEAT - TOTAL_SERVERS: {TOTAL_SERVERS}")
        logger.info(f"DEBUG HEARTBEAT - Total STREAMS carregados: {len(STREAMS) if STREAMS else 0}")
        logger.info(f"DEBUG HEARTBEAT - processing_stream_names count: {len(processing_stream_names)}")
        logger.info(f"DEBUG HEARTBEAT - processing_stream_names: {processing_stream_names}")
        
        conn = connect_db()
        if not conn:
            logger.error("Não foi possível conectar ao banco de dados para enviar heartbeat.")
            return

        # Coletar informações do sistema
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage('/')
        
        # Informações para o banco de dados
        info = {
            "hostname": hostname,
            "platform": platform.platform(),
            "cpu_percent": cpu_percent,
            "memory_percent": mem.percent,
            "memory_available_mb": round(mem.available / (1024 * 1024), 2),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
            "processing_streams": len([s for s in STREAMS if s.get('processed_by_server', 
                                                               (int(s.get('index', 0)) % TOTAL_SERVERS) == (SERVER_ID - 1))]),
            "total_streams": len(STREAMS),
            "python_version": platform.python_version(),
            "processing_stream_names": processing_stream_names,
            "server_id_debug": SERVER_ID,
            "distribute_load": DISTRIBUTE_LOAD,
        }

        with conn.cursor() as cursor:
            # Verificar se a tabela existe, se não, criar
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
                VALUES (%s, NOW(), 'ONLINE', %s, %s::jsonb)
                ON CONFLICT (server_id) 
                DO UPDATE SET 
                    last_heartbeat = NOW(),
                    status = 'ONLINE',
                    ip_address = EXCLUDED.ip_address,
                    info = EXCLUDED.info;
            """, (SERVER_ID, ip_address, json.dumps(info)))
            
            conn.commit()
            logger.info(f"Heartbeat enviado com sucesso para servidor ID: {SERVER_ID}")
            logger.debug(f"DEBUG HEARTBEAT - Payload info enviado: {json.dumps(info, indent=2)}")
        
    except Exception as e:
        logger.error(f"Erro ao enviar heartbeat: {e}")
        logger.error(f"DEBUG - SERVER_ID durante erro: {SERVER_ID}")
    finally:
        if conn:
            conn.close()

# Função para verificar status de outros servidores
async def check_servers_status():
    # Intervalo de verificação: a cada 5 minutos
    CHECK_INTERVAL_SECS = 300
    # Tempo limite para considerar um servidor offline (10 minutos)
    OFFLINE_THRESHOLD_SECS = 600
    
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECS)
            
            conn = connect_db()
            if not conn:
                logger.error("Não foi possível conectar ao banco de dados para verificar status dos servidores.")
                continue
                
            with conn.cursor() as cursor:
                # Verificar se a tabela existe
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'server_heartbeats'
                    );
                """)
                
                if not cursor.fetchone()[0]:
                    logger.warning("Tabela de heartbeats não existe no banco de dados.")
                    continue
                
                # Marcar servidores offline se não enviarem heartbeat há muito tempo
                cursor.execute("""
                    UPDATE server_heartbeats
                    SET status = 'OFFLINE'
                    WHERE last_heartbeat < NOW() - INTERVAL '%s seconds'
                    AND status = 'ONLINE'
                    RETURNING server_id, last_heartbeat;
                """, (OFFLINE_THRESHOLD_SECS,))
                
                offline_servers = cursor.fetchall()
                conn.commit()
                
                if offline_servers:
                    # Servidores detectados como offline
                    server_ids = [row[0] for row in offline_servers]
                    last_heartbeats = [row[1] for row in offline_servers]
                    
                    # Log dos servidores que ficaram offline
                    logger.warning(f"Servidores detectados como OFFLINE: {server_ids}")
                    
                    # Enviar alerta por e-mail (apenas se este servidor for o ID 1)
                    # Isso evita múltiplos alertas do mesmo problema
                    if SERVER_ID == 1:
                        servers_info = "\n".join([f"Servidor {sid}: Último heartbeat em {lh}" 
                                                  for sid, lh in zip(server_ids, last_heartbeats)])
                        
                        subject = "ALERTA: Servidores de Identificação OFFLINE"
                        body = f"""Foram detectados servidores offline no sistema de identificação musical.

Servidores offline:
{servers_info}

O que fazer:
1. Verificar se os servidores estão operacionais
2. Verificar logs de erro
3. Reiniciar os servidores offline se necessário
4. Se um servidor não for retornar, considere ajustar TOTAL_SERVERS={TOTAL_SERVERS-len(server_ids)} e reiniciar os demais

Este é um alerta automático.
"""
                        send_email_alert(subject, body)
                        logger.info(f"Alerta de servidores offline enviado por e-mail")
                
                # Obter estatísticas dos servidores online
                cursor.execute("""
                    SELECT server_id, last_heartbeat, ip_address, info
                    FROM server_heartbeats
                    WHERE status = 'ONLINE'
                    ORDER BY server_id;
                """)
                
                online_servers = cursor.fetchall()
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
                            except:
                                logger.debug(f"Servidor {server_id} ({ip}): Último heartbeat em {last_hb}")
                
        except Exception as e:
            logger.error(f"Erro ao verificar status dos servidores: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

# Variável global para controlar o tempo da última solicitação
last_request_time = 0

# Função principal para processar todos os streams
async def main():
    logger.debug("Iniciando a função main()")
    logger.info(f"Configurações de distribuição carregadas do .env: SERVER_ID={SERVER_ID}, TOTAL_SERVERS={TOTAL_SERVERS}")
    logger.info(f"Distribuição de carga: {DISTRIBUTE_LOAD}, Rotação: {ENABLE_ROTATION}, Horas de rotação: {ROTATION_HOURS}")
    
    # Verificar se a tabela de logs existe e criar se necessário
    if not check_log_table():
        logger.warning("A verificação da tabela de logs falhou. Tentando prosseguir mesmo assim.")
    
    # Criar instância do Shazam para reconhecimento
    shazam = Shazam()
    
    global STREAMS
    STREAMS = load_streams()
    
    if not STREAMS:
        logger.error("Não foi possível carregar os streamings. Verifique a configuração do banco de dados ou o arquivo JSON local.")
        sys.exit(1)
        
    last_songs = load_last_songs()
    tasks = []
    
    # Inicializar fila para processamento
    global shazam_queue
    shazam_queue = asyncio.Queue()
    
    # Registrar informações sobre a distribuição de carga
    if DISTRIBUTE_LOAD:
        logger.info(f"Modo de distribuição de carga ativado: Servidor {SERVER_ID} de {TOTAL_SERVERS}")
        if ENABLE_ROTATION:
            logger.info(f"Rotação de rádios ativada: a cada {ROTATION_HOURS} horas")
            rotation_offset = calculate_rotation_offset()
            logger.info(f"Offset de rotação atual: {rotation_offset}")
        
        # Calcular e exibir quantos streams cada servidor está processando
        streams_per_server = {}
        total_streams = len(STREAMS)
        for i in range(1, TOTAL_SERVERS + 1):
            streams_for_this_server = len([s for s in STREAMS if s.get('processed_by_server', 
                                                                      (int(s.get('index', 0)) % TOTAL_SERVERS) == (i - 1))])
            streams_per_server[i] = streams_for_this_server
            
        logger.info(f"Distribuição de streams por servidor: {streams_per_server}")
        logger.info(f"Este servidor ({SERVER_ID}) processará {streams_per_server.get(SERVER_ID, 0)} de {total_streams} streams")
    else:
        logger.info("Modo de distribuição de carga desativado. Processando todos os streams.")

    def reload_streams():
        global STREAMS
        STREAMS = load_streams()
        logger.info("Streams recarregados.")
        if 'update_streams_in_db' in globals():
            update_streams_in_db(STREAMS)  # Atualiza o banco de dados com as rádios do arquivo
        # Cancelar todas as tarefas existentes
        for task in tasks:
            if not task.done():
                task.cancel()
        # Criar novas tarefas para os streams recarregados
        tasks.clear()
        # Apenas adicionar tarefas para streams que devem ser processados por este servidor
        for stream in STREAMS:
            task = asyncio.create_task(process_stream(stream, last_songs))
            register_task(task)  # Registrar para controle de finalização
            tasks.append(task)
        logger.info(f"{len(tasks)} tasks criadas para os novos streams.")

    # Criar e registrar todas as tarefas necessárias
    monitor_task = register_task(asyncio.create_task(monitor_streams_file(reload_streams)))
    shazam_task = register_task(asyncio.create_task(identify_song_shazamio(shazam)))
    shutdown_monitor_task = register_task(asyncio.create_task(monitor_shutdown()))
    
    # Adicionar tarefas de heartbeat e monitoramento de servidores
    heartbeat_task = register_task(asyncio.create_task(heartbeat_loop()))
    server_monitor_task = register_task(asyncio.create_task(check_servers_status()))
    
    if 'send_data_to_db' in globals():
        send_data_task = register_task(asyncio.create_task(send_data_to_db()))
        tasks_to_gather = [monitor_task, shazam_task, send_data_task, shutdown_monitor_task, 
                          heartbeat_task, server_monitor_task]
    else:
        tasks_to_gather = [monitor_task, shazam_task, shutdown_monitor_task, 
                          heartbeat_task, server_monitor_task]
    
    alert_task = register_task(asyncio.create_task(check_and_alert_persistent_errors()))
    json_sync_task = register_task(asyncio.create_task(schedule_json_sync()))
    
    tasks_to_gather.extend([alert_task, json_sync_task])
    
    # Adicionar tarefa para verificar a rotação de streams
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
        logger.error(f"Erro durante execução principal: {e}")
    finally:
        logger.info("Finalizando aplicação...")

def stop_and_restart():
    """Função para parar e reiniciar o script."""
    logger.info("Reiniciando o script...")
    os.execv(sys.executable, ['python'] + sys.argv)

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

# Ponto de entrada
if __name__ == '__main__':
    # Configurar temporizador para reinício diário às 00:00
    schedule.every().day.at("00:00").do(stop_and_restart)

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
    schedule_thread.daemon = True  # Thread será encerrada quando o programa principal terminar
    schedule_thread.start()

    # Bloco try/except/finally principal corretamente indentado
    try:
        # Executar o loop principal
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Programa interrompido pelo usuário (KeyboardInterrupt)")
        shutdown_event.set() # Aciona o evento de shutdown
    except Exception as e:
        logger.critical(f"Erro crítico: {e}", exc_info=True)
        shutdown_event.set() # Aciona o evento de shutdown em caso de erro crítico
        
        # Enviar e-mail de alerta para erro crítico
        try:
            subject = "Erro Crítico no Servidor de Identificação"
            body = f"O servidor {SERVER_ID} encontrou um erro crítico e precisou ser encerrado.\\n\\nErro: {e}\\n\\nPor favor, verifique os logs para mais detalhes."
            send_email_alert(subject, body)
        except Exception as email_err:
            logger.error(f"Não foi possível enviar e-mail de alerta para erro crítico: {email_err}")
    finally:
        logger.info("Aplicação encerrando...")
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
                logger.info("Nenhum loop de eventos em execução para cancelar tarefas.")

            if loop and not loop.is_closed():
                # Dar tempo para as tarefas serem canceladas
                # A função monitor_shutdown já aguarda asyncio.wait
                # Apenas esperamos que ela termine (ou timeout)
                for task in active_tasks: # Indentação correta do for loop
                    if not task.done():
                        task.cancel()
                try: # try/except corretamente indentado
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
                 logger.info("Loop de eventos não está ativo ou fechado, pulando cancelamento de tarefas.")
                 
        logger.info("Aplicação encerrada.")
        sys.exit(0)

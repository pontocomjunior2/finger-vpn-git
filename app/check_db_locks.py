import os
import psycopg2
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Database connection parameters from environment variables
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", 5432)

def check_locks():
    """
    Connects to the PostgreSQL database and checks for active locks.
    """
    conn = None
    try:
        # Establish a connection to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            port=DB_PORT
        )
        logging.info("Conectado ao banco de dados com sucesso.")

        with conn.cursor() as cursor:
            # Query to get information about locks
            # This query joins pg_locks with pg_stat_activity to get more details
            # about the process holding the lock.
            query = """
            SELECT
                a.datname,
                l.relation::regclass,
                l.transactionid,
                l.mode,
                l.granted,
                a.usename,
                a.query,
                a.pid
            FROM pg_locks l
            JOIN pg_stat_activity a ON l.pid = a.pid
            WHERE a.datname = %s
            ORDER BY a.pid;
            """
            cursor.execute(query, (DB_NAME,))
            locks = cursor.fetchall()

            if not locks:
                logging.info("Nenhum bloqueio ativo encontrado no banco de dados '%s'.", DB_NAME)
            else:
                logging.warning("Bloqueios ativos encontrados no banco de dados '%s':", DB_NAME)
                for lock in locks:
                    logging.info(
                        "Tabela: %s, Modo: %s, Concedido: %s, Usuário: %s, PID: %s, Query: %s",
                        lock[1], lock[3], lock[4], lock[5], lock[7], lock[6].strip()
                    )

    except psycopg2.OperationalError as e:
        logging.error("Erro de conexão com o banco de dados: %s", e)
    except Exception as e:
        logging.error("Ocorreu um erro inesperado: %s", e)
    finally:
        if conn:
            conn.close()
            logging.info("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    check_locks()
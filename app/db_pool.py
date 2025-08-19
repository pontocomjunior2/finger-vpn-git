"""
Módulo de Pool de Conexões PostgreSQL
Resolve problemas de esgotamento de conexões e timeouts
"""
import os
import time
import random
import logging
import threading
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager, asynccontextmanager

logger = logging.getLogger(__name__)

class PoolMetrics:
    """Classe para monitorar métricas do pool de conexões"""
    def __init__(self):
        self.active_connections = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.wait_times = []
        self.pool_exhausted_count = 0
        self._lock = threading.Lock()
    
    def record_request(self, wait_time_ms, success=True):
        with self._lock:
            self.total_requests += 1
            if not success:
                self.failed_requests += 1
            if wait_time_ms > 50:  # Log tempos de espera > 50ms
                logger.warning(f"Pool connection wait time: {wait_time_ms:.2f}ms")
            self.wait_times.append(wait_time_ms)
            # Manter apenas os últimos 100 tempos
            if len(self.wait_times) > 100:
                self.wait_times.pop(0)
    
    def record_pool_exhausted(self):
        with self._lock:
            self.pool_exhausted_count += 1
            logger.error("Pool de conexões esgotado!")
    
    def get_stats(self):
        with self._lock:
            avg_wait = sum(self.wait_times) / len(self.wait_times) if self.wait_times else 0
            return {
                'active_connections': self.active_connections,
                'total_requests': self.total_requests,
                'failed_requests': self.failed_requests,
                'success_rate': (self.total_requests - self.failed_requests) / max(self.total_requests, 1) * 100,
                'avg_wait_time_ms': avg_wait,
                'pool_exhausted_count': self.pool_exhausted_count
            }

class DatabasePool:
    def __init__(self, minconn=5, maxconn=20):
        self.minconn = minconn
        self.maxconn = maxconn
        self.pool = None
        self.metrics = PoolMetrics()
        self.max_retries = 3
        self.base_delay = 1  # Delay base para retry em segundos
        self._last_pool_check = time.time()
        self._pool_stats = {
            'created_connections': 0,
            'closed_connections': 0,
            'connection_errors': 0,
            'pool_resets': 0,
            'last_error': None,
            'last_error_time': None
        }
        self._create_pool()
    
    def _create_pool(self):
        """Cria o pool de conexões com retry e jitter"""
        for attempt in range(self.max_retries):
            try:
                # Configurações do banco de dados
                db_config = {
                    'host': os.getenv('POSTGRES_HOST'),
                    'user': os.getenv('POSTGRES_USER'),
                    'password': os.getenv('POSTGRES_PASSWORD'),
                    'database': os.getenv('POSTGRES_DB'),
                    'port': os.getenv('POSTGRES_PORT', '5432'),
                    'connect_timeout': 60,  # Aumentado para 60 segundos
                    'options': '-c statement_timeout=30000 -c idle_in_transaction_session_timeout=30000'
                    'application_name': f'fingerv7_server_{os.getenv("SERVER_ID", "1")}'
                }
                
                # Verificar se todas as configurações obrigatórias estão presentes
                required_configs = ['host', 'user', 'password', 'database']
                missing_configs = [key for key in required_configs if not db_config[key]]
                
                if missing_configs:
                    raise ValueError(f"Configurações obrigatórias do banco de dados não encontradas: {missing_configs}")
                
                # Criar pool com configurações otimizadas
                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self.minconn,  # Usar valor configurado no construtor
                    maxconn=self.maxconn,  # Usar valor configurado no construtor
                    **db_config
                )
                
                logger.info(f"Pool de conexões criado com sucesso (tentativa {attempt + 1})")
                return
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Falha ao criar pool de conexões após {self.max_retries} tentativas: {e}")
                    raise
                
                # Delay exponencial com jitter
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.2f}s: {e}")
                time.sleep(delay)
    
    def _configure_session(self, conn):
        """Configura parâmetros de sessão para otimização"""
        try:
            with conn.cursor() as cursor:
                # Configurar timeouts para evitar bloqueios
                cursor.execute("SET statement_timeout = '30000'")  # 30 segundos
                cursor.execute("SET lock_timeout = '10000'")       # 10 segundos
                cursor.execute("SET idle_in_transaction_session_timeout = '30000'")  # 30 segundos
                # Configurar comportamento de transação
                cursor.execute("SET application_name = 'fingerv7_worker'")  # Identificar conexão
                conn.commit()
        except Exception as e:
            logger.warning(f"Erro ao configurar parâmetros de sessão: {e}")
            conn.rollback()
    
    @asynccontextmanager
    async def get_connection(self):
        """Gerenciador de contexto assíncrono para obter conexão do pool"""
        conn = None
        start_time = time.time()
        max_retries = 5  # Aumentado para 5 tentativas
        base_delay = 0.2  # Delay base aumentado
        
        for attempt in range(max_retries):
            try:
                # Obter conexão do pool de forma assíncrona
                import asyncio
                
                # Verificar se o pool precisa ser recriado
                if self.pool is None or self.pool.closed:
                    logger.warning("Pool fechado ou não inicializado. Recriando...")
                    self._create_pool()
                
                conn = await asyncio.to_thread(self.pool.getconn)
                
                if conn:
                    # Configurar sessão e testar a conexão
                    await asyncio.to_thread(self._configure_session, conn)
                    await asyncio.to_thread(self._test_connection, conn)
                    
                    # Registrar métricas
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=True)
                    self.metrics.active_connections += 1
                    
                    try:
                        yield conn
                    finally:
                        self.metrics.active_connections -= 1
                        try:
                            if conn and not conn.closed:
                                await asyncio.to_thread(self.pool.putconn, conn)
                            else:
                                logger.warning("Conexão já fechada, não retornando ao pool")
                        except Exception as e:
                            logger.error(f"Erro ao retornar conexão ao pool: {e}")
                    return
                else:
                    raise psycopg2.OperationalError("Não foi possível obter conexão do pool")
                    
            except psycopg2.OperationalError as e:
                if conn:
                    try:
                        # Fechar conexão inválida
                        await asyncio.to_thread(conn.close)
                    except:
                        pass
                    conn = None
                
                if attempt == max_retries - 1:
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=False)
                    self.metrics.record_pool_exhausted()
                    logger.error(f"Falha ao obter conexão após {max_retries} tentativas: {e}")
                    raise
                
                # Delay exponencial com jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.05)
                logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.3f}s: {e}")
                await asyncio.sleep(delay)
                
            except Exception as e:
                wait_time_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(wait_time_ms, success=False)
                logger.error(f"Erro inesperado ao obter conexão: {e}")
                if conn:
                    try:
                        await asyncio.to_thread(self.pool.putconn, conn)
                    except Exception as put_err:
                        logger.error(f"Erro ao retornar conexão ao pool: {put_err}")
                raise
    
    def get_connection_sync(self):
        """Versão síncrona do gerenciador de contexto"""
        return self._get_connection_sync()
    
    @contextmanager
    def _get_connection_sync(self):
        """Gerenciador de contexto síncrono para obter conexão do pool"""
        conn = None
        start_time = time.time()
        max_retries = 5  # Aumentado para 5 tentativas
        base_delay = 0.2  # Delay base aumentado
        connection_timeout = 60  # Timeout em segundos para obtenção de conexão
        
        for attempt in range(max_retries):
            try:
                # Verificar se o timeout foi excedido
                if time.time() - start_time > connection_timeout:
                    logger.error(f"Timeout de {connection_timeout}s excedido ao tentar obter conexão")
                    self._pool_stats['connection_errors'] += 1
                    raise psycopg2.OperationalError(f"Timeout de {connection_timeout}s excedido ao tentar obter conexão")
                
                # Verificar se o pool precisa ser recriado
                if self.pool is None or self.pool.closed:
                    logger.warning("Pool fechado ou não inicializado. Recriando...")
                    self._create_pool()
                    self._pool_stats['pool_resets'] += 1
                    
                conn = self.pool.getconn()
                self._pool_stats['created_connections'] += 1
                
                if conn:
                    # Configurar sessão e testar a conexão
                    self._configure_session(conn)
                    self._test_connection(conn)
                    
                    # Registrar métricas
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=True)
                    self.metrics.active_connections += 1
                    
                    try:
                        yield conn
                    finally:
                        self.metrics.active_connections -= 1
                        try:
                            if conn and not conn.closed:
                                self.pool.putconn(conn)
                            else:
                                logger.warning("Conexão já fechada, não retornando ao pool")
                                self._pool_stats['closed_connections'] += 1
                        except Exception as e:
                            logger.error(f"Erro ao retornar conexão ao pool: {e}")
                    return
                else:
                    raise psycopg2.OperationalError("Não foi possível obter conexão do pool")
                    
            except psycopg2.OperationalError as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None
                
                self._pool_stats['connection_errors'] += 1
                
                if attempt == max_retries - 1:
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=False)
                    self.metrics.record_pool_exhausted()
                    logger.error(f"Falha ao obter conexão após {max_retries} tentativas: {e}")
                    self._pool_stats['last_error'] = str(e)
                    self._pool_stats['last_error_time'] = datetime.now().isoformat()
                    raise
                
                # Delay exponencial com jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.05)
                # Limitar o delay máximo a 10 segundos
                delay = min(delay, 10)
                
                # Verificar se o delay não excederá o timeout
                if time.time() + delay - start_time > connection_timeout:
                    delay = max(0.1, connection_timeout - (time.time() - start_time) - 0.1)  # Deixar 0.1s para a próxima tentativa
                
                logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.3f}s: {e}")
                time.sleep(delay)
                
            except Exception as e:
                wait_time_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(wait_time_ms, success=False)
                logger.error(f"Erro inesperado ao obter conexão: {e}")
                self._pool_stats['last_error'] = str(e)
                self._pool_stats['last_error_time'] = datetime.now().isoformat()
                if conn:
                    try:
                        self.pool.putconn(conn)
                    except:
                        pass
                raise
    
    def _test_connection(self, conn):
        """Testa se a conexão está válida"""
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as e:
            logger.error(f"Teste de conexão falhou: {e}")
            raise psycopg2.OperationalError(f"Conexão inválida: {e}")
    
    def recreate_pool(self):
        """Recria o pool em caso de falha crítica"""
        try:
            if self.pool:
                self.pool.closeall()
        except:
            pass
        self._create_pool()
    
    def get_pool_stats(self):
        """Retorna estatísticas do pool"""
        stats = self.metrics.get_stats()
        if self.pool:
            # Adicionar informações do pool psycopg2
            stats.update({
                'pool_min_conn': self.pool.minconn,
                'pool_max_conn': self.pool.maxconn,
                'pool_closed': self.pool.closed
            })
            
            # Verificar se é hora de fazer uma verificação de saúde do pool
            current_time = time.time()
            if current_time - self._last_pool_check > 300:  # Verificar a cada 5 minutos
                self._check_pool_health()
                self._last_pool_check = current_time
                
        stats.update({'pool_stats': self._pool_stats})
        return stats
        
    def _check_pool_health(self):
        """Verifica a saúde do pool de conexões e detecta possíveis vazamentos"""
        if not self.pool:
            return
            
        try:
            # Verificar se há muitas conexões em uso por muito tempo
            if self.metrics.active_connections > (self.maxconn * 0.8):  # Se mais de 80% das conexões estão em uso
                logger.warning(f"Possível vazamento de conexões detectado: {self.metrics.active_connections}/{self.maxconn} conexões em uso")
                
                # Se todas as conexões estiverem em uso, tentar resetar o pool
                if self.metrics.active_connections >= self.maxconn:
                    logger.error("Pool de conexões esgotado. Tentando resetar o pool.")
                    self.recreate_pool()
                    self._pool_stats['pool_resets'] += 1
        except Exception as e:
            logger.error(f"Erro ao verificar saúde do pool: {e}")
            self._pool_stats['last_error'] = str(e)
            self._pool_stats['last_error_time'] = datetime.now().isoformat()
    
    def putconn(self, conn):
        """Retorna uma conexão ao pool"""
        if self.pool and conn:
            try:
                self.pool.putconn(conn)
            except Exception as e:
                logger.error(f"Erro ao retornar conexão ao pool: {e}")
    
    def close_all(self):
        """Fecha todas as conexões do pool"""
        if self.pool:
            try:
                self.pool.closeall()
                logger.info("Pool de conexões fechado")
            except Exception as e:
                logger.error(f"Erro ao fechar pool: {e}")

# Instância global do pool (lazy initialization)
db_pool = None

def get_db_pool():
    """Retorna a instância do pool, criando-a se necessário"""
    global db_pool
    if db_pool is None:
        db_pool = DatabasePool()
    return db_pool
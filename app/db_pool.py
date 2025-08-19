"""
Módulo de Pool de Conexões PostgreSQL
Resolve problemas de esgotamento de conexões e timeouts
"""

import os
import time
import random
import logging
import threading
import traceback
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
        self.connection_tracking = {}  # Para rastrear conexões ativas
        self.long_lived_connections = {}  # Para rastrear conexões de longa duração
        self.connection_threshold = 60  # Tempo em segundos para considerar uma conexão como suspeita
        self.last_leak_check = time.time()
        self.leak_check_interval = 120  # 2 minutos
        self.last_metrics_log = time.time()
        self.metrics_log_interval = 300  # 5 minutos

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
            
    def track_connection_acquired(self, conn_id):
        """Registra quando uma conexão é adquirida"""
        with self._lock:
            self.connection_tracking[conn_id] = {
                'acquired_at': time.time(),
                'stack_trace': ''.join(traceback.format_stack())
            }
    
    def track_connection_released(self, conn_id):
        """Registra quando uma conexão é liberada"""
        with self._lock:
            if conn_id in self.connection_tracking:
                acquired_time = self.connection_tracking[conn_id]['acquired_at']
                duration = time.time() - acquired_time
                
                # Se a conexão foi mantida por muito tempo, registrar como suspeita
                if duration > self.connection_threshold:
                    self.long_lived_connections[conn_id] = {
                        'duration': duration,
                        'stack_trace': self.connection_tracking[conn_id]['stack_trace']
                    }
                    logger.warning(f"Conexão {conn_id} mantida por {duration:.2f}s (acima do limite de {self.connection_threshold}s)")
                
                # Remover do rastreamento
                del self.connection_tracking[conn_id]
    
    def check_for_connection_leaks(self):
        """Verifica conexões que podem estar vazando (não foram liberadas)"""
        with self._lock:
            current_time = time.time()
            leaked_connections = []
            
            for conn_id, data in list(self.connection_tracking.items()):
                duration = current_time - data['acquired_at']
                if duration > self.connection_threshold * 2:  # Tempo dobrado para considerar vazamento
                    leaked_connections.append((conn_id, duration, data['stack_trace']))
            
            if leaked_connections:
                logger.warning(f"Possíveis vazamentos de conexão detectados: {len(leaked_connections)} conexões")
                for conn_id, duration, stack_trace in leaked_connections:
                    logger.warning(f"Conexão {conn_id} em uso por {duration:.2f}s. Stack trace de aquisição:\n{stack_trace}")
                    
            # Limpar conexões muito antigas do rastreamento (podem ser conexões perdidas)
            for conn_id, data in list(self.connection_tracking.items()):
                if current_time - data['acquired_at'] > 3600:  # 1 hora
                    logger.error(f"Removendo conexão {conn_id} do rastreamento após 1 hora (provável vazamento)")
                    del self.connection_tracking[conn_id]

    def get_stats(self):
        with self._lock:
            avg_wait = (
                sum(self.wait_times) / len(self.wait_times) if self.wait_times else 0
            )
            return {
                "active_connections": self.active_connections,
                "total_requests": self.total_requests,
                "failed_requests": self.failed_requests,
                "success_rate": (self.total_requests - self.failed_requests)
                / max(self.total_requests, 1)
                * 100,
                "avg_wait_time_ms": avg_wait,
                "pool_exhausted_count": self.pool_exhausted_count,
                "tracked_connections": len(self.connection_tracking),
                "long_lived_connections": len(self.long_lived_connections)
            }


class DatabasePool:
    def __init__(self, minconn=20, maxconn=50):
        self.minconn = minconn
        self.maxconn = maxconn
        self.pool = None
        self.metrics = PoolMetrics()
        self.max_retries = 3
        self.base_delay = 1  # Delay base para retry em segundos
        self._last_pool_check = time.time()
        self._pool_stats = {
            "created_connections": 0,
            "closed_connections": 0,
            "connection_errors": 0,
            "pool_resets": 0,
            "last_error": None,
            "last_error_time": None,
        }
        # Inicializar monitoramento de conexões
        self._connection_ids = {}
        self._connection_tracking = {}
        self._long_lived_connections = {}
        self._last_leak_check = time.time()
        self._create_pool()

    def _create_pool(self):
        """Cria o pool de conexões com retry e jitter"""
        for attempt in range(self.max_retries):
            try:
                # Configurações do banco de dados
                db_config = {
                    "host": os.getenv("POSTGRES_HOST"),
                    "user": os.getenv("POSTGRES_USER"),
                    "password": os.getenv("POSTGRES_PASSWORD"),
                    "database": os.getenv("POSTGRES_DB"),
                    "port": os.getenv("POSTGRES_PORT", "5432"),
                    "connect_timeout": 90,  # Aumentado para 90 segundos
                    "options": "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=30000",
                    "application_name": f'fingerv7_server_{os.getenv("SERVER_ID", "1")}',
                }

                # Verificar se todas as configurações obrigatórias estão presentes
                required_configs = ["host", "user", "password", "database"]
                missing_configs = [
                    key for key in required_configs if not db_config[key]
                ]

                if missing_configs:
                    raise ValueError(
                        f"Configurações obrigatórias do banco de dados não encontradas: {missing_configs}"
                    )

                # Criar pool com configurações otimizadas
                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self.minconn,  # Usar valor configurado no construtor
                    maxconn=self.maxconn,  # Usar valor configurado no construtor
                    **db_config,
                )

                logger.info(
                    f"Pool de conexões criado com sucesso (tentativa {attempt + 1})"
                )
                return

            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(
                        f"Falha ao criar pool de conexões após {self.max_retries} tentativas: {e}"
                    )
                    raise

                # Delay exponencial com jitter
                delay = self.base_delay * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.2f}s: {e}"
                )
                time.sleep(delay)

    def _configure_session(self, conn):
        """Configura parâmetros de sessão para otimização"""
        try:
            with conn.cursor() as cursor:
                # Configurar timeouts para evitar bloqueios
                cursor.execute("SET statement_timeout = '30000'")  # 30 segundos
                cursor.execute("SET lock_timeout = '10000'")  # 10 segundos
                cursor.execute(
                    "SET idle_in_transaction_session_timeout = '30000'"
                )  # 30 segundos
                # Configurar comportamento de transação
                cursor.execute(
                    "SET application_name = 'fingerv7_worker'"
                )  # Identificar conexão
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
        connection_timeout = 180  # Timeout em segundos para obtenção de conexão (aumentado para 3 minutos)

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

                    # Gerar um ID único para esta conexão para rastreamento
                    conn_id = id(conn)
                    
                    # Registrar métricas
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=True)
                    self.metrics.active_connections += 1
                    self.metrics.track_connection_acquired(conn_id)

                    try:
                        yield conn
                    finally:
                        self.metrics.active_connections -= 1
                        try:
                            if conn and not conn.closed:
                                # Registrar liberação da conexão
                                self.metrics.track_connection_released(conn_id)
                                await asyncio.to_thread(self.pool.putconn, conn)
                            else:
                                logger.warning(
                                    "Conexão já fechada, não retornando ao pool"
                                )
                        except Exception as e:
                            logger.error(f"Erro ao retornar conexão ao pool: {e}")
                    return
                else:
                    raise psycopg2.OperationalError(
                        "Não foi possível obter conexão do pool"
                    )

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
                    logger.error(
                        f"Falha ao obter conexão após {max_retries} tentativas: {e}"
                    )
                    raise

                # Delay exponencial com jitter
                delay = base_delay * (2**attempt) + random.uniform(0, 0.05)
                logger.warning(
                    f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.3f}s: {e}"
                )
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
        connection_timeout = 180  # Timeout em segundos para obtenção de conexão (aumentado para 3 minutos)

        for attempt in range(max_retries):
            try:
                # Verificar se o timeout foi excedido
                if time.time() - start_time > connection_timeout:
                    logger.error(
                        f"Timeout de {connection_timeout}s excedido ao tentar obter conexão"
                    )
                    self._pool_stats["connection_errors"] += 1
                    raise psycopg2.OperationalError(
                        f"Timeout de {connection_timeout}s excedido ao tentar obter conexão"
                    )

                # Verificar se o pool precisa ser recriado
                if self.pool is None or self.pool.closed:
                    logger.warning("Pool fechado ou não inicializado. Recriando...")
                    self._create_pool()
                    self._pool_stats["pool_resets"] += 1

                conn = self.pool.getconn()
                self._pool_stats["created_connections"] += 1

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
                                logger.warning(
                                    "Conexão já fechada, não retornando ao pool"
                                )
                                self._pool_stats["closed_connections"] += 1
                        except Exception as e:
                            logger.error(f"Erro ao retornar conexão ao pool: {e}")
                    return
                else:
                    raise psycopg2.OperationalError(
                        "Não foi possível obter conexão do pool"
                    )

            except psycopg2.OperationalError as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None

                self._pool_stats["connection_errors"] += 1

                if attempt == max_retries - 1:
                    wait_time_ms = (time.time() - start_time) * 1000
                    self.metrics.record_request(wait_time_ms, success=False)
                    self.metrics.record_pool_exhausted()
                    logger.error(
                        f"Falha ao obter conexão após {max_retries} tentativas: {e}"
                    )
                    self._pool_stats["last_error"] = str(e)
                    self._pool_stats["last_error_time"] = datetime.now().isoformat()
                    raise

                # Delay exponencial com jitter
                delay = base_delay * (2**attempt) + random.uniform(0, 0.05)
                # Limitar o delay máximo a 10 segundos
                delay = min(delay, 10)

                # Verificar se o delay não excederá o timeout
                if time.time() + delay - start_time > connection_timeout:
                    delay = max(
                        0.1, connection_timeout - (time.time() - start_time) - 0.1
                    )  # Deixar 0.1s para a próxima tentativa

                logger.warning(
                    f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.3f}s: {e}"
                )
                time.sleep(delay)

            except Exception as e:
                wait_time_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(wait_time_ms, success=False)
                logger.error(f"Erro inesperado ao obter conexão: {e}")
                self._pool_stats["last_error"] = str(e)
                self._pool_stats["last_error_time"] = datetime.now().isoformat()
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
        except Exception as e:
            logger.error(f"Erro ao fechar pool existente: {e}")

        # Adicionar delay antes de recriar para evitar sobrecarga
        time.sleep(1)
        self._create_pool()
        logger.info("Pool de conexões recriado com sucesso")

    def handle_connection_failure(self, error):
        """Gerencia falhas de conexão com estratégia de retry avançada"""
        self._pool_stats["connection_errors"] += 1
        self._pool_stats["last_error"] = str(error)
        self._pool_stats["last_error_time"] = datetime.now().isoformat()
        error_str = str(error).lower()
        
        # Inicializar contador de falhas se não existir
        if not hasattr(self, "_consecutive_failures"):
            self._consecutive_failures = 0
            self._last_failure_time = None
            self._failure_types = {}
        
        # Incrementar contador de falhas consecutivas
        self._consecutive_failures += 1
        self._last_failure_time = datetime.now()
        
        # Registrar tipo de falha para análise de padrões
        error_type = "unknown"
        if "connection refused" in error_str:
            error_type = "connection_refused"
        elif "too many connections" in error_str:
            error_type = "too_many_connections"
        elif "connection timed out" in error_str:
            error_type = "connection_timeout"
        elif "idle in transaction" in error_str:
            error_type = "idle_transaction"
        elif "deadlock detected" in error_str:
            error_type = "deadlock"
        
        # Incrementar contador para este tipo de erro
        self._failure_types[error_type] = self._failure_types.get(error_type, 0) + 1
        
        # Verificar se é necessário recriar o pool
        critical_error = (
            "connection refused" in error_str
            or "too many connections" in error_str
            or "connection timed out" in error_str
            or "cannot connect now" in error_str
            or "no connection to the server" in error_str
        )
        
        # Estratégia de recuperação baseada na gravidade e frequência
        if critical_error or self._consecutive_failures >= 5:
            logger.warning(
                f"Detectado erro crítico de conexão: {error}. Recriando pool. "
                f"Falhas consecutivas: {self._consecutive_failures}"
            )
            self.recreate_pool()
            
            # Se muitas falhas consecutivas, aguardar um pouco antes de continuar
            if self._consecutive_failures >= 10:
                logger.error(f"Muitas falhas consecutivas ({self._consecutive_failures}). Pausando operações.")
                time.sleep(5)  # Pausa mais longa para permitir recuperação do sistema
            
            return True
        
        # Resetar contador se última falha foi há mais de 5 minutos
        if self._last_failure_time and (datetime.now() - self._last_failure_time) > timedelta(minutes=5):
            self._consecutive_failures = 1
            self._failure_types = {error_type: 1}
            
        return False
        
    def _force_release_idle_connections(self):
        """Tenta liberar conexões que possam estar inativas por muito tempo"""
        if not self.pool or self.pool.closed:
            return
            
        try:
            released = 0
            
            # Forçar coleta de lixo para liberar conexões não utilizadas
            import gc
            gc.collect()
            
            # Tentar recriar o pool em caso de uso muito elevado
            if self.metrics.active_connections > self.maxconn * 0.9:
                logger.warning("Uso crítico do pool. Recriando pool para liberar conexões.")
                self.recreate_pool()
                released = self.metrics.active_connections
                logger.info(f"Pool recriado. Liberadas aproximadamente {released} conexões.")
            
            if released > 0:
                logger.info(f"Liberadas {released} conexões potencialmente inativas")
                
        except Exception as e:
            logger.error(f"Erro ao tentar liberar conexões inativas: {e}")
            # Não propagar o erro, pois esta é uma operação de recuperação

    def get_pool_stats(self):
        """Retorna estatísticas do pool"""
        stats = self.metrics.get_stats()
        if self.pool:
            # Adicionar informações do pool psycopg2
            stats.update(
                {
                    "pool_min_conn": self.pool.minconn,
                    "pool_max_conn": self.pool.maxconn,
                    "pool_closed": self.pool.closed,
                }
            )

            # Verificar se é hora de fazer uma verificação de saúde do pool
            current_time = time.time()
            if current_time - self._last_pool_check > 300:  # Verificar a cada 5 minutos
                self._check_pool_health()
                self._last_pool_check = current_time

        stats.update({"pool_stats": self._pool_stats})
        return stats
        
    def get_detailed_stats(self):
        """Retorna estatísticas detalhadas do pool para análise de vazamentos"""
        stats = self.get_pool_stats()
        
        # Adicionar informações de tendência se disponível
        if hasattr(self, "_usage_history") and self._usage_history:
            # Calcular média de uso nas últimas horas
            hour_ago = time.time() - 3600
            recent_points = [p for p in self._usage_history if p[0] >= hour_ago]
            if recent_points:
                avg_usage = sum(p[2] for p in recent_points) / len(recent_points)
                stats["avg_usage_last_hour"] = avg_usage
                
                # Calcular taxa de crescimento
                if len(recent_points) >= 2:
                    start_usage = recent_points[0][2]
                    end_usage = recent_points[-1][2]
                    stats["usage_growth_last_hour"] = end_usage - start_usage
                    
                    # Detectar padrão de crescimento constante
                    is_growing = all(p[2] >= p_prev[2] for p_prev, p in zip(recent_points, recent_points[1:]))
                    stats["constant_growth_pattern"] = is_growing
        
        # Adicionar informações sobre falhas de conexão
        if hasattr(self, "_consecutive_failures"):
            stats["consecutive_failures"] = self._consecutive_failures
            stats["failure_types"] = self._failure_types
            
        return stats

    def _check_pool_health(self):
        """Verifica a saúde do pool de conexões e detecta possíveis vazamentos"""
        if not self.pool:
            return

        try:
            # Inicializar histórico de uso se não existir
            if not hasattr(self, "_usage_history"):
                self._usage_history = []
                self._connection_tracking = {}
                self._last_leak_check = time.time()
                self._last_connection_dump = 0

            # Verificar se há muitas conexões em uso por muito tempo
            usage_ratio = (
                self.metrics.active_connections / self.maxconn
                if self.maxconn > 0
                else 0
            )
            usage_percent = usage_ratio * 100
            
            # Manter histórico de uso para análise de tendências
            current_time = time.time()
            self._usage_history.append((current_time, usage_ratio, self.metrics.active_connections))
            # Limitar o histórico a 24 horas (288 pontos com intervalo de 5 minutos)
            if len(self._usage_history) > 288:
                self._usage_history.pop(0)
            
            # Calcular tendência de uso nas últimas horas
            if len(self._usage_history) >= 12:  # Pelo menos 1 hora de dados
                # Calcular taxa de crescimento do uso do pool
                hour_ago = current_time - 3600
                recent_points = [p for p in self._usage_history if p[0] >= hour_ago]
                if recent_points:
                    start_usage = recent_points[0][2]  # Conexões em uso 1 hora atrás
                    current_usage = self.metrics.active_connections
                    growth_rate = current_usage - start_usage
                    self._pool_stats["hourly_growth_rate"] = growth_rate
                    
                    # Alertar se houver crescimento constante (possível vazamento)
                    if growth_rate > 5 and all(p[2] >= p_prev[2] for p_prev, p in zip(recent_points, recent_points[1:])):
                        logger.warning(
                            f"Possível vazamento de conexões detectado: crescimento constante de {growth_rate} "
                            f"conexões na última hora. Uso atual: {current_usage}/{self.maxconn}"
                        )

            # Registrar estatísticas de uso do pool
            if usage_percent > 80:
                logger.warning(
                    f"Possível vazamento de conexões detectado: {self.metrics.active_connections}/{self.maxconn} conexões em uso ({usage_percent:.1f}%)"
                )

                # Verificar duração do problema
                if not hasattr(self, "_high_usage_start_time"):
                    self._high_usage_start_time = current_time
                elif (
                    current_time - self._high_usage_start_time > 300
                ):  # 5 minutos de uso alto
                    logger.error(
                        f"Uso elevado persistente do pool por mais de 5 minutos: {usage_percent:.1f}%"
                    )
                    # Forçar coleta de lixo para liberar conexões não utilizadas
                    import gc
                    gc.collect()
                    
                    # Tentar liberar conexões inativas
                    self._force_release_idle_connections()

            elif usage_percent > 60:
                logger.info(
                    f"Uso elevado do pool: {usage_percent:.1f}% ({self.metrics.active_connections}/{self.maxconn})"
                )
                if hasattr(self, "_high_usage_start_time"):
                    delattr(self, "_high_usage_start_time")
            else:
                if hasattr(self, "_high_usage_start_time"):
                    delattr(self, "_high_usage_start_time")

            # Se todas as conexões estiverem em uso, tentar resetar o pool
            if self.metrics.active_connections >= self.maxconn:
                logger.error("Pool de conexões esgotado. Tentando resetar o pool.")
                self.recreate_pool()
                self._pool_stats["pool_resets"] += 1

            # Verificar tempos de espera elevados
            if hasattr(self.metrics, "wait_times") and self.metrics.wait_times:
                avg_wait = sum(self.metrics.wait_times) / len(self.metrics.wait_times)
                if avg_wait > 500:  # Tempo médio de espera > 500ms
                    logger.warning(f"Tempo médio de espera elevado: {avg_wait:.2f}ms")
                    
            # Registrar estatísticas detalhadas periodicamente
            if current_time - self._last_leak_check > 1800:  # A cada 30 minutos
                self._last_leak_check = current_time
                logger.info(f"Estatísticas detalhadas do pool: {self.get_detailed_stats()}")

        except Exception as e:
            logger.error(f"Erro ao verificar saúde do pool: {e}")
            self._pool_stats["last_error"] = str(e)
            self._pool_stats["last_error_time"] = datetime.now().isoformat()

    def putconn(self, conn):
        """Retorna uma conexão ao pool"""
        if self.pool and conn:
            try:
                # Recuperar o ID da conexão para rastreamento
                conn_id = id(conn)
                
                # Registrar liberação da conexão
                self.metrics.track_connection_released(conn_id)
                
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

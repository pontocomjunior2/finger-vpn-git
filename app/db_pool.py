"""
Módulo de Pool de Conexões PostgreSQL
Resolve problemas de esgotamento de conexões e timeouts
"""

import logging
import os
import random
import threading
import time
import traceback
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta

import psycopg2
from dotenv import load_dotenv
from psycopg2 import pool

# Carregar variáveis de ambiente
load_dotenv(dotenv_path=".env")

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
        self.connection_threshold = (
            60  # Tempo em segundos para considerar uma conexão como suspeita
        )
        self.last_leak_check = time.time()
        self.leak_check_interval = 120  # 2 minutos
        self.last_metrics_log = time.time()
        self.metrics_log_interval = 300  # 5 minutos
        self.context_stats = {}  # Estatísticas por contexto de uso

    def record_request(self, wait_time_ms, success=True):
        with self._lock:
            self.total_requests += 1
            if not success:
                self.failed_requests += 1
            if wait_time_ms > 100:  # Log tempos de espera > 100ms (reduzido ruído)
                logger.warning(f"Pool connection wait time: {wait_time_ms:.2f}ms")
            self.wait_times.append(wait_time_ms)
            # Manter apenas os últimos 100 tempos
            if len(self.wait_times) > 100:
                self.wait_times.pop(0)

    def record_pool_exhausted(self):
        with self._lock:
            self.pool_exhausted_count += 1
            logger.error("Pool de conexões esgotado!")

    def track_connection_acquired(self, conn_id, context=None, stack_trace=None):
        """Registra quando uma conexão é adquirida

        Args:
            conn_id: ID único da conexão
            context: Contexto de uso da conexão (ex: nome da função)
            stack_trace: Stack trace no momento da aquisição
        """
        with self._lock:
            if not context:
                context = "unknown"

            if not stack_trace:
                stack_trace = "".join(traceback.format_stack())

            self.connection_tracking[conn_id] = {
                "acquired_at": time.time(),
                "context": context,
                "stack_trace": stack_trace,
            }

            # Atualizar estatísticas por contexto
            if context not in self.context_stats:
                self.context_stats[context] = {
                    "total_connections": 0,
                    "active_connections": 0,
                    "avg_duration": 0,
                    "max_duration": 0,
                }

            self.context_stats[context]["total_connections"] += 1
            self.context_stats[context]["active_connections"] += 1

    def track_connection_released(self, conn_id):
        """Registra quando uma conexão é liberada"""
        with self._lock:
            if conn_id in self.connection_tracking:
                acquired_time = self.connection_tracking[conn_id]["acquired_at"]
                duration = time.time() - acquired_time
                context = self.connection_tracking[conn_id].get("context", "unknown")

                # Se a conexão foi mantida por muito tempo, registrar como suspeita
                if duration > self.connection_threshold:
                    self.long_lived_connections[conn_id] = {
                        "duration": duration,
                        "context": context,
                        "stack_trace": self.connection_tracking[conn_id]["stack_trace"],
                    }
                    logger.warning(
                        f"Conexão {conn_id} mantida por {duration:.2f}s (acima do limite de {self.connection_threshold}s). Contexto: {context}"
                    )

                # Atualizar estatísticas do contexto
                if context in self.context_stats:
                    self.context_stats[context]["active_connections"] = max(
                        0, self.context_stats[context]["active_connections"] - 1
                    )

                    # Atualizar duração média e máxima
                    if duration > self.context_stats[context].get("max_duration", 0):
                        self.context_stats[context]["max_duration"] = duration

                    # Calcular média móvel
                    current_avg = self.context_stats[context].get("avg_duration", 0)
                    total_conns = self.context_stats[context].get(
                        "total_connections", 1
                    )
                    new_avg = current_avg + (duration - current_avg) / min(
                        total_conns, 100
                    )
                    self.context_stats[context]["avg_duration"] = new_avg

                # Remover do rastreamento
                del self.connection_tracking[conn_id]

    def check_for_connection_leaks(self):
        """Verifica conexões que podem estar vazando (não foram liberadas)"""
        with self._lock:
            current_time = time.time()
            leaked_connections = []

            for conn_id, data in list(self.connection_tracking.items()):
                duration = current_time - data["acquired_at"]
                if (
                    duration > self.connection_threshold * 2
                ):  # Tempo dobrado para considerar vazamento
                    leaked_connections.append((conn_id, duration, data["stack_trace"]))

            if leaked_connections:
                logger.warning(
                    f"Possíveis vazamentos de conexão detectados: {len(leaked_connections)} conexões"
                )
                for conn_id, duration, stack_trace in leaked_connections:
                    logger.warning(
                        f"Conexão {conn_id} em uso por {duration:.2f}s. Stack trace de aquisição:\n{stack_trace}"
                    )

            # Limpar conexões muito antigas do rastreamento (podem ser conexões perdidas)
            for conn_id, data in list(self.connection_tracking.items()):
                if current_time - data["acquired_at"] > 3600:  # 1 hora
                    logger.error(
                        f"Removendo conexão {conn_id} do rastreamento após 1 hora (provável vazamento)"
                    )
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
                "long_lived_connections": len(self.long_lived_connections),
            }


class DatabasePool:
    def __init__(self, minconn=3, maxconn=15):
        # Reduzido minconn de 5 para 3 e maxconn de 20 para 15 para evitar "too many clients already"
        self.minconn = minconn
        self.maxconn = maxconn
        self.pool = None
        self.metrics = PoolMetrics()
        self.max_retries = 3
        self.base_delay = 0.5  # Delay base para retry em segundos (otimizado)
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
                    "connect_timeout": 30,  # Otimizado para 30 segundos
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
    async def get_connection(self, context=None):
        """Gerenciador de contexto assíncrono para obter conexão do pool

        Args:
            context (str, optional): Contexto de uso da conexão para rastreamento. Defaults to None.
        """
        conn = None
        start_time = time.time()
        max_retries = 3  # Reduzido para 3 tentativas para resposta mais rápida
        base_delay = 0.1  # Delay base otimizado para menor latência
        connection_timeout = 60  # Timeout reduzido para 1 minuto

        # Capturar stack trace para diagnóstico de vazamentos
        import traceback

        stack_trace = traceback.format_stack()

        # Se o contexto não for fornecido, tentar inferir do stack trace
        if not context:
            # Analisar o stack trace para identificar o chamador
            for frame in stack_trace[-5:-1]:  # Olhar alguns frames acima
                if "fingerv7.py" in frame or "dashboard_api.py" in frame:
                    parts = frame.split("\n")[0].strip()
                    if "in " in parts:
                        context = parts.split("in ")[-1].strip()
                        break

            # Se ainda não tiver contexto, usar um valor padrão
            if not context:
                context = "unknown_context"

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
                    self.metrics.track_connection_acquired(
                        conn_id, context=context, stack_trace="".join(stack_trace)
                    )

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
                                    f"Conexão já fechada, não retornando ao pool. Contexto: {context}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Erro ao retornar conexão ao pool: {e}. Contexto: {context}"
                            )
                    return
                else:
                    raise psycopg2.OperationalError(
                        f"Não foi possível obter conexão do pool. Contexto: {context}"
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
                        f"Falha ao obter conexão após {max_retries} tentativas: {e}. Contexto: {context}"
                    )
                    raise

                # Delay exponencial com jitter
                delay = base_delay * (2**attempt) + random.uniform(0, 0.05)
                logger.warning(
                    f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.3f}s: {e}. Contexto: {context}"
                )
                await asyncio.sleep(delay)

            except Exception as e:
                wait_time_ms = (time.time() - start_time) * 1000
                self.metrics.record_request(wait_time_ms, success=False)
                logger.error(
                    f"Erro inesperado ao obter conexão: {e}. Contexto: {context}"
                )
                if conn:
                    try:
                        await asyncio.to_thread(self.pool.putconn, conn)
                    except Exception as put_err:
                        logger.error(
                            f"Erro ao retornar conexão ao pool: {put_err}. Contexto: {context}"
                        )
                raise

    def get_connection_sync(self):
        """Versão síncrona do gerenciador de contexto"""
        return self._get_connection_sync()

    @contextmanager
    def _get_connection_sync(self):
        """Gerenciador de contexto síncrono para obter conexão do pool"""
        conn = None
        start_time = time.time()
        max_retries = 3  # Reduzido para 3 tentativas para resposta mais rápida
        base_delay = 0.1  # Delay base otimizado para menor latência
        connection_timeout = 60  # Timeout reduzido para 1 minuto

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

    def handle_connection_failure(self, error, context=None):
        """Gerencia falhas de conexão com estratégia de retry avançada

        Args:
            error: O erro que ocorreu
            context: Contexto onde o erro ocorreu (ex: nome da função)
        """
        self._pool_stats["connection_errors"] += 1
        self._pool_stats["last_error"] = str(error)
        self._pool_stats["last_error_time"] = datetime.now().isoformat()
        error_str = str(error).lower()

        # Inicializar contador de falhas se não existir
        if not hasattr(self, "_consecutive_failures"):
            self._consecutive_failures = 0
            self._last_failure_time = None
            self._failure_types = {}
            self._failure_contexts = {}
            self._failure_frequency = []

        # Incrementar contador de falhas consecutivas
        self._consecutive_failures += 1
        self._last_failure_time = datetime.now()
        current_time = time.time()

        # Registrar frequência de falhas
        self._failure_frequency.append(current_time)
        if len(self._failure_frequency) > 100:
            self._failure_frequency.pop(0)

        # Calcular taxa de falhas por minuto
        one_minute_ago = current_time - 60
        recent_failures = [t for t in self._failure_frequency if t > one_minute_ago]
        failure_rate = len(recent_failures) / 1.0 if recent_failures else 0

        # Registrar tipo de falha para análise de padrões
        error_type = "unknown"
        if "connection refused" in error_str:
            error_type = "connection_refused"
        elif "too many connections" in error_str:
            error_type = "too_many_connections"
        elif "too many clients already" in error_str:
            error_type = "too_many_clients"
        elif "connection timed out" in error_str:
            error_type = "connection_timeout"
        elif "idle in transaction" in error_str:
            error_type = "idle_transaction"
        elif "deadlock detected" in error_str:
            error_type = "deadlock"
        elif "broken pipe" in error_str:
            error_type = "broken_pipe"

        # Incrementar contador para este tipo de erro
        self._failure_types[error_type] = self._failure_types.get(error_type, 0) + 1

        # Registrar contexto da falha
        if context:
            if context not in self._failure_contexts:
                self._failure_contexts[context] = {"count": 0, "types": {}}
            self._failure_contexts[context]["count"] += 1
            self._failure_contexts[context]["types"][error_type] = (
                self._failure_contexts[context]["types"].get(error_type, 0) + 1
            )
            self._failure_contexts[context]["last_error"] = str(error)
            self._failure_contexts[context]["last_time"] = current_time

        # Verificar se é necessário recriar o pool
        critical_error = (
            "connection refused" in error_str
            or "too many connections" in error_str
            or "too many clients already" in error_str
            or "connection timed out" in error_str
            or "cannot connect now" in error_str
            or "no connection to the server" in error_str
            or "broken pipe" in error_str
        )

        # Registrar informações detalhadas para diagnóstico
        logger.error(
            f"Falha de conexão: {error}. Contexto: {context}. Tipo: {error_type}. Taxa: {failure_rate:.1f}/min"
        )

        # Estratégia de recuperação baseada na gravidade e frequência
        if critical_error or self._consecutive_failures >= 5 or failure_rate > 10:
            # Registrar estatísticas de falha para diagnóstico
            failure_stats = {
                "consecutive": self._consecutive_failures,
                "types": self._failure_types,
                "rate": failure_rate,
                "context": context,
            }
            logger.warning(
                f"Detectado erro crítico de conexão: {error}. Recriando pool. "
                f"Falhas consecutivas: {self._consecutive_failures}. Estatísticas: {failure_stats}"
            )
            # Tentar liberar conexões inativas antes de recriar o pool
            self._force_release_idle_connections()
            self.recreate_pool()

            # Se muitas falhas consecutivas, aguardar um pouco antes de continuar
            if self._consecutive_failures >= 10 or failure_rate > 20:
                logger.error(
                    f"Muitas falhas consecutivas ({self._consecutive_failures}) ou taxa alta ({failure_rate:.1f}/min). Pausando operações."
                )
                time.sleep(5)  # Pausa mais longa para permitir recuperação do sistema

            return True

        # Resetar contador se última falha foi há mais de 5 minutos
        if self._last_failure_time and (
            datetime.now() - self._last_failure_time
        ) > timedelta(minutes=5):
            self._consecutive_failures = 1
            self._failure_types = {error_type: 1}

        return False

    def _force_release_idle_connections(self):
        """Força a liberação de conexões inativas no pool"""
        try:
            if not self.pool or self.pool.closed:
                logger.warning(
                    "Pool fechado ou não inicializado durante liberação de conexões"
                )
                return 0

            # Registrar estatísticas antes da limpeza
            before_active = self.metrics.active_connections
            before_pool_size = (
                len(self.pool._pool) if hasattr(self.pool, "_pool") else 0
            )

            logger.info("Tentando liberar conexões inativas")
            released = 0

            # Forçar coleta de lixo para liberar conexões não utilizadas
            import gc

            gc.collect()

            # Analisar conexões ativas por contexto
            context_counts = {}
            long_lived_connections = []
            current_time = time.time()

            for conn_id, info in list(self.metrics.connection_tracking.items()):
                context = info.get("context", "unknown")
                acquired_time = info.get("acquired_at", 0)
                duration = current_time - acquired_time

                # Contar conexões por contexto
                context_counts[context] = context_counts.get(context, 0) + 1

                # Identificar conexões de longa duração
                if duration > 600:  # 10 minutos
                    long_lived_connections.append((conn_id, duration, context))

            # Registrar informações sobre conexões ativas
            if context_counts:
                logger.warning(
                    f"Distribuição de conexões ativas por contexto: {context_counts}"
                )

            if long_lived_connections:
                # Ordenar por duração (mais longa primeiro)
                long_lived_connections.sort(key=lambda x: x[1], reverse=True)

                # Registrar as 5 conexões mais antigas
                top_connections = long_lived_connections[:5]
                logger.error(
                    f"Conexões mais antigas: {[(conn_id, f'{duration:.1f}s', ctx) for conn_id, duration, ctx in top_connections]}"
                )

                # Remover conexões muito antigas do rastreamento
                for conn_id, duration, _ in long_lived_connections:
                    if duration > 1800:  # 30 minutos
                        logger.error(
                            f"Removendo conexão {conn_id} do rastreamento (ativa por {duration:.1f}s)"
                        )
                        self.metrics.connection_tracking.pop(conn_id, None)

            # Tentar identificar conexões de longa duração
            if hasattr(self.metrics, "long_lived_connections"):
                for conn_id in list(self.metrics.long_lived_connections.keys()):
                    # Verificar se a conexão ainda está no rastreamento
                    if conn_id in self.metrics.connection_tracking:
                        logger.warning(f"Conexão de longa duração detectada: {conn_id}")
                        # Não podemos fechar diretamente, mas podemos registrar para debug
                    else:
                        # Remover do rastreamento de longa duração
                        self.metrics.long_lived_connections.pop(conn_id, None)

                # Limpar rastreamento se estiver muito grande
                if len(self.metrics.long_lived_connections) > 100:
                    logger.warning("Limpando rastreamento de conexões de longa duração")
                    self.metrics.long_lived_connections.clear()

            # Tentar identificar conexões específicas que podem estar inativas
            if hasattr(self.pool, "_used") and hasattr(self.pool, "_pool"):
                # Tentar identificar conexões problemáticas
                for conn in list(getattr(self.pool, "_used", {}).values()):
                    try:
                        # Verificar se a conexão está responsiva
                        cursor = conn.cursor()
                        cursor.execute("SELECT 1")
                        cursor.close()
                    except Exception:
                        # Conexão com problema - tentar fechar
                        try:
                            conn.close()
                            released += 1
                            logger.info("Conexão problemática fechada")
                        except Exception as e:
                            logger.error(f"Erro ao fechar conexão problemática: {e}")

            # Verificar se há conexões que podem ser fechadas no pool
            if hasattr(self.pool, "_pool"):
                closed_count = 0
                for conn in list(self.pool._pool):
                    try:
                        # Verificar se a conexão está fechada ou com erro
                        if hasattr(conn, "closed") and conn.closed:
                            self.pool._pool.remove(conn)
                            closed_count += 1
                    except Exception as conn_err:
                        logger.error(f"Erro ao verificar conexão: {conn_err}")

                if closed_count > 0:
                    logger.info(f"Removidas {closed_count} conexões fechadas do pool")
                    released += closed_count

            # Tentar recriar o pool em caso de uso muito elevado
            if (
                self.metrics.active_connections > self.maxconn * 0.7
            ):  # Reduzido para 70%
                logger.warning("Uso muito elevado do pool. Recriando o pool.")
                self.recreate_pool()
                released = self.maxconn  # Consideramos que todas foram liberadas

            # Registrar estatísticas após a limpeza
            after_active = self.metrics.active_connections
            after_pool_size = len(self.pool._pool) if hasattr(self.pool, "_pool") else 0

            logger.info(
                f"Resultado da limpeza: Conexões ativas antes={before_active}, depois={after_active}. "
                f"Tamanho do pool antes={before_pool_size}, depois={after_pool_size}"
            )

            logger.info(f"Liberadas {released} conexões inativas")
            return released
        except Exception as e:
            logger.error(f"Erro ao tentar liberar conexões inativas: {e}")
            import traceback

            logger.error(f"Stack trace: {traceback.format_exc()}")
            return 0

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
            if (
                current_time - self._last_pool_check > 180
            ):  # Verificar a cada 3 minutos (reduzido de 5 para 3)
                self._check_pool_health()
                self._last_pool_check = current_time

                # Verificar e limpar conexões vazadas
                if (
                    hasattr(self.metrics, "connection_tracking")
                    and len(self.metrics.connection_tracking) > 0
                ):
                    self._check_for_leaked_connections()

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
                    is_growing = all(
                        p[2] >= p_prev[2]
                        for p_prev, p in zip(recent_points, recent_points[1:])
                    )
                    stats["constant_growth_pattern"] = is_growing

                    # Calcular volatilidade (desvio padrão do uso)
                    if len(recent_points) >= 5:
                        import numpy as np

                        usage_values = [p[2] for p in recent_points]
                        stats["usage_volatility"] = float(np.std(usage_values))

        # Adicionar informações sobre falhas de conexão
        if hasattr(self, "_consecutive_failures"):
            stats["consecutive_failures"] = self._consecutive_failures
            stats["failure_types"] = self._failure_types

        # Adicionar métricas de vazamento de conexões
        if hasattr(self, "_leak_metrics"):
            stats["leak_metrics"] = {
                "total_leaks": self._leak_metrics["total_leaks"],
                "last_leak_time": self._leak_metrics["last_leak_time"],
                "leak_frequency_count": len(self._leak_metrics["leak_frequency"]),
            }

            # Calcular frequência de vazamentos (vazamentos por hora)
            if self._leak_metrics["leak_frequency"]:
                now = time.time()
                # Considerar apenas vazamentos nas últimas 24 horas
                recent_leaks = [
                    t for t in self._leak_metrics["leak_frequency"] if now - t < 86400
                ]
                if recent_leaks and len(recent_leaks) >= 2:
                    time_span = (recent_leaks[-1] - recent_leaks[0]) / 3600  # em horas
                    if time_span > 0:
                        leaks_per_hour = len(recent_leaks) / time_span
                        stats["leak_metrics"]["leaks_per_hour"] = round(
                            leaks_per_hour, 2
                        )

        # Adicionar informações sobre conexões ativas por tempo
        active_connections = []
        if hasattr(self.metrics, "connection_tracking"):
            current_time = time.time()
            for conn_id, info in self.metrics.connection_tracking.items():
                acquired_time = info.get("acquired_at", 0)
                duration = current_time - acquired_time
                active_connections.append(
                    (conn_id, duration, info.get("context", "unknown"))
                )

            # Ordenar por duração (mais longa primeiro)
            active_connections.sort(key=lambda x: x[1], reverse=True)

            # Adicionar as 5 conexões mais antigas
            if active_connections:
                stats["oldest_connections"] = [
                    {
                        "id": str(conn_id),
                        "duration_seconds": round(duration, 1),
                        "context": context,
                    }
                    for conn_id, duration, context in active_connections[:5]
                ]

                # Agrupar por contexto para identificar padrões
                context_counts = {}
                for _, _, context in active_connections:
                    context_counts[context] = context_counts.get(context, 0) + 1
                stats["connection_contexts"] = context_counts

        return stats

    def _check_for_leaked_connections(self):
        """Verifica e limpa conexões que podem ter vazado (não foram liberadas)"""
        try:
            current_time = time.time()
            leaked_connections = []

            # Identificar conexões que estão ativas há muito tempo (potenciais vazamentos)
            for conn_id, info in list(self.metrics.connection_tracking.items()):
                acquired_time = info.get("acquired_at", 0)
                duration = current_time - acquired_time

                # Conexões ativas por mais de 5 minutos são suspeitas de vazamento (reduzido de 10 para 5 minutos)
                if duration > 300:  # 5 minutos
                    leaked_connections.append((conn_id, duration))
                    # Registrar stack trace para depuração
                    stack_trace = info.get("stack_trace", "Stack trace não disponível")
                    context = info.get("context", "Contexto não disponível")
                    logger.warning(
                        f"Possível vazamento de conexão detectado. Ativa por {duration:.1f}s. Contexto: {context}. Stack trace: {stack_trace}"
                    )

                    # Marcar como verificado, mas manter no rastreamento para análise de tendências
                    info["leak_checked"] = True
                    info["leak_checked_at"] = current_time

                    # Se a conexão estiver ativa por mais de 15 minutos, tentar forçar sua liberação
                    if duration > 900:  # 15 minutos
                        logger.error(
                            f"Conexão {conn_id} ativa por {duration:.1f}s. Removendo do rastreamento."
                        )
                        self.metrics.connection_tracking.pop(conn_id, None)

            if leaked_connections:
                logger.error(
                    f"Detectados {len(leaked_connections)} possíveis vazamentos de conexão. Forçando limpeza do pool."
                )
                # Forçar limpeza do pool se houver muitos vazamentos
                if len(leaked_connections) >= 2:  # Reduzido de 3 para 2
                    self._force_release_idle_connections()

                # Registrar métricas de vazamento para monitoramento
                if not hasattr(self, "_leak_metrics"):
                    self._leak_metrics = {
                        "total_leaks": 0,
                        "last_leak_time": 0,
                        "leak_frequency": [],
                    }

                self._leak_metrics["total_leaks"] += len(leaked_connections)
                self._leak_metrics["last_leak_time"] = current_time
                self._leak_metrics["leak_frequency"].append(current_time)

                # Manter apenas as últimas 50 ocorrências para análise de frequência
                if len(self._leak_metrics["leak_frequency"]) > 50:
                    self._leak_metrics["leak_frequency"].pop(0)
        except Exception as e:
            logger.error(f"Erro ao verificar vazamentos de conexão: {e}")
            import traceback

            logger.error(f"Stack trace: {traceback.format_exc()}")

    def _check_pool_health(self):
        """Verifica a saúde do pool de conexões e detecta possíveis vazamentos"""
        if not self.pool:
            return

        try:
            # Inicializar histórico de uso se não existir
            if not hasattr(self, "_usage_history"):
                self._usage_history = []
                self._last_leak_check = time.time()
                self._last_health_report = 0
                self._health_check_interval = 900  # 15 minutos

            # Verificar se há muitas conexões em uso por muito tempo
            usage_ratio = (
                self.metrics.active_connections / self.maxconn
                if self.maxconn > 0
                else 0
            )
            usage_percent = usage_ratio * 100

            # Manter histórico de uso para análise de tendências
            current_time = time.time()
            self._usage_history.append(
                (current_time, usage_ratio, self.metrics.active_connections)
            )
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
                    if growth_rate > 5 and all(
                        p[2] >= p_prev[2]
                        for p_prev, p in zip(recent_points, recent_points[1:])
                    ):
                        logger.warning(
                            f"Possível vazamento de conexões detectado: crescimento constante de {growth_rate} "
                            f"conexões na última hora. Uso atual: {current_usage}/{self.maxconn}"
                        )
                        # Gerar relatório de saúde imediatamente em caso de suspeita de vazamento
                        self._generate_health_report()

            # Registrar estatísticas de uso do pool
            if usage_percent > 70:  # Reduzido de 80% para 70%
                logger.warning(
                    f"Possível vazamento de conexões detectado: {self.metrics.active_connections}/{self.maxconn} conexões em uso ({usage_percent:.1f}%)"
                )

                # Verificar duração do problema
                if not hasattr(self, "_high_usage_start_time"):
                    self._high_usage_start_time = current_time
                elif (
                    current_time - self._high_usage_start_time > 180
                ):  # Reduzido de 5 para 3 minutos
                    logger.error(
                        f"Uso elevado persistente do pool por mais de 3 minutos: {usage_percent:.1f}%"
                    )
                    # Forçar coleta de lixo para liberar conexões não utilizadas
                    import gc

                    gc.collect()

                    # Tentar liberar conexões inativas
                    self._force_release_idle_connections()

                    # Gerar relatório de saúde em caso de uso elevado persistente
                    self._generate_health_report()

            elif usage_percent > 50:  # Reduzido de 60% para 50%
                logger.info(
                    f"Uso elevado do pool: {usage_percent:.1f}% ({self.metrics.active_connections}/{self.maxconn})"
                )
                if hasattr(self, "_high_usage_start_time"):
                    delattr(self, "_high_usage_start_time")
            else:
                if hasattr(self, "_high_usage_start_time"):
                    delattr(self, "_high_usage_start_time")

            # Se todas as conexões estiverem em uso, tentar resetar o pool
            if (
                self.metrics.active_connections >= self.maxconn * 0.85
            ):  # Reduzido para 85% do máximo
                logger.error(
                    "Pool de conexões quase esgotado. Tentando resetar o pool."
                )
                self.recreate_pool()
                self._pool_stats["pool_resets"] += 1
                # Gerar relatório de saúde em caso de esgotamento do pool
                self._generate_health_report()

            # Verificar tempos de espera elevados
            if hasattr(self.metrics, "wait_times") and self.metrics.wait_times:
                avg_wait = sum(self.metrics.wait_times) / len(self.metrics.wait_times)
                if avg_wait > 300:  # Reduzido de 500ms para 300ms
                    logger.warning(f"Tempo médio de espera elevado: {avg_wait:.2f}ms")

            # Registrar estatísticas detalhadas periodicamente
            if current_time - self._last_leak_check > 1800:  # A cada 30 minutos
                self._last_leak_check = current_time
                logger.info(f"Verificação periódica de vazamentos de conexão")
                # Verificar e limpar conexões vazadas
                self._check_for_leaked_connections()

            # Gerar relatório de saúde periodicamente
            if current_time - self._last_health_report > self._health_check_interval:
                self._last_health_report = current_time
                self._generate_health_report()

        except Exception as e:
            logger.error(f"Erro ao verificar saúde do pool: {e}")
            self._pool_stats["last_error"] = str(e)
            self._pool_stats["last_error_time"] = datetime.now().isoformat()
            import traceback

            logger.error(f"Stack trace: {traceback.format_exc()}")

    def _generate_health_report(self):
        """Gera um relatório detalhado de saúde do pool de conexões"""
        try:
            # Obter estatísticas detalhadas
            stats = self.get_detailed_stats()

            # Formatar relatório
            report = ["=== RELATÓRIO DE SAÚDE DO POOL DE CONEXÕES ==="]
            report.append(f"Timestamp: {datetime.now().isoformat()}")
            report.append(
                f"Conexões ativas: {self.metrics.active_connections}/{self.maxconn} ({self.metrics.active_connections/self.maxconn*100:.1f}%)"
            )

            # Estatísticas de uso
            if "avg_usage_last_hour" in stats:
                report.append(
                    f"Uso médio na última hora: {stats['avg_usage_last_hour']:.1f} conexões"
                )
            if "usage_growth_last_hour" in stats:
                report.append(
                    f"Crescimento na última hora: {stats['usage_growth_last_hour']} conexões"
                )
            if "constant_growth_pattern" in stats:
                report.append(
                    f"Padrão de crescimento constante: {stats['constant_growth_pattern']}"
                )
            if "usage_volatility" in stats:
                report.append(f"Volatilidade de uso: {stats['usage_volatility']:.2f}")

            # Estatísticas de vazamento
            if "leak_metrics" in stats:
                leak_metrics = stats["leak_metrics"]
                report.append("\n--- Métricas de Vazamento ---")
                report.append(
                    f"Total de vazamentos detectados: {leak_metrics['total_leaks']}"
                )
                if "leaks_per_hour" in leak_metrics:
                    report.append(
                        f"Taxa de vazamentos: {leak_metrics['leaks_per_hour']}/hora"
                    )

            # Conexões mais antigas
            if "oldest_connections" in stats and stats["oldest_connections"]:
                report.append("\n--- Conexões Mais Antigas ---")
                for i, conn in enumerate(stats["oldest_connections"]):
                    report.append(
                        f"{i+1}. ID: {conn['id']}, Duração: {conn['duration_seconds']}s, Contexto: {conn['context']}"
                    )

            # Distribuição por contexto
            if "connection_contexts" in stats and stats["connection_contexts"]:
                report.append("\n--- Distribuição por Contexto ---")
                for ctx, count in sorted(
                    stats["connection_contexts"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]:
                    report.append(f"{ctx}: {count} conexões")

            # Estatísticas de falhas
            if hasattr(self, "_failure_types") and self._failure_types:
                report.append("\n--- Tipos de Falhas ---")
                for error_type, count in sorted(
                    self._failure_types.items(), key=lambda x: x[1], reverse=True
                ):
                    report.append(f"{error_type}: {count} ocorrências")

            # Estatísticas de contexto de falhas
            if hasattr(self, "_failure_contexts") and self._failure_contexts:
                report.append("\n--- Contextos com Mais Falhas ---")
                for ctx, data in sorted(
                    self._failure_contexts.items(),
                    key=lambda x: x[1]["count"],
                    reverse=True,
                )[:5]:
                    report.append(
                        f"{ctx}: {data['count']} falhas, Último erro: {data.get('last_error', 'N/A')}"
                    )

            # Registrar relatório
            logger.info("\n".join(report))

            # Salvar estatísticas para análise futura
            self._pool_stats["last_health_report"] = {
                "timestamp": datetime.now().isoformat(),
                "stats": stats,
            }

            # Ajustar intervalo de verificação com base na saúde do pool
            # Se houver problemas, verificar com mais frequência
            if stats.get("constant_growth_pattern", False) or (
                "leak_metrics" in stats
                and stats["leak_metrics"].get("leaks_per_hour", 0) > 1
            ):
                self._health_check_interval = 300  # 5 minutos
            else:
                self._health_check_interval = 900  # 15 minutos

        except Exception as e:
            logger.error(f"Erro ao gerar relatório de saúde: {e}")
            import traceback

            logger.error(f"Stack trace: {traceback.format_exc()}")

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

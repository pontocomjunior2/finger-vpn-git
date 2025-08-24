"""
Sistema de fila assíncrona para inserções no banco de dados
Implementa um worker único para evitar concorrência em operações de INSERT
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


@dataclass
class InsertTask:
    """Representa uma tarefa de inserção na fila"""

    data: Dict[str, Any]
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self):
        """Converte para dicionário para logging"""
        return {
            "data": self.data,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


class AsyncInsertQueue:
    """
    Fila assíncrona para inserções no banco de dados
    Implementa um worker único para evitar concorrência
    """

    def __init__(self, max_queue_size: int = 10000, batch_size: int = 200):
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.batch_size = (
            batch_size  # Aumentado para 100 para reduzir número de conexões
        )
        self.worker_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.processing_lock = (
            asyncio.Lock()
        )  # Lock para evitar processamento concorrente
        self.stats = {
            "total_queued": 0,
            "total_processed": 0,
            "total_failed": 0,
            "queue_full_count": 0,
            "last_batch_time": None,
            "avg_processing_time": 0.0,
            "worker_restarts": 0,
        }
        self._processing_times = []

    async def start_worker(self):
        """Inicia o worker assíncrono"""
        if self.is_running:
            logger.warning("Worker já está em execução")
            return

        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Worker de inserção assíncrona iniciado")

    async def stop_worker(self):
        """Para o worker assíncrono"""
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Worker de inserção assíncrona parado")

    async def add_insert_task(self, data: Dict[str, Any]) -> bool:
        """
        Adiciona uma tarefa de inserção à fila

        Args:
            data: Dados para inserção

        Returns:
            bool: True se adicionado com sucesso, False se fila cheia
        """
        try:
            # Garantir compatibilidade: mapear server_id para identified_by se necessário
            if "server_id" in data and "identified_by" not in data:
                data["identified_by"] = data["server_id"]
                logger.debug(
                    f"Mapeando server_id para identified_by: {data['server_id']}"
                )

            task = InsertTask(data=data, timestamp=time.time())

            # Tentar adicionar à fila sem bloquear
            self.queue.put_nowait(task)
            self.stats["total_queued"] += 1

            logger.debug(
                f"Tarefa adicionada à fila: {task.data.get('name', 'unknown')}"
            )
            return True

        except asyncio.QueueFull:
            self.stats["queue_full_count"] += 1
            logger.warning(
                f"Fila de inserção cheia ({self.queue.qsize()}/{self.queue.maxsize})"
            )
            return False

    async def _worker_loop(self):
        """Loop principal do worker"""
        logger.info("Worker loop iniciado")

        # Variáveis para backoff exponencial (otimizado)
        base_delay = 0.05
        max_delay = 15
        current_delay = base_delay
        consecutive_errors = 0
        max_consecutive_errors = 10

        # Variáveis para monitoramento do pool
        last_pool_check = time.time()
        pool_check_interval = 60  # Verificar o pool a cada 60 segundos

        while self.is_running:
            try:
                # Verificar estado do pool periodicamente
                current_time = time.time()
                if current_time - last_pool_check > pool_check_interval:
                    await self._check_db_pool_health()
                    last_pool_check = current_time

                # Coletar tarefas em lote
                batch = await self._collect_batch()

                if batch:
                    await self._process_batch(batch)

                # Resetar o backoff após sucesso
                current_delay = base_delay
                consecutive_errors = 0

            except asyncio.CancelledError:
                logger.info("Worker cancelado")
                break
            except Exception as e:
                # Incrementar contador de erros consecutivos
                consecutive_errors += 1

                # Verificar se é um erro de pool de conexões
                error_str = str(e).lower()
                if (
                    "connection pool exhausted" in error_str
                    or "timeout" in error_str
                    or "too many connections" in error_str
                    or "connection refused" in error_str
                    or "operational error" in error_str
                ):
                    logger.error(f"Erro de pool de conexões: {e}")
                    # Aumentar o delay para dar tempo ao pool se recuperar
                    current_delay = min(current_delay * 2, max_delay)
                    # Forçar verificação do pool na próxima iteração
                    last_pool_check = 0

                    # Tentar recuperar o pool de conexões
                    try:
                        from db_pool import get_db_pool

                        # Verificar se o pool precisa ser recriado
                        if get_db_pool().handle_connection_failure(e):
                            logger.info("Pool de conexões recriado após falha")
                    except Exception as pool_error:
                        logger.error(f"Erro ao tentar recuperar pool: {pool_error}")
                else:
                    logger.error(f"Erro no worker loop: {e}")

                self.stats["worker_restarts"] += 1

                # Aplicar backoff exponencial
                import random

                backoff_time = current_delay * (
                    0.5 + random.random()
                )  # Adicionar jitter
                logger.warning(
                    f"Aguardando {backoff_time:.2f}s antes de tentar novamente (erros consecutivos: {consecutive_errors})"
                )
                await asyncio.sleep(backoff_time)

                # Se muitos erros consecutivos, forçar uma pausa maior
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(
                        f"Muitos erros consecutivos ({consecutive_errors}). Pausando worker por 60 segundos."
                    )
                    await asyncio.sleep(60)
                    consecutive_errors = 0  # Resetar contador após pausa longa

        logger.info("Worker loop finalizado")

    async def _check_db_pool_health(self):
        """Verifica a saúde do pool de conexões do banco de dados"""
        try:
            from db_pool import get_db_pool

            # Obter estatísticas do pool
            pool_stats = get_db_pool().get_pool_stats()

            # Registrar métricas no log
            if "active_connections" in pool_stats and "pool_max_conn" in pool_stats:
                used = pool_stats["active_connections"]
                free = pool_stats.get("pool_max_conn", 0) - used
                max_conn = pool_stats.get("pool_max_conn", 0)

                # Calcular porcentagem de uso
                usage_percent = (used / max_conn) * 100 if max_conn > 0 else 0

                # Registrar no log com nível apropriado
                if usage_percent > 80:
                    logger.warning(
                        f"Pool de conexões com uso elevado: {usage_percent:.1f}% ({used}/{max_conn})"
                    )
                elif usage_percent > 50:
                    logger.info(
                        f"Pool de conexões com uso moderado: {usage_percent:.1f}% ({used}/{max_conn})"
                    )
                else:
                    logger.debug(
                        f"Pool de conexões com uso normal: {usage_percent:.1f}% ({used}/{max_conn})"
                    )

                # Registrar estatísticas detalhadas em nível de debug
                if "pool_stats" in pool_stats:
                    logger.debug(f"Estatísticas do pool: {pool_stats['pool_stats']}")

        except Exception as e:
            logger.error(f"Erro ao verificar saúde do pool: {e}")
            # Não propagar a exceção para não interromper o worker

    async def _collect_batch(self) -> list[InsertTask]:
        """Coleta um lote de tarefas da fila com controle de fluxo adaptativo"""
        batch = []

        # Determinar tamanho do lote baseado no estado do pool de conexões
        current_batch_size = self._get_adaptive_batch_size()

        try:
            # Aguardar primeira tarefa (bloqueia se fila vazia)
            first_task = await asyncio.wait_for(self.queue.get(), timeout=5.0)
            batch.append(first_task)

            # Coletar tarefas adicionais sem bloquear
            while len(batch) < current_batch_size:
                try:
                    task = self.queue.get_nowait()
                    batch.append(task)
                except asyncio.QueueEmpty:
                    break

            # Se o lote for muito pequeno e houver muitas tarefas na fila, aguardar um pouco
            # para permitir que mais tarefas cheguem e possam ser processadas em conjunto
            if len(batch) < 10 and self.queue.qsize() > 50:
                logger.debug(
                    f"Aguardando mais tarefas chegarem (lote atual: {len(batch)}, fila: {self.queue.qsize()})"
                )
                await asyncio.sleep(0.2)  # Pausa maior para acumular mais tarefas

                # Tentar pegar mais algumas tarefas após a pausa
                try:
                    remaining = min(
                        current_batch_size - len(batch), 30
                    )  # Aumentado para 30 tarefas adicionais
                    for _ in range(remaining):
                        task = self.queue.get_nowait()
                        batch.append(task)
                except asyncio.QueueEmpty:
                    pass

        except asyncio.TimeoutError:
            # Timeout normal, continuar loop
            pass

        if batch:
            logger.debug(
                f"Coletado lote de {len(batch)} tarefas (tamanho adaptativo: {current_batch_size})"
            )

        return batch

    def _get_adaptive_batch_size(self) -> int:
        """Determina o tamanho do lote baseado no estado do sistema"""
        try:
            from db_pool import get_db_pool

            # Tentar obter estatísticas do pool
            pool_stats = get_db_pool().get_pool_stats()

            # Se o pool estiver com uso elevado, reduzir o tamanho do lote
            if "active_connections" in pool_stats and "pool_max_conn" in pool_stats:
                used = pool_stats.get("active_connections", 0)
                max_conn = pool_stats.get("pool_max_conn", 1)
                usage_ratio = used / max_conn if max_conn > 0 else 0

                if usage_ratio > 0.9:  # Mais de 90% do pool em uso
                    # Reduzir drasticamente o tamanho do lote
                    return max(20, int(self.batch_size * 0.2))
                elif usage_ratio > 0.7:  # Mais de 70% do pool em uso
                    # Reduzir moderadamente o tamanho do lote
                    return max(40, int(self.batch_size * 0.4))
                elif usage_ratio > 0.5:  # Mais de 50% do pool em uso
                    # Reduzir levemente o tamanho do lote
                    return max(60, int(self.batch_size * 0.6))

            # Verificar o tamanho da fila
            queue_size = self.queue.qsize()
            if queue_size > 2000:  # Fila extremamente grande
                # Aumentar significativamente o tamanho do lote para processar mais rapidamente
                return min(int(self.batch_size * 1.5), 300)
            elif queue_size > 1000:  # Fila muito grande
                # Aumentar o tamanho do lote para processar mais rapidamente
                return min(int(self.batch_size * 1.3), 250)

        except Exception as e:
            logger.warning(f"Erro ao calcular tamanho adaptativo do lote: {e}")

        # Valor padrão se não conseguir determinar um tamanho adaptativo
        return self.batch_size

    async def _process_batch(self, batch: list[InsertTask]):
        """Processa um lote de tarefas com mecanismo de retry robusto"""
        start_time = time.time()
        successful_inserts = 0
        failed_inserts = 0

        # Usar lock para evitar processamento concorrente
        async with self.processing_lock:
            try:
                from db_pool import get_db_pool
                import random

                # Usar pool de conexões para inserção em lote
                # Obter conexão com timeout mais longo
                max_conn_retries = 3
                conn_retry_count = 0
                conn_retry_delay = 1  # segundos inicial

                while conn_retry_count <= max_conn_retries:
                    try:
                        async with get_db_pool().get_connection() as conn:
                            cursor = conn.cursor()

                            # Processar em grupos maiores para reduzir o número de transações
                            chunk_size = 100  # Aumentado para 100 para reduzir número de transações

                            for i in range(0, len(batch), chunk_size):
                                chunk = batch[i : i + chunk_size]
                                chunk_retry_count = 0
                                max_chunk_retries = 2

                                while chunk_retry_count <= max_chunk_retries:
                                    try:
                                        # Iniciar transação para o chunk
                                        cursor.execute("BEGIN")

                                        for task in chunk:
                                            try:
                                                await self._insert_single_task(
                                                    cursor, task
                                                )
                                                successful_inserts += 1

                                            except Exception as e:
                                                failed_inserts += 1

                                                # Tentar novamente se não excedeu limite
                                                if task.retry_count < task.max_retries:
                                                    task.retry_count += 1
                                                    await self.queue.put(task)
                                                    logger.warning(
                                                        f"Recolocando tarefa na fila (tentativa {task.retry_count}): {e}"
                                                    )
                                                else:
                                                    logger.error(
                                                        f"Tarefa falhou após {task.max_retries} tentativas: {e}"
                                                    )
                                                    self.stats["total_failed"] += 1

                                        # Commit da transação do chunk
                                        cursor.execute("COMMIT")
                                        # Se chegou aqui, processamento foi bem-sucedido
                                        break

                                    except Exception as chunk_error:
                                        # Rollback em caso de erro no chunk
                                        cursor.execute("ROLLBACK")
                                        chunk_retry_count += 1
                                        error_str = str(chunk_error).lower()

                                        # Verificar se é um erro de conexão ou de banco de dados
                                        db_error = any(
                                            err in error_str
                                            for err in [
                                                "connection",
                                                "timeout",
                                                "deadlock",
                                                "serialization",
                                                "operational error",
                                                "database is locked",
                                            ]
                                        )

                                        if (
                                            chunk_retry_count <= max_chunk_retries
                                            and db_error
                                        ):
                                            # Calcular delay com jitter para evitar thundering herd
                                            jitter = random.uniform(0.1, 0.5)
                                            current_delay = (
                                                conn_retry_delay
                                                * (2 ** (chunk_retry_count - 1))
                                                + jitter
                                            )

                                            logger.warning(
                                                f"Erro de banco ao processar chunk: {chunk_error}. "
                                                f"Tentativa {chunk_retry_count}/{max_chunk_retries}. "
                                                f"Aguardando {current_delay:.2f}s antes de retry."
                                            )
                                            await asyncio.sleep(current_delay)
                                        else:
                                            logger.error(
                                                f"Erro ao processar chunk após {chunk_retry_count} tentativas: {chunk_error}"
                                            )
                                            # Recolocar tarefas do chunk na fila
                                            for task in chunk:
                                                if task.retry_count < task.max_retries:
                                                    task.retry_count += 1
                                                    await self.queue.put(task)
                                                else:
                                                    self.stats["total_failed"] += 1
                                            break

                            # Commit das inserções bem-sucedidas
                            if successful_inserts > 0:
                                conn.commit()
                                self.stats["total_processed"] += successful_inserts
                        # Se chegou aqui, conexão foi bem-sucedida
                        break

                    except Exception as conn_error:
                        conn_retry_count += 1
                        error_str = str(conn_error).lower()

                        # Verificar se é um erro de conexão
                        conn_error_detected = any(
                            err in error_str
                            for err in [
                                "connection",
                                "timeout",
                                "too many connections",
                                "connection refused",
                            ]
                        )

                        if conn_retry_count <= max_conn_retries and conn_error_detected:
                            # Calcular delay com jitter para evitar thundering herd (otimizado)
                            jitter = random.uniform(0.05, 0.2)
                            current_delay = (
                                conn_retry_delay * (1.5 ** (conn_retry_count - 1))
                                + jitter
                            )

                            logger.warning(
                                f"Erro de conexão: {conn_error}. "
                                f"Tentativa {conn_retry_count}/{max_conn_retries}. "
                                f"Aguardando {current_delay:.2f}s antes de retry."
                            )

                            # Tentar recuperar o pool se necessário
                            try:
                                get_db_pool().handle_connection_failure(conn_error)
                            except Exception as pool_error:
                                logger.error(
                                    f"Erro ao tentar recuperar pool: {pool_error}"
                                )

                            await asyncio.sleep(current_delay)
                        else:
                            logger.error(
                                f"Erro de conexão após {conn_retry_count} tentativas: {conn_error}"
                            )
                            # Recolocar todas as tarefas na fila
                            for task in batch:
                                if task.retry_count < task.max_retries:
                                    task.retry_count += 1
                                    await self.queue.put(task)
                                else:
                                    self.stats["total_failed"] += 1
                            break

            except Exception as e:
                logger.error(f"Erro ao processar lote: {e}")
                # Recolocar todas as tarefas na fila
                for task in batch:
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        await self.queue.put(task)
                    else:
                        self.stats["total_failed"] += 1

            # Calcular tempo de processamento e atualizar estatísticas
            processing_time = time.time() - start_time
            self._update_processing_stats(processing_time)

            logger.info(
                f"Lote processado: {successful_inserts} sucessos, {failed_inserts} falhas em {processing_time:.3f}s"
            )

    async def _insert_single_task(self, cursor, task: InsertTask):
        """Insere uma única tarefa no banco com verificação atômica de duplicatas"""
        data = task.data

        try:
            # Validar dados mínimos necessários
            if not data.get("name"):
                logger.warning(f"Tarefa ignorada: nome ausente - {data}")
                return

            # Garantir que identified_by esteja presente
            if "identified_by" not in data and "server_id" in data:
                data["identified_by"] = data["server_id"]
                logger.debug(
                    f"_insert_single_task: Mapeando server_id para identified_by: {data['server_id']}"
                )
            elif "identified_by" not in data:
                # Se não tiver nem identified_by nem server_id, usar 0 como padrão
                data["identified_by"] = "0"
                logger.warning(
                    f"_insert_single_task: Usando identified_by padrão '0' para: {data.get('name')}"
                )

            # Preparar valores para verificação de duplicatas
            radio_name = data.get("name", "") or ""
            isrc = data.get("isrc", "") or ""
            song_title = data.get("song_title", "") or ""
            artist = data.get("artist", "") or ""
            current_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
            current_time = data.get("time", datetime.now().strftime("%H:%M:%S"))

            # Calcular timestamp de 10 minutos atrás para verificação mais ampla
            now = datetime.now()
            ten_minutes_ago = now - timedelta(minutes=10)

            # Verificação atômica com SELECT FOR UPDATE para prevenir condições de corrida
            # Usando uma transação mais robusta com verificação de duplicatas
            duplicate_check_query = """
            SELECT id FROM music_log 
            WHERE name = %s 
            AND (
                (isrc != '' AND isrc = %s) OR
                (isrc = '' AND song_title = %s AND artist = %s)
            )
            AND (date || ' ' || time)::timestamp >= %s
            FOR UPDATE SKIP LOCKED
            """

            cursor.execute(
                duplicate_check_query,
                (
                    radio_name,
                    isrc,
                    song_title,
                    artist,
                    ten_minutes_ago.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

            existing_records = cursor.fetchall()

            if existing_records:
                logger.debug(
                    f"Duplicata detectada e ignorada: {radio_name} - {song_title} ({artist}) - ID: {existing_records[0][0]}"
                )
                return

            # Verificação adicional por tempo exato para garantir que não há duplicatas
            # mesmo que o servidor esteja processando o mesmo segmento
            exact_check_query = """
            SELECT id FROM music_log 
            WHERE name = %s 
            AND date = %s 
            AND time = %s 
            AND (
                (isrc != '' AND isrc = %s) OR
                (isrc = '' AND song_title = %s AND artist = %s)
            )
            FOR UPDATE SKIP LOCKED
            """

            cursor.execute(
                exact_check_query,
                (radio_name, current_date, current_time, isrc, song_title, artist),
            )

            exact_records = cursor.fetchall()

            if exact_records:
                logger.debug(
                    f"Duplicata exata detectada e ignorada: {radio_name} - {song_title} ({artist})"
                )
                return

            # Query de inserção com todas as colunas da tabela
            insert_query = """
            INSERT INTO music_log (
                name, artist, song_title, date, time, identified_by,
                isrc, cidade, estado, regiao, segmento, label, genre
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name, artist, song_title, date, time) DO NOTHING
            RETURNING id
            """

            # Preparar valores com tratamento para nulos
            values = (
                radio_name,
                artist,
                song_title,
                data.get("date", "") or now.strftime("%Y-%m-%d"),
                data.get("time", "") or now.strftime("%H:%M:%S"),
                data.get("identified_by", 0) or 0,
                isrc,
                data.get("cidade", "") or "",
                data.get("estado", "") or "",
                data.get("regiao", "") or "",
                data.get("segmento", "") or "",
                data.get("label", "") or "",
                data.get("genre", "") or "",
            )

            # Executar a query
            cursor.execute(insert_query, values)

            # Verificar se a inserção foi bem-sucedida (retornou um ID)
            result = cursor.fetchone()
            if result and result[0]:
                logger.debug(
                    f"Inserção bem-sucedida: ID={result[0]} - {radio_name} - {song_title}"
                )
            else:
                logger.debug(
                    f"Registro já existente (ignorado): {radio_name} - {song_title}"
                )

        except Exception as e:
            # Capturar erros específicos para melhor diagnóstico
            error_msg = str(e).lower()

            if "duplicate key" in error_msg:
                logger.debug(
                    f"Registro duplicado ignorado: {data.get('name')} - {data.get('song_title')}"
                )
            elif "connection" in error_msg:
                logger.error(f"Erro de conexão ao inserir tarefa: {e}")
                raise  # Propagar erro de conexão para retry
            elif "timeout" in error_msg:
                logger.error(f"Timeout ao inserir tarefa: {e}")
                raise  # Propagar erro de timeout para retry
            elif "column" in error_msg and "does not exist" in error_msg:
                # Erro específico para coluna inexistente
                logger.error(f"Erro de esquema ao inserir tarefa: {e} - Dados: {data}")
                # Registrar detalhes adicionais para ajudar na depuração
                logger.error(
                    f"Colunas esperadas: name, artist, song_title, date, time, identified_by"
                )
                logger.error(f"Colunas fornecidas: {', '.join(data.keys())}")
                raise  # Propagar erro de esquema para retry
            else:
                logger.error(f"Erro ao inserir tarefa: {e} - Dados: {data}")
                raise  # Propagar outros erros para retry

    def _update_processing_stats(self, processing_time: float):
        """Atualiza estatísticas de processamento"""
        self.stats["last_batch_time"] = time.time()
        self._processing_times.append(processing_time)

        # Manter apenas os últimos 100 tempos para média móvel
        if len(self._processing_times) > 100:
            self._processing_times = self._processing_times[-100:]

        self.stats["avg_processing_time"] = sum(self._processing_times) / len(
            self._processing_times
        )

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da fila"""
        return {
            **self.stats,
            "queue_size": self.queue.qsize(),
            "queue_max_size": self.queue.maxsize,
            "is_running": self.is_running,
            "worker_active": self.worker_task is not None
            and not self.worker_task.done(),
        }

    async def wait_for_empty(self, timeout: float = 30.0):
        """Aguarda a fila esvaziar"""
        start_time = time.time()

        while self.queue.qsize() > 0 and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)

        return self.queue.qsize() == 0


# Instância global da fila
insert_queue = AsyncInsertQueue()

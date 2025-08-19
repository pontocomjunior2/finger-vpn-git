"""
Sistema de fila assíncrona para inserções no banco de dados
Implementa um worker único para evitar concorrência em operações de INSERT
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
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
            'data': self.data,
            'timestamp': self.timestamp,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries
        }

class AsyncInsertQueue:
    """
    Fila assíncrona para inserções no banco de dados
    Implementa um worker único para evitar concorrência
    """
    
    def __init__(self, max_queue_size: int = 10000, batch_size: int = 50):
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.batch_size = batch_size
        self.worker_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.stats = {
            'total_queued': 0,
            'total_processed': 0,
            'total_failed': 0,
            'queue_full_count': 0,
            'last_batch_time': None,
            'avg_processing_time': 0.0,
            'worker_restarts': 0
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
            task = InsertTask(
                data=data,
                timestamp=time.time()
            )
            
            # Tentar adicionar à fila sem bloquear
            self.queue.put_nowait(task)
            self.stats['total_queued'] += 1
            
            logger.debug(f"Tarefa adicionada à fila: {task.data.get('name', 'unknown')}")
            return True
            
        except asyncio.QueueFull:
            self.stats['queue_full_count'] += 1
            logger.warning(f"Fila de inserção cheia ({self.queue.qsize()}/{self.queue.maxsize})")
            return False
            
    async def _worker_loop(self):
        """Loop principal do worker"""
        logger.info("Worker loop iniciado")
        
        while self.is_running:
            try:
                # Coletar tarefas em lote
                batch = await self._collect_batch()
                
                if batch:
                    await self._process_batch(batch)
                    
            except asyncio.CancelledError:
                logger.info("Worker cancelado")
                break
            except Exception as e:
                logger.error(f"Erro no worker loop: {e}")
                self.stats['worker_restarts'] += 1
                # Aguardar antes de tentar novamente
                await asyncio.sleep(1)
                
        logger.info("Worker loop finalizado")
        
    async def _collect_batch(self) -> list[InsertTask]:
        """Coleta um lote de tarefas da fila"""
        batch = []
        
        try:
            # Aguardar primeira tarefa (bloqueia se fila vazia)
            first_task = await asyncio.wait_for(self.queue.get(), timeout=5.0)
            batch.append(first_task)
            
            # Coletar tarefas adicionais sem bloquear
            while len(batch) < self.batch_size:
                try:
                    task = self.queue.get_nowait()
                    batch.append(task)
                except asyncio.QueueEmpty:
                    break
                    
        except asyncio.TimeoutError:
            # Timeout normal, continuar loop
            pass
            
        return batch
        
    async def _process_batch(self, batch: list[InsertTask]):
        """Processa um lote de tarefas"""
        start_time = time.time()
        
        try:
            from db_pool import db_pool
            
            # Usar pool de conexões para inserção em lote
            async with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                successful_inserts = 0
                failed_inserts = 0
                
                for task in batch:
                    try:
                        await self._insert_single_task(cursor, task)
                        successful_inserts += 1
                        
                    except Exception as e:
                        failed_inserts += 1
                        
                        # Tentar novamente se não excedeu limite
                        if task.retry_count < task.max_retries:
                            task.retry_count += 1
                            await self.queue.put(task)
                            logger.warning(f"Recolocando tarefa na fila (tentativa {task.retry_count}): {e}")
                        else:
                            logger.error(f"Tarefa falhou após {task.max_retries} tentativas: {e}")
                            self.stats['total_failed'] += 1
                
                # Commit das inserções bem-sucedidas
                if successful_inserts > 0:
                    conn.commit()
                    self.stats['total_processed'] += successful_inserts
                    
                processing_time = time.time() - start_time
                self._update_processing_stats(processing_time)
                
                logger.info(f"Lote processado: {successful_inserts} sucessos, {failed_inserts} falhas em {processing_time:.3f}s")
                
        except Exception as e:
            logger.error(f"Erro ao processar lote: {e}")
            
            # Recolocar todas as tarefas na fila
            for task in batch:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    await self.queue.put(task)
                    
    async def _insert_single_task(self, cursor, task: InsertTask):
        """Insere uma única tarefa no banco"""
        data = task.data
        
        # Query de inserção
        insert_query = """
        INSERT INTO music_log (name, artist, song_title, date, time, server_id, ip_address, port)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (name, artist, song_title, date, time) DO NOTHING
        """
        
        values = (
            data.get('name'),
            data.get('artist'),
            data.get('song_title'),
            data.get('date'),
            data.get('time'),
            data.get('server_id'),
            data.get('ip_address'),
            data.get('port')
        )
        
        cursor.execute(insert_query, values)
        
    def _update_processing_stats(self, processing_time: float):
        """Atualiza estatísticas de processamento"""
        self.stats['last_batch_time'] = time.time()
        self._processing_times.append(processing_time)
        
        # Manter apenas os últimos 100 tempos para média móvel
        if len(self._processing_times) > 100:
            self._processing_times = self._processing_times[-100:]
            
        self.stats['avg_processing_time'] = sum(self._processing_times) / len(self._processing_times)
        
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da fila"""
        return {
            **self.stats,
            'queue_size': self.queue.qsize(),
            'queue_max_size': self.queue.maxsize,
            'is_running': self.is_running,
            'worker_active': self.worker_task is not None and not self.worker_task.done()
        }
        
    async def wait_for_empty(self, timeout: float = 30.0):
        """Aguarda a fila esvaziar"""
        start_time = time.time()
        
        while self.queue.qsize() > 0 and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)
            
        return self.queue.qsize() == 0

# Instância global da fila
insert_queue = AsyncInsertQueue()
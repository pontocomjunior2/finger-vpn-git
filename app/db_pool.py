import asyncio
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PoolMetrics:
    def __init__(self):
        self.requests = []
        self.active_connections = 0
        self.max_active_connections = 0
        self.pool_exhausted_events = 0

    def record_request(self, wait_time_ms, success):
        self.requests.append(
            {"wait_time": wait_time_ms, "success": success, "timestamp": time.time()}
        )
        if len(self.requests) > 1000:
            self.requests.pop(0)

    def record_pool_exhausted(self):
        self.pool_exhausted_events += 1

    def get_stats(self):
        if not self.requests:
            return {
                "avg_wait_time": 0,
                "success_rate": 100,
                "total_requests": 0,
                "active_connections": self.active_connections,
                "max_active_connections": self.max_active_connections,
                "pool_exhausted_events": self.pool_exhausted_events,
            }
        avg_wait_time = sum(r["wait_time"] for r in self.requests) / len(self.requests)
        success_rate = (
            sum(1 for r in self.requests if r["success"]) / len(self.requests) * 100
        )
        return {
            "avg_wait_time": avg_wait_time,
            "success_rate": success_rate,
            "total_requests": len(self.requests),
            "active_connections": self.active_connections,
            "max_active_connections": self.max_active_connections,
            "pool_exhausted_events": self.pool_exhausted_events,
        }


class DatabasePool:
    _instance = None
    _pool = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, min_conn=2, max_conn=15):
        if not hasattr(self, "_initialized"):
            self.min_conn = int(os.getenv("DB_MIN_CONN", min_conn))
            self.max_conn = int(os.getenv("DB_MAX_CONN", max_conn))
            self.metrics = PoolMetrics()
            self._initialized = True
            self._pool_stats = {
                "pool_resets": 0,
                "created_connections": 0,
                "closed_connections": 0,
                "connection_errors": 0,
                "last_error": None,
                "last_error_time": None,
            }

    async def create_pool(self):
        if self._pool and not self._pool._closed:
            return

        dsn = (
            f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
            f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        )

        for attempt in range(5):
            try:
                self._pool = await asyncpg.create_pool(
                    dsn,
                    min_size=self.min_conn,
                    max_size=self.max_conn,
                    timeout=30,
                    command_timeout=60,
                )
                logger.info(
                    f"Pool de conexões com o banco de dados criado com sucesso. Conexões: {self.min_conn}-{self.max_conn}"
                )
                return
            except Exception as e:
                logger.error(f"Falha ao criar pool de conexões: {e}")
                if attempt < 4:
                    delay = (2**attempt) + random.uniform(0, 1)
                    logger.info(f"Tentando novamente em {delay:.2f} segundos...")
                    await asyncio.sleep(delay)
                else:
                    logger.critical(
                        "Não foi possível criar o pool de conexões após várias tentativas."
                    )
                    raise

    @asynccontextmanager
    async def get_connection(self):
        if not self._pool:
            await self.create_pool()

        conn = None
        start_time = time.time()
        try:
            conn = await self._pool.acquire(timeout=10)
            self.metrics.active_connections += 1
            if self.metrics.active_connections > self.metrics.max_active_connections:
                self.metrics.max_active_connections = self.metrics.active_connections

            wait_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_request(wait_time_ms, success=True)

            yield conn
        except asyncio.TimeoutError:
            wait_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_request(wait_time_ms, success=False)
            self.metrics.record_pool_exhausted()
            logger.error(
                "Timeout ao adquirir conexão do pool. O pool pode estar esgotado."
            )
            raise
        except Exception as e:
            wait_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_request(wait_time_ms, success=False)
            logger.error(f"Erro inesperado ao adquirir conexão: {e}")
            raise
        finally:
            if conn:
                self.metrics.active_connections -= 1
                await self._pool.release(conn)

    async def close_pool(self):
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Pool de conexões fechado.")

    def get_pool_stats(self):
        if not self._pool:
            return {"status": "Not initialized"}

        return {
            "size": self._pool.get_size(),
            "free_size": self._pool.get_freesize(),
            "metrics": self.metrics.get_stats(),
            "internal_stats": self._pool_stats,
        }


async def get_db_pool():
    pool = DatabasePool()
    if not pool._pool:
        await pool.create_pool()
    return pool

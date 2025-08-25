#!/usr/bin/env python3
"""
Orquestrador Central para Distribuição de Streams

Este serviço gerencia a distribuição de streams entre múltiplas instâncias
do sistema de fingerprinting, eliminando duplicidades e garantindo
balanceamento de carga adequado.

Autor: Sistema de Fingerprinting
Data: 2025
"""

import asyncio
import logging
import os
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

# Configuração de logging (deve vir antes de qualquer uso do logger)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Importar psutil para métricas de sistema
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil não encontrado. Métricas de sistema não estarão disponíveis.")

# Carregar variáveis de ambiente
# Primeiro tenta carregar do .env da raiz do projeto
root_env_file = Path(__file__).parent.parent / ".env"
app_env_file = Path(__file__).parent / ".env"

if root_env_file.exists():
    load_dotenv(root_env_file)
    print(f"Orquestrador: Variáveis carregadas de {root_env_file}")
elif app_env_file.exists():
    load_dotenv(app_env_file)
    print(f"Orquestrador: Variáveis carregadas de {app_env_file}")
else:
    print("Orquestrador: Nenhum arquivo .env encontrado")

# Mapear variáveis POSTGRES_* para DB_* se necessário
if os.getenv("POSTGRES_HOST") and not os.getenv("DB_HOST"):
    os.environ["DB_HOST"] = os.getenv("POSTGRES_HOST")
if os.getenv("POSTGRES_DB") and not os.getenv("DB_NAME"):
    os.environ["DB_NAME"] = os.getenv("POSTGRES_DB")
if os.getenv("POSTGRES_USER") and not os.getenv("DB_USER"):
    os.environ["DB_USER"] = os.getenv("POSTGRES_USER")
if os.getenv("POSTGRES_PASSWORD") and not os.getenv("DB_PASSWORD"):
    os.environ["DB_PASSWORD"] = os.getenv("POSTGRES_PASSWORD")
if os.getenv("POSTGRES_PORT") and not os.getenv("DB_PORT"):
    os.environ["DB_PORT"] = os.getenv("POSTGRES_PORT")

# Configuração de logging já foi feita acima

# Configurações do banco de dados
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "radio_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "port": int(os.getenv("DB_PORT", 5432)),
}

# Configurações do orquestrador
MAX_STREAMS_PER_INSTANCE = int(os.getenv("MAX_STREAMS_PER_INSTANCE", 20))
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", 300))  # 5 minutos
REBALANCE_INTERVAL = int(os.getenv("REBALANCE_INTERVAL", 60))  # 1 minuto


# Modelos Pydantic
class InstanceRegistration(BaseModel):
    server_id: str
    ip: str
    port: int
    max_streams: int = MAX_STREAMS_PER_INSTANCE


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_free_gb: float
    disk_total_gb: float
    load_average: Optional[List[float]] = None
    uptime_seconds: Optional[float] = None


class HeartbeatRequest(BaseModel):
    server_id: str
    current_streams: int
    status: str = "active"
    system_metrics: Optional[SystemMetrics] = None


class StreamRequest(BaseModel):
    server_id: str
    requested_count: int = MAX_STREAMS_PER_INSTANCE


class StreamRelease(BaseModel):
    server_id: str
    stream_ids: List[int]


class DiagnosticRequest(BaseModel):
    server_id: str
    local_streams: List[int]  # Lista de stream IDs que a instância acredita ter
    local_stream_count: int


# Função de ciclo de vida da aplicação
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação FastAPI."""
    # Startup
    logger.info("Iniciando orquestrador...")
    orchestrator = StreamOrchestrator()
    orchestrator.create_tables()

    # Iniciar tarefas em background usando as funções independentes
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    failover_task_handle = asyncio.create_task(failover_monitor_task())

    # Armazenar referência do orquestrador no app
    app.state.orchestrator = orchestrator

    try:
        yield
    finally:
        # Shutdown
        logger.info("Encerrando orquestrador...")
        cleanup_task_handle.cancel()
        failover_task_handle.cancel()

        try:
            await cleanup_task_handle
        except asyncio.CancelledError:
            pass

        try:
            await failover_task_handle
        except asyncio.CancelledError:
            pass


# Aplicação FastAPI
app = FastAPI(
    title="Stream Orchestrator",
    description="Orquestrador central para distribuição de streams",
    version="1.0.0",
    lifespan=lifespan,
)


class StreamOrchestrator:
    """Classe principal do orquestrador de streams."""

    def __init__(self):
        self.db_config = DB_CONFIG
        self.active_instances: Dict[str, dict] = {}
        self.stream_assignments: Dict[int, str] = {}  # stream_id -> server_id

    def get_db_connection(self):
        """Obtém conexão com o banco de dados."""
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar com banco de dados: {e}")
            raise

    def create_tables(self):
        """Cria as tabelas necessárias para o orquestrador."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # Tabela de instâncias registradas
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_instances (
                    id SERIAL PRIMARY KEY,
                    server_id VARCHAR(50) UNIQUE NOT NULL,
                    ip VARCHAR(45) NOT NULL,
                    port INTEGER NOT NULL,
                    max_streams INTEGER DEFAULT 20,
                    current_streams INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'active',
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Criar índices para a tabela de instâncias
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_server_id ON orchestrator_instances(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_status ON orchestrator_instances(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_instances_heartbeat ON orchestrator_instances(last_heartbeat)"
            )

            # Tabela de atribuições de streams
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_stream_assignments (
                    id SERIAL PRIMARY KEY,
                    stream_id INTEGER NOT NULL,
                    server_id VARCHAR(50) NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active',
                    UNIQUE(stream_id)
                )
            """
            )

            # Criar índices para a tabela de atribuições
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_server_id ON orchestrator_stream_assignments(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_stream_id ON orchestrator_stream_assignments(stream_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_assignments_status ON orchestrator_stream_assignments(status)"
            )

            # Tabela de métricas de sistema das instâncias
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_instance_metrics (
                    id SERIAL PRIMARY KEY,
                    server_id VARCHAR(50) NOT NULL,
                    cpu_percent FLOAT,
                    memory_percent FLOAT,
                    memory_used_gb FLOAT,
                    memory_total_gb FLOAT,
                    disk_percent FLOAT,
                    disk_free_gb FLOAT,
                    disk_total_gb FLOAT,
                    load_average_1m FLOAT,
                    load_average_5m FLOAT,
                    load_average_15m FLOAT,
                    uptime_seconds FLOAT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (server_id) REFERENCES orchestrator_instances(server_id) ON DELETE CASCADE
                )
            """
            )

            # Criar índices para a tabela de métricas
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_server_id ON orchestrator_instance_metrics(server_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_recorded_at ON orchestrator_instance_metrics(recorded_at)"
            )

            # Tabela de histórico de rebalanceamentos
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_rebalance_history (
                    id SERIAL PRIMARY KEY,
                    rebalance_type VARCHAR(50) NOT NULL,
                    streams_moved INTEGER DEFAULT 0,
                    instances_affected INTEGER DEFAULT 0,
                    reason TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info("Tabelas do orquestrador criadas com sucesso")
            return True

        except Exception as e:
            logger.error(f"Erro ao criar tabelas: {e}")
            return False
            raise
        finally:
            cursor.close()
            conn.close()

    def get_available_streams(self) -> List[int]:
        """Obtém lista de streams disponíveis do banco de dados."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Buscar todos os streams disponíveis
            cursor.execute(
                """
                SELECT DISTINCT id 
                FROM streams 
                ORDER BY id
            """
            )

            all_streams = [row[0] for row in cursor.fetchall()]

            # Buscar streams já atribuídos
            cursor.execute(
                """
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE status = 'active'
            """
            )

            assigned_streams = set(row[0] for row in cursor.fetchall())

            # Retornar streams não atribuídos
            available_streams = [s for s in all_streams if s not in assigned_streams]

            logger.info(
                f"Streams disponíveis: {len(available_streams)}, Total: {len(all_streams)}"
            )
            return available_streams

        except Exception as e:
            logger.error(f"Erro ao buscar streams disponíveis: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def register_instance(self, registration: InstanceRegistration) -> dict:
        """Registra uma nova instância no orquestrador."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Verificar se é uma re-registração (instância já existe)
            cursor.execute(
                """
                SELECT server_id, current_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s
            """,
                (registration.server_id,),
            )

            existing_instance = cursor.fetchone()
            is_reregistration = existing_instance is not None

            # Inserir ou atualizar instância
            cursor.execute(
                """
                INSERT INTO orchestrator_instances 
                (server_id, ip, port, max_streams, current_streams, status, last_heartbeat)
                VALUES (%s, %s, %s, %s, 0, 'active', CURRENT_TIMESTAMP)
                ON CONFLICT (server_id) 
                DO UPDATE SET 
                    ip = EXCLUDED.ip,
                    port = EXCLUDED.port,
                    max_streams = EXCLUDED.max_streams,
                    current_streams = 0,
                    status = 'active',
                    last_heartbeat = CURRENT_TIMESTAMP
                RETURNING id
            """,
                (
                    registration.server_id,
                    registration.ip,
                    registration.port,
                    registration.max_streams,
                ),
            )

            instance_id = cursor.fetchone()[0]

            # Se é uma re-registração, liberar streams órfãos imediatamente
            if is_reregistration:
                logger.info(
                    f"Re-registração detectada para instância {registration.server_id}, liberando streams órfãos"
                )

                # Liberar todos os streams atribuídos à instância anterior
                cursor.execute(
                    """
                    DELETE FROM orchestrator_stream_assignments 
                    WHERE server_id = %s
                """,
                    (registration.server_id,),
                )

                released_count = cursor.rowcount
                if released_count > 0:
                    logger.info(
                        f"Liberados {released_count} streams órfãos da instância {registration.server_id}"
                    )

                    # Forçar reatribuição imediata dos streams liberados
                    try:
                        self._immediate_stream_rebalance(cursor, registration.server_id)
                    except Exception as e:
                        logger.warning(f"Erro na reatribuição imediata de streams: {e}")

            # Commit das alterações
            conn.commit()

            # Atualizar cache local
            self.active_instances[registration.server_id] = {
                "id": instance_id,
                "ip": registration.ip,
                "port": registration.port,
                "max_streams": registration.max_streams,
                "current_streams": 0,
                "status": "active",
                "last_heartbeat": datetime.now(),
            }

            # Verificar se deve fazer rebalanceamento automático
            should_rebalance = False

            if not is_reregistration:
                # Nova instância - verificar se há necessidade de rebalanceamento
                cursor.execute(
                    """
                    SELECT COUNT(*) as total_instances,
                           SUM(max_streams) as total_capacity,
                           (
                               SELECT COUNT(*) 
                               FROM orchestrator_stream_assignments 
                               WHERE status = 'active'
                           ) as total_assigned_streams
                    FROM orchestrator_instances 
                    WHERE status = 'active' 
                      AND last_heartbeat > NOW() - INTERVAL '1 minute'
                """
                )

                stats = cursor.fetchone()
                total_instances = stats[0]
                total_capacity = stats[1] or 0
                total_assigned_streams = stats[2] or 0

                # Rebalancear se:
                # 1. Há mais de uma instância ativa
                # 2. Há streams atribuídos
                # 3. A nova capacidade permite melhor distribuição
                if total_instances > 1 and total_assigned_streams > 0:
                    # Calcular se o rebalanceamento seria benéfico
                    # (diferença significativa na distribuição atual)
                    cursor.execute(
                        """
                        SELECT 
                            server_id,
                            current_streams,
                            max_streams
                        FROM orchestrator_instances 
                        WHERE status = 'active' 
                          AND last_heartbeat > NOW() - INTERVAL '1 minute'
                          AND server_id != %s
                        ORDER BY current_streams DESC
                    """,
                        (registration.server_id,),
                    )

                    other_instances = cursor.fetchall()

                    if other_instances:
                        max_load = max(inst[1] for inst in other_instances)
                        avg_load = total_assigned_streams / total_instances

                        # Rebalancear se a diferença for significativa (> 20% da média)
                        if max_load > avg_load * 1.2:
                            should_rebalance = True
                            logger.info(
                                f"Rebalanceamento automático ativado: carga máxima {max_load} > 20% da média {avg_load:.1f}"
                            )

            if is_reregistration:
                logger.info(
                    f"Instância {registration.server_id} re-registrada com sucesso (streams órfãos liberados)"
                )
            else:
                logger.info(
                    f"Instância {registration.server_id} registrada com sucesso"
                )

                # Executar rebalanceamento automático se necessário
                if should_rebalance:
                    try:
                        logger.info(
                            f"Iniciando rebalanceamento automático devido ao registro da nova instância {registration.server_id}"
                        )

                        # Fechar conexão atual antes do rebalanceamento
                        cursor.close()
                        conn.close()

                        # Executar rebalanceamento completo
                        self.rebalance_all_streams()

                        # Registrar histórico do rebalanceamento
                        conn = self.get_db_connection()
                        cursor = conn.cursor()

                        cursor.execute(
                            """
                            INSERT INTO orchestrator_rebalance_history 
                            (rebalance_type, reason, executed_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                        """,
                            (
                                "automatic",
                                f"Nova instância registrada: {registration.server_id}",
                            ),
                        )

                        conn.commit()

                        logger.info(
                            f"Rebalanceamento automático concluído para nova instância {registration.server_id}"
                        )

                    except Exception as e:
                        logger.error(f"Erro no rebalanceamento automático: {e}")
                        # Continuar mesmo se o rebalanceamento falhar

            return {
                "status": "registered",
                "server_id": registration.server_id,
                "max_streams": registration.max_streams,
                "reregistration": is_reregistration,
                "auto_rebalanced": should_rebalance,
            }

        except Exception as e:
            conn.rollback()
            logger.error(f"Erro ao registrar instância {registration.server_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Erro ao registrar instância: {e}"
            )
        finally:
            cursor.close()
            conn.close()

    def update_heartbeat(self, heartbeat: HeartbeatRequest) -> dict:
        """Atualiza o heartbeat de uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET last_heartbeat = CURRENT_TIMESTAMP,
                    current_streams = %s,
                    status = %s
                WHERE server_id = %s
                RETURNING id
            """,
                (heartbeat.current_streams, heartbeat.status, heartbeat.server_id),
            )

            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Instância não encontrada")

            instance_id = result[0]

            # Armazenar métricas de sistema se fornecidas
            if heartbeat.system_metrics:
                metrics = heartbeat.system_metrics
                
                # Extrair valores de load average da lista
                load_avg_1m = load_avg_5m = load_avg_15m = None
                if metrics.load_average and len(metrics.load_average) >= 3:
                    load_avg_1m = metrics.load_average[0]
                    load_avg_5m = metrics.load_average[1]
                    load_avg_15m = metrics.load_average[2]
                
                cursor.execute(
                    """
                    INSERT INTO orchestrator_instance_metrics 
                    (server_id, cpu_percent, memory_percent, memory_used_gb,
                     memory_total_gb, disk_percent, disk_free_gb, disk_total_gb,
                     load_average_1m, load_average_5m, load_average_15m, 
                     uptime_seconds, recorded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                    (
                        heartbeat.server_id,
                        metrics.cpu_percent,
                        metrics.memory_percent,
                        metrics.memory_used_gb,
                        metrics.memory_total_gb,
                        metrics.disk_percent,
                        metrics.disk_free_gb,
                        metrics.disk_total_gb,
                        load_avg_1m,
                        load_avg_5m,
                        load_avg_15m,
                        metrics.uptime_seconds,
                    ),
                )
                logger.debug(f"Métricas de sistema armazenadas para {heartbeat.server_id}")

            # Atualizar cache local
            if heartbeat.server_id in self.active_instances:
                self.active_instances[heartbeat.server_id].update(
                    {
                        "current_streams": heartbeat.current_streams,
                        "status": heartbeat.status,
                        "last_heartbeat": datetime.now(),
                    }
                )

            return {"status": "heartbeat_updated"}

        except Exception as e:
            logger.error(f"Erro ao atualizar heartbeat de {heartbeat.server_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Erro ao atualizar heartbeat: {e}"
            )
        finally:
            cursor.close()
            conn.close()

    def assign_streams(self, request: StreamRequest) -> dict:
        """Atribui streams para uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Verificar se instância existe e está ativa
            cursor.execute(
                """
                SELECT current_streams, max_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
            """,
                (request.server_id,),
            )

            instance_data = cursor.fetchone()
            if not instance_data:
                raise HTTPException(
                    status_code=404, detail="Instância não encontrada ou inativa"
                )

            current_streams, max_streams = instance_data
            available_slots = max_streams - current_streams

            if available_slots <= 0:
                return {
                    "status": "no_capacity",
                    "assigned_streams": [],
                    "message": "Instância já está na capacidade máxima",
                }

            # Buscar streams disponíveis
            available_streams = self.get_available_streams()
            streams_to_assign = min(
                available_slots, request.requested_count, len(available_streams)
            )

            if streams_to_assign == 0:
                return {
                    "status": "no_streams",
                    "assigned_streams": [],
                    "message": "Nenhum stream disponível para atribuição",
                }

            # Atribuir streams
            assigned_streams = available_streams[:streams_to_assign]

            for stream_id in assigned_streams:
                cursor.execute(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, status)
                    VALUES (%s, %s, 'active')
                """,
                    (stream_id, request.server_id),
                )

            # Atualizar contador de streams da instância
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = current_streams + %s
                WHERE server_id = %s
            """,
                (len(assigned_streams), request.server_id),
            )

            # Commit da transação
            conn.commit()

            logger.info(
                f"Atribuídos {len(assigned_streams)} streams para {request.server_id}"
            )

            return {
                "status": "assigned",
                "assigned_streams": assigned_streams,
                "count": len(assigned_streams),
            }

        except Exception as e:
            logger.error(f"Erro ao atribuir streams para {request.server_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Erro ao atribuir streams: {e}"
            )
        finally:
            cursor.close()
            conn.close()

    def release_streams(self, release: StreamRelease) -> dict:
        """Libera streams de uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            if not release.stream_ids:
                return {"status": "no_streams_to_release"}

            # Remover atribuições
            cursor.execute(
                """
                DELETE FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND stream_id = ANY(%s)
                RETURNING stream_id
            """,
                (release.server_id, release.stream_ids),
            )

            released_streams = [row[0] for row in cursor.fetchall()]

            # Atualizar contador de streams da instância
            if released_streams:
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET current_streams = GREATEST(0, current_streams - %s)
                    WHERE server_id = %s
                """,
                    (len(released_streams), release.server_id),
                )

            # Commit da transação
            conn.commit()

            logger.info(
                f"Liberados {len(released_streams)} streams de {release.server_id}"
            )

            return {
                "status": "released",
                "released_streams": released_streams,
                "count": len(released_streams),
            }

        except Exception as e:
            logger.error(f"Erro ao liberar streams de {release.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao liberar streams: {e}")
        finally:
            cursor.close()
            conn.close()

    def _immediate_stream_rebalance(self, cursor, reregistered_server_id: str):
        """Força reatribuição imediata de streams para instância re-registrada."""
        # Buscar streams não atribuídos
        cursor.execute(
            """
            SELECT id FROM streams 
            WHERE id NOT IN (
                SELECT stream_id FROM orchestrator_stream_assignments WHERE status = 'active'
            )
            LIMIT 50
        """
        )

        available_streams = cursor.fetchall()

        if available_streams:
            # Buscar capacidade da instância re-registrada
            cursor.execute(
                """
                SELECT max_streams, current_streams
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
            """,
                (reregistered_server_id,),
            )

            instance_info = cursor.fetchone()

            if instance_info:
                max_streams, current_streams = instance_info
                available_capacity = max_streams - current_streams
                streams_to_assign = min(len(available_streams), available_capacity)

                if streams_to_assign > 0:
                    assigned_count = 0
                    for i, (stream_id,) in enumerate(
                        available_streams[:streams_to_assign]
                    ):
                        cursor.execute(
                            """
                            INSERT INTO orchestrator_stream_assignments (stream_id, server_id, assigned_at)
                            VALUES (%s, %s, CURRENT_TIMESTAMP)
                        """,
                            (stream_id, reregistered_server_id),
                        )
                        assigned_count += 1

                    # Atualizar contador da instância
                    cursor.execute(
                        """
                        UPDATE orchestrator_instances 
                        SET current_streams = current_streams + %s
                        WHERE server_id = %s
                    """,
                        (assigned_count, reregistered_server_id),
                    )

                    logger.info(
                        f"Reatribuídos {assigned_count} streams imediatamente para instância re-registrada {reregistered_server_id}"
                    )

    def handle_orphaned_streams(self):
        """Detecta e reatribui streams órfãos automaticamente de forma mais agressiva."""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Encontrar streams órfãos (atribuídos a instâncias inativas)
            cursor.execute(
                """
                SELECT DISTINCT osa.stream_id 
                FROM orchestrator_stream_assignments osa
                JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
                WHERE oi.status = 'inactive' 
                   OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes'
            """
            )

            orphaned_streams = [row["stream_id"] for row in cursor.fetchall()]

            if orphaned_streams:
                logger.warning(
                    f"Detectados {len(orphaned_streams)} streams órfãos: {orphaned_streams}"
                )

                # Liberar streams órfãos
                cursor.execute(
                    """
                    DELETE FROM orchestrator_stream_assignments osa
                    USING orchestrator_instances oi
                    WHERE osa.server_id = oi.server_id
                    AND (oi.status = 'inactive' OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes')
                """
                )

                # Atualizar contadores das instâncias que perderam streams
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET current_streams = (
                        SELECT COUNT(*) 
                        FROM orchestrator_stream_assignments 
                        WHERE server_id = orchestrator_instances.server_id
                    )
                    WHERE server_id IN (
                        SELECT DISTINCT oi.server_id 
                        FROM orchestrator_instances oi
                        WHERE oi.status = 'inactive' 
                           OR oi.last_heartbeat < NOW() - INTERVAL '2 minutes'
                    )
                """
                )

                # Reatribuir todos os streams órfãos de uma vez usando distribuição otimizada
                if orphaned_streams:
                    self._redistribute_orphaned_streams_optimized(
                        cursor, orphaned_streams
                    )

                logger.info(
                    f"Failover automático concluído para {len(orphaned_streams)} streams"
                )

        except Exception as e:
            logger.error(f"Erro no failover automático: {e}")
        finally:
            cursor.close()
            conn.close()

    def _redistribute_orphaned_streams_optimized(self, cursor, orphaned_streams: list):
        """Redistribui streams órfãos de forma otimizada para balanceamento de carga."""
        try:
            # Buscar todas as instâncias ativas com suas capacidades e cargas atuais
            cursor.execute(
                """
                SELECT 
                    oi.server_id,
                    oi.max_streams,
                    COALESCE(COUNT(osa.stream_id), 0) as current_load,
                    (oi.max_streams - COALESCE(COUNT(osa.stream_id), 0)) as available_capacity
                FROM orchestrator_instances oi
                LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id
                WHERE oi.status = 'active' 
                  AND oi.last_heartbeat > NOW() - INTERVAL '1 minute'
                GROUP BY oi.server_id, oi.max_streams
                HAVING (oi.max_streams - COALESCE(COUNT(osa.stream_id), 0)) > 0
                ORDER BY current_load ASC, available_capacity DESC
            """
            )

            available_instances = cursor.fetchall()

            if not available_instances:
                logger.error(
                    "Nenhuma instância ativa com capacidade disponível para reatribuir streams órfãos"
                )
                return

            # Distribuir streams órfãos de forma balanceada
            assignments = []
            instance_index = 0

            for stream_id in orphaned_streams:
                # Encontrar a próxima instância com capacidade disponível
                attempts = 0
                while attempts < len(available_instances):
                    instance = available_instances[instance_index]

                    if instance["available_capacity"] > 0:
                        assignments.append((stream_id, instance["server_id"]))
                        # Reduzir capacidade disponível temporariamente para balanceamento
                        available_instances[instance_index] = {
                            **instance,
                            "available_capacity": instance["available_capacity"] - 1,
                            "current_load": instance["current_load"] + 1,
                        }
                        break

                    instance_index = (instance_index + 1) % len(available_instances)
                    attempts += 1

                if attempts >= len(available_instances):
                    logger.warning(
                        f"Não foi possível encontrar capacidade para stream {stream_id}"
                    )
                    break

                # Avançar para próxima instância para distribuição round-robin
                instance_index = (instance_index + 1) % len(available_instances)

            # Executar todas as atribuições em lote
            if assignments:
                cursor.executemany(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, assigned_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                """,
                    assignments,
                )

                # Atualizar contadores das instâncias
                for stream_id, server_id in assignments:
                    cursor.execute(
                        """
                        UPDATE orchestrator_instances 
                        SET current_streams = current_streams + 1
                        WHERE server_id = %s
                    """,
                        (server_id,),
                    )

                logger.info(
                    f"Reatribuídos {len(assignments)} streams órfãos para {len(set(a[1] for a in assignments))} instâncias"
                )

                # Log detalhado das atribuições
                for stream_id, server_id in assignments:
                    logger.debug(
                        f"Stream órfão {stream_id} reatribuído para instância {server_id}"
                    )

        except Exception as e:
            logger.error(f"Erro na redistribuição otimizada de streams órfãos: {e}")
            raise

    def rebalance_all_streams(self):
        """Rebalanceia todos os streams de forma igualitária entre todas as instâncias ativas."""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Buscar todas as instâncias ativas
            cursor.execute(
                """
                SELECT server_id, max_streams
                FROM orchestrator_instances 
                WHERE status = 'active' 
                  AND last_heartbeat > NOW() - INTERVAL '1 minute'
                ORDER BY server_id
            """
            )

            active_instances = cursor.fetchall()

            if not active_instances:
                logger.warning(
                    "Nenhuma instância ativa encontrada para rebalanceamento"
                )
                return

            # Buscar todos os streams atribuídos
            cursor.execute(
                """
                SELECT stream_id, server_id
                FROM orchestrator_stream_assignments
                WHERE status = 'active'
                ORDER BY stream_id
            """
            )

            current_assignments = cursor.fetchall()

            if not current_assignments:
                logger.info("Nenhum stream atribuído encontrado")
                return

            # Calcular distribuição ideal
            total_capacity = sum(
                instance["max_streams"] for instance in active_instances
            )
            total_streams = len(current_assignments)

            if total_streams > total_capacity:
                logger.error(
                    f"Número de streams ({total_streams}) excede capacidade total ({total_capacity})"
                )
                return

            # Calcular quantos streams cada instância deve ter
            target_distribution = {}
            remaining_streams = total_streams

            for i, instance in enumerate(active_instances):
                if i == len(active_instances) - 1:
                    # Última instância recebe os streams restantes
                    target_distribution[instance["server_id"]] = remaining_streams
                else:
                    # Distribuição proporcional baseada na capacidade
                    proportion = instance["max_streams"] / total_capacity
                    target_count = min(
                        int(total_streams * proportion),
                        remaining_streams,
                        instance["max_streams"],
                    )
                    target_distribution[instance["server_id"]] = target_count
                    remaining_streams -= target_count

            logger.info(f"Distribuição alvo: {target_distribution}")

            # Liberar todos os streams atuais
            cursor.execute(
                "DELETE FROM orchestrator_stream_assignments WHERE status = 'active'"
            )

            # Redistribuir streams de acordo com a distribuição alvo
            assignments = []
            stream_index = 0

            for server_id, target_count in target_distribution.items():
                for _ in range(target_count):
                    if stream_index < len(current_assignments):
                        stream_id = current_assignments[stream_index]["stream_id"]
                        assignments.append((stream_id, server_id))
                        stream_index += 1

            # Executar novas atribuições
            if assignments:
                cursor.executemany(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, assigned_at, status)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
                """,
                    assignments,
                )

                # Atualizar contadores das instâncias
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET current_streams = (
                        SELECT COUNT(*) 
                        FROM orchestrator_stream_assignments 
                        WHERE server_id = orchestrator_instances.server_id 
                          AND status = 'active'
                    )
                    WHERE status = 'active'
                """
                )

                # Log da nova distribuição
                cursor.execute(
                    """
                    SELECT 
                        oi.server_id,
                        oi.current_streams,
                        oi.max_streams
                    FROM orchestrator_instances oi
                    WHERE oi.status = 'active'
                    ORDER BY oi.server_id
                """
                )

                final_distribution = cursor.fetchall()
                logger.info(f"Rebalanceamento concluído. Nova distribuição:")
                for dist in final_distribution:
                    logger.info(
                        f"  {dist['server_id']}: {dist['current_streams']}/{dist['max_streams']} streams"
                    )

        except Exception as e:
            logger.error(f"Erro no rebalanceamento completo: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    async def cleanup_inactive_instances(self):
        """Remove instâncias inativas e reatribui seus streams."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Primeiro, executar failover automático
            self.handle_orphaned_streams()

            # Buscar instâncias inativas
            timeout_threshold = datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT)

            cursor.execute(
                """
                SELECT server_id, current_streams
                FROM orchestrator_instances 
                WHERE last_heartbeat < %s AND status = 'active'
            """,
                (timeout_threshold,),
            )

            inactive_instances = cursor.fetchall()

            for server_id, current_streams in inactive_instances:
                logger.warning(
                    f"Instância {server_id} inativa, liberando {current_streams} streams"
                )

                # Marcar instância como inativa
                cursor.execute(
                    """
                    UPDATE orchestrator_instances 
                    SET status = 'inactive', current_streams = 0
                    WHERE server_id = %s
                """,
                    (server_id,),
                )

                # Remover do cache local
                if server_id in self.active_instances:
                    del self.active_instances[server_id]

                logger.info(f"Instância {server_id} marcada como inativa")

            if inactive_instances:
                logger.info(
                    f"Limpeza concluída: {len(inactive_instances)} instâncias inativas removidas"
                )

        except Exception as e:
            logger.error(f"Erro durante limpeza de instâncias inativas: {e}")
        finally:
            cursor.close()
            conn.close()

    def get_orchestrator_status(self) -> dict:
        """Retorna status atual do orquestrador."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Estatísticas de instâncias
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_instances,
                    COUNT(*) FILTER (WHERE status = 'active') as active_instances,
                    COALESCE(SUM(current_streams), 0) as total_assigned_streams,
                    COALESCE(SUM(max_streams), 0) as total_capacity
                FROM orchestrator_instances
            """
            )

            instance_stats = cursor.fetchone()

            # Estatísticas de streams
            cursor.execute(
                """
                SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE status = 'active'
            """
            )

            assigned_streams = cursor.fetchone()[0]

            # Streams disponíveis
            available_streams = len(self.get_available_streams())

            return {
                "orchestrator_status": "active",
                "instances": {
                    "total": instance_stats[0],
                    "active": instance_stats[1],
                    "total_capacity": instance_stats[3],
                    "current_load": instance_stats[2],
                },
                "streams": {
                    "assigned": assigned_streams,
                    "available": available_streams,
                    "total": assigned_streams + available_streams,
                },
                "load_percentage": round(
                    (instance_stats[2] / max(instance_stats[3], 1)) * 100, 2
                ),
            }

        except Exception as e:
            logger.error(f"Erro ao obter status do orquestrador: {e}")
            return {"orchestrator_status": "error", "error": str(e)}
        finally:
            cursor.close()
            conn.close()


# Instância global do orquestrador
orchestrator = StreamOrchestrator()

# Endpoints da API


@app.post("/register")
async def register_instance(registration: InstanceRegistration):
    """Registra uma nova instância."""
    return orchestrator.register_instance(registration)


@app.post("/heartbeat")
async def heartbeat(heartbeat_req: HeartbeatRequest):
    """Atualiza heartbeat de uma instância."""
    return orchestrator.update_heartbeat(heartbeat_req)


@app.post("/streams/assign")
async def assign_streams(request: StreamRequest):
    """Atribui streams para uma instância."""
    return orchestrator.assign_streams(request)


@app.post("/streams/release")
async def release_streams(release: StreamRelease):
    """Libera streams de uma instância."""
    return orchestrator.release_streams(release)


@app.get("/health")
async def health_check():
    """Endpoint de health check para verificação de saúde."""
    try:
        # Verificar conexão com banco de dados
        conn = orchestrator.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()

        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/status")
async def get_status():
    """Retorna status do orquestrador."""
    return orchestrator.get_orchestrator_status()


@app.get("/instances")
async def get_instances():
    """Lista todas as instâncias registradas."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, registered_at, last_heartbeat
            FROM orchestrator_instances 
            ORDER BY registered_at DESC
        """
        )

        instances = cursor.fetchall()
        return {"instances": [dict(instance) for instance in instances]}

    except Exception as e:
        logger.error(f"Erro ao listar instâncias: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar instâncias: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/instances/{server_id}")
async def get_instance(server_id: str):
    """Retorna informações detalhadas de uma instância específica."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Obter informações da instância
        cursor.execute(
            """
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, registered_at, last_heartbeat
            FROM orchestrator_instances 
            WHERE server_id = %s
        """,
            (server_id,),
        )

        instance = cursor.fetchone()
        if not instance:
            raise HTTPException(
                status_code=404, detail=f"Instância {server_id} não encontrada"
            )

        # Obter streams atribuídos
        cursor.execute(
            """
            SELECT stream_id FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
            ORDER BY stream_id
        """,
            (server_id,),
        )

        assigned_streams = [row["stream_id"] for row in cursor.fetchall()]

        # Preparar resposta
        instance_data = dict(instance)
        instance_data["assigned_streams"] = assigned_streams

        return {"status": "success", "data": instance_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter instância {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter instância: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/streams/assignments")
async def get_stream_assignments():
    """Lista todas as atribuições de streams."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT osa.stream_id, osa.server_id, osa.assigned_at, osa.status,
                   oi.ip, oi.port
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
            ORDER BY osa.assigned_at DESC
        """
        )

        assignments = cursor.fetchall()
        return {"assignments": [dict(assignment) for assignment in assignments]}

    except Exception as e:
        logger.error(f"Erro ao listar atribuições: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar atribuições: {e}")
    finally:
        cursor.close()
        conn.close()


@app.post("/diagnostic")
async def diagnostic_check(request: DiagnosticRequest):
    """Endpoint de diagnóstico para comparar estado local com o orquestrador."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Obter streams atribuídos pelo orquestrador para esta instância
        cursor.execute(
            """
            SELECT stream_id FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
            ORDER BY stream_id
        """,
            (request.server_id,),
        )

        orchestrator_streams = [row["stream_id"] for row in cursor.fetchall()]

        # Obter informações da instância
        cursor.execute(
            """
            SELECT current_streams, max_streams, status, last_heartbeat
            FROM orchestrator_instances 
            WHERE server_id = %s
        """,
            (request.server_id,),
        )

        instance_info = cursor.fetchone()
        if not instance_info:
            raise HTTPException(
                status_code=404, detail=f"Instância {request.server_id} não encontrada"
            )

        # Comparar estados
        local_streams_set = set(request.local_streams)
        orchestrator_streams_set = set(orchestrator_streams)

        # Identificar inconsistências
        streams_only_local = local_streams_set - orchestrator_streams_set
        streams_only_orchestrator = orchestrator_streams_set - local_streams_set
        streams_in_sync = local_streams_set & orchestrator_streams_set

        # Verificar contagens
        count_mismatch = request.local_stream_count != len(orchestrator_streams)
        orchestrator_count_mismatch = instance_info["current_streams"] != len(
            orchestrator_streams
        )

        # Determinar status de sincronização
        is_synchronized = (
            len(streams_only_local) == 0
            and len(streams_only_orchestrator) == 0
            and not count_mismatch
            and not orchestrator_count_mismatch
        )

        # Calcular tempo desde último heartbeat
        last_heartbeat = instance_info["last_heartbeat"]
        heartbeat_age_seconds = None
        if last_heartbeat:
            heartbeat_age_seconds = (datetime.now() - last_heartbeat).total_seconds()

        result = {
            "server_id": request.server_id,
            "timestamp": datetime.now().isoformat(),
            "is_synchronized": is_synchronized,
            "synchronization_status": "OK" if is_synchronized else "INCONSISTENT",
            "local_state": {
                "stream_count": request.local_stream_count,
                "streams": sorted(request.local_streams),
            },
            "orchestrator_state": {
                "stream_count": len(orchestrator_streams),
                "streams": sorted(orchestrator_streams),
                "instance_current_streams": instance_info["current_streams"],
            },
            "inconsistencies": {
                "streams_only_in_local": sorted(list(streams_only_local)),
                "streams_only_in_orchestrator": sorted(list(streams_only_orchestrator)),
                "count_mismatch": count_mismatch,
                "orchestrator_count_mismatch": orchestrator_count_mismatch,
            },
            "streams_in_sync": sorted(list(streams_in_sync)),
            "instance_info": {
                "status": instance_info["status"],
                "max_streams": instance_info["max_streams"],
                "last_heartbeat": (
                    last_heartbeat.isoformat() if last_heartbeat else None
                ),
                "heartbeat_age_seconds": heartbeat_age_seconds,
            },
            "recommendations": [],
        }

        # Adicionar recomendações baseadas nas inconsistências
        if streams_only_local:
            result["recommendations"].append(
                f"Instância tem {len(streams_only_local)} streams não reconhecidos pelo orquestrador"
            )

        if streams_only_orchestrator:
            result["recommendations"].append(
                f"Orquestrador tem {len(streams_only_orchestrator)} streams não processados pela instância"
            )

        if count_mismatch:
            result["recommendations"].append(
                "Contagem local de streams não confere com orquestrador"
            )

        if orchestrator_count_mismatch:
            result["recommendations"].append(
                "Contagem do orquestrador não confere com assignments ativos"
            )

        if heartbeat_age_seconds and heartbeat_age_seconds > 120:
            result["recommendations"].append(
                f"Último heartbeat há {heartbeat_age_seconds:.0f} segundos - possível problema de conectividade"
            )

        if not is_synchronized:
            result["recommendations"].append(
                "Recomenda-se executar reload_streams_dynamic ou verificação de consistência"
            )

        logger.info(
            f"Diagnóstico para {request.server_id}: {'SINCRONIZADO' if is_synchronized else 'INCONSISTENTE'}"
        )

        return result

    except Exception as e:
        logger.error(f"Erro no diagnóstico para {request.server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no diagnóstico: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/instances/{server_id}/metrics")
async def get_instance_metrics(server_id: str, hours: int = 24):
    """Obtém métricas de performance de uma instância específica."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Verificar se a instância existe
        cursor.execute(
            "SELECT id FROM orchestrator_instances WHERE server_id = %s",
            (server_id,)
        )
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Instância não encontrada")

        # Obter métricas das últimas N horas
        cursor.execute(
            """
            SELECT 
                cpu_percent,
                memory_percent,
                disk_percent,
                load_average_1m,
                load_average_5m,
                load_average_15m,
                uptime_seconds,
                recorded_at
            FROM orchestrator_instance_metrics 
            WHERE server_id = %s 
                AND recorded_at >= NOW() - INTERVAL '%s hours'
            ORDER BY recorded_at DESC
            LIMIT 1000
        """,
            (server_id, hours)
        )

        metrics = cursor.fetchall()
        
        if not metrics:
            return {
                "server_id": server_id,
                "metrics": [],
                "summary": "Nenhuma métrica encontrada para o período especificado"
            }

        # Calcular estatísticas resumidas
        cpu_values = [m['cpu_percent'] for m in metrics if m['cpu_percent'] is not None]
        memory_values = [m['memory_percent'] for m in metrics if m['memory_percent'] is not None]
        disk_values = [m['disk_percent'] for m in metrics if m['disk_percent'] is not None]
        
        summary = {
            "total_records": len(metrics),
            "time_range_hours": hours,
            "latest_record": metrics[0]['recorded_at'].isoformat() if metrics else None,
            "oldest_record": metrics[-1]['recorded_at'].isoformat() if metrics else None
        }
        
        if cpu_values:
            summary["cpu"] = {
                "avg": round(sum(cpu_values) / len(cpu_values), 2),
                "min": round(min(cpu_values), 2),
                "max": round(max(cpu_values), 2)
            }
            
        if memory_values:
            summary["memory"] = {
                "avg": round(sum(memory_values) / len(memory_values), 2),
                "min": round(min(memory_values), 2),
                "max": round(max(memory_values), 2)
            }
            
        if disk_values:
            summary["disk"] = {
                "avg": round(sum(disk_values) / len(disk_values), 2),
                "min": round(min(disk_values), 2),
                "max": round(max(disk_values), 2)
            }

        return {
            "server_id": server_id,
            "metrics": [dict(metric) for metric in metrics],
            "summary": summary
        }

    except Exception as e:
        logger.error(f"Erro ao obter métricas de {server_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter métricas: {e}")
    finally:
        cursor.close()
        conn.close()


@app.get("/metrics/overview")
async def get_metrics_overview():
    """Obtém visão geral das métricas de todas as instâncias ativas."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Obter métricas mais recentes de cada instância ativa
        cursor.execute(
            """
            WITH latest_metrics AS (
                SELECT DISTINCT ON (server_id) 
                    server_id,
                    cpu_percent,
                    memory_percent,
                    disk_percent,
                    load_average_1m,
                    recorded_at
                FROM orchestrator_instance_metrics 
                WHERE recorded_at >= NOW() - INTERVAL '1 hour'
                ORDER BY server_id, recorded_at DESC
            )
            SELECT 
                oi.server_id,
                oi.ip,
                oi.port,
                oi.current_streams,
                oi.max_streams,
                oi.status,
                oi.last_heartbeat,
                lm.cpu_percent,
                lm.memory_percent,
                lm.disk_percent,
                lm.load_average_1m,
                lm.recorded_at as metrics_timestamp
            FROM orchestrator_instances oi
            LEFT JOIN latest_metrics lm ON oi.server_id = lm.server_id
            WHERE oi.status = 'active'
            ORDER BY oi.server_id
        """
        )

        instances = cursor.fetchall()
        
        overview = {
            "total_instances": len(instances),
            "instances_with_metrics": len([i for i in instances if i['cpu_percent'] is not None]),
            "timestamp": datetime.now().isoformat(),
            "instances": []
        }
        
        for instance in instances:
            instance_data = {
                "server_id": instance['server_id'],
                "ip": instance['ip'],
                "port": instance['port'],
                "streams": {
                    "current": instance['current_streams'],
                    "max": instance['max_streams'],
                    "utilization_percent": round((instance['current_streams'] / instance['max_streams']) * 100, 1) if instance['max_streams'] > 0 else 0
                },
                "status": instance['status'],
                "last_heartbeat": instance['last_heartbeat'].isoformat() if instance['last_heartbeat'] else None,
                "metrics": None
            }
            
            if instance['cpu_percent'] is not None:
                instance_data["metrics"] = {
                    "cpu_percent": instance['cpu_percent'],
                    "memory_percent": instance['memory_percent'],
                    "disk_percent": instance['disk_percent'],
                    "load_average_1m": instance['load_average_1m'],
                    "timestamp": instance['metrics_timestamp'].isoformat() if instance['metrics_timestamp'] else None
                }
            
            overview["instances"].append(instance_data)

        return overview

    except Exception as e:
        logger.error(f"Erro ao obter visão geral das métricas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter visão geral: {e}")
    finally:
        cursor.close()
        conn.close()


async def cleanup_task():
    """Tarefa de limpeza que executa periodicamente."""
    while True:
        try:
            await orchestrator.cleanup_inactive_instances()
            await asyncio.sleep(REBALANCE_INTERVAL)
        except Exception as e:
            logger.error(f"Erro na tarefa de limpeza: {e}")
            await asyncio.sleep(30)  # Aguardar menos tempo em caso de erro


async def failover_monitor_task():
    """Tarefa de monitoramento de failover que executa mais frequentemente."""
    while True:
        try:
            # Executar verificação de failover a cada 10 segundos para maior responsividade
            orchestrator.handle_orphaned_streams()
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Erro na tarefa de failover: {e}")
            await asyncio.sleep(5)  # Aguardar menos tempo em caso de erro


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ORCHESTRATOR_PORT", 8001))
    host = os.getenv("ORCHESTRATOR_HOST", "0.0.0.0")

    logger.info(f"Iniciando orquestrador em {host}:{port}")

    uvicorn.run(app, host=host, port=port, log_level="info")

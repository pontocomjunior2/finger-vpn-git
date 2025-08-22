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
if os.getenv('POSTGRES_HOST') and not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = os.getenv('POSTGRES_HOST')
if os.getenv('POSTGRES_DB') and not os.getenv('DB_NAME'):
    os.environ['DB_NAME'] = os.getenv('POSTGRES_DB')
if os.getenv('POSTGRES_USER') and not os.getenv('DB_USER'):
    os.environ['DB_USER'] = os.getenv('POSTGRES_USER')
if os.getenv('POSTGRES_PASSWORD') and not os.getenv('DB_PASSWORD'):
    os.environ['DB_PASSWORD'] = os.getenv('POSTGRES_PASSWORD')
if os.getenv('POSTGRES_PORT') and not os.getenv('DB_PORT'):
    os.environ['DB_PORT'] = os.getenv('POSTGRES_PORT')

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações do banco de dados
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'radio_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port': int(os.getenv('DB_PORT', 5432))
}

# Configurações do orquestrador
MAX_STREAMS_PER_INSTANCE = int(os.getenv('MAX_STREAMS_PER_INSTANCE', 20))
HEARTBEAT_TIMEOUT = int(os.getenv('HEARTBEAT_TIMEOUT', 300))  # 5 minutos
REBALANCE_INTERVAL = int(os.getenv('REBALANCE_INTERVAL', 60))  # 1 minuto

# Modelos Pydantic
class InstanceRegistration(BaseModel):
    server_id: str
    ip: str
    port: int
    max_streams: int = MAX_STREAMS_PER_INSTANCE

class HeartbeatRequest(BaseModel):
    server_id: str
    current_streams: int
    status: str = "active"

class StreamRequest(BaseModel):
    server_id: str
    requested_count: int = MAX_STREAMS_PER_INSTANCE

class StreamRelease(BaseModel):
    server_id: str
    stream_ids: List[int]

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
    lifespan=lifespan
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
            cursor.execute("""
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
            """)
            
            # Criar índices para a tabela de instâncias
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_server_id ON orchestrator_instances(server_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_status ON orchestrator_instances(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instances_heartbeat ON orchestrator_instances(last_heartbeat)")
            
            # Tabela de atribuições de streams
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_stream_assignments (
                    id SERIAL PRIMARY KEY,
                    stream_id INTEGER NOT NULL,
                    server_id VARCHAR(50) NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active',
                    UNIQUE(stream_id)
                )
            """)
            
            # Criar índices para a tabela de atribuições
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_server_id ON orchestrator_stream_assignments(server_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_stream_id ON orchestrator_stream_assignments(stream_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_status ON orchestrator_stream_assignments(status)")
            
            # Tabela de histórico de rebalanceamentos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_rebalance_history (
                    id SERIAL PRIMARY KEY,
                    rebalance_type VARCHAR(50) NOT NULL,
                    streams_moved INTEGER DEFAULT 0,
                    instances_affected INTEGER DEFAULT 0,
                    reason TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
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
            # Buscar todos os streams ativos
            cursor.execute("""
                SELECT DISTINCT stream_id 
                FROM streams 
                WHERE status = 'active' 
                ORDER BY stream_id
            """)
            
            all_streams = [row[0] for row in cursor.fetchall()]
            
            # Buscar streams já atribuídos
            cursor.execute("""
                SELECT stream_id 
                FROM orchestrator_stream_assignments 
                WHERE status = 'active'
            """)
            
            assigned_streams = set(row[0] for row in cursor.fetchall())
            
            # Retornar streams não atribuídos
            available_streams = [s for s in all_streams if s not in assigned_streams]
            
            logger.info(f"Streams disponíveis: {len(available_streams)}, Total: {len(all_streams)}")
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
            # Inserir ou atualizar instância
            cursor.execute("""
                INSERT INTO orchestrator_instances 
                (server_id, ip, port, max_streams, current_streams, status, last_heartbeat)
                VALUES (%s, %s, %s, %s, 0, 'active', CURRENT_TIMESTAMP)
                ON CONFLICT (server_id) 
                DO UPDATE SET 
                    ip = EXCLUDED.ip,
                    port = EXCLUDED.port,
                    max_streams = EXCLUDED.max_streams,
                    status = 'active',
                    last_heartbeat = CURRENT_TIMESTAMP
                RETURNING id
            """, (registration.server_id, registration.ip, registration.port, registration.max_streams))
            
            instance_id = cursor.fetchone()[0]
            
            # Atualizar cache local
            self.active_instances[registration.server_id] = {
                'id': instance_id,
                'ip': registration.ip,
                'port': registration.port,
                'max_streams': registration.max_streams,
                'current_streams': 0,
                'status': 'active',
                'last_heartbeat': datetime.now()
            }
            
            logger.info(f"Instância {registration.server_id} registrada com sucesso")
            
            return {
                'status': 'registered',
                'server_id': registration.server_id,
                'max_streams': registration.max_streams
            }
            
        except Exception as e:
            logger.error(f"Erro ao registrar instância {registration.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao registrar instância: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def update_heartbeat(self, heartbeat: HeartbeatRequest) -> dict:
        """Atualiza o heartbeat de uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET last_heartbeat = CURRENT_TIMESTAMP,
                    current_streams = %s,
                    status = %s
                WHERE server_id = %s
                RETURNING id
            """, (heartbeat.current_streams, heartbeat.status, heartbeat.server_id))
            
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Instância não encontrada")
            
            # Atualizar cache local
            if heartbeat.server_id in self.active_instances:
                self.active_instances[heartbeat.server_id].update({
                    'current_streams': heartbeat.current_streams,
                    'status': heartbeat.status,
                    'last_heartbeat': datetime.now()
                })
            
            return {'status': 'heartbeat_updated'}
            
        except Exception as e:
            logger.error(f"Erro ao atualizar heartbeat de {heartbeat.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao atualizar heartbeat: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def assign_streams(self, request: StreamRequest) -> dict:
        """Atribui streams para uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Verificar se instância existe e está ativa
            cursor.execute("""
                SELECT current_streams, max_streams 
                FROM orchestrator_instances 
                WHERE server_id = %s AND status = 'active'
            """, (request.server_id,))
            
            instance_data = cursor.fetchone()
            if not instance_data:
                raise HTTPException(status_code=404, detail="Instância não encontrada ou inativa")
            
            current_streams, max_streams = instance_data
            available_slots = max_streams - current_streams
            
            if available_slots <= 0:
                return {
                    'status': 'no_capacity',
                    'assigned_streams': [],
                    'message': 'Instância já está na capacidade máxima'
                }
            
            # Buscar streams disponíveis
            available_streams = self.get_available_streams()
            streams_to_assign = min(available_slots, request.requested_count, len(available_streams))
            
            if streams_to_assign == 0:
                return {
                    'status': 'no_streams',
                    'assigned_streams': [],
                    'message': 'Nenhum stream disponível para atribuição'
                }
            
            # Atribuir streams
            assigned_streams = available_streams[:streams_to_assign]
            
            for stream_id in assigned_streams:
                cursor.execute("""
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, status)
                    VALUES (%s, %s, 'active')
                """, (stream_id, request.server_id))
            
            # Atualizar contador de streams da instância
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = current_streams + %s
                WHERE server_id = %s
            """, (len(assigned_streams), request.server_id))
            
            logger.info(f"Atribuídos {len(assigned_streams)} streams para {request.server_id}")
            
            return {
                'status': 'assigned',
                'assigned_streams': assigned_streams,
                'count': len(assigned_streams)
            }
            
        except Exception as e:
            logger.error(f"Erro ao atribuir streams para {request.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao atribuir streams: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def release_streams(self, release: StreamRelease) -> dict:
        """Libera streams de uma instância."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            if not release.stream_ids:
                return {'status': 'no_streams_to_release'}
            
            # Remover atribuições
            cursor.execute("""
                DELETE FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND stream_id = ANY(%s)
                RETURNING stream_id
            """, (release.server_id, release.stream_ids))
            
            released_streams = [row[0] for row in cursor.fetchall()]
            
            # Atualizar contador de streams da instância
            if released_streams:
                cursor.execute("""
                    UPDATE orchestrator_instances 
                    SET current_streams = GREATEST(0, current_streams - %s)
                    WHERE server_id = %s
                """, (len(released_streams), release.server_id))
            
            logger.info(f"Liberados {len(released_streams)} streams de {release.server_id}")
            
            return {
                'status': 'released',
                'released_streams': released_streams,
                'count': len(released_streams)
            }
            
        except Exception as e:
            logger.error(f"Erro ao liberar streams de {release.server_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao liberar streams: {e}")
        finally:
            cursor.close()
            conn.close()
    
    def handle_orphaned_streams(self):
        """Detecta e reatribui streams órfãos automaticamente."""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Encontrar streams órfãos (atribuídos a instâncias inativas)
            cursor.execute("""
                SELECT DISTINCT osa.stream_id 
                FROM orchestrator_stream_assignments osa
                JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
                WHERE oi.status = 'inactive' 
                   OR oi.last_heartbeat < NOW() - INTERVAL '3 minutes'
            """)
            
            orphaned_streams = [row['stream_id'] for row in cursor.fetchall()]
            
            if orphaned_streams:
                logger.warning(f"Detectados {len(orphaned_streams)} streams órfãos: {orphaned_streams}")
                
                # Liberar streams órfãos
                cursor.execute("""
                    DELETE FROM orchestrator_stream_assignments osa
                    USING orchestrator_instances oi
                    WHERE osa.server_id = oi.server_id
                    AND (oi.status = 'inactive' OR oi.last_heartbeat < NOW() - INTERVAL '3 minutes')
                """)
                
                # Reatribuir streams órfãos para instâncias ativas
                for stream_id in orphaned_streams:
                    try:
                        # Encontrar instância com menor carga
                        cursor.execute("""
                            SELECT oi.server_id, 
                                   COALESCE(COUNT(osa.stream_id), 0) as current_load
                            FROM orchestrator_instances oi
                            LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id
                            WHERE oi.status = 'active' 
                              AND oi.last_heartbeat > NOW() - INTERVAL '2 minutes'
                            GROUP BY oi.server_id
                            ORDER BY current_load ASC
                            LIMIT 1
                        """)
                        
                        best_instance = cursor.fetchone()
                        
                        if best_instance:
                            # Atribuir stream à melhor instância
                            cursor.execute("""
                                INSERT INTO orchestrator_stream_assignments 
                                (stream_id, server_id, assigned_at)
                                VALUES (%s, %s, CURRENT_TIMESTAMP)
                            """, (stream_id, best_instance['server_id']))
                            
                            logger.info(f"Stream órfão {stream_id} reatribuído para instância {best_instance['server_id']}")
                        else:
                            logger.error(f"Nenhuma instância ativa disponível para reatribuir stream {stream_id}")
                            
                    except Exception as e:
                        logger.error(f"Erro ao reatribuir stream órfão {stream_id}: {e}")
                
                logger.info(f"Failover automático concluído para {len(orphaned_streams)} streams")
            
        except Exception as e:
            logger.error(f"Erro no failover automático: {e}")
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
            
            cursor.execute("""
                SELECT server_id, current_streams
                FROM orchestrator_instances 
                WHERE last_heartbeat < %s AND status = 'active'
            """, (timeout_threshold,))
            
            inactive_instances = cursor.fetchall()
            
            for server_id, current_streams in inactive_instances:
                logger.warning(f"Instância {server_id} inativa, liberando {current_streams} streams")
                
                # Marcar instância como inativa
                cursor.execute("""
                    UPDATE orchestrator_instances 
                    SET status = 'inactive', current_streams = 0
                    WHERE server_id = %s
                """, (server_id,))
                
                # Remover do cache local
                if server_id in self.active_instances:
                    del self.active_instances[server_id]
                
                logger.info(f"Instância {server_id} marcada como inativa")
            
            if inactive_instances:
                logger.info(f"Limpeza concluída: {len(inactive_instances)} instâncias inativas removidas")
            
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
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_instances,
                    COUNT(*) FILTER (WHERE status = 'active') as active_instances,
                    COALESCE(SUM(current_streams), 0) as total_assigned_streams,
                    COALESCE(SUM(max_streams), 0) as total_capacity
                FROM orchestrator_instances
            """)
            
            instance_stats = cursor.fetchone()
            
            # Estatísticas de streams
            cursor.execute("""
                SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE status = 'active'
            """)
            
            assigned_streams = cursor.fetchone()[0]
            
            # Streams disponíveis
            available_streams = len(self.get_available_streams())
            
            return {
                'orchestrator_status': 'active',
                'instances': {
                    'total': instance_stats[0],
                    'active': instance_stats[1],
                    'total_capacity': instance_stats[3],
                    'current_load': instance_stats[2]
                },
                'streams': {
                    'assigned': assigned_streams,
                    'available': available_streams,
                    'total': assigned_streams + available_streams
                },
                'load_percentage': round((instance_stats[2] / max(instance_stats[3], 1)) * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter status do orquestrador: {e}")
            return {'orchestrator_status': 'error', 'error': str(e)}
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
        cursor.execute("""
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, registered_at, last_heartbeat
            FROM orchestrator_instances 
            ORDER BY registered_at DESC
        """)
        
        instances = cursor.fetchall()
        return {'instances': [dict(instance) for instance in instances]}
        
    except Exception as e:
        logger.error(f"Erro ao listar instâncias: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar instâncias: {e}")
    finally:
        cursor.close()
        conn.close()

@app.get("/streams/assignments")
async def get_stream_assignments():
    """Lista todas as atribuições de streams."""
    conn = orchestrator.get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT osa.stream_id, osa.server_id, osa.assigned_at, osa.status,
                   oi.ip, oi.port
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
            ORDER BY osa.assigned_at DESC
        """)
        
        assignments = cursor.fetchall()
        return {'assignments': [dict(assignment) for assignment in assignments]}
        
    except Exception as e:
        logger.error(f"Erro ao listar atribuições: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar atribuições: {e}")
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
            # Executar verificação de failover a cada 30 segundos
            orchestrator.handle_orphaned_streams()
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Erro na tarefa de failover: {e}")
            await asyncio.sleep(15)  # Aguardar menos tempo em caso de erro

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('ORCHESTRATOR_PORT', 8001))
    host = os.getenv('ORCHESTRATOR_HOST', '0.0.0.0')
    
    logger.info(f"Iniciando orquestrador em {host}:{port}")
    
    uvicorn.run(app, host=host, port=port, log_level="info")
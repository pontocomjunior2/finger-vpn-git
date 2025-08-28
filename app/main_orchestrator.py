#!/usr/bin/env python3
"""
Main Orchestrator Application Entry Point
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime

# Adicionar diretório app ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from integration_system import IntegratedOrchestrator
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from contextlib import asynccontextmanager
    import uvicorn
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Gerenciar ciclo de vida da aplicação"""
        global orchestrator
        
        logger.info("🔍 DEBUG: lifespan startup called")
        logger.info("Starting Enhanced Stream Orchestrator...")
        logger.info(f"Internal database config: {DB_CONFIG}")
        logger.info(f"External PostgreSQL config: {POSTGRES_CONFIG}")

        # Verificar configuração do banco interno
        required_vars = ["host", "database", "user", "password"]
        missing_vars = [var for var in required_vars if not DB_CONFIG.get(var)]

        # Verificar configuração do PostgreSQL externo
        postgres_required = ["host", "database", "user", "password"]
        postgres_missing = [
            var for var in postgres_required if not POSTGRES_CONFIG.get(var)
        ]

        if missing_vars:
            logger.warning(f"Missing internal database configurations: {missing_vars}")
            logger.warning(
                "Starting in limited mode without full orchestrator functionality"
            )

        if postgres_missing:
            logger.warning(f"Missing PostgreSQL configurations: {postgres_missing}")
            logger.warning("Stream monitoring will be limited")
        else:
            logger.info("✅ PostgreSQL external database configured successfully")
            logger.info(f"✅ Streams table: {POSTGRES_CONFIG['table_name']}")
        
        logger.info("🔍 DEBUG: About to start orchestrator initialization...")

        try:
            logger.info("🔍 DEBUG: Inside try block")
            # Forçar configuração padrão se não estiver definida
            if not DB_CONFIG.get("host"):
                DB_CONFIG["host"] = "localhost"
            if not DB_CONFIG.get("database"):
                DB_CONFIG["database"] = "orchestrator"
            if not DB_CONFIG.get("user"):
                DB_CONFIG["user"] = "orchestrator_user"
            if not DB_CONFIG.get("password"):
                DB_CONFIG["password"] = os.getenv("DB_PASSWORD", "orchestrator_pass")

            logger.info(f"Final database config: {DB_CONFIG}")
            logger.info("🔍 DEBUG: About to create IntegratedOrchestrator")

            orchestrator = IntegratedOrchestrator(DB_CONFIG, POSTGRES_CONFIG)
            logger.info("🔍 DEBUG: IntegratedOrchestrator created, starting system...")
            success = await orchestrator.start_system()
            logger.info(f"🔍 DEBUG: start_system returned: {success}")

            if not success:
                logger.error("Failed to start orchestrator system")
                logger.warning("Continuing in limited mode")
            else:
                logger.info("Enhanced Stream Orchestrator started successfully")
                logger.info("🔍 DEBUG: Orchestrator initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}")
            logger.warning("Continuing in limited mode")
        
        # Aplicação iniciada
        yield
        
        # Cleanup na shutdown
        if orchestrator:
            logger.info("Shutting down orchestrator...")
            try:
                await orchestrator.shutdown()
            except Exception as e:
                logger.error(f"Error during orchestrator shutdown: {e}")

except ImportError as e:
    print(f"Import error: {e}")
    print("Running in simple mode...")

    # Simple health check server
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI(title="Enhanced Stream Orchestrator", version="1.0.0")

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "message": "Simple mode - components not fully loaded",
        }

    @app.get("/")
    async def root():
        return {"message": "Enhanced Stream Orchestrator", "status": "running"}

    if __name__ == "__main__":
        port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
        host = os.getenv("ORCHESTRATOR_HOST", "0.0.0.0")
        uvicorn.run(app, host=host, port=port)

    sys.exit(0)

# Configurar logging
log_handlers = [logging.StreamHandler()]

# Adicionar file handler se diretório existir
log_dir = os.getenv("LOG_DIR", "/app/logs")
if os.path.exists(log_dir):
    log_handlers.append(logging.FileHandler(f"{log_dir}/orchestrator.log"))
elif os.path.exists("./logs"):
    log_handlers.append(logging.FileHandler("./logs/orchestrator.log"))

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)

logger = logging.getLogger(__name__)

# Configuração do banco de dados interno (orchestrator)
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# Configuração do banco PostgreSQL externo (streams)
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    # Priorizar variável específica para streams; manter compatibilidade com DB_TABLE_NAME
    "table_name": os.getenv("DB_TABLE_STREAMS", os.getenv("DB_TABLE_NAME", "streams")),
}

# Instância global do orchestrator
orchestrator = None


app = FastAPI(
    title="Enhanced Stream Orchestrator",
    description="Stream orchestrator with load balancing and resilience",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Função startup_event removida - agora usando lifespan pattern


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown graceful do orchestrator"""
    global orchestrator

    logger.info("Shutting down Enhanced Stream Orchestrator...")

    if orchestrator:
        await orchestrator.stop_system()

    logger.info("Enhanced Stream Orchestrator stopped")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if not orchestrator:
        return {
            "status": "limited",
            "message": "Running in limited mode - database not configured",
            "timestamp": datetime.now().isoformat(),
            "database_config": {
                "host": bool(DB_CONFIG.get("host")),
                "database": bool(DB_CONFIG.get("database")),
                "user": bool(DB_CONFIG.get("user")),
                "password": bool(DB_CONFIG.get("password")),
            },
        }

    try:
        status = await orchestrator.get_system_status()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_status": status,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


@app.get("/metrics")
async def get_metrics():
    """Endpoint para métricas do sistema"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        status = await orchestrator.get_system_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@app.get("/postgres/test")
async def test_postgres_connection():
    """Testar conexão com PostgreSQL externo"""
    try:
        import asyncpg

        # Conectar ao PostgreSQL externo
        conn = await asyncpg.connect(
            host=POSTGRES_CONFIG["host"],
            port=POSTGRES_CONFIG["port"],
            database=POSTGRES_CONFIG["database"],
            user=POSTGRES_CONFIG["user"],
            password=POSTGRES_CONFIG["password"],
        )

        # Testar consulta na tabela streams
        table_name = POSTGRES_CONFIG["table_name"]
        query = f"SELECT COUNT(*) as total FROM {table_name} LIMIT 1"
        result = await conn.fetchrow(query)

        await conn.close()

        return {
            "status": "success",
            "message": "PostgreSQL connection successful",
            "database": POSTGRES_CONFIG["database"],
            "table": table_name,
            "total_streams": result["total"] if result else 0,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return {
            "status": "error",
            "message": f"PostgreSQL connection failed: {str(e)}",
            "database": POSTGRES_CONFIG["database"],
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/streams")
async def get_streams():
    """Obter streams do PostgreSQL externo"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=POSTGRES_CONFIG["host"],
            port=POSTGRES_CONFIG["port"],
            database=POSTGRES_CONFIG["database"],
            user=POSTGRES_CONFIG["user"],
            password=POSTGRES_CONFIG["password"],
        )

        table_name = POSTGRES_CONFIG["table_name"]
        query = f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 10"
        results = await conn.fetch(query)

        await conn.close()

        streams = [dict(row) for row in results]

        return {
            "status": "success",
            "total": len(streams),
            "streams": streams,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get streams: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get streams: {str(e)}")


# ==========================================
# WORKER MANAGEMENT API ENDPOINTS
# ==========================================

# Armazenamento em memória para workers (temporário)
workers_registry = {}
stream_assignments = {}


@app.post("/api/workers/register")
async def register_worker(worker_data: dict):
    """Registrar um worker FingerV7"""
    try:
        instance_id = worker_data.get("instance_id")
        if not instance_id:
            raise HTTPException(status_code=400, detail="instance_id is required")

        # Registrar worker
        workers_registry[instance_id] = {
            **worker_data,
            "registered_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "status": "active",
        }

        logger.info(f"✅ Worker registered: {instance_id}")

        return {
            "success": True,
            "worker_id": instance_id,
            "message": "Worker registered successfully",
        }

    except Exception as e:
        logger.error(f"❌ Error registering worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/heartbeat")
async def worker_heartbeat(heartbeat_data: dict):
    """Receber heartbeat de worker"""
    try:
        worker_id = heartbeat_data.get("worker_instance_id")
        if not worker_id:
            raise HTTPException(
                status_code=400, detail="worker_instance_id is required"
            )

        if worker_id not in workers_registry:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Atualizar heartbeat
        workers_registry[worker_id].update(
            {
                "last_heartbeat": datetime.now().isoformat(),
                "status": heartbeat_data.get("status", "active"),
                "current_load": heartbeat_data.get("current_load", 0),
                "available_capacity": heartbeat_data.get("available_capacity", 0),
                "metrics": heartbeat_data.get("metrics", {}),
            }
        )

        logger.debug(f"💓 Heartbeat received from {worker_id}")

        return {"success": True, "message": "Heartbeat received"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing heartbeat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workers")
async def list_workers():
    """Listar workers registrados"""
    try:
        workers_list = []
        for worker_id, worker_data in workers_registry.items():
            workers_list.append(
                {
                    "instance_id": worker_id,
                    "worker_type": worker_data.get("worker_type"),
                    "status": worker_data.get("status"),
                    "capacity": worker_data.get("capacity"),
                    "current_load": worker_data.get("current_load", 0),
                    "available_capacity": worker_data.get("available_capacity", 0),
                    "last_heartbeat": worker_data.get("last_heartbeat"),
                    "registered_at": worker_data.get("registered_at"),
                }
            )

        return {"workers": workers_list, "total": len(workers_list)}

    except Exception as e:
        logger.error(f"❌ Error listing workers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/streams/assign")
async def assign_streams(
    worker_id: str, capacity: int = 1, worker_type: str = "fingerv7"
):
    """Atribuir streams para um worker"""
    try:
        if worker_id not in workers_registry:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Buscar streams disponíveis do PostgreSQL
        import asyncpg

        conn = await asyncpg.connect(
            host=POSTGRES_CONFIG["host"],
            port=POSTGRES_CONFIG["port"],
            database=POSTGRES_CONFIG["database"],
            user=POSTGRES_CONFIG["user"],
            password=POSTGRES_CONFIG["password"],
        )

        table_name = POSTGRES_CONFIG["table_name"]

        # Buscar streams que não estão sendo processados
        query = f"""
        SELECT * FROM {table_name} 
        WHERE id NOT IN (
            SELECT DISTINCT stream_id::int 
            FROM (VALUES {','.join([f"('{sid}')" for sid in stream_assignments.keys()])}) AS assigned(stream_id)
            WHERE stream_id IS NOT NULL
        )
        ORDER BY RANDOM() 
        LIMIT $1
        """

        if not stream_assignments:
            # Se não há assignments, buscar qualquer stream
            query = f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT $1"

        results = await conn.fetch(query, capacity)
        await conn.close()

        streams = []
        for row in results:
            stream_data = dict(row)
            stream_id = str(stream_data["id"])

            # Marcar como atribuído
            stream_assignments[stream_id] = {
                "worker_id": worker_id,
                "assigned_at": datetime.now().isoformat(),
                "status": "assigned",
            }

            streams.append(
                {
                    "stream_id": stream_id,
                    "id": stream_data["id"],
                    "stream_url": stream_data.get("url"),
                    "url": stream_data.get("url"),
                    "name": stream_data.get("name"),
                    "metadata": {
                        "cidade": stream_data.get("cidade"),
                        "estado": stream_data.get("estado"),
                        "regiao": stream_data.get("regiao"),
                        "segmento": stream_data.get("segmento"),
                        "frequencia": stream_data.get("frequencia"),
                    },
                }
            )

        logger.info(f"📤 Assigned {len(streams)} streams to worker {worker_id}")

        # Retornar formato compatível com ResilientWorkerClient
        if streams:
            # Extrair apenas os IDs dos streams para o campo assigned_streams
            assigned_stream_ids = [int(stream["id"]) for stream in streams]
            return {
                "status": "assigned",
                "assigned_streams": assigned_stream_ids,
                "streams": streams,  # Manter streams completos para compatibilidade
                "total": len(streams),
                "worker_id": worker_id
            }
        else:
            return {
                "status": "no_streams",
                "assigned_streams": [],
                "message": "Nenhum stream disponível para atribuição",
                "worker_id": worker_id
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error assigning streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/streams/update")
async def update_stream_status(update_data: dict):
    """Atualizar status de processamento de stream"""
    try:
        stream_id = update_data.get("stream_id")
        worker_id = update_data.get("worker_instance_id")
        status = update_data.get("status")
        result = update_data.get("result", {})

        if not all([stream_id, worker_id, status]):
            raise HTTPException(
                status_code=400,
                detail="stream_id, worker_instance_id, and status are required",
            )

        # Atualizar assignment
        if stream_id in stream_assignments:
            stream_assignments[stream_id].update(
                {
                    "status": status,
                    "updated_at": datetime.now().isoformat(),
                    "result": result,
                }
            )

            # Se completado ou falhou, remover da lista de assignments
            if status in ["completed", "failed", "cancelled"]:
                logger.info(f"🎯 Stream {stream_id} {status} by worker {worker_id}")
                # Manter por um tempo para histórico
                stream_assignments[stream_id][
                    "finished_at"
                ] = datetime.now().isoformat()

        return {
            "success": True,
            "message": f"Stream {stream_id} status updated to {status}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating stream status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics")
async def get_orchestrator_metrics():
    """Obter métricas do orchestrator"""
    try:
        # Calcular métricas dos workers
        total_workers = len(workers_registry)
        active_workers = sum(
            1 for w in workers_registry.values() if w.get("status") == "active"
        )
        total_capacity = sum(w.get("capacity", 0) for w in workers_registry.values())
        current_load = sum(w.get("current_load", 0) for w in workers_registry.values())

        # Métricas de streams
        total_assignments = len(stream_assignments)
        completed_streams = sum(
            1 for s in stream_assignments.values() if s.get("status") == "completed"
        )
        failed_streams = sum(
            1 for s in stream_assignments.values() if s.get("status") == "failed"
        )
        processing_streams = sum(
            1 for s in stream_assignments.values() if s.get("status") == "processing"
        )

        return {
            "orchestrator": {
                "status": "running",
                "uptime": "N/A",  # TODO: calcular uptime real
                "timestamp": datetime.now().isoformat(),
            },
            "workers": {
                "total": total_workers,
                "active": active_workers,
                "total_capacity": total_capacity,
                "current_load": current_load,
                "utilization_percent": round(
                    (current_load / max(1, total_capacity)) * 100, 2
                ),
            },
            "streams": {
                "total_assignments": total_assignments,
                "completed": completed_streams,
                "failed": failed_streams,
                "processing": processing_streams,
                "success_rate": round(
                    (completed_streams / max(1, completed_streams + failed_streams))
                    * 100,
                    2,
                ),
            },
        }

    except Exception as e:
        logger.error(f"❌ Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "message": "Enhanced Stream Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "databases": {
            "internal": "localhost (orchestrator data)",
            "external": f"{POSTGRES_CONFIG['host']} (streams data)",
        },
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "postgres_test": "/postgres/test",
            "streams": "/streams",
            "docs": "/docs",
            "api": {
                "workers_register": "/api/workers/register",
                "workers_list": "/api/workers",
                "heartbeat": "/api/heartbeat",
                "streams_assign": "/api/streams/assign",
                "streams_update": "/api/streams/update",
                "api_metrics": "/api/metrics",
            },
        },
    }


def signal_handler(signum, frame):
    """Handler para sinais de sistema"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    # Configurar handlers de sinal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Configurações do servidor
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
    host = os.getenv("ORCHESTRATOR_HOST", "0.0.0.0")
    workers = int(os.getenv("MAX_WORKERS", "1"))

    logger.info(f"Starting server on {host}:{port} with {workers} workers")

    # Iniciar servidor
    uvicorn.run(
        "main_orchestrator:app",
        host=host,
        port=port,
        workers=workers,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
    )

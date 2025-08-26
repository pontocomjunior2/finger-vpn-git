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
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError as e:
    print(f"Import error: {e}")
    print("Running in simple mode...")
    
    # Simple health check server
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI(title="Enhanced Stream Orchestrator", version="1.0.0")
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "message": "Simple mode - components not fully loaded"}
    
    @app.get("/")
    async def root():
        return {"message": "Enhanced Stream Orchestrator", "status": "running"}
    
    if __name__ == "__main__":
        port = int(os.getenv('ORCHESTRATOR_PORT', '8000'))
        host = os.getenv('ORCHESTRATOR_HOST', '0.0.0.0')
        uvicorn.run(app, host=host, port=port)
    
    sys.exit(0)

# Configurar logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/orchestrator.log')
    ]
)

logger = logging.getLogger(__name__)

# Configuração do banco de dados interno (orchestrator)
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

# Configuração do banco PostgreSQL externo (streams)
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DB'),
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD'),
    'table_name': os.getenv('DB_TABLE_NAME', 'streams')
}

# Instância global do orchestrator
orchestrator = None

# FastAPI app
app = FastAPI(
    title="Enhanced Stream Orchestrator",
    description="Stream orchestrator with load balancing and resilience",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Inicializar orchestrator na startup"""
    global orchestrator
    
    logger.info("Starting Enhanced Stream Orchestrator...")
    logger.info(f"Internal database config: {DB_CONFIG}")
    logger.info(f"External PostgreSQL config: {POSTGRES_CONFIG}")
    
    # Verificar configuração do banco interno
    required_vars = ['host', 'database', 'user', 'password']
    missing_vars = [var for var in required_vars if not DB_CONFIG.get(var)]
    
    # Verificar configuração do PostgreSQL externo
    postgres_required = ['host', 'database', 'user', 'password']
    postgres_missing = [var for var in postgres_required if not POSTGRES_CONFIG.get(var)]
    
    if missing_vars:
        logger.warning(f"Missing internal database configurations: {missing_vars}")
        logger.warning("Starting in limited mode without full orchestrator functionality")
    
    if postgres_missing:
        logger.warning(f"Missing PostgreSQL configurations: {postgres_missing}")
        logger.warning("Stream monitoring will be limited")
    else:
        logger.info("✅ PostgreSQL external database configured successfully")
        logger.info(f"✅ Streams table: {POSTGRES_CONFIG['table_name']}")
        return
    
    try:
        # Forçar configuração padrão se não estiver definida
        if not DB_CONFIG.get('host'):
            DB_CONFIG['host'] = 'localhost'
        if not DB_CONFIG.get('database'):
            DB_CONFIG['database'] = 'orchestrator'
        if not DB_CONFIG.get('user'):
            DB_CONFIG['user'] = 'orchestrator_user'
        if not DB_CONFIG.get('password'):
            DB_CONFIG['password'] = os.getenv('DB_PASSWORD', 'orchestrator_pass')
            
        logger.info(f"Final database config: {DB_CONFIG}")
        
        orchestrator = IntegratedOrchestrator(DB_CONFIG)
        success = await orchestrator.start_system()
        
        if not success:
            logger.error("Failed to start orchestrator system")
            logger.warning("Continuing in limited mode")
            return
        
        logger.info("Enhanced Stream Orchestrator started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start orchestrator: {e}")
        logger.warning("Continuing in limited mode")

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
                "host": bool(DB_CONFIG.get('host')),
                "database": bool(DB_CONFIG.get('database')),
                "user": bool(DB_CONFIG.get('user')),
                "password": bool(DB_CONFIG.get('password'))
            }
        }
    
    try:
        status = await orchestrator.get_system_status()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_status": status
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
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        
        # Testar consulta na tabela streams
        table_name = POSTGRES_CONFIG['table_name']
        query = f"SELECT COUNT(*) as total FROM {table_name} LIMIT 1"
        result = await conn.fetchrow(query)
        
        await conn.close()
        
        return {
            "status": "success",
            "message": "PostgreSQL connection successful",
            "database": POSTGRES_CONFIG['database'],
            "table": table_name,
            "total_streams": result['total'] if result else 0,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return {
            "status": "error",
            "message": f"PostgreSQL connection failed: {str(e)}",
            "database": POSTGRES_CONFIG['database'],
            "timestamp": datetime.now().isoformat()
        }

@app.get("/streams")
async def get_streams():
    """Obter streams do PostgreSQL externo"""
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        
        table_name = POSTGRES_CONFIG['table_name']
        query = f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 10"
        results = await conn.fetch(query)
        
        await conn.close()
        
        streams = [dict(row) for row in results]
        
        return {
            "status": "success",
            "total": len(streams),
            "streams": streams,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get streams: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get streams: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "message": "Enhanced Stream Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "databases": {
            "internal": "localhost (orchestrator data)",
            "external": f"{POSTGRES_CONFIG['host']} (streams data)"
        },
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "postgres_test": "/postgres/test",
            "streams": "/streams",
            "docs": "/docs"
        }
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
    port = int(os.getenv('ORCHESTRATOR_PORT', '8000'))
    host = os.getenv('ORCHESTRATOR_HOST', '0.0.0.0')
    workers = int(os.getenv('MAX_WORKERS', '1'))
    
    logger.info(f"Starting server on {host}:{port} with {workers} workers")
    
    # Iniciar servidor
    uvicorn.run(
        "main_orchestrator:app",
        host=host,
        port=port,
        workers=workers,
        log_level=os.getenv('LOG_LEVEL', 'info').lower(),
        access_log=True
    )
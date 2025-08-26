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

# Configuração do banco de dados
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
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
    logger.info(f"Database config: {DB_CONFIG}")
    
    # Verificar se todas as variáveis obrigatórias estão definidas
    required_vars = ['host', 'database', 'user', 'password']
    missing_vars = [var for var in required_vars if not DB_CONFIG.get(var)]
    
    if missing_vars:
        logger.warning(f"Missing database configurations: {missing_vars}")
        logger.warning("Starting in limited mode without full orchestrator functionality")
        return
    
    try:
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

@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "message": "Enhanced Stream Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
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
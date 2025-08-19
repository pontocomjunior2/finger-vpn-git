from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from db_pool import db_pool

# Novo: suporte a Redis para leitura em tempo real
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Top-level: função load_env_from_file e configuração de envs

def load_env_from_file(paths: list[str]) -> None:
    """Carrega KEY=VALUE de arquivos .env para os.environ, sobrescrevendo chaves existentes e lendo todos os arquivos em ordem (os últimos prevalecem)."""
    for p in paths:
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if not s or s.startswith("#") or "=" not in s:
                            continue
                        key, value = s.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value
        except Exception:
            pass

BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(BASE_DIR)  # novo: raiz do projeto (d:\dataradio\finger_vpn)
load_env_from_file([
    os.path.join(BASE_DIR, "dashboard-web", ".env.local"),            # recomendado (dev)
    os.path.join(BASE_DIR, ".env.local"),                             # backend local
    os.path.join(BASE_DIR, "dashboard-web.env.local"),                # legado
    os.path.join(BASE_DIR, "dashboard-web", "dashboard-web.env.local"),# legado
    os.path.join(ROOT_DIR, "app.env.local"),                          # novo: raiz do projeto
])

# --- Config DB (mesmas envs do fingerv7.py) ---
DB_HOST = os.getenv('POSTGRES_HOST')
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')
DB_NAME = os.getenv('POSTGRES_DB')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_TABLE_NAME = os.getenv('DB_TABLE_NAME', 'music_log')

# Online/offline threshold: mantenha igual ao app
OFFLINE_THRESHOLD_SECS = int(os.getenv("OFFLINE_THRESHOLD_SECS", "600"))

def connect_db():
    try:
        sslmode = os.getenv("DB_SSLMODE")  # ex.: 'require', 'prefer', 'disable'
        conn_kwargs = {
            "host": DB_HOST,
            "port": DB_PORT,
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASSWORD,
        }
        if sslmode:
            conn_kwargs["sslmode"] = sslmode
        return psycopg2.connect(**conn_kwargs)
    except Exception as e:
        raise RuntimeError(f"DB connection failed (host={DB_HOST}, port={DB_PORT}): {e}")

app = FastAPI(title="Finger Dashboard API", version="1.0.0")

# CORS para facilitar o frontend (Next.js ou outro)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("DASHBOARD_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _row_to_instance(row: Dict[str, Any]) -> Dict[str, Any]:
    # row: server_id, last_heartbeat, status, ip_address, info
    now = datetime.now(timezone.utc)
    last_hb = row["last_heartbeat"]
    # Garantir timezone aware
    if last_hb.tzinfo is None:
        last_hb = last_hb.replace(tzinfo=timezone.utc)
    diff_secs = (now - last_hb).total_seconds()
    is_online = diff_secs <= OFFLINE_THRESHOLD_SECS

    info_json = row.get("info")
    info: Dict[str, Any] = {}
    if isinstance(info_json, (dict, list)):
        info = info_json
    else:
        try:
            info = json.loads(info_json) if info_json else {}
        except Exception:
            info = {}

    # Campos com defaults caso não existam ainda (até todas instâncias atualizarem)
    processing_stream_names = info.get("processing_stream_names", [])
    vpn_info = info.get("vpn", {"in_use": None, "interface": None, "type": None})
    recent_errors = info.get("recent_errors", [])

    return {
        "server_id": row["server_id"],
        "last_heartbeat": last_hb.isoformat(),
        "status": "ONLINE" if is_online else "OFFLINE",
        "ip_address": row.get("ip_address"),
        "info": {
            "hostname": info.get("hostname"),
            "platform": info.get("platform"),
            "cpu_percent": info.get("cpu_percent"),
            "memory_percent": info.get("memory_percent"),
            "memory_available_mb": info.get("memory_available_mb"),
            "disk_percent": info.get("disk_percent"),
            "disk_free_gb": info.get("disk_free_gb"),
            "processing_streams": info.get("processing_streams"),
            "total_streams": info.get("total_streams"),
            "distribution_mode": info.get("distribution_mode"),
            "static_total_servers": info.get("static_total_servers"),
            "cached_active_servers": info.get("cached_active_servers"),
            "python_version": info.get("python_version"),
            # Extras para o dashboard
            "processing_stream_names": processing_stream_names,
            "vpn": vpn_info,
            "recent_errors": recent_errors,
        },
    }

# Configuração Redis (mesmo prefixo do fingerv7.py)
REDIS_URL = os.getenv("REDIS_URL")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "smf:server")
REDIS_HEARTBEAT_TTL_SECS = int(os.getenv("REDIS_HEARTBEAT_TTL_SECS", "120"))

_redis_client: "redis.Redis | None" = None

async def get_redis_client() -> "redis.Redis | None":
    """Inicializa cliente Redis para dashboard (mesmo prefixo smf:)."""
    global _redis_client
    if not REDIS_URL or not REDIS_AVAILABLE:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            await _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client

async def get_redis_server_data(server_id: int) -> Optional[Dict[str, Any]]:
    """Obtém dados de um servidor específico do Redis usando prefixo smf:."""
    client = await get_redis_client()
    if not client:
        return None
    try:
        key = f"{REDIS_KEY_PREFIX}:{server_id}"  # smf:server:1
        data = await client.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None

async def list_redis_online_servers() -> List[Dict[str, Any]]:
    """Lista servidores online via Redis usando prefixo smf:."""
    client = await get_redis_client()
    if not client:
        return []
    
    try:
        pattern = f"{REDIS_KEY_PREFIX}:*"  # smf:server:*
        keys = await client.keys(pattern)
        servers = []
        now_ts = time.time()
        
        for key in keys:
            try:
                server_id = int(key.split(":")[-1])  # smf:server:1 -> 1
                data_str = await client.get(key)
                if not data_str:
                    continue
                    
                data = json.loads(data_str)
                last_ts = data.get("last_ts", 0)
                
                # Verificar se está online baseado no TTL
                is_online = (now_ts - last_ts) < REDIS_HEARTBEAT_TTL_SECS
                
                servers.append({
                    "server_id": server_id,
                    "last_heartbeat": datetime.fromtimestamp(last_ts, timezone.utc).isoformat(),
                    "status": "ONLINE" if is_online else "OFFLINE",
                    "ip_address": data.get("ip_address"),
                    "info": {
                        "processing_streams": data.get("processing_streams", 0),
                        "processing_stream_names": data.get("processing_stream_names", []),
                        # Outros campos serão None até implementarmos cache mais completo
                        "hostname": None,
                        "platform": None,
                        "cpu_percent": None,
                        "memory_percent": None,
                        "memory_available_mb": None,
                        "disk_percent": None,
                        "disk_free_gb": None,
                        "total_streams": None,
                        "distribution_mode": None,
                        "static_total_servers": None,
                        "cached_active_servers": None,
                        "python_version": None,
                        "vpn": {"in_use": None, "interface": None, "type": None},
                        "recent_errors": [],
                    },
                })
            except Exception as e:
                continue
                
        return sorted(servers, key=lambda x: x["server_id"])
    except Exception:
        return []

@app.get("/api/instances")
async def list_instances() -> List[Dict[str, Any]]:
    """
    Lista todas as instâncias. Prioriza Redis (tempo real) quando disponível,
    fallback para DB quando Redis indisponível.
    """
    # Tentar Redis primeiro (tempo real)
    if REDIS_URL and REDIS_AVAILABLE:
        try:
            redis_data = await list_redis_online_servers()
            if redis_data:  # Se temos dados do Redis, usar eles
                return redis_data
        except Exception as e:
            # Log do erro mas continue para fallback DB
            pass
    
    # Fallback: usar DB (comportamento original)
    conn = None
    try:
        conn = db_pool.get_connection_sync()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT server_id, last_heartbeat, status, ip_address, info
                FROM server_heartbeats
                ORDER BY server_id ASC
            """)
            rows = cur.fetchall()
            return [_row_to_instance(dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            db_pool.putconn(conn)

@app.get("/api/instances/{server_id}/last-records")
def last_records(server_id: int, limit: int = Query(5, ge=1, le=50)) -> List[Dict[str, Any]]:
    """
    Retorna os últimos registros gravados no DB pela instância (identified_by = server_id).
    """
    conn = None
    try:
        conn = db_pool.get_connection_sync()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # IMPORTANTE: respeitar tabela configurada via DB_TABLE_NAME
            query = f"""
                SELECT date, time, name, artist, song_title
                FROM {DB_TABLE_NAME}
                WHERE identified_by = %s
                ORDER BY date DESC, time DESC
                LIMIT %s
            """
            cur.execute(query, (str(server_id), limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            db_pool.putconn(conn)

@app.get("/api/instances/{server_id}/errors")
def last_errors(server_id: int) -> Dict[str, Any]:
    """
    Retorna os últimos erros reportados pela instância no último heartbeat (se presentes no info.recent_errors).
    """
    conn = None
    try:
        conn = db_pool.get_connection_sync()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT info
                FROM server_heartbeats
                WHERE server_id = %s
            """, (server_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Instância não encontrada")

            info_json = row["info"]
            try:
                info = json.loads(info_json) if not isinstance(info_json, dict) else info_json
            except Exception:
                info = {}
            errors = info.get("recent_errors", [])
            return {"server_id": server_id, "recent_errors": errors}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            db_pool.putconn(conn)
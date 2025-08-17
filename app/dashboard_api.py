from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
                        # Sobrescreve variáveis existentes para garantir que o .env prevaleça
                        os.environ[key] = value
                # Removido 'break': carregamos todos os arquivos em ordem,
                # permitindo que os últimos sobrescrevam os anteriores.
        except Exception:
            # Silencioso: se não conseguir ler, segue sem interromper o servidor
            pass

BASE_DIR = os.path.dirname(__file__)
load_env_from_file([
    os.path.join(BASE_DIR, "dashboard-web", ".env.local"),            # recomendado
    os.path.join(BASE_DIR, ".env.local"),                             
    os.path.join(BASE_DIR, "dashboard-web.env.local"),                
    os.path.join(BASE_DIR, "dashboard-web", "dashboard-web.env.local")# seu arquivo atual
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

@app.get("/api/instances")
def list_instances() -> List[Dict[str, Any]]:
    """
    Lista todas as instâncias com status (online/offline), VPN, streams e métricas.
    """
    try:
        conn = connect_db()
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
        try:
            conn.close()
        except Exception:
            pass

@app.get("/api/instances/{server_id}/last-records")
def last_records(server_id: int, limit: int = Query(5, ge=1, le=50)) -> List[Dict[str, Any]]:
    """
    Retorna os últimos registros gravados no DB pela instância (identified_by = server_id).
    """
    try:
        conn = connect_db()
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
        try:
            conn.close()
        except Exception:
            pass

@app.get("/api/instances/{server_id}/errors")
def last_errors(server_id: int) -> Dict[str, Any]:
    """
    Retorna os últimos erros reportados pela instância no último heartbeat (se presentes no info.recent_errors).
    """
    try:
        conn = connect_db()
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
        try:
            conn.close()
        except Exception:
            pass
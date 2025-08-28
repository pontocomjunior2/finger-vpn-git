#!/usr/bin/env python3
"""
Monitor contínuo das atribuições de streams para identificar quando desaparecem.
"""

import os
import sys
import time
from datetime import datetime

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path)

# Configuração do banco
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "music_log"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

ORCHESTRATOR_URL = "http://localhost:8080"


def get_assignments_count():
    """Obtém contagem de assignments do banco."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orchestrator_stream_assignments")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count
    except Exception as e:
        return f"ERROR: {e}"


def get_instances_streams():
    """Obtém contadores de streams das instances."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT server_id, current_streams, max_streams, status
            FROM orchestrator_instances 
            ORDER BY server_id
        """
        )
        instances = cursor.fetchall()
        cursor.close()
        conn.close()
        return {inst["server_id"]: inst["current_streams"] for inst in instances}
    except Exception as e:
        return f"ERROR: {e}"


def get_endpoint_assignments():
    """Obtém assignments via endpoint."""
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/streams/assignments", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return len(data.get("assignments", []))
        else:
            return f"HTTP {response.status_code}"
    except Exception as e:
        return f"ERROR: {e}"


def monitor_assignments():
    """Monitora assignments continuamente."""
    print(f"🔍 Monitorando assignments - {datetime.now().strftime('%H:%M:%S')}")
    print("Pressione Ctrl+C para parar\n")

    last_db_count = None
    last_instances = None
    last_endpoint_count = None

    try:
        while True:
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Obter dados atuais
            db_count = get_assignments_count()
            instances = get_instances_streams()
            endpoint_count = get_endpoint_assignments()

            # Verificar mudanças
            db_changed = db_count != last_db_count
            instances_changed = instances != last_instances
            endpoint_changed = endpoint_count != last_endpoint_count

            # Mostrar apenas se houver mudanças ou a cada 30 segundos
            show_status = db_changed or instances_changed or endpoint_changed

            if show_status:
                print(
                    f"[{timestamp}] DB: {db_count} | Instances: {instances} | Endpoint: {endpoint_count}"
                )

                # Detectar inconsistências
                if (
                    isinstance(db_count, int)
                    and isinstance(instances, dict)
                    and isinstance(endpoint_count, int)
                ):
                    total_instance_streams = sum(instances.values())

                    if db_count == 0 and total_instance_streams > 0:
                        print(
                            f"  ⚠️  INCONSISTÊNCIA: DB vazio mas instances têm {total_instance_streams} streams"
                        )

                    if db_count != endpoint_count:
                        print(
                            f"  ⚠️  INCONSISTÊNCIA: DB ({db_count}) != Endpoint ({endpoint_count})"
                        )

                    if db_count > 0 and endpoint_count == 0:
                        print(f"  ⚠️  PROBLEMA: DB tem dados mas endpoint retorna vazio")

                # Atualizar valores anteriores
                last_db_count = db_count
                last_instances = instances
                last_endpoint_count = endpoint_count

            time.sleep(2)  # Verificar a cada 2 segundos

    except KeyboardInterrupt:
        print(
            f"\n🛑 Monitoramento interrompido - {datetime.now().strftime('%H:%M:%S')}"
        )
    except Exception as e:
        print(f"\n❌ Erro no monitoramento: {e}")


if __name__ == "__main__":
    monitor_assignments()

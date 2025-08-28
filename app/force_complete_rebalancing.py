#!/usr/bin/env python3
"""
Script para forçar rebalanceamento completo de streams
Corrige instâncias sobrecarregadas movendo streams para instâncias disponíveis
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List

import psycopg2
import requests

# Configurações do banco de dados
DB_CONFIG = {
    "host": "104.234.173.96",
    "database": "music_log",
    "user": "postgres",
    "password": "Conquista@@2",
    "port": 5432,
}


def get_db_connection():
    """Conecta ao banco de dados PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None


def get_instances_from_api():
    """Obtém instâncias da API do orquestrador"""
    try:
        response = requests.get("http://localhost:8001/instances", timeout=10)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "instances" in data:
            return data["instances"]
        elif isinstance(data, list):
            return data
        else:
            print(f"❌ Estrutura de resposta inesperada")
            return []
    except Exception as e:
        print(f"❌ Erro ao obter instâncias da API: {e}")
        return []


def get_stream_assignments(conn, server_id: str):
    """Obtém assignments de streams de uma instância específica"""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT stream_id, status, assigned_at
            FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
            ORDER BY assigned_at ASC
        """,
            (server_id,),
        )

        return cursor.fetchall()
    except Exception as e:
        print(f"❌ Erro ao obter assignments da instância {server_id}: {e}")
        return []


def move_stream_assignment(conn, stream_id: str, from_server: str, to_server: str):
    """Move um stream assignment de uma instância para outra"""
    try:
        cursor = conn.cursor()

        # Atualizar o assignment
        cursor.execute(
            """
            UPDATE orchestrator_stream_assignments 
            SET server_id = %s, assigned_at = NOW()
            WHERE stream_id = %s AND server_id = %s
        """,
            (to_server, stream_id, from_server),
        )

        if cursor.rowcount > 0:
            conn.commit()
            return True
        else:
            print(
                f"⚠️ Nenhum assignment encontrado para stream {stream_id} na instância {from_server}"
            )
            return False

    except Exception as e:
        print(f"❌ Erro ao mover stream {stream_id}: {e}")
        conn.rollback()
        return False


def update_instance_stream_count(conn, server_id: str):
    """Atualiza o contador de streams de uma instância"""
    try:
        cursor = conn.cursor()

        # Contar streams ativos
        cursor.execute(
            """
            SELECT COUNT(*) 
            FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
        """,
            (server_id,),
        )

        count = cursor.fetchone()[0]

        # Atualizar na tabela de instâncias
        cursor.execute(
            """
            UPDATE orchestrator_instances 
            SET current_streams = %s, last_heartbeat = NOW()
            WHERE server_id = %s
        """,
            (count, server_id),
        )

        conn.commit()
        return count

    except Exception as e:
        print(f"❌ Erro ao atualizar contador da instância {server_id}: {e}")
        conn.rollback()
        return None


def force_rebalance():
    """Força rebalanceamento completo"""
    print(
        f"🔄 REBALANCEAMENTO FORÇADO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print("=" * 80)

    # Conectar ao banco
    conn = get_db_connection()
    if not conn:
        return False

    try:
        # Obter instâncias da API
        instances = get_instances_from_api()
        if not instances:
            print("❌ Nenhuma instância encontrada")
            return False

        # Separar instâncias ativas
        active_instances = [i for i in instances if i["status"] == "active"]

        if not active_instances:
            print("❌ Nenhuma instância ativa encontrada")
            return False

        print(f"📡 Encontradas {len(active_instances)} instâncias ativas")

        # Identificar instâncias sobrecarregadas e disponíveis
        overloaded = []
        available = []

        for instance in active_instances:
            server_id = instance["server_id"]
            current = instance["current_streams"]
            max_streams = instance["max_streams"]

            if current > max_streams:
                excess = current - max_streams
                overloaded.append(
                    {
                        "server_id": server_id,
                        "current": current,
                        "max": max_streams,
                        "excess": excess,
                    }
                )
            elif current < max_streams:
                available_capacity = max_streams - current
                available.append(
                    {
                        "server_id": server_id,
                        "current": current,
                        "max": max_streams,
                        "available": available_capacity,
                    }
                )

        if not overloaded:
            print("✅ Nenhuma instância sobrecarregada encontrada")
            return True

        if not available:
            print("❌ Nenhuma instância com capacidade disponível")
            return False

        print(f"\n⚠️ Instâncias sobrecarregadas: {len(overloaded)}")
        print(f"✅ Instâncias disponíveis: {len(available)}")

        # Ordenar por prioridade
        overloaded.sort(
            key=lambda x: x["excess"], reverse=True
        )  # Mais sobrecarregadas primeiro
        available.sort(
            key=lambda x: x["available"], reverse=True
        )  # Mais capacidade primeiro

        total_moved = 0

        # Processar cada instância sobrecarregada
        for overloaded_instance in overloaded:
            server_id = overloaded_instance["server_id"]
            excess = overloaded_instance["excess"]

            print(f"\n📤 Processando {server_id} (excesso: {excess} streams)")

            # Obter streams desta instância
            stream_assignments = get_stream_assignments(conn, server_id)

            if not stream_assignments:
                print(f"  ⚠️ Nenhum stream assignment encontrado para {server_id}")
                continue

            streams_to_move = min(excess, len(stream_assignments))
            streams_moved_from_instance = 0

            # Mover streams para instâncias disponíveis
            for i in range(streams_to_move):
                if not available:
                    print(f"  ⚠️ Nenhuma instância disponível restante")
                    break

                stream_id, status, assigned_at = stream_assignments[i]

                # Encontrar instância com capacidade
                target_instance = None
                for j, avail_inst in enumerate(available):
                    if avail_inst["available"] > 0:
                        target_instance = avail_inst
                        target_index = j
                        break

                if not target_instance:
                    print(f"  ⚠️ Nenhuma capacidade disponível restante")
                    break

                # Mover o stream
                if move_stream_assignment(
                    conn, stream_id, server_id, target_instance["server_id"]
                ):
                    print(
                        f"  ✅ Stream {stream_id} movido: {server_id} → {target_instance['server_id']}"
                    )

                    # Atualizar contadores
                    available[target_index]["current"] += 1
                    available[target_index]["available"] -= 1

                    streams_moved_from_instance += 1
                    total_moved += 1

                    # Remover instância se não tem mais capacidade
                    if available[target_index]["available"] <= 0:
                        available.pop(target_index)
                else:
                    print(f"  ❌ Falha ao mover stream {stream_id}")

                # Pequena pausa para evitar sobrecarga
                time.sleep(0.1)

            print(f"  📊 Movidos {streams_moved_from_instance} streams de {server_id}")

        print(f"\n📊 Rebalanceamento concluído:")
        print(f"  • Total de streams movidos: {total_moved}")

        # Atualizar contadores de todas as instâncias afetadas
        print(f"\n🔄 Atualizando contadores...")
        for instance in active_instances:
            server_id = instance["server_id"]
            new_count = update_instance_stream_count(conn, server_id)
            if new_count is not None:
                print(f"  ✅ {server_id}: {new_count} streams")

        return True

    except Exception as e:
        print(f"❌ Erro durante rebalanceamento: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = force_rebalance()

    if success:
        print(f"\n🎉 Rebalanceamento concluído com sucesso!")
        print(f"\n🔍 Verificando resultado...")

        # Aguardar um pouco e verificar o resultado
        time.sleep(2)

        # Executar verificação final
        import subprocess

        try:
            subprocess.run(["python", "check_instances_status.py"], check=True)
        except:
            print("⚠️ Não foi possível executar verificação automática")
    else:
        print(f"\n❌ Rebalanceamento falhou")

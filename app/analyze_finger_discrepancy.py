#!/usr/bin/env python3
"""
Análise simplificada da discrepância entre finger e orquestrador.
"""

import os
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "music_log"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}


def analyze_finger_discrepancy():
    """Analisa a discrepância específica do finger SERVER_ID=1."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("=== ANÁLISE DA DISCREPÂNCIA DO FINGER (SERVER_ID=1) ===")
        print(f"Timestamp da análise: {datetime.now()}")
        print()

        # 1. Estado da instância SERVER_ID=1
        print("=== ESTADO DA INSTÂNCIA SERVER_ID=1 ===")
        cursor.execute(
            """
        SELECT 
            id,
            server_id,
            ip,
            port,
            max_streams,
            current_streams,
            status,
            registered_at,
            last_heartbeat,
            EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
        FROM orchestrator_instances 
        WHERE server_id = '1'
        ORDER BY registered_at DESC;
        """
        )

        instances = cursor.fetchall()
        if instances:
            for instance in instances:
                (
                    id_inst,
                    server_id,
                    ip,
                    port,
                    max_streams,
                    current_streams,
                    status,
                    registered_at,
                    last_heartbeat,
                    seconds_since,
                ) = instance
                print(f"Instância ID {id_inst} (Server ID: {server_id}):")
                print(f"  IP:Port: {ip}:{port}")
                print(f"  Max streams: {max_streams}")
                print(f"  Current streams: {current_streams}")
                print(f"  Status: {status}")
                print(f"  Registrado em: {registered_at}")
                print(f"  Último heartbeat: {last_heartbeat}")
                if seconds_since is not None:
                    print(f"  Segundos desde último heartbeat: {seconds_since:.1f}s")
                    if seconds_since > 300:  # 5 minutos
                        print(f"  ⚠️  HEARTBEAT DESATUALIZADO (>{seconds_since:.0f}s)")
                    else:
                        print(f"  ✅ HEARTBEAT ATIVO")
                print()
        else:
            print("❌ Nenhuma instância encontrada com SERVER_ID=1")
            return

        # 2. Assignments ativos para SERVER_ID=1
        print("=== ASSIGNMENTS ATIVOS PARA SERVER_ID=1 ===")
        cursor.execute(
            """
        SELECT 
            osa.id,
            osa.stream_id,
            osa.server_id,
            osa.assigned_at,
            osa.status,
            s.name as stream_name
        FROM orchestrator_stream_assignments osa
        JOIN streams s ON osa.stream_id = s.id
        WHERE osa.server_id = '1' AND osa.status = 'active'
        ORDER BY osa.assigned_at DESC;
        """
        )

        active_assignments = cursor.fetchall()
        print(f"Total de assignments ativos: {len(active_assignments)}")

        if active_assignments:
            print("\nStreams atribuídos:")
            for i, assignment in enumerate(active_assignments, 1):
                assign_id, stream_id, server_id, assigned_at, status, stream_name = (
                    assignment
                )
                print(f"  {i:2d}. {stream_name} (Stream ID: {stream_id})")
                print(f"      Assignment ID: {assign_id}")
                print(f"      Atribuído em: {assigned_at}")
        else:
            print("❌ Nenhum assignment ativo encontrado")

        # 3. Análise da discrepância
        print("\n=== ANÁLISE DA DISCREPÂNCIA ===")

        # Pegar dados da instância mais recente
        latest_instance = instances[0]
        (
            id_inst,
            server_id,
            ip,
            port,
            max_streams,
            current_streams,
            status,
            registered_at,
            last_heartbeat,
            seconds_since,
        ) = latest_instance

        print(f"📊 DADOS DO ORQUESTRADOR:")
        print(f"   Max streams: {max_streams}")
        print(f"   Current streams (reportado pelo finger): {current_streams}")
        print(f"   Status da instância: {status}")
        print()

        print(f"📊 DADOS REAIS DO BANCO:")
        print(f"   Assignments ativos: {len(active_assignments)}")
        print()

        discrepancy = current_streams - len(active_assignments)
        print(f"📊 DISCREPÂNCIA: {discrepancy}")

        if discrepancy > 0:
            print(
                f"   ⚠️  O finger reporta {discrepancy} streams a mais do que o banco mostra"
            )
        elif discrepancy < 0:
            print(
                f"   ⚠️  O banco mostra {abs(discrepancy)} assignments a mais do que o finger reporta"
            )
        else:
            print(f"   ✅ Não há discrepância")

        print()
        print("🔍 EXPLICAÇÃO DA SITUAÇÃO:")

        if current_streams == max_streams and len(active_assignments) == 0:
            print("   🎯 PROBLEMA IDENTIFICADO:")
            print("      - O finger reporta estar na capacidade máxima (20/20 streams)")
            print("      - Mas o banco não mostra nenhum assignment ativo")
            print(
                "      - Isso indica que o finger não estava sincronizado com o orquestrador"
            )
            print(
                "      - Quando o finger foi reiniciado, ele carregou streams do banco local"
            )
            print("      - Mas esses streams não estavam registrados no orquestrador")
            print(
                "      - Por isso o orquestrador liberou 20 streams 'órfãos' e os reatribuiu"
            )
        elif current_streams == 0 and len(active_assignments) > 0:
            print("   🎯 SITUAÇÃO ATUAL:")
            print("      - O finger agora reporta 0 streams")
            print(
                f"      - Mas há {len(active_assignments)} assignments ativos no banco"
            )
            print(
                "      - Isso indica que o finger foi reiniciado e ainda não processou os assignments"
            )
        elif current_streams == len(active_assignments):
            print("   ✅ SITUAÇÃO NORMAL:")
            print("      - O finger e o orquestrador estão sincronizados")

        # 4. Histórico de assignments recentes
        print("\n=== HISTÓRICO DE ASSIGNMENTS RECENTES (SERVER_ID=1) ===")
        cursor.execute(
            """
        SELECT 
            osa.id,
            osa.stream_id,
            osa.server_id,
            osa.assigned_at,
            osa.status,
            s.name as stream_name
        FROM orchestrator_stream_assignments osa
        JOIN streams s ON osa.stream_id = s.id
        WHERE osa.server_id = '1'
        ORDER BY osa.assigned_at DESC
        LIMIT 25;
        """
        )

        all_assignments = cursor.fetchall()

        if all_assignments:
            active_count = len([a for a in all_assignments if a[4] == "active"])
            inactive_count = len([a for a in all_assignments if a[4] != "active"])

            print(f"Últimos 25 assignments: {len(all_assignments)}")
            print(f"  - Ativos: {active_count}")
            print(f"  - Inativos: {inactive_count}")

            print("\nÚltimos assignments (mais recentes primeiro):")
            for i, assignment in enumerate(all_assignments[:10], 1):
                assign_id, stream_id, server_id, assigned_at, status, stream_name = (
                    assignment
                )
                status_icon = "✅" if status == "active" else "❌"
                print(f"  {i:2d}. {status_icon} {stream_name} ({status})")
                print(f"      Assignment ID: {assign_id} - {assigned_at}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Erro durante a análise: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    analyze_finger_discrepancy()

#!/usr/bin/env python3
"""
Análise da discrepância entre finger e orquestrador sobre streams atribuídos.
"""

import os
from datetime import datetime, timedelta

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

def connect_db():
    """Conecta ao banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        return None

def analyze_stream_discrepancy():
    """Analisa a discrepância entre finger e orquestrador."""
    conn = connect_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        print("=== ANÁLISE DE DISCREPÂNCIA FINGER vs ORQUESTRADOR ===")
        print(f"Timestamp da análise: {datetime.now()}")
        print()
        
        # 1. Verificar estado atual das instâncias do orquestrador
        print("=== ESTADO ATUAL DAS INSTÂNCIAS NO ORQUESTRADOR ===")
        cursor.execute("""
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
        ORDER BY id;
        """)
        
        instances = cursor.fetchall()
        print(f"Total de instâncias registradas: {len(instances)}")
        for instance in instances:
            id_inst, server_id, ip, port, max_streams, current_streams, status, registered_at, last_heartbeat, seconds_since = instance
            print(f"\nInstância ID {id_inst} (Server ID: {server_id}):")
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
        
        # 2. Verificar assignments de streams
        print("\n=== ASSIGNMENTS DE STREAMS ===")
        cursor.execute("""
        SELECT 
            osa.id,
            osa.stream_id,
            osa.server_id,
            osa.assigned_at,
            osa.status,
            s.name as stream_name
        FROM orchestrator_stream_assignments osa
        JOIN streams s ON osa.stream_id = s.id
        ORDER BY osa.assigned_at DESC
        LIMIT 20;
        """)
        
        assignments = cursor.fetchall()
        print(f"Total de assignments recentes: {len(assignments)}")
        
        if assignments:
            print("\nÚltimos assignments:")
            for assignment in assignments:
                assign_id, stream_id, server_id, assigned_at, status, stream_name = assignment
                print(f"  Assignment ID: {assign_id}")
                print(f"    Stream: {stream_name} (ID: {stream_id})")
                print(f"    Server ID: {server_id}")
                print(f"    Status: {status}")
                print(f"    Atribuído em: {assigned_at}")
                print()
        
        # 3. Verificar assignments específicos da instância 1 (SERVER_ID=1)
        print("=== ASSIGNMENTS ESPECÍFICOS DO SERVER_ID=1 ===")
        cursor.execute("""
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
        ORDER BY osa.assigned_at DESC;
        """)
        
        server1_assignments = cursor.fetchall()
        print(f"Assignments para SERVER_ID=1: {len(server1_assignments)}")
        
        if server1_assignments:
            active_assignments = [a for a in server1_assignments if a[4] == 'active']
            print(f"Assignments ativos: {len(active_assignments)}")
            
            print("\nDetalhes dos assignments:")
            for assignment in server1_assignments[:10]:  # Mostrar apenas os 10 mais recentes
                assign_id, stream_id, server_id, assigned_at, status, stream_name = assignment
                print(f"  Assignment ID: {assign_id}")
                print(f"    Stream: {stream_name} (ID: {stream_id})")
                print(f"    Server ID: {server_id}")
                print(f"    Status: {status}")
                print(f"    Atribuído em: {assigned_at}")
                print()
        else:
            print("❌ Nenhum assignment encontrado para SERVER_ID=1")
        
        # 4. Verificar heartbeats recentes
        print("=== HEARTBEATS RECENTES ===")
        cursor.execute("""
        SELECT 
            sh.server_id,
            sh.timestamp,
            sh.status,
            EXTRACT(EPOCH FROM (NOW() - sh.timestamp)) as seconds_ago
        FROM server_heartbeats sh
        WHERE sh.timestamp >= NOW() - INTERVAL '1 hour'
        ORDER BY sh.timestamp DESC
        LIMIT 10;
        """)
        
        heartbeats = cursor.fetchall()
        if heartbeats:
            print(f"Heartbeats na última hora: {len(heartbeats)}")
            for heartbeat in heartbeats:
                server_id, timestamp, status, seconds_ago = heartbeat
                print(f"  Server {server_id}: {timestamp} ({seconds_ago:.0f}s atrás) - Status: {status}")
        else:
            print("Nenhum heartbeat encontrado na última hora")
        
        # 5. Verificar histórico de rebalanceamento (se existir)
        print("\n=== HISTÓRICO DE REBALANCEAMENTO ===")
        try:
            cursor.execute("""
            SELECT 
                orh.id,
                orh.action,
                orh.instance_id,
                orh.stream_count,
                orh.reason,
                orh.created_at,
                oi.server_id
            FROM orchestrator_rebalance_history orh
            LEFT JOIN orchestrator_instances oi ON orh.instance_id = oi.id
            WHERE orh.created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY orh.created_at DESC
            LIMIT 15;
            """)
        
            rebalance_history = cursor.fetchall()
            if rebalance_history:
                print(f"Ações de rebalanceamento nas últimas 24h: {len(rebalance_history)}")
                for action in rebalance_history:
                    action_id, action_type, instance_id, stream_count, reason, created_at, server_id = action
                    print(f"  {created_at}: {action_type}")
                    print(f"    Instância: {instance_id} (Server ID: {server_id})")
                    print(f"    Streams: {stream_count}")
                    print(f"    Razão: {reason}")
                    print()
            else:
                print("Nenhuma ação de rebalanceamento nas últimas 24h")
        except psycopg2.errors.UndefinedTable:
            print("Tabela orchestrator_rebalance_history não existe")
        
        # 6. Análise de capacidade vs assignments reais
        print("=== ANÁLISE DE CAPACIDADE vs ASSIGNMENTS REAIS ===")
        cursor.execute("""
        SELECT 
            oi.id,
            oi.server_id,
            oi.max_streams,
            oi.current_streams,
            COUNT(osa.id) FILTER (WHERE osa.status = 'active') as active_assignments,
            oi.current_streams - COUNT(osa.id) FILTER (WHERE osa.status = 'active') as discrepancy,
            oi.status as instance_status
        FROM orchestrator_instances oi
        LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id
        GROUP BY oi.id, oi.server_id, oi.max_streams, oi.current_streams, oi.status
        ORDER BY oi.id;
        """)
        
        capacity_analysis = cursor.fetchall()
        print("Análise de capacidade por instância:")
        for analysis in capacity_analysis:
            instance_id, server_id, max_streams, current_streams, active_assignments, discrepancy, instance_status = analysis
            print(f"\nInstância {instance_id} (Server ID: {server_id}):")
            print(f"  Status da instância: {instance_status}")
            print(f"  Max streams: {max_streams}")
            print(f"  Current streams (reportado): {current_streams}")
            print(f"  Assignments ativos (real): {active_assignments}")
            print(f"  Discrepância: {discrepancy}")
            
            if discrepancy != 0:
                print(f"  ⚠️  DISCREPÂNCIA DETECTADA!")
            
            if server_id == '1':
                print(f"  🎯 ESTA É A INSTÂNCIA DO LOG ANALISADO")
                if current_streams == max_streams:
                    print(f"  📊 EXPLICAÇÃO: Instância reporta estar na capacidade máxima")
                if active_assignments == 0:
                    print(f"  📊 REALIDADE: Não há assignments ativos no banco")
                elif active_assignments > 0:
                    print(f"  📊 REALIDADE: {active_assignments} assignments ativos encontrados no banco")
        
    except Exception as e:
        print(f"Erro durante a análise: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    analyze_stream_discrepancy()
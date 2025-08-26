#!/usr/bin/env python3
"""
Verifica o status dos heartbeats das instâncias.
"""

import os
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

print(f"Variáveis carregadas de {env_path}")

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

print(f"Conectando ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
print(f"Usuário: {DB_CONFIG['user']}")
print(f"Senha: {'*' * len(DB_CONFIG['password'])}")

def check_heartbeats():
    """Verifica status dos heartbeats das instâncias."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("\n=== STATUS DOS HEARTBEATS ===")
        
        # Buscar todas as instâncias
        cursor.execute("""
            SELECT server_id, status, current_streams, max_streams,
                   registered_at, last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
            FROM orchestrator_instances
            ORDER BY server_id
        """)
        
        instances = cursor.fetchall()
        
        if not instances:
            print("Nenhuma instância encontrada")
            return
        
        now = datetime.now()
        
        for instance in instances:
            server_id = instance['server_id']
            status = instance['status']
            current_streams = instance['current_streams']
            max_streams = instance['max_streams']
            registered_at = instance['registered_at']
            last_heartbeat = instance['last_heartbeat']
            seconds_since = instance['seconds_since_heartbeat']
            
            print(f"\n📡 {server_id}:")
            print(f"  Status: {status}")
            print(f"  Streams: {current_streams}/{max_streams}")
            print(f"  Registrado em: {registered_at}")
            print(f"  Último heartbeat: {last_heartbeat}")
            print(f"  Tempo desde último heartbeat: {seconds_since:.0f} segundos")
            
            # Verificar se está dentro do timeout
            if seconds_since > 180:  # 3 minutos
                print(f"  ⚠️  TIMEOUT: Sem heartbeat há {seconds_since:.0f}s (>180s)")
            elif seconds_since > 120:  # 2 minutos
                print(f"  ⚠️  ALERTA: Sem heartbeat há {seconds_since:.0f}s (>120s)")
            else:
                print(f"  ✅ OK: Heartbeat recente")
        
        # Verificar assignments órfãos
        print("\n=== VERIFICAÇÃO DE STREAMS ÓRFÃOS ===")
        cursor.execute("""
            SELECT DISTINCT osa.stream_id, osa.server_id,
                   oi.status, oi.last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - oi.last_heartbeat)) as seconds_since_heartbeat
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE oi.status = 'inactive' 
               OR oi.last_heartbeat < NOW() - INTERVAL '3 minutes'
            ORDER BY osa.stream_id
        """)
        
        orphaned = cursor.fetchall()
        
        if orphaned:
            print(f"🚨 {len(orphaned)} streams órfãos detectados:")
            for stream in orphaned:
                print(f"  Stream {stream['stream_id']} -> {stream['server_id']} ")
                print(f"    (sem heartbeat há {stream['seconds_since_heartbeat']:.0f}s)")
        else:
            print("✅ Nenhum stream órfão detectado")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    check_heartbeats()
import os
from datetime import datetime, timedelta

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    database=os.getenv('POSTGRES_DB'),
    port=os.getenv('POSTGRES_PORT', '5432')
)

cur = conn.cursor()

print("=== RELATÓRIO DE SAÚDE DO ORQUESTRADOR ===")
print(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 50)

# 1. Status geral das instâncias
print("\n📊 STATUS GERAL DAS INSTÂNCIAS")
print("-" * 30)

try:
    response = requests.get('http://localhost:8001/instances')
    instances = response.json()['instances']
    
    active_instances = [i for i in instances if i['current_streams'] > 0]
    total_streams_used = sum(i['current_streams'] for i in instances)
    total_capacity = sum(i['max_streams'] for i in instances)
    
    print(f"Total de instâncias registradas: {len(instances)}")
    print(f"Instâncias ativas (com streams): {len(active_instances)}")
    print(f"Total de streams em uso: {total_streams_used}")
    print(f"Capacidade total: {total_capacity}")
    print(f"Utilização: {(total_streams_used/total_capacity*100):.1f}%")
    
except Exception as e:
    print(f"❌ Erro ao consultar orquestrador: {e}")

# 2. Verificar inconsistências
print("\n🔍 VERIFICAÇÃO DE INCONSISTÊNCIAS")
print("-" * 35)

inconsistencies = []

for instance in instances:
    server_id = instance['server_id']
    orch_streams = instance['current_streams']
    max_streams = instance['max_streams']
    
    # Verificar no banco
    cur.execute("""
        SELECT current_streams, status, last_heartbeat,
               EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
        FROM orchestrator_instances 
        WHERE server_id = %s
    """, (server_id,))
    
    db_result = cur.fetchone()
    if db_result:
        db_streams, status, last_heartbeat, seconds_ago = db_result
        
        # Verificar inconsistências
        if orch_streams != db_streams:
            inconsistencies.append({
                'server_id': server_id,
                'type': 'stream_count_mismatch',
                'orchestrator': orch_streams,
                'database': db_streams
            })
        
        if orch_streams > max_streams:
            inconsistencies.append({
                'server_id': server_id,
                'type': 'exceeds_max_streams',
                'current': orch_streams,
                'max': max_streams
            })
        
        if seconds_ago > 300:  # 5 minutos
            inconsistencies.append({
                'server_id': server_id,
                'type': 'stale_heartbeat',
                'seconds_ago': int(seconds_ago)
            })

if inconsistencies:
    print(f"⚠️  {len(inconsistencies)} inconsistência(s) encontrada(s):")
    for inc in inconsistencies:
        if inc['type'] == 'stream_count_mismatch':
            print(f"   • Instância {inc['server_id']}: Orquestrador={inc['orchestrator']}, DB={inc['database']}")
        elif inc['type'] == 'exceeds_max_streams':
            print(f"   • Instância {inc['server_id']}: {inc['current']} streams > máximo {inc['max']}")
        elif inc['type'] == 'stale_heartbeat':
            print(f"   • Instância {inc['server_id']}: Heartbeat há {inc['seconds_ago']}s")
else:
    print("✅ Nenhuma inconsistência detectada")

# 3. Top instâncias ativas
print("\n🏆 TOP INSTÂNCIAS ATIVAS")
print("-" * 25)

active_sorted = sorted(active_instances, key=lambda x: x['current_streams'], reverse=True)
for i, instance in enumerate(active_sorted[:5], 1):
    utilization = (instance['current_streams'] / instance['max_streams']) * 100
    print(f"{i}. Instância {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} streams ({utilization:.1f}%)")

# 4. Distribuição de streams
print("\n📈 DISTRIBUIÇÃO DE STREAMS")
print("-" * 25)

cur.execute("""
    SELECT 
        COUNT(*) as total_streams,
        COUNT(CASE WHEN status = 'active' THEN 1 END) as assigned_streams,
        COUNT(CASE WHEN status = 'released' THEN 1 END) as released_streams
    FROM orchestrator_stream_assignments
""")

stream_stats = cur.fetchone()
if stream_stats:
    total, assigned, released = stream_stats
    available = total - assigned
    print(f"Total de streams: {total}")
    print(f"Streams atribuídos: {assigned}")
    print(f"Streams disponíveis: {available}")
    print(f"Streams liberados: {released}")

conn.close()

print("\n" + "=" * 50)
print("✅ Relatório concluído")
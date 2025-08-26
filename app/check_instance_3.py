import os

import psycopg2
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

# Verificar streams atribuídos à instância 3
cur.execute("""
    SELECT stream_id, status, assigned_at 
    FROM orchestrator_stream_assignments 
    WHERE server_id = '3' 
    ORDER BY assigned_at DESC 
    LIMIT 10
""")
assignments = cur.fetchall()

print(f'Streams atribuídos à instância 3:')
for stream_id, status, assigned_at in assignments:
    print(f'  Stream {stream_id}: {status} (atribuído em {assigned_at})')

# Verificar estado da instância 3
cur.execute("""
    SELECT server_id, current_streams, max_streams, status, last_heartbeat 
    FROM orchestrator_instances 
    WHERE server_id = '3'
""")
instance = cur.fetchone()
if instance:
    print(f'\nInstância 3:')
    print(f'  Server ID: {instance[0]}')
    print(f'  Current streams: {instance[1]}')
    print(f'  Max streams: {instance[2]}')
    print(f'  Status: {instance[3]}')
    print(f'  Last heartbeat: {instance[4]}')

conn.close()
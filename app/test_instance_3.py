import time

import requests

try:
    response = requests.get('http://10.2.0.2:8000/health', timeout=5)
    print(f'Instância 3 respondeu: {response.status_code} - {response.text}')
except Exception as e:
    print(f'Instância 3 não está respondendo: {e}')

# Verificar se a instância está enviando heartbeats
print('\nVerificando heartbeats recentes...')
import os
from datetime import datetime, timedelta

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

# Verificar último heartbeat
cur.execute("""
    SELECT server_id, last_heartbeat, 
           EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
    FROM orchestrator_instances 
    WHERE server_id = '3'
""")
result = cur.fetchone()

if result:
    server_id, last_heartbeat, seconds_ago = result
    print(f'Último heartbeat da instância {server_id}: {last_heartbeat}')
    print(f'Há {seconds_ago:.0f} segundos atrás')
    
    if seconds_ago > 120:  # Mais de 2 minutos
        print('⚠️  ALERTA: Instância pode estar offline (heartbeat muito antigo)')
    else:
        print('✅ Instância parece estar ativa (heartbeat recente)')
else:
    print('❌ Instância 3 não encontrada no banco de dados')

conn.close()
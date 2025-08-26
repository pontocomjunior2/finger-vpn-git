import json
import os

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

print("=== Diagnóstico da Instância 3 ===")

# 1. Verificar estado atual no banco
cur.execute("""
    SELECT server_id, current_streams, max_streams, status, last_heartbeat 
    FROM orchestrator_instances 
    WHERE server_id = '3'
""")
instance = cur.fetchone()
print(f"Estado no banco: current_streams={instance[1]}, status={instance[3]}")

# 2. Verificar streams atribuídos
cur.execute("""
    SELECT COUNT(*) 
    FROM orchestrator_stream_assignments 
    WHERE server_id = '3' AND status = 'active'
""")
assigned_count = cur.fetchone()[0]
print(f"Streams atribuídos ativos: {assigned_count}")

# 3. Verificar estado no orquestrador
try:
    response = requests.get('http://localhost:8001/instances')
    instances = response.json()['instances']
    instance_3 = next((i for i in instances if i['server_id'] == '3'), None)
    if instance_3:
        print(f"Estado no orquestrador: current_streams={instance_3['current_streams']}")
    else:
        print("Instância 3 não encontrada no orquestrador")
except Exception as e:
    print(f"Erro ao consultar orquestrador: {e}")

print("\n=== Corrigindo Inconsistência ===")

# Se há inconsistência, corrigir
if instance and instance_3 and instance[1] != instance_3['current_streams']:
    print(f"Inconsistência detectada: DB={instance[1]}, Orquestrador={instance_3['current_streams']}")
    
    # Opção 1: Atualizar o banco para refletir o estado do orquestrador
    if instance_3['current_streams'] == 0:
        print("Atualizando banco para refletir estado do orquestrador (0 streams)")
        cur.execute("""
            UPDATE orchestrator_instances 
            SET current_streams = 0 
            WHERE server_id = '3'
        """)
        
        # Liberar streams atribuídos se a instância não está realmente processando
        cur.execute("""
            UPDATE orchestrator_stream_assignments 
            SET status = 'released', released_at = NOW()
            WHERE server_id = '3' AND status = 'active'
        """)
        
        conn.commit()
        print("✅ Banco atualizado - streams liberados")
    
    # Opção 2: Forçar redistribuição
    print("\nForçando redistribuição de streams...")
    try:
        # Simular uma requisição de streams da instância 3
        redistribute_response = requests.post(
            'http://localhost:8001/streams/assign',
            json={'server_id': '3', 'requested_streams': 10}
        )
        if redistribute_response.status_code == 200:
            result = redistribute_response.json()
            print(f"✅ Redistribuição bem-sucedida: {len(result.get('assigned_streams', []))} streams atribuídos")
        else:
            print(f"❌ Erro na redistribuição: {redistribute_response.status_code} - {redistribute_response.text}")
    except Exception as e:
        print(f"❌ Erro ao forçar redistribuição: {e}")

else:
    print("Estados sincronizados ou instância não encontrada")

conn.close()
print("\n=== Diagnóstico Concluído ===")
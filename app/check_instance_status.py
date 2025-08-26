#!/usr/bin/env python3
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    # Conectar ao banco do orquestrador
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB'),
        port=os.getenv('POSTGRES_PORT')
    )
    conn.autocommit = True  # Evitar problemas de transação

    cursor = conn.cursor()

    print("=== VERIFICAÇÃO DO STATUS DA INSTÂNCIA ===")
    
    # Verificar estado da instância 1
    cursor.execute('SELECT server_id, current_streams, max_streams, status, last_heartbeat FROM orchestrator_instances WHERE server_id = %s', ('1',))
    result = cursor.fetchone()

    if result:
        server_id, current_streams, max_streams, status, last_heartbeat = result
        print(f'Instância {server_id}:')
        print(f'  - current_streams: {current_streams}')
        print(f'  - max_streams: {max_streams}')
        print(f'  - status: {status}')
        print(f'  - last_heartbeat: {last_heartbeat}')
        print(f'  - Capacidade disponível: {max_streams - current_streams}')
        
        if current_streams >= max_streams:
            print(f'  ⚠️  PROBLEMA: Instância reportada como na capacidade máxima!')
        else:
            print(f'  ✅ Instância tem capacidade disponível')
    else:
        print('❌ Instância 1 não encontrada no banco de dados')

    print("\n=== VERIFICAÇÃO DE ASSIGNMENTS ===")
    
    # Verificar estrutura da tabela orchestrator_stream_assignments
    try:
        cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'orchestrator_stream_assignments'")
        columns = cursor.fetchall()
        print("Colunas da tabela orchestrator_stream_assignments:")
        for col in columns:
            print(f'  - {col[0]}: {col[1]}')
            
        # Verificar assignments para a instância 1
        cursor.execute('SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE server_id = %s', ('1',))
        assignments_count = cursor.fetchone()[0]
        print(f'\nAssignments para instância 1: {assignments_count}')
        
        if assignments_count > 0:
            cursor.execute('SELECT stream_id FROM orchestrator_stream_assignments WHERE server_id = %s LIMIT 10', ('1',))
            stream_ids = cursor.fetchall()
            print(f'Primeiros stream IDs atribuídos: {[s[0] for s in stream_ids]}')
        
    except Exception as e:
        print(f"Erro ao verificar assignments: {e}")

    print("\n=== VERIFICAÇÃO DE STREAMS DISPONÍVEIS ===")
    
    # Verificar total de streams disponíveis
    try:
        cursor.execute('SELECT COUNT(*) FROM streams')
        total_streams = cursor.fetchone()[0]
        print(f'Total de streams na tabela streams: {total_streams}')
        
        # Verificar alguns IDs de streams
        cursor.execute('SELECT index FROM streams LIMIT 10')
        stream_samples = cursor.fetchall()
        print(f'Primeiros stream IDs disponíveis: {[s[0] for s in stream_samples]}')
        
    except Exception as e:
        print(f"Erro ao verificar streams: {e}")

    conn.close()
    
except Exception as e:
    print(f"Erro: {e}")
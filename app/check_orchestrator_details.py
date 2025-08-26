#!/usr/bin/env python3
import json
import os
from datetime import datetime

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

def check_orchestrator_details():
    """Verifica detalhes do orquestrador e instâncias registradas."""
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB'),
            port=os.getenv('POSTGRES_PORT')
        )
        cursor = conn.cursor()
        
        print("=== ANÁLISE DETALHADA DO ORQUESTRADOR ===")
        
        # 1. Status geral do orquestrador
        print("\n1. STATUS GERAL:")
        try:
            response = requests.get('http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080/status')
            status = response.json()
            print(f"   Status: {status['orchestrator_status']}")
            print(f"   Instâncias totais: {status['instances']['total']}")
            print(f"   Instâncias ativas: {status['instances']['active']}")
            print(f"   Capacidade total: {status['instances']['total_capacity']}")
            print(f"   Carga atual: {status['instances']['current_load']}")
            print(f"   Streams atribuídos: {status['streams']['assigned']}")
            print(f"   Streams disponíveis: {status['streams']['available']}")
            print(f"   Total de streams: {status['streams']['total']}")
            print(f"   Percentual de carga: {status['load_percentage']:.2f}%")
        except Exception as e:
            print(f"   Erro ao obter status: {e}")
        
        # 2. Instâncias registradas
        print("\n2. INSTÂNCIAS REGISTRADAS:")
        cursor.execute("""
            SELECT id, server_id, ip, port, max_streams, current_streams, status, 
                   registered_at, last_heartbeat
            FROM orchestrator_instances 
            ORDER BY server_id, registered_at DESC
        """)
        
        instances = cursor.fetchall()
        if instances:
            for i, inst in enumerate(instances, 1):
                print(f"   {i:2d}. ID: {inst[0]:3d} | Server: {inst[1]:<15} | IP: {inst[2]:<15} | Port: {inst[3]:5d}")
                print(f"       Max: {inst[4]:2d} | Current: {inst[5]:2d} | Status: {inst[6]:<8}")
                print(f"       Registrado: {inst[7]} | Último heartbeat: {inst[8]}")
                print()
        else:
            print("   Nenhuma instância registrada.")
        
        # 3. Verificar instâncias com mesmo SERVER_ID
        print("\n3. INSTÂNCIAS COM MESMO SERVER_ID:")
        cursor.execute("""
            SELECT server_id, COUNT(*) as count, 
                   STRING_AGG(CAST(id AS TEXT), ', ') as instance_ids,
                   STRING_AGG(status, ', ') as statuses
            FROM orchestrator_instances 
            GROUP BY server_id 
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            for dup in duplicates:
                print(f"   Server ID: {dup[0]} | Instâncias: {dup[1]} | IDs: [{dup[2]}] | Status: [{dup[3]}]")
        else:
            print("   ✅ Nenhuma duplicata de SERVER_ID encontrada.")
        
        # 4. Atribuições de streams
        print("\n4. ATRIBUIÇÕES DE STREAMS:")
        cursor.execute("""
            SELECT osa.server_id, COUNT(*) as assigned_streams,
                   oi.max_streams, oi.current_streams, oi.status
            FROM orchestrator_stream_assignments osa
            JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'assigned'
            GROUP BY osa.server_id, oi.max_streams, oi.current_streams, oi.status
            ORDER BY assigned_streams DESC
        """)
        
        assignments = cursor.fetchall()
        if assignments:
            for assign in assignments:
                print(f"   Server: {assign[0]:<15} | Atribuídos: {assign[1]:2d} | Max: {assign[2]:2d} | Current: {assign[3]:2d} | Status: {assign[4]}")
                if assign[1] > assign[2]:  # Mais streams atribuídos que o máximo
                    print(f"   ⚠️  ATENÇÃO: Server {assign[0]} tem mais streams atribuídos ({assign[1]}) que o máximo ({assign[2]})!")
        else:
            print("   Nenhuma atribuição de stream encontrada.")
        
        # 5. Verificar se há streams atribuídos a múltiplas instâncias
        print("\n5. STREAMS ATRIBUÍDOS A MÚLTIPLAS INSTÂNCIAS:")
        cursor.execute("""
            SELECT stream_id, COUNT(*) as assignment_count,
                   STRING_AGG(server_id, ', ') as servers
            FROM orchestrator_stream_assignments 
            WHERE status = 'assigned'
            GROUP BY stream_id 
            HAVING COUNT(*) > 1
            ORDER BY assignment_count DESC
            LIMIT 10
        """)
        
        multi_assignments = cursor.fetchall()
        if multi_assignments:
            print("   ⚠️  STREAMS COM MÚLTIPLAS ATRIBUIÇÕES:")
            for multi in multi_assignments:
                print(f"   Stream {multi[0]}: {multi[1]} atribuições para servers [{multi[2]}]")
        else:
            print("   ✅ Nenhum stream atribuído a múltiplas instâncias.")
        
        # 6. Verificar instâncias ativas vs inativas
        print("\n6. RESUMO POR STATUS:")
        cursor.execute("""
            SELECT status, COUNT(*) as count, 
                   SUM(max_streams) as total_max_streams,
                   SUM(current_streams) as total_current_streams
            FROM orchestrator_instances 
            GROUP BY status
            ORDER BY status
        """)
        
        status_summary = cursor.fetchall()
        for status in status_summary:
            print(f"   Status {status[0]:<8}: {status[1]:2d} instâncias | Max total: {status[2]:3d} | Current total: {status[3]:3d}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro ao verificar detalhes do orquestrador: {e}")

if __name__ == "__main__":
    check_orchestrator_details()
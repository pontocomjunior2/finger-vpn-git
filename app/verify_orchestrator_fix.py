#!/usr/bin/env python3
"""
Script para verificar se a correção do orquestrador está funcionando corretamente.
Verifica se as instâncias estão respeitando o limite de MAX_STREAMS.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def check_orchestrator_state():
    """Verifica o estado atual do orquestrador e instâncias."""
    
    # Configurações do banco de dados
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'postgres'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', '')
    }
    
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=== VERIFICAÇÃO DO ESTADO DO ORQUESTRADOR ===")
        print()
        
        # 1. Verificar instâncias registradas
        print("1. INSTÂNCIAS REGISTRADAS:")
        cursor.execute("""
            SELECT server_id, max_streams, current_streams, status, last_heartbeat
            FROM orchestrator_instances
            ORDER BY server_id
        """)
        
        instances = cursor.fetchall()
        if instances:
            for instance in instances:
                print(f"   Instância {instance['server_id']}:")
                print(f"     - Max Streams: {instance['max_streams']}")
                print(f"     - Current Streams: {instance['current_streams']}")
                print(f"     - Status: {instance['status']}")
                print(f"     - Last Heartbeat: {instance['last_heartbeat']}")
                
                # Verificar se está respeitando o limite
                if instance['current_streams'] > instance['max_streams']:
                    print(f"     ⚠️  PROBLEMA: Instância excede limite! ({instance['current_streams']} > {instance['max_streams']})")
                else:
                    print(f"     ✅ OK: Dentro do limite ({instance['current_streams']} <= {instance['max_streams']})")
                print()
        else:
            print("   Nenhuma instância registrada.")
            print()
        
        # 2. Verificar assignments de streams
        print("2. ASSIGNMENTS DE STREAMS:")
        cursor.execute("""
            SELECT server_id, COUNT(*) as assigned_streams
            FROM orchestrator_stream_assignments
            GROUP BY server_id
            ORDER BY server_id
        """)
        
        assignments = cursor.fetchall()
        if assignments:
            for assignment in assignments:
                print(f"   Instância {assignment['server_id']}: {assignment['assigned_streams']} streams atribuídos")
                
                # Comparar com a instância registrada
                instance = next((i for i in instances if i['server_id'] == assignment['server_id']), None)
                if instance:
                    if assignment['assigned_streams'] != instance['current_streams']:
                        print(f"     ⚠️  INCONSISTÊNCIA: Assignments ({assignment['assigned_streams']}) != Current Streams ({instance['current_streams']})")
                    else:
                        print(f"     ✅ CONSISTENTE: Assignments = Current Streams")
                print()
        else:
            print("   Nenhum assignment encontrado.")
            print()
        
        # 3. Verificar streams disponíveis
        print("3. STREAMS DISPONÍVEIS:")
        cursor.execute("""
            SELECT COUNT(*) as total_streams
            FROM streams
            WHERE status = 'active'
        """)
        
        result = cursor.fetchone()
        total_streams = result['total_streams'] if result else 0
        
        cursor.execute("""
            SELECT COUNT(*) as assigned_streams
            FROM orchestrator_stream_assignments
        """)
        
        result = cursor.fetchone()
        assigned_streams = result['assigned_streams'] if result else 0
        
        available_streams = total_streams - assigned_streams
        
        print(f"   Total de streams ativos: {total_streams}")
        print(f"   Streams atribuídos: {assigned_streams}")
        print(f"   Streams disponíveis: {available_streams}")
        print()
        
        # 4. Resumo da verificação
        print("4. RESUMO DA VERIFICAÇÃO:")
        
        all_within_limits = True
        for instance in instances:
            if instance['current_streams'] > instance['max_streams']:
                all_within_limits = False
                break
        
        if all_within_limits:
            print("   ✅ SUCESSO: Todas as instâncias estão respeitando seus limites de MAX_STREAMS")
        else:
            print("   ❌ PROBLEMA: Algumas instâncias excedem seus limites de MAX_STREAMS")
        
        # Verificar se há capacidade disponível
        total_capacity = sum(i['max_streams'] for i in instances)
        total_used = sum(i['current_streams'] for i in instances)
        
        print(f"   Capacidade total: {total_capacity}")
        print(f"   Capacidade utilizada: {total_used}")
        print(f"   Capacidade disponível: {total_capacity - total_used}")
        
        cursor.close()
        conn.close()
        
        return all_within_limits
        
    except Exception as e:
        print(f"Erro ao verificar estado do orquestrador: {e}")
        return False

if __name__ == "__main__":
    success = check_orchestrator_state()
    if success:
        print("\n🎉 Verificação concluída com sucesso!")
    else:
        print("\n⚠️  Verificação encontrou problemas.")
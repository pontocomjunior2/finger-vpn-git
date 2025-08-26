#!/usr/bin/env python3
"""
Script para debugar por que o rebalanceamento automático não está sendo acionado.
"""

import asyncio
import os
from datetime import datetime

import aiohttp
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://localhost:8001')
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}

def get_db_connection():
    """Conecta ao banco de dados."""
    return psycopg2.connect(**DB_CONFIG)

def analyze_current_state():
    """Analisa o estado atual do sistema antes de registrar nova instância."""
    print("\n=== ANÁLISE DO ESTADO ATUAL ===")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Buscar estatísticas atuais
        cursor.execute("""
            SELECT COUNT(*) as total_instances,
                   SUM(max_streams) as total_capacity,
                   (
                       SELECT COUNT(*) 
                       FROM orchestrator_stream_assignments 
                       WHERE status = 'active'
                   ) as total_assigned_streams
            FROM orchestrator_instances 
            WHERE status = 'active' 
              AND last_heartbeat > NOW() - INTERVAL '1 minute'
        """)
        
        stats = cursor.fetchone()
        total_instances = stats['total_instances']
        total_capacity = stats['total_capacity'] or 0
        total_assigned_streams = stats['total_assigned_streams'] or 0
        
        print(f"📊 Instâncias ativas: {total_instances}")
        print(f"📊 Capacidade total: {total_capacity}")
        print(f"📊 Streams atribuídos: {total_assigned_streams}")
        
        if total_instances > 0:
            avg_load = total_assigned_streams / total_instances
            print(f"📊 Carga média: {avg_load:.2f}")
        
        # Buscar detalhes das instâncias
        cursor.execute("""
            SELECT 
                server_id,
                current_streams,
                max_streams,
                ROUND(CAST(current_streams AS NUMERIC) / CAST(max_streams AS NUMERIC) * 100, 2) as load_percentage,
                last_heartbeat
            FROM orchestrator_instances 
            WHERE status = 'active'
            ORDER BY current_streams DESC
        """)
        
        instances = cursor.fetchall()
        
        print(f"\n📋 Detalhes das instâncias ({len(instances)}):")
        for inst in instances:
            print(f"  🖥️  {inst['server_id']}: {inst['current_streams']}/{inst['max_streams']} ({inst['load_percentage']}%)")
        
        if instances:
            max_load = max(inst['current_streams'] for inst in instances)
            min_load = min(inst['current_streams'] for inst in instances)
            load_diff = max_load - min_load
            
            print(f"\n📈 Análise de carga:")
            print(f"  Carga máxima: {max_load}")
            print(f"  Carga mínima: {min_load}")
            print(f"  Diferença: {load_diff}")
            
            if total_instances > 0:
                avg_load = total_assigned_streams / total_instances
                threshold = avg_load * 1.2
                print(f"  Média: {avg_load:.2f}")
                print(f"  Threshold (120%): {threshold:.2f}")
                print(f"  Rebalanceamento necessário: {'SIM' if max_load > threshold else 'NÃO'}")
        
        return {
            'total_instances': total_instances,
            'total_capacity': total_capacity,
            'total_assigned_streams': total_assigned_streams,
            'instances': instances
        }
        
    finally:
        cursor.close()
        conn.close()

async def register_test_instance(server_id, max_streams=20):
    """Registra uma instância de teste."""
    print(f"\n🔄 Registrando instância de teste: {server_id}")
    
    registration_data = {
        'server_id': server_id,
        'ip': '127.0.0.1',
        'port': 8000,
        'max_streams': max_streams
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{ORCHESTRATOR_URL}/register",
                json=registration_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Instância {server_id} registrada: {result}")
                    return True
                else:
                    text = await response.text()
                    print(f"❌ Falha no registro: {response.status} - {text}")
                    return False
        except Exception as e:
            print(f"❌ Erro no registro: {e}")
            return False

async def simulate_streams(server_id, count):
    """Simula a atribuição de streams para uma instância."""
    print(f"\n📡 Simulando {count} streams para {server_id}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Inserir assignments simulados
        for i in range(count):
            stream_id = f"test-stream-{server_id}-{i}"
            cursor.execute("""
                INSERT INTO orchestrator_stream_assignments 
                (stream_id, server_id, assigned_at, status)
                VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
                ON CONFLICT (stream_id) DO NOTHING
            """, (stream_id, server_id))
        
        # Atualizar contador da instância
        cursor.execute("""
            UPDATE orchestrator_instances 
            SET current_streams = (
                SELECT COUNT(*) 
                FROM orchestrator_stream_assignments 
                WHERE server_id = %s AND status = 'active'
            )
            WHERE server_id = %s
        """, (server_id, server_id))
        
        conn.commit()
        print(f"✅ {count} streams simulados para {server_id}")
        
    except Exception as e:
        print(f"❌ Erro ao simular streams: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

async def cleanup_test_data():
    """Remove dados de teste."""
    print("\n🧹 Limpando dados de teste...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Remover assignments de teste
        cursor.execute("""
            DELETE FROM orchestrator_stream_assignments 
            WHERE CAST(stream_id AS TEXT) LIKE 'test-stream-%'
        """)
        
        # Remover instâncias de teste
        cursor.execute("""
            DELETE FROM orchestrator_instances 
            WHERE CAST(server_id AS TEXT) LIKE 'test-instance-%'
        """)
        
        conn.commit()
        print("✅ Dados de teste removidos")
        
    except Exception as e:
        print(f"❌ Erro na limpeza: {e}")
    finally:
        cursor.close()
        conn.close()

async def main():
    """Função principal do teste."""
    print("🔍 DEBUGANDO TRIGGER DE REBALANCEAMENTO AUTOMÁTICO")
    print("=" * 60)
    
    try:
        # 1. Analisar estado inicial
        print("\n1️⃣ Estado inicial:")
        initial_state = analyze_current_state()
        
        # 2. Se não há instâncias, criar algumas para teste
        if initial_state['total_instances'] == 0:
            print("\n2️⃣ Criando cenário de teste...")
            
            # Registrar primeira instância
            await register_test_instance('debug-test-1', 20)
            await simulate_streams('debug-test-1', 15)
            
            # Registrar segunda instância com carga
            await register_test_instance('debug-test-2', 20)
            await simulate_streams('debug-test-2', 25)
            
            print("\n📊 Estado após setup:")
            analyze_current_state()
        
        # 3. Registrar nova instância que deveria triggerar rebalanceamento
        print("\n3️⃣ Registrando nova instância (deveria triggerar rebalanceamento):")
        await register_test_instance('debug-test-new', 20)
        
        # 4. Aguardar e verificar se houve rebalanceamento
        print("\n⏳ Aguardando possível rebalanceamento...")
        await asyncio.sleep(3)
        
        print("\n4️⃣ Estado final:")
        analyze_current_state()
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpeza
        await cleanup_test_data()

if __name__ == "__main__":
    asyncio.run(main())
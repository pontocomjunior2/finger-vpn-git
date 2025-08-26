#!/usr/bin/env python3
"""
Script para implementar rebalanceamento automático de streams
Corrige instâncias que excedem o limite e redistribui streams
"""

import os
import time
from datetime import datetime, timedelta

import psycopg2
import requests

# Configurações
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '104.234.173.96'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Conquista@@2'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

ORCHESTRATOR_URL = "http://localhost:8001"

def get_db_connection():
    """Conecta ao banco de dados"""
    try:
        return psycopg2.connect(**POSTGRES_CONFIG)
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def get_active_instances():
    """Obtém instâncias ativas do orquestrador"""
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/instances", timeout=10)
        if response.status_code == 200:
            data = response.json()
            instances = data.get('instances', [])
            
            # Filtrar apenas instâncias ativas e com heartbeat recente
            active_instances = []
            cutoff_time = datetime.now() - timedelta(minutes=2)
            
            for instance in instances:
                last_heartbeat = datetime.fromisoformat(instance['last_heartbeat'].replace('Z', '+00:00'))
                if (instance['status'] == 'active' and 
                    last_heartbeat.replace(tzinfo=None) > cutoff_time):
                    active_instances.append(instance)
            
            return active_instances
        else:
            print(f"❌ Erro ao obter instâncias: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Erro ao conectar com orquestrador: {e}")
        return []

def identify_rebalancing_needs(instances):
    """Identifica necessidades de rebalanceamento"""
    overloaded = []  # Instâncias com streams > max_streams
    underutilized = []  # Instâncias com espaço disponível
    
    total_streams = 0
    total_capacity = 0
    
    for instance in instances:
        current = instance['current_streams']
        max_streams = instance['max_streams']
        available = max_streams - current
        
        total_streams += current
        total_capacity += max_streams
        
        if current > max_streams:
            excess = current - max_streams
            overloaded.append({
                'server_id': instance['server_id'],
                'current': current,
                'max': max_streams,
                'excess': excess
            })
        elif available > 0:
            underutilized.append({
                'server_id': instance['server_id'],
                'current': current,
                'max': max_streams,
                'available': available
            })
    
    return {
        'overloaded': overloaded,
        'underutilized': underutilized,
        'total_streams': total_streams,
        'total_capacity': total_capacity,
        'utilization': (total_streams / total_capacity * 100) if total_capacity > 0 else 0
    }

def get_streams_to_move(server_id, count):
    """Obtém streams específicos para mover de uma instância"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        
        # Buscar streams ativos da instância
        cursor.execute("""
            SELECT stream_id, assigned_at
            FROM orchestrator_stream_assignments 
            WHERE server_id = %s 
            AND status = 'active'
            ORDER BY assigned_at ASC
            LIMIT %s
        """, (server_id, count))
        
        streams = cursor.fetchall()
        return [{'stream_id': s[0], 'assigned_at': s[1]} for s in streams]
        
    except Exception as e:
        print(f"❌ Erro ao buscar streams: {e}")
        return []
    finally:
        conn.close()

def move_streams(streams, from_instance, to_instance):
    """Move streams de uma instância para outra"""
    if not streams:
        return True
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        stream_ids = [s['stream_id'] for s in streams]
        
        # Atualizar streams no banco
        cursor.execute("""
            UPDATE orchestrator_stream_assignments 
            SET server_id = %s, assigned_at = NOW()
            WHERE stream_id = ANY(%s) AND server_id = %s
        """, (to_instance, stream_ids, from_instance))
        
        moved_count = cursor.rowcount
        
        if moved_count > 0:
            # Atualizar contadores das instâncias
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = current_streams - %s
                WHERE server_id = %s
            """, (moved_count, from_instance))
            
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = current_streams + %s
                WHERE server_id = %s
            """, (moved_count, to_instance))
            
            conn.commit()
            print(f"   ✅ Movidos {moved_count} streams: {from_instance} → {to_instance}")
            return True
        else:
            print(f"   ⚠️  Nenhum stream foi movido")
            return False
            
    except Exception as e:
        print(f"   ❌ Erro ao mover streams: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def perform_rebalancing(analysis):
    """Executa o rebalanceamento de streams"""
    overloaded = analysis['overloaded']
    underutilized = analysis['underutilized']
    
    if not overloaded:
        print("✅ Nenhuma instância sobrecarregada encontrada")
        return True
    
    if not underutilized:
        print("⚠️  Não há instâncias disponíveis para receber streams")
        return False
    
    print(f"\n🔄 Iniciando rebalanceamento:")
    print(f"   - Instâncias sobrecarregadas: {len(overloaded)}")
    print(f"   - Instâncias disponíveis: {len(underutilized)}")
    
    # Ordenar por prioridade
    overloaded.sort(key=lambda x: x['excess'], reverse=True)  # Mais sobrecarregadas primeiro
    underutilized.sort(key=lambda x: x['available'], reverse=True)  # Mais espaço primeiro
    
    total_moved = 0
    
    for overloaded_instance in overloaded:
        server_id = overloaded_instance['server_id']
        excess = overloaded_instance['excess']
        
        print(f"\n📤 Processando {server_id} (excesso: {excess} streams):")
        
        remaining_excess = excess
        
        for underutilized_instance in underutilized:
            if remaining_excess <= 0:
                break
            
            target_id = underutilized_instance['server_id']
            available = underutilized_instance['available']
            
            if available <= 0:
                continue
            
            # Calcular quantos streams mover
            to_move = min(remaining_excess, available)
            
            print(f"   📋 Movendo {to_move} streams para {target_id}...")
            
            # Obter streams específicos para mover
            streams = get_streams_to_move(server_id, to_move)
            
            if streams:
                success = move_streams(streams, server_id, target_id)
                if success:
                    remaining_excess -= to_move
                    underutilized_instance['available'] -= to_move
                    total_moved += to_move
                else:
                    print(f"   ❌ Falha ao mover streams")
            else:
                print(f"   ⚠️  Nenhum stream encontrado para mover")
        
        if remaining_excess > 0:
            print(f"   ⚠️  Ainda há {remaining_excess} streams em excesso")
    
    print(f"\n📊 Rebalanceamento concluído:")
    print(f"   - Total de streams movidos: {total_moved}")
    
    return total_moved > 0

def cleanup_orphaned_streams():
    """Remove streams órfãos (de instâncias inativas)"""
    print("\n🧹 Limpando streams órfãos...")
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Encontrar streams de instâncias inativas
        cursor.execute("""
            SELECT s.stream_id, s.server_id
            FROM orchestrator_stream_assignments s
            LEFT JOIN orchestrator_instances i ON s.server_id = i.server_id
            WHERE s.status = 'active' 
            AND (i.status != 'active' OR i.last_heartbeat < NOW() - INTERVAL '5 minutes')
        """)
        
        orphaned_streams = cursor.fetchall()
        
        if not orphaned_streams:
            print("   ✅ Nenhum stream órfão encontrado")
            return True
        
        print(f"   🔍 Encontrados {len(orphaned_streams)} streams órfãos")
        
        # Marcar streams como órfãos para reatribuição
        orphaned_ids = [s[0] for s in orphaned_streams]
        
        cursor.execute("""
            UPDATE orchestrator_stream_assignments 
            SET status = 'pending', assigned_at = NOW()
            WHERE stream_id = ANY(%s)
        """, (orphaned_ids,))
        
        conn.commit()
        print(f"   ✅ {cursor.rowcount} streams marcados para reatribuição")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Erro na limpeza: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def reassign_pending_streams():
    """Reatribui streams pendentes para instâncias ativas"""
    print("\n🔄 Reatribuindo streams pendentes...")
    
    # Obter instâncias ativas
    active_instances = get_active_instances()
    if not active_instances:
        print("   ❌ Nenhuma instância ativa disponível")
        return False
    
    # Filtrar instâncias com espaço disponível
    available_instances = [
        inst for inst in active_instances 
        if inst['current_streams'] < inst['max_streams']
    ]
    
    if not available_instances:
        print("   ⚠️  Todas as instâncias estão no limite")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Buscar streams pendentes
        cursor.execute("""
            SELECT stream_id 
            FROM orchestrator_stream_assignments 
            WHERE status = 'pending'
            ORDER BY assigned_at ASC
        """)
        
        pending_streams = cursor.fetchall()
        
        if not pending_streams:
            print("   ✅ Nenhum stream pendente encontrado")
            return True
        
        print(f"   🔍 Encontrados {len(pending_streams)} streams pendentes")
        
        # Distribuir streams
        assigned_count = 0
        instance_index = 0
        
        for (stream_id,) in pending_streams:
            # Encontrar instância com espaço
            while instance_index < len(available_instances):
                instance = available_instances[instance_index]
                if instance['current_streams'] < instance['max_streams']:
                    # Atribuir stream
                    cursor.execute("""
                        UPDATE orchestrator_stream_assignments 
                        SET server_id = %s, status = 'active', assigned_at = NOW()
                        WHERE stream_id = %s
                    """, (instance['server_id'], stream_id))
                    
                    # Atualizar contador da instância
                    cursor.execute("""
                        UPDATE orchestrator_instances 
                        SET current_streams = current_streams + 1
                        WHERE server_id = %s
                    """, (instance['server_id'],))
                    
                    instance['current_streams'] += 1
                    assigned_count += 1
                    
                    print(f"   ✅ Stream {stream_id} → {instance['server_id']}")
                    break
                else:
                    instance_index += 1
            
            if instance_index >= len(available_instances):
                print(f"   ⚠️  Não há mais espaço para atribuir streams")
                break
        
        conn.commit()
        print(f"   📊 {assigned_count} streams reatribuídos")
        
        return assigned_count > 0
        
    except Exception as e:
        print(f"   ❌ Erro na reatribuição: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def main():
    """Função principal"""
    print("🔄 REBALANCEAMENTO AUTOMÁTICO DE STREAMS")
    print("=" * 80)
    print(f"⏰ Executado em: {datetime.now()}")
    
    # 1. Obter instâncias ativas
    print("\n📡 Obtendo instâncias ativas...")
    instances = get_active_instances()
    
    if not instances:
        print("❌ Nenhuma instância ativa encontrada")
        return
    
    print(f"✅ Encontradas {len(instances)} instâncias ativas")
    
    # 2. Analisar necessidades de rebalanceamento
    print("\n📊 Analisando distribuição de streams...")
    analysis = identify_rebalancing_needs(instances)
    
    print(f"   - Total de streams: {analysis['total_streams']}")
    print(f"   - Capacidade total: {analysis['total_capacity']}")
    print(f"   - Utilização: {analysis['utilization']:.1f}%")
    print(f"   - Instâncias sobrecarregadas: {len(analysis['overloaded'])}")
    print(f"   - Instâncias disponíveis: {len(analysis['underutilized'])}")
    
    # 3. Limpar streams órfãos
    cleanup_orphaned_streams()
    
    # 4. Executar rebalanceamento
    if analysis['overloaded']:
        perform_rebalancing(analysis)
    else:
        print("\n✅ Sistema já está balanceado")
    
    # 5. Reatribuir streams pendentes
    reassign_pending_streams()
    
    # 6. Verificação final
    print("\n🔍 Verificação final...")
    final_instances = get_active_instances()
    final_analysis = identify_rebalancing_needs(final_instances)
    
    print(f"\n📊 Estado final:")
    print(f"   - Total de streams: {final_analysis['total_streams']}")
    print(f"   - Utilização: {final_analysis['utilization']:.1f}%")
    print(f"   - Instâncias sobrecarregadas: {len(final_analysis['overloaded'])}")
    
    if final_analysis['overloaded']:
        print("\n⚠️  Ainda há instâncias sobrecarregadas:")
        for instance in final_analysis['overloaded']:
            print(f"   - {instance['server_id']}: {instance['current']}/{instance['max']} (+{instance['excess']})")
    else:
        print("\n🎉 Sistema totalmente balanceado!")
    
    print("\n" + "=" * 80)
    print("🏁 REBALANCEAMENTO CONCLUÍDO")

if __name__ == "__main__":
    main()
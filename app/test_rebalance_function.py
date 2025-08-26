#!/usr/bin/env python3
"""
Script para testar diretamente a função de rebalanceamento
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
root_env_file = Path(__file__).parent.parent / ".env"
if root_env_file.exists():
    load_dotenv(root_env_file)

# Configuração do banco
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "database": os.getenv("POSTGRES_DB", "music_log"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
}

def get_db_connection():
    """Conecta ao banco de dados"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def test_rebalance_function():
    """Testa a função de rebalanceamento diretamente"""
    print("🧪 TESTANDO FUNÇÃO DE REBALANCEAMENTO")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        print("\n1️⃣ Verificando instâncias ativas...")
        
        # Buscar todas as instâncias ativas com suas cargas atuais
        cursor.execute(
            """
            SELECT 
                oi.server_id, 
                oi.max_streams,
                COALESCE(COUNT(osa.stream_id), 0) as current_streams
            FROM orchestrator_instances oi
            LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id AND osa.status = 'active'
            WHERE oi.status = 'active' 
              AND oi.last_heartbeat > NOW() - INTERVAL '1 minute'
            GROUP BY oi.server_id, oi.max_streams
            ORDER BY oi.server_id
        """
        )
        
        active_instances = cursor.fetchall()
        
        if not active_instances:
            print("❌ Nenhuma instância ativa encontrada")
            return False
        
        print(f"✅ Encontradas {len(active_instances)} instâncias ativas:")
        for instance in active_instances:
            print(f"   - {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']}")
        
        # Calcular estatísticas atuais
        total_capacity = sum(instance["max_streams"] for instance in active_instances)
        total_streams = sum(instance["current_streams"] for instance in active_instances)
        
        print(f"\n📊 Estatísticas:")
        print(f"   - Total de streams: {total_streams}")
        print(f"   - Capacidade total: {total_capacity}")
        print(f"   - Utilização: {(total_streams/total_capacity*100):.1f}%")
        
        if total_streams == 0:
            print("⚠️  Nenhum stream atribuído encontrado")
            return True
        
        if total_streams > total_capacity:
            print(f"❌ Número de streams ({total_streams}) excede capacidade total ({total_capacity})")
            return False
        
        print("\n2️⃣ Calculando distribuição ideal...")
        
        # Calcular distribuição ideal baseada na capacidade proporcional
        target_distribution = {}
        remaining_streams = total_streams
        
        # Primeira passada: distribuição proporcional
        for instance in active_instances:
            server_id = instance["server_id"]
            max_streams = instance["max_streams"]
            
            # Calcular proporção baseada na capacidade
            proportion = max_streams / total_capacity
            ideal_count = int(total_streams * proportion)
            
            # Garantir que não exceda a capacidade da instância
            target_count = min(ideal_count, max_streams, remaining_streams)
            target_distribution[server_id] = target_count
            remaining_streams -= target_count
        
        # Segunda passada: distribuir streams restantes
        if remaining_streams > 0:
            print(f"   - Distribuindo {remaining_streams} streams restantes...")
            # Ordenar instâncias por capacidade disponível
            available_instances = [
                (server_id, instance["max_streams"] - target_distribution[server_id])
                for instance in active_instances
                for server_id in [instance["server_id"]]
                if target_distribution[server_id] < instance["max_streams"]
            ]
            available_instances.sort(key=lambda x: x[1], reverse=True)
            
            for server_id, available_capacity in available_instances:
                if remaining_streams <= 0:
                    break
                
                additional = min(remaining_streams, available_capacity)
                target_distribution[server_id] += additional
                remaining_streams -= additional
        
        print(f"✅ Distribuição alvo calculada:")
        for server_id, target in target_distribution.items():
            current = next(inst["current_streams"] for inst in active_instances if inst["server_id"] == server_id)
            print(f"   - {server_id}: {current} → {target} ({target-current:+d})")
        
        print("\n3️⃣ Verificando necessidade de rebalanceamento...")
        
        # Verificar se rebalanceamento é necessário
        current_distribution = {instance["server_id"]: instance["current_streams"] for instance in active_instances}
        
        # Calcular diferença
        needs_rebalancing = False
        max_diff = 0
        for server_id in target_distribution:
            current = current_distribution.get(server_id, 0)
            target = target_distribution[server_id]
            diff = abs(current - target)
            max_diff = max(max_diff, diff)
            if diff > 1:  # Tolerância de 1 stream
                needs_rebalancing = True
        
        print(f"   - Maior diferença: {max_diff} streams")
        print(f"   - Rebalanceamento necessário: {'SIM' if needs_rebalancing else 'NÃO'}")
        
        if not needs_rebalancing:
            print("✅ Sistema já está balanceado")
            return True
        
        print("\n4️⃣ Executando rebalanceamento...")
        
        # Buscar todos os streams atribuídos
        cursor.execute(
            """
            SELECT stream_id, server_id
            FROM orchestrator_stream_assignments
            WHERE status = 'active'
            ORDER BY assigned_at ASC
        """
        )
        
        current_assignments = cursor.fetchall()
        print(f"   - Encontrados {len(current_assignments)} streams atribuídos")
        
        # Implementar rebalanceamento incremental
        # 1. Identificar instâncias que precisam liberar streams
        streams_to_move = []
        
        print("\n   📤 Identificando streams para mover:")
        for instance in active_instances:
            server_id = instance["server_id"]
            current = current_distribution[server_id]
            target = target_distribution[server_id]
            
            if current > target:
                # Esta instância precisa liberar streams
                excess = current - target
                print(f"      - {server_id}: precisa liberar {excess} streams")
                
                # Buscar streams desta instância para mover
                instance_streams = [
                    assignment["stream_id"] for assignment in current_assignments
                    if assignment["server_id"] == server_id
                ][:excess]
                
                streams_to_move.extend(instance_streams)
                print(f"        Streams selecionados: {instance_streams}")
        
        print(f"   - Total de streams para mover: {len(streams_to_move)}")
        
        # 2. Reatribuir streams para instâncias que precisam de mais
        if streams_to_move:
            print("\n   🔄 Executando movimentação...")
            
            # Primeiro, liberar os streams que serão movidos
            print(f"      - Liberando {len(streams_to_move)} streams...")
            cursor.execute(
                "DELETE FROM orchestrator_stream_assignments WHERE stream_id = ANY(%s)",
                (streams_to_move,)
            )
            deleted_count = cursor.rowcount
            print(f"      - {deleted_count} streams liberados")
            
            # Redistribuir para instâncias que precisam
            new_assignments = []
            stream_index = 0
            
            print("      - Redistribuindo streams:")
            for instance in active_instances:
                server_id = instance["server_id"]
                current = current_distribution[server_id]
                target = target_distribution[server_id]
                
                if current < target:
                    # Esta instância precisa receber streams
                    needed = target - current
                    print(f"        {server_id}: precisa receber {needed} streams")
                    
                    for _ in range(needed):
                        if stream_index < len(streams_to_move):
                            stream_id = streams_to_move[stream_index]
                            new_assignments.append((stream_id, server_id))
                            print(f"          Stream {stream_id} → {server_id}")
                            stream_index += 1
            
            # Executar novas atribuições
            if new_assignments:
                print(f"      - Inserindo {len(new_assignments)} novas atribuições...")
                cursor.executemany(
                    """
                    INSERT INTO orchestrator_stream_assignments 
                    (stream_id, server_id, assigned_at, status)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, 'active')
                """,
                    new_assignments,
                )
                inserted_count = cursor.rowcount
                print(f"      - {inserted_count} atribuições inseridas")
            
            # Atualizar contadores das instâncias
            print("      - Atualizando contadores...")
            cursor.execute(
                """
                UPDATE orchestrator_instances 
                SET current_streams = (
                    SELECT COUNT(*) 
                    FROM orchestrator_stream_assignments 
                    WHERE server_id = orchestrator_instances.server_id 
                      AND status = 'active'
                )
                WHERE status = 'active'
            """
            )
            updated_count = cursor.rowcount
            print(f"      - {updated_count} instâncias atualizadas")
            
            conn.commit()
            print("      ✅ Transação commitada")
        
        print("\n5️⃣ Verificando resultado final...")
        
        # Log da nova distribuição
        cursor.execute(
            """
            SELECT 
                oi.server_id,
                oi.current_streams,
                oi.max_streams
            FROM orchestrator_instances oi
            WHERE oi.status = 'active'
            ORDER BY oi.server_id
        """
        )
        
        final_distribution = cursor.fetchall()
        print(f"✅ Rebalanceamento concluído. Nova distribuição:")
        for dist in final_distribution:
            utilization = (dist['current_streams'] / dist['max_streams'] * 100) if dist['max_streams'] > 0 else 0
            print(f"   - {dist['server_id']}: {dist['current_streams']}/{dist['max_streams']} ({utilization:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro durante teste: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = test_rebalance_function()
    if success:
        print("\n🎉 Teste concluído com sucesso!")
    else:
        print("\n❌ Teste falhou!")
        sys.exit(1)
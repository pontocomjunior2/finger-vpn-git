#!/usr/bin/env python3
"""
Script para verificar a integridade dos streams no banco de dados
"""

import os
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

def check_stream_integrity():
    """Verifica a integridade dos streams"""
    print("🔍 VERIFICANDO INTEGRIDADE DOS STREAMS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        print("\n1️⃣ Verificando tabela de streams...")
        
        # Verificar total de streams na tabela principal
        cursor.execute("SELECT COUNT(*) as total FROM streams")
        total_streams = cursor.fetchone()['total']
        print(f"   - Total de streams na tabela 'streams': {total_streams}")
        
        print("\n2️⃣ Verificando assignments...")
        
        # Verificar assignments por status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM orchestrator_stream_assignments
            GROUP BY status
            ORDER BY status
        """)
        
        assignments_by_status = cursor.fetchall()
        print("   - Assignments por status:")
        total_assignments = 0
        for row in assignments_by_status:
            print(f"     {row['status']}: {row['count']}")
            total_assignments += row['count']
        print(f"   - Total de assignments: {total_assignments}")
        
        print("\n3️⃣ Verificando duplicatas...")
        
        # Verificar streams duplicados
        cursor.execute("""
            SELECT stream_id, COUNT(*) as count
            FROM orchestrator_stream_assignments
            WHERE status = 'active'
            GROUP BY stream_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC, stream_id
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"   ❌ Encontradas {len(duplicates)} duplicatas:")
            for dup in duplicates[:10]:  # Mostrar apenas os primeiros 10
                print(f"     Stream {dup['stream_id']}: {dup['count']} assignments")
            if len(duplicates) > 10:
                print(f"     ... e mais {len(duplicates) - 10} duplicatas")
        else:
            print("   ✅ Nenhuma duplicata encontrada")
        
        print("\n4️⃣ Verificando streams órfãos...")
        
        # Verificar streams atribuídos a instâncias inativas
        cursor.execute("""
            SELECT 
                osa.server_id,
                COUNT(*) as orphaned_streams,
                oi.status as instance_status,
                oi.last_heartbeat
            FROM orchestrator_stream_assignments osa
            LEFT JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE osa.status = 'active'
              AND (oi.status IS NULL OR oi.status != 'active' OR oi.last_heartbeat < NOW() - INTERVAL '1 minute')
            GROUP BY osa.server_id, oi.status, oi.last_heartbeat
            ORDER BY orphaned_streams DESC
        """)
        
        orphaned = cursor.fetchall()
        if orphaned:
            print(f"   ❌ Encontrados streams órfãos:")
            total_orphaned = 0
            for orph in orphaned:
                print(f"     {orph['server_id']}: {orph['orphaned_streams']} streams (status: {orph['instance_status']})")
                total_orphaned += orph['orphaned_streams']
            print(f"   - Total de streams órfãos: {total_orphaned}")
        else:
            print("   ✅ Nenhum stream órfão encontrado")
        
        print("\n5️⃣ Verificando instâncias ativas...")
        
        # Verificar instâncias ativas e suas cargas
        cursor.execute("""
            SELECT 
                oi.server_id,
                oi.current_streams as reported_streams,
                oi.max_streams,
                oi.status,
                oi.last_heartbeat,
                COALESCE(COUNT(osa.stream_id), 0) as actual_streams
            FROM orchestrator_instances oi
            LEFT JOIN orchestrator_stream_assignments osa ON oi.server_id = osa.server_id AND osa.status = 'active'
            WHERE oi.status = 'active'
              AND oi.last_heartbeat > NOW() - INTERVAL '1 minute'
            GROUP BY oi.server_id, oi.current_streams, oi.max_streams, oi.status, oi.last_heartbeat
            ORDER BY oi.server_id
        """)
        
        active_instances = cursor.fetchall()
        print(f"   - Instâncias ativas: {len(active_instances)}")
        
        total_capacity = 0
        total_reported = 0
        total_actual = 0
        
        for instance in active_instances:
            reported = instance['reported_streams']
            actual = instance['actual_streams']
            max_streams = instance['max_streams']
            
            status_icon = "✅" if reported == actual else "⚠️"
            overload_icon = "🔥" if actual > max_streams else ""
            
            print(f"     {status_icon} {instance['server_id']}: {reported}→{actual}/{max_streams} {overload_icon}")
            
            total_capacity += max_streams
            total_reported += reported
            total_actual += actual
        
        print(f"\n📊 Resumo:")
        print(f"   - Capacidade total: {total_capacity}")
        print(f"   - Streams reportados: {total_reported}")
        print(f"   - Streams reais: {total_actual}")
        print(f"   - Diferença: {total_actual - total_reported}")
        print(f"   - Sobrecarga: {total_actual - total_capacity} streams")
        
        if total_actual > total_capacity:
            print(f"\n⚠️  PROBLEMA: Sistema sobrecarregado em {total_actual - total_capacity} streams!")
            print("   Possíveis causas:")
            print("   - Streams órfãos de instâncias inativas")
            print("   - Assignments duplicados")
            print("   - Contadores desatualizados")
            
            # Sugerir correções
            print("\n🔧 Sugestões de correção:")
            if orphaned:
                print("   1. Limpar streams órfãos")
            if duplicates:
                print("   2. Remover assignments duplicados")
            print("   3. Atualizar contadores das instâncias")
            print("   4. Executar rebalanceamento forçado")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro durante verificação: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()
        conn.close()

def fix_stream_integrity():
    """Corrige problemas de integridade dos streams"""
    print("\n🔧 CORRIGINDO INTEGRIDADE DOS STREAMS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        print("\n1️⃣ Removendo streams órfãos...")
        
        # Remover streams de instâncias inativas
        cursor.execute("""
            DELETE FROM orchestrator_stream_assignments
            WHERE status = 'active'
              AND server_id NOT IN (
                  SELECT server_id 
                  FROM orchestrator_instances 
                  WHERE status = 'active' 
                    AND last_heartbeat > NOW() - INTERVAL '1 minute'
              )
        """)
        
        orphaned_removed = cursor.rowcount
        print(f"   ✅ {orphaned_removed} streams órfãos removidos")
        
        print("\n2️⃣ Removendo duplicatas...")
        
        # Remover assignments duplicados (manter apenas o mais recente)
        cursor.execute("""
            DELETE FROM orchestrator_stream_assignments
            WHERE id NOT IN (
                SELECT DISTINCT ON (stream_id) id
                FROM orchestrator_stream_assignments
                WHERE status = 'active'
                ORDER BY stream_id, assigned_at DESC
            )
            AND status = 'active'
        """)
        
        duplicates_removed = cursor.rowcount
        print(f"   ✅ {duplicates_removed} duplicatas removidas")
        
        print("\n3️⃣ Atualizando contadores das instâncias...")
        
        # Atualizar contadores
        cursor.execute("""
            UPDATE orchestrator_instances 
            SET current_streams = (
                SELECT COUNT(*) 
                FROM orchestrator_stream_assignments 
                WHERE server_id = orchestrator_instances.server_id 
                  AND status = 'active'
            )
            WHERE status = 'active'
        """)
        
        instances_updated = cursor.rowcount
        print(f"   ✅ {instances_updated} instâncias atualizadas")
        
        conn.commit()
        print("\n✅ Correções aplicadas com sucesso!")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro durante correção: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Verificar integridade
    if check_stream_integrity():
        # Perguntar se deve corrigir
        response = input("\n🤔 Deseja corrigir os problemas encontrados? (s/N): ")
        if response.lower() in ['s', 'sim', 'y', 'yes']:
            if fix_stream_integrity():
                print("\n🎉 Correções aplicadas! Verificando novamente...")
                check_stream_integrity()
            else:
                print("\n❌ Falha ao aplicar correções!")
        else:
            print("\n👋 Nenhuma correção aplicada.")
    else:
        print("\n❌ Falha na verificação!")
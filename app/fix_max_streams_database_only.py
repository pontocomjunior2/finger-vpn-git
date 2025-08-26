#!/usr/bin/env python3
"""
Script para corrigir max_streams diretamente no banco de dados
Atualiza todas as instâncias para max_streams=20
"""

import os
from datetime import datetime

import psycopg2

# Configurações do banco
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '104.234.173.96'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Conquista@@2'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

def get_db_connection():
    """Conecta ao banco de dados"""
    try:
        return psycopg2.connect(**POSTGRES_CONFIG)
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def check_and_fix_max_streams():
    """Verifica e corrige max_streams no banco de dados"""
    print("\n🔧 CORRIGINDO MAX_STREAMS NO BANCO DE DADOS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # 1. Verificar estado atual
        print("\n📊 Estado atual das instâncias:")
        cursor.execute("""
            SELECT server_id, max_streams, current_streams, status,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
            FROM orchestrator_instances 
            ORDER BY last_heartbeat DESC
        """)
        
        instances = cursor.fetchall()
        problem_instances = []
        
        for instance in instances:
            server_id, max_streams, current_streams, status, seconds_since = instance
            print(f"   - {server_id}: max_streams={max_streams}, current={current_streams}, status={status}")
            
            if max_streams != 20:
                problem_instances.append(server_id)
        
        print(f"\n📈 Resumo:")
        print(f"   - Total de instâncias: {len(instances)}")
        print(f"   - Instâncias com max_streams incorreto: {len(problem_instances)}")
        
        if not problem_instances:
            print("\n✅ Todas as instâncias já têm max_streams=20")
            return True
        
        # 2. Corrigir instâncias problemáticas
        print(f"\n🔄 Corrigindo {len(problem_instances)} instâncias:")
        
        for server_id in problem_instances:
            print(f"   - Corrigindo {server_id}...")
            
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET max_streams = 20
                WHERE server_id = %s
            """, (server_id,))
            
            if cursor.rowcount > 0:
                print(f"     ✅ Atualizado com sucesso")
            else:
                print(f"     ❌ Falha na atualização")
        
        # 3. Commit das alterações
        conn.commit()
        print(f"\n✅ Todas as correções foram aplicadas")
        
        # 4. Verificar resultado final
        print(f"\n🔍 Verificação final:")
        cursor.execute("""
            SELECT server_id, max_streams, current_streams 
            FROM orchestrator_instances 
            WHERE max_streams != 20
        """)
        
        remaining_problems = cursor.fetchall()
        
        if not remaining_problems:
            print(f"   ✅ Todas as instâncias agora têm max_streams=20")
        else:
            print(f"   ⚠️  Ainda há {len(remaining_problems)} instâncias com problemas:")
            for server_id, max_streams, current_streams in remaining_problems:
                print(f"      - {server_id}: max_streams={max_streams}")
        
        return len(remaining_problems) == 0
        
    except Exception as e:
        print(f"❌ Erro ao corrigir banco: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def check_stream_assignments():
    """Verifica se há problemas com atribuições de streams"""
    print("\n📋 VERIFICANDO ATRIBUIÇÕES DE STREAMS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Verificar instâncias que excedem o limite
        cursor.execute("""
            SELECT oi.server_id, oi.max_streams, oi.current_streams,
                   (oi.current_streams - oi.max_streams) as excess
            FROM orchestrator_instances oi
            WHERE oi.current_streams > oi.max_streams
            ORDER BY excess DESC
        """)
        
        excess_instances = cursor.fetchall()
        
        if excess_instances:
            print(f"⚠️  Instâncias excedendo limite:")
            for server_id, max_streams, current_streams, excess in excess_instances:
                print(f"   - {server_id}: {current_streams}/{max_streams} (+{excess} streams)")
        else:
            print(f"✅ Nenhuma instância excede seu limite")
        
        # Verificar capacidade total
        cursor.execute("""
            SELECT 
                SUM(max_streams) as total_capacity,
                SUM(current_streams) as total_used,
                COUNT(*) as total_instances,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_instances
            FROM orchestrator_instances
        """)
        
        capacity_info = cursor.fetchone()
        total_capacity, total_used, total_instances, active_instances = capacity_info
        
        print(f"\n📊 Capacidade do sistema:")
        print(f"   - Capacidade total: {total_capacity} streams")
        print(f"   - Streams em uso: {total_used}")
        print(f"   - Utilização: {(total_used/total_capacity)*100:.1f}%")
        print(f"   - Instâncias: {active_instances} ativas de {total_instances} total")
        
    except Exception as e:
        print(f"❌ Erro ao verificar atribuições: {e}")
    finally:
        conn.close()

def main():
    """Função principal"""
    print("🔧 CORREÇÃO: MAX_STREAMS = 20 (BANCO DE DADOS)")
    print("=" * 80)
    print(f"⏰ Executado em: {datetime.now()}")
    
    # 1. Corrigir max_streams no banco
    success = check_and_fix_max_streams()
    
    # 2. Verificar atribuições de streams
    check_stream_assignments()
    
    if success:
        print("\n🎉 SUCESSO: Correção concluída com êxito")
        print("\n📝 PRÓXIMOS PASSOS:")
        print("   1. Reiniciar o orquestrador para aplicar as mudanças")
        print("   2. Verificar se as instâncias fingerv7 se reconectam corretamente")
        print("   3. Monitorar o balanceamento automático de streams")
    else:
        print("\n❌ FALHA: Algumas correções não foram aplicadas")
    
    print("\n" + "=" * 80)
    print("🏁 SCRIPT CONCLUÍDO")

if __name__ == "__main__":
    main()
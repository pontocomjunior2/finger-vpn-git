#!/usr/bin/env python3
"""
Script para verificar a situação dos streams no SQLite
"""

import os
import sqlite3


def check_streams():
    # Conectar ao banco SQLite
    db_path = os.path.join(os.path.dirname(__file__), 'orchestrator.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Banco de dados não encontrado: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("🔍 VERIFICANDO STREAMS NO SQLITE")
        print("=" * 60)
        
        # Verificar se as tabelas existem
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"📋 Tabelas encontradas: {tables}")
        
        # Verificar streams
        if 'streams' in tables:
            cursor.execute("SELECT COUNT(*) FROM streams")
            total_streams = cursor.fetchone()[0]
            print(f"📊 Total de streams na tabela: {total_streams}")
        else:
            print("❌ Tabela 'streams' não encontrada")
            total_streams = 0
        
        # Verificar assignments
        if 'orchestrator_stream_assignments' in tables:
            cursor.execute("SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE status = 'active'")
            assigned_streams = cursor.fetchone()[0]
            print(f"📊 Streams atribuídos (ativos): {assigned_streams}")
            
            cursor.execute("SELECT COUNT(*) FROM orchestrator_stream_assignments")
            total_assignments = cursor.fetchone()[0]
            print(f"📊 Total de assignments: {total_assignments}")
        else:
            print("❌ Tabela 'orchestrator_stream_assignments' não encontrada")
            assigned_streams = 0
        
        # Verificar instâncias
        if 'orchestrator_instances' in tables:
            cursor.execute("SELECT COUNT(*) FROM orchestrator_instances WHERE status = 'active'")
            active_instances = cursor.fetchone()[0]
            print(f"📊 Instâncias ativas: {active_instances}")
            
            cursor.execute("SELECT SUM(capacity) FROM orchestrator_instances WHERE status = 'active'")
            result = cursor.fetchone()[0]
            total_capacity = result if result else 0
            print(f"📊 Capacidade total: {total_capacity}")
            
            # Mostrar detalhes das instâncias
            cursor.execute("""
                SELECT server_id, current_streams, capacity, status 
                FROM orchestrator_instances 
                WHERE status = 'active'
                ORDER BY server_id
            """)
            instances = cursor.fetchall()
            print("\n🖥️ Instâncias ativas:")
            for server_id, current_streams, capacity, status in instances:
                utilization = (current_streams / capacity * 100) if capacity > 0 else 0
                print(f"   {server_id}: {current_streams}/{capacity} ({utilization:.1f}%)")
        else:
            print("❌ Tabela 'orchestrator_instances' não encontrada")
            total_capacity = 0
        
        # Calcular estatísticas
        if total_streams > 0 and total_capacity > 0:
            unassigned_streams = total_streams - assigned_streams
            utilization = (assigned_streams / total_capacity * 100) if total_capacity > 0 else 0
            
            print("\n📈 Resumo:")
            print(f"   - Streams não atribuídos: {unassigned_streams}")
            print(f"   - Utilização: {utilization:.1f}%")
            
            if assigned_streams > total_capacity:
                print(f"   ⚠️ SOBRECARGA: {assigned_streams - total_capacity} streams acima da capacidade")
            elif unassigned_streams > 0:
                print(f"   ⚠️ PENDENTES: {unassigned_streams} streams aguardando atribuição")
            else:
                print("   ✅ Sistema balanceado")
        
    except Exception as e:
        print(f"❌ Erro ao verificar streams: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_streams()
#!/usr/bin/env python3
"""
Script para limpar assignments órfãos que excedem a capacidade da instância

Este script identifica e remove assignments que fazem com que uma instância
exceda sua capacidade máxima configurada.

Autor: Sistema de Fingerprinting
Data: 2024
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

def clean_orphan_assignments():
    """
    Remove assignments órfãos que excedem a capacidade máxima das instâncias.
    """
    try:
        # Conectar ao banco de dados
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT
        )
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        print("=== Limpeza de Assignments Órfãos ===")
        print()
        
        # 1. Verificar status atual das instâncias
        print("1. Status atual das instâncias:")
        cursor.execute("""
            SELECT server_id, max_streams, current_streams, 
                   (current_streams - max_streams) as excess
            FROM orchestrator_instances 
            WHERE status = 'active'
            ORDER BY server_id
        """)
        
        instances = cursor.fetchall()
        instances_with_excess = []
        
        for instance in instances:
            excess = instance['excess']
            print(f"  Instância {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} streams")
            if excess > 0:
                print(f"    ⚠️  EXCESSO: {excess} streams acima da capacidade")
                instances_with_excess.append(instance)
            else:
                print(f"    ✅ OK: Dentro da capacidade")
        
        print()
        
        if not instances_with_excess:
            print("✅ Nenhuma instância com excesso de assignments encontrada.")
            return
        
        # 2. Para cada instância com excesso, remover assignments mais antigos
        for instance in instances_with_excess:
            server_id = instance['server_id']
            excess = instance['excess']
            
            print(f"2. Limpando {excess} assignments da instância {server_id}:")
            
            # Buscar assignments mais antigos para esta instância
            cursor.execute("""
                SELECT assignment_id, stream_id, assigned_at
                FROM orchestrator_stream_assignments 
                WHERE server_id = %s
                ORDER BY assigned_at ASC
                LIMIT %s
            """, (server_id, excess))
            
            assignments_to_remove = cursor.fetchall()
            
            if assignments_to_remove:
                assignment_ids = [a['assignment_id'] for a in assignments_to_remove]
                stream_ids = [a['stream_id'] for a in assignments_to_remove]
                
                print(f"  Removendo {len(assignment_ids)} assignments mais antigos:")
                for assignment in assignments_to_remove:
                    print(f"    - Assignment {assignment['assignment_id']}: Stream {assignment['stream_id']} (desde {assignment['assigned_at']})")
                
                # Remover os assignments
                cursor.execute("""
                    DELETE FROM orchestrator_stream_assignments 
                    WHERE assignment_id = ANY(%s)
                """, (assignment_ids,))
                
                # Atualizar contador da instância
                new_current_streams = instance['current_streams'] - len(assignment_ids)
                cursor.execute("""
                    UPDATE orchestrator_instances 
                    SET current_streams = %s,
                        last_heartbeat = NOW()
                    WHERE server_id = %s
                """, (new_current_streams, server_id))
                
                print(f"  ✅ Contador atualizado: {instance['current_streams']} → {new_current_streams}")
            
            print()
        
        # 3. Verificar status final
        print("3. Status final das instâncias:")
        cursor.execute("""
            SELECT server_id, max_streams, current_streams,
                   (max_streams - current_streams) as available_capacity
            FROM orchestrator_instances 
            WHERE status = 'active'
            ORDER BY server_id
        """)
        
        final_instances = cursor.fetchall()
        
        for instance in final_instances:
            available = instance['available_capacity']
            print(f"  Instância {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} streams")
            if available >= 0:
                print(f"    ✅ Capacidade disponível: {available} streams")
            else:
                print(f"    ⚠️  Ainda em excesso: {abs(available)} streams")
        
        print()
        
        # 4. Verificar assignments totais
        cursor.execute("""
            SELECT COUNT(*) as total_assignments
            FROM orchestrator_stream_assignments
        """)
        total_assignments = cursor.fetchone()['total_assignments']
        
        cursor.execute("""
            SELECT COUNT(*) as total_streams
            FROM streams
        """)
        total_streams = cursor.fetchone()['total_streams']
        
        print(f"4. Resumo final:")
        print(f"  Total de assignments: {total_assignments}")
        print(f"  Total de streams: {total_streams}")
        
        # Confirmar mudanças
        conn.commit()
        print("\n✅ Limpeza concluída com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro durante a limpeza: {e}")
        if 'conn' in locals():
            conn.rollback()
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    clean_orphan_assignments()
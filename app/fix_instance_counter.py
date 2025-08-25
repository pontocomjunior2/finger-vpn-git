#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações do banco
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

SERVER_ID = os.getenv('SERVER_ID', '1')

def fix_instance_counter():
    """Corrige a inconsistência entre current_streams e assignments reais."""
    
    print("=== CORREÇÃO DO CONTADOR DE STREAMS DA INSTÂNCIA ===")
    
    try:
        # Conectar ao banco
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print(f"\n1. Verificando estado atual da instância {SERVER_ID}...")
        
        # Verificar estado atual
        cursor.execute("""
            SELECT current_streams, max_streams, status, last_heartbeat
            FROM orchestrator_instances 
            WHERE server_id = %s
        """, (SERVER_ID,))
        
        instance_data = cursor.fetchone()
        if not instance_data:
            print(f"   ❌ Instância {SERVER_ID} não encontrada")
            return False
        
        current_streams, max_streams, status, last_heartbeat = instance_data
        print(f"   Estado atual: {current_streams}/{max_streams} streams, status: {status}")
        print(f"   Último heartbeat: {last_heartbeat}")
        
        # Contar assignments reais
        print(f"\n2. Contando assignments reais para instância {SERVER_ID}...")
        cursor.execute("""
            SELECT COUNT(*) 
            FROM orchestrator_stream_assignments 
            WHERE server_id = %s AND status = 'active'
        """, (SERVER_ID,))
        
        real_assignments = cursor.fetchone()[0]
        print(f"   Assignments reais: {real_assignments}")
        
        # Verificar se há inconsistência
        if current_streams != real_assignments:
            print(f"\n⚠️  INCONSISTÊNCIA DETECTADA!")
            print(f"   current_streams na tabela: {current_streams}")
            print(f"   Assignments reais: {real_assignments}")
            print(f"   Diferença: {current_streams - real_assignments}")
            
            # Corrigir o contador
            print(f"\n3. Corrigindo contador de streams...")
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = %s
                WHERE server_id = %s
            """, (real_assignments, SERVER_ID))
            
            print(f"   ✅ Contador atualizado de {current_streams} para {real_assignments}")
            
            # Verificar correção
            cursor.execute("""
                SELECT current_streams, max_streams
                FROM orchestrator_instances 
                WHERE server_id = %s
            """, (SERVER_ID,))
            
            new_current, max_streams = cursor.fetchone()
            capacidade_disponivel = max_streams - new_current
            
            print(f"\n4. Estado após correção:")
            print(f"   current_streams: {new_current}")
            print(f"   max_streams: {max_streams}")
            print(f"   Capacidade disponível: {capacidade_disponivel}")
            
            if capacidade_disponivel > 0:
                print(f"   ✅ Instância agora tem capacidade para {capacidade_disponivel} streams")
                return True
            else:
                print(f"   ⚠️  Instância ainda está na capacidade máxima")
                return False
        else:
            print(f"\n✅ Nenhuma inconsistência detectada")
            print(f"   current_streams ({current_streams}) == assignments reais ({real_assignments})")
            
            capacidade_disponivel = max_streams - current_streams
            if capacidade_disponivel > 0:
                print(f"   Capacidade disponível: {capacidade_disponivel} streams")
                return True
            else:
                print(f"   Instância está na capacidade máxima")
                return False
            
    except Exception as e:
        print(f"❌ Erro durante a correção: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def cleanup_orphaned_assignments():
    """Remove assignments órfãos que podem estar causando problemas."""
    
    print("\n=== LIMPEZA DE ASSIGNMENTS ÓRFÃOS ===")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Verificar assignments órfãos (sem instância correspondente)
        print("\n1. Verificando assignments órfãos...")
        cursor.execute("""
            SELECT osa.server_id, COUNT(*) as assignments
            FROM orchestrator_stream_assignments osa
            LEFT JOIN orchestrator_instances oi ON osa.server_id = oi.server_id
            WHERE oi.server_id IS NULL AND osa.status = 'active'
            GROUP BY osa.server_id
        """)
        
        orphaned = cursor.fetchall()
        if orphaned:
            print(f"   ⚠️  Encontrados assignments órfãos:")
            for server_id, count in orphaned:
                print(f"     - Servidor {server_id}: {count} assignments")
            
            # Remover assignments órfãos
            print("\n2. Removendo assignments órfãos...")
            cursor.execute("""
                DELETE FROM orchestrator_stream_assignments
                WHERE server_id NOT IN (
                    SELECT server_id FROM orchestrator_instances
                ) AND status = 'active'
            """)
            
            removed = cursor.rowcount
            print(f"   ✅ Removidos {removed} assignments órfãos")
            return True
        else:
            print("   ✅ Nenhum assignment órfão encontrado")
            return True
            
    except Exception as e:
        print(f"❌ Erro durante limpeza: {e}")
        return False
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def main():
    """Executa todas as correções."""
    
    print("🔧 INICIANDO CORREÇÃO DE INCONSISTÊNCIAS\n")
    
    # 1. Limpar assignments órfãos
    cleanup_success = cleanup_orphaned_assignments()
    
    # 2. Corrigir contador da instância
    if cleanup_success:
        fix_success = fix_instance_counter()
        
        if fix_success:
            print("\n🎉 CORREÇÃO CONCLUÍDA COM SUCESSO!")
            print("   ✅ Inconsistências corrigidas")
            print("   ✅ Instância pronta para receber novos streams")
            print("\n📝 PRÓXIMOS PASSOS:")
            print("   1. Testar novamente a atribuição de streams")
            print("   2. Verificar se o fingerv7 consegue processar streams")
        else:
            print("\n⚠️  CORREÇÃO PARCIAL")
            print("   Algumas inconsistências podem persistir")
    else:
        print("\n❌ FALHA NA LIMPEZA")
        print("   Não foi possível limpar assignments órfãos")

if __name__ == "__main__":
    main()
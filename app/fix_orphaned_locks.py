#!/usr/bin/env python3
import os
from datetime import datetime, timedelta

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def fix_orphaned_locks():
    """
    Remove locks órfãos ou expirados da tabela stream_locks
    para permitir que outras instâncias adquiram os locks.
    """
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
        
        print("=== Verificando locks órfãos/expirados ===")
        
        # 1. Verificar locks expirados (mais de 2 minutos sem heartbeat)
        cursor.execute("""
            SELECT stream_id, server_id, heartbeat_at,
                   EXTRACT(EPOCH FROM (NOW() - heartbeat_at))/60 as minutes_ago
            FROM stream_locks 
            WHERE heartbeat_at < NOW() - INTERVAL '2 minutes'
            ORDER BY heartbeat_at
        """)
        
        expired_locks = cursor.fetchall()
        
        if expired_locks:
            print(f"\nEncontrados {len(expired_locks)} locks expirados:")
            for stream_id, server_id, heartbeat_at, minutes_ago in expired_locks:
                print(f"  Stream {stream_id} (servidor {server_id}) - {minutes_ago:.1f} min atrás")
            
            # Remover locks expirados
            cursor.execute("""
                DELETE FROM stream_locks 
                WHERE heartbeat_at < NOW() - INTERVAL '2 minutes'
            """)
            
            deleted_count = cursor.rowcount
            print(f"\n✅ {deleted_count} locks expirados removidos")
        else:
            print("\n✅ Nenhum lock expirado encontrado")
        
        # 2. Verificar se há instâncias inativas no orquestrador
        print("\n=== Verificando instâncias ativas no orquestrador ===")
        
        cursor.execute("""
            SELECT server_id, status, last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat))/60 as minutes_ago
            FROM orchestrator_instances 
            ORDER BY server_id
        """)
        
        instances = cursor.fetchall()
        
        if instances:
            print("\nInstâncias registradas no orquestrador:")
            inactive_servers = []
            
            for server_id, status, last_heartbeat, minutes_ago in instances:
                status_icon = "🟢" if status == 'active' else "🔴"
                print(f"  {status_icon} Servidor {server_id}: {status} (heartbeat há {minutes_ago:.1f} min)")
                
                # Considerar inativa se não enviou heartbeat há mais de 5 minutos
                if minutes_ago > 5:
                    inactive_servers.append(server_id)
            
            # Remover locks de servidores inativos
            if inactive_servers:
                print(f"\n⚠️  Servidores inativos detectados: {inactive_servers}")
                
                for server_id in inactive_servers:
                    cursor.execute("""
                        SELECT COUNT(*) FROM stream_locks WHERE server_id = %s
                    """, (str(server_id),))
                    
                    lock_count = cursor.fetchone()[0]
                    
                    if lock_count > 0:
                        print(f"   Removendo {lock_count} locks do servidor inativo {server_id}")
                        
                        cursor.execute("""
                            DELETE FROM stream_locks WHERE server_id = %s
                        """, (str(server_id),))
                        
                        print(f"   ✅ {cursor.rowcount} locks removidos do servidor {server_id}")
        
        # 3. Verificar estado final
        print("\n=== Estado final da tabela stream_locks ===")
        
        cursor.execute("""
            SELECT server_id, COUNT(*) as lock_count
            FROM stream_locks 
            GROUP BY server_id
            ORDER BY server_id
        """)
        
        final_distribution = cursor.fetchall()
        
        if final_distribution:
            print("\nDistribuição final de locks:")
            for server_id, count in final_distribution:
                print(f"  Servidor {server_id}: {count} locks")
        else:
            print("\n✅ Tabela stream_locks está vazia - pronta para novos locks")
        
        # Commit das alterações
        conn.commit()
        conn.close()
        
        print("\n🎉 Limpeza de locks órfãos concluída com sucesso!")
        print("\n💡 O fingerv7.py agora deve conseguir adquirir locks normalmente.")
        
    except Exception as e:
        print(f"❌ Erro ao limpar locks órfãos: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🔧 LIMPEZA DE LOCKS ÓRFÃOS/EXPIRADOS")
    print("=" * 50)
    fix_orphaned_locks()
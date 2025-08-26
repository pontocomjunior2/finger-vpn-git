#!/usr/bin/env python3
"""
Script para corrigir o max_streams da instância 5
"""

from datetime import datetime

import psycopg2

# Configurações do banco de dados
DB_CONFIG = {
    'host': '104.234.173.96',
    'database': 'music_log',
    'user': 'postgres',
    'password': 'Conquista@@2',
    'port': 5432
}

def fix_instance_5():
    """Corrige o max_streams da instância 5"""
    print(f"🔧 CORREÇÃO DA INSTÂNCIA 5 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Verificar estado atual
        cursor.execute("""
            SELECT server_id, max_streams, current_streams, status
            FROM orchestrator_instances 
            WHERE server_id = '5'
        """)
        
        result = cursor.fetchone()
        if not result:
            print("❌ Instância 5 não encontrada")
            return False
        
        server_id, max_streams, current_streams, status = result
        print(f"📊 Estado atual da instância 5:")
        print(f"  • max_streams: {max_streams}")
        print(f"  • current_streams: {current_streams}")
        print(f"  • status: {status}")
        
        if max_streams == 20:
            print("✅ Instância 5 já está com max_streams=20")
            return True
        
        # Corrigir max_streams
        print(f"\n🔄 Corrigindo max_streams de {max_streams} para 20...")
        
        cursor.execute("""
            UPDATE orchestrator_instances 
            SET max_streams = 20, last_heartbeat = NOW()
            WHERE server_id = '5'
        """)
        
        if cursor.rowcount > 0:
            conn.commit()
            print("✅ max_streams corrigido com sucesso!")
            
            # Verificar resultado
            cursor.execute("""
                SELECT max_streams, current_streams
                FROM orchestrator_instances 
                WHERE server_id = '5'
            """)
            
            new_max, current = cursor.fetchone()
            print(f"\n📊 Estado após correção:")
            print(f"  • max_streams: {new_max}")
            print(f"  • current_streams: {current}")
            print(f"  • utilização: {(current/new_max*100):.1f}%")
            
            if current <= new_max:
                print("✅ Instância 5 não está mais sobrecarregada!")
            else:
                print(f"⚠️ Instância 5 ainda está sobrecarregada (+{current-new_max} streams)")
            
            return True
        else:
            print("❌ Nenhuma linha foi atualizada")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = fix_instance_5()
    
    if success:
        print(f"\n🎉 Correção concluída!")
        
        # Verificar resultado final
        print(f"\n🔍 Verificando estado geral...")
        import subprocess
        try:
            subprocess.run(['python', 'check_instances_status.py'], check=True)
        except:
            print("⚠️ Não foi possível executar verificação automática")
    else:
        print(f"\n❌ Correção falhou")
#!/usr/bin/env python3
"""
Script para corrigir as atribuições da instância finger_app_8.
Libera todos os streams e reatribui para que sejam registrados corretamente.
"""

import os
import sys
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
print(f"Variáveis carregadas de {env_path}")

# Configuração do banco de dados
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

ORCHESTRATOR_URL = "http://localhost:8080"

def fix_finger_app_8():
    """Corrige as atribuições da instância finger_app_8."""
    
    print("\n=== CORRIGINDO FINGER_APP_8 ===")
    
    try:
        # Conectar ao banco
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print(f"Conectado ao banco: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        
        # 1. Verificar estado atual da instância
        cursor.execute("""
            SELECT server_id, current_streams, max_streams, status 
            FROM orchestrator_instances 
            WHERE server_id = 'finger_app_8'
        """)
        
        instance = cursor.fetchone()
        if not instance:
            print("❌ Instância finger_app_8 não encontrada!")
            return
            
        print(f"📊 Estado atual: {instance['current_streams']}/{instance['max_streams']} streams, status: {instance['status']}")
        
        # 2. Verificar se há atribuições na tabela
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM orchestrator_stream_assignments 
            WHERE server_id = 'finger_app_8' AND status = 'active'
        """)
        
        assignments_count = cursor.fetchone()['count']
        print(f"📋 Atribuições registradas: {assignments_count}")
        
        # 3. Se há inconsistência, corrigir
        if instance['current_streams'] > 0 and assignments_count == 0:
            print("⚠️  Inconsistência detectada! Corrigindo...")
            
            # Resetar contador de streams da instância
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET current_streams = 0 
                WHERE server_id = 'finger_app_8'
            """)
            
            conn.commit()
            print("✅ Contador de streams resetado para 0")
            
            # 4. Reatribuir streams via API
            print("🔄 Reatribuindo streams via API...")
            
            response = requests.post(
                f"{ORCHESTRATOR_URL}/streams/assign",
                json={
                    "server_id": "finger_app_8",
                    "requested_count": instance['current_streams']  # Reatribuir a mesma quantidade
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Reatribuídos {result.get('count', 0)} streams: {result.get('assigned_streams', [])}")
            else:
                print(f"❌ Erro na reatribuição: {response.status_code} - {response.text}")
                
        elif assignments_count > 0:
            print("✅ Instância já tem atribuições registradas corretamente")
        else:
            print("ℹ️  Instância não tem streams atribuídos")
            
    except Exception as e:
        print(f"❌ Erro: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    fix_finger_app_8()
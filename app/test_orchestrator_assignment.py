#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()

ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://localhost:8001')
SERVER_ID = '1'

def test_orchestrator_assignment():
    """Testa diretamente a atribuição de streams via API do orquestrador."""
    
    print("=== TESTE DE ATRIBUIÇÃO DE STREAMS ===")
    
    try:
        # 1. Verificar se o orquestrador está rodando
        print("\n1. Verificando se orquestrador está ativo...")
        response = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        if response.status_code == 200:
            print("   ✅ Orquestrador está ativo")
        else:
            print(f"   ❌ Orquestrador retornou status {response.status_code}")
            return
            
    except Exception as e:
        print(f"   ❌ Erro ao conectar com orquestrador: {e}")
        return
    
    try:
        # 2. Registrar instância
        print("\n2. Registrando instância...")
        register_data = {
            "server_id": SERVER_ID,
            "ip": "93.127.141.215",
            "port": 8000,
            "max_streams": 20
        }
        
        response = requests.post(
            f"{ORCHESTRATOR_URL}/register",
            json=register_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print("   ✅ Instância registrada com sucesso")
            print(f"   Resposta: {response.json()}")
        else:
            print(f"   ❌ Erro no registro: {response.status_code} - {response.text}")
            return
            
    except Exception as e:
        print(f"   ❌ Erro ao registrar instância: {e}")
        return
    
    try:
        # 3. Solicitar atribuição de streams
        print("\n3. Solicitando atribuição de streams...")
        assign_data = {
            "server_id": SERVER_ID,
            "requested_count": 20
        }
        
        response = requests.post(
            f"{ORCHESTRATOR_URL}/streams/assign",
            json=assign_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ Solicitação de atribuição bem-sucedida")
            print(f"   Status: {result.get('status')}")
            print(f"   Streams atribuídos: {len(result.get('assigned_streams', []))}")
            print(f"   Primeiros IDs: {result.get('assigned_streams', [])[:10]}")
            
            if result.get('status') == 'assigned' and len(result.get('assigned_streams', [])) > 0:
                print("   ✅ Streams foram atribuídos com sucesso!")
                return True
            else:
                print(f"   ⚠️  Problema na atribuição: {result.get('message', 'Sem mensagem')}")
                return False
        else:
            print(f"   ❌ Erro na atribuição: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Erro ao solicitar streams: {e}")
        return False

def verify_assignment_in_db():
    """Verifica se a atribuição foi persistida no banco de dados."""
    
    print("\n=== VERIFICAÇÃO NO BANCO DE DADOS ===")
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB'),
            port=os.getenv('POSTGRES_PORT')
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Verificar assignments
        cursor.execute('SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE server_id = %s AND status = %s', (SERVER_ID, 'active'))
        assignments_count = cursor.fetchone()[0]
        print(f"Assignments ativos para instância {SERVER_ID}: {assignments_count}")
        
        if assignments_count > 0:
            cursor.execute('SELECT stream_id FROM orchestrator_stream_assignments WHERE server_id = %s AND status = %s LIMIT 10', (SERVER_ID, 'active'))
            stream_ids = cursor.fetchall()
            print(f"Primeiros stream IDs atribuídos: {[s[0] for s in stream_ids]}")
            
        # Verificar current_streams da instância
        cursor.execute('SELECT current_streams, max_streams FROM orchestrator_instances WHERE server_id = %s', (SERVER_ID,))
        instance_data = cursor.fetchone()
        if instance_data:
            current_streams, max_streams = instance_data
            print(f"Current streams na instância: {current_streams}/{max_streams}")
        
        conn.close()
        return assignments_count > 0
        
    except Exception as e:
        print(f"Erro ao verificar banco: {e}")
        return False

if __name__ == "__main__":
    # Executar teste
    assignment_success = test_orchestrator_assignment()
    
    if assignment_success:
        # Verificar se foi persistido no banco
        db_success = verify_assignment_in_db()
        
        if db_success:
            print("\n🎉 SUCESSO: Streams foram atribuídos E persistidos no banco!")
        else:
            print("\n⚠️  PROBLEMA: Streams foram atribuídos mas NÃO foram persistidos no banco!")
    else:
        print("\n❌ FALHA: Streams não foram atribuídos pelo orquestrador")
        
        # Verificar estado atual do banco mesmo assim
        verify_assignment_in_db()
#!/usr/bin/env python3
"""
Script para resetar o contador de streams de uma instância no orquestrador.
"""

import requests
import json
from datetime import datetime

# Configurações
ORCHESTRATOR_URL = "http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080"
SERVER_ID = "1"

def reset_instance_streams():
    """Reseta o contador de streams da instância."""
    print(f"[{datetime.now()}] Resetando contador de streams da instância {SERVER_ID}...")
    
    try:
        # Primeiro, vamos liberar todos os streams atribuídos à instância
        print("1. Verificando streams atribuídos...")
        response = requests.get(f"{ORCHESTRATOR_URL}/streams/assignments", timeout=10)
        
        if response.status_code == 200:
            assignments = response.json().get('assignments', [])
            instance_streams = [a['stream_id'] for a in assignments if a['server_id'] == SERVER_ID]
            
            print(f"Streams atribuídos à instância {SERVER_ID}: {instance_streams}")
            
            if instance_streams:
                print("2. Liberando streams atribuídos...")
                release_response = requests.post(
                    f"{ORCHESTRATOR_URL}/streams/release",
                    json={
                        "server_id": SERVER_ID,
                        "stream_ids": instance_streams
                    },
                    timeout=10
                )
                
                print(f"Status da liberação: {release_response.status_code}")
                if release_response.status_code == 200:
                    result = release_response.json()
                    print(f"Resposta: {json.dumps(result, indent=2)}")
                    print("✅ Streams liberados com sucesso!")
                else:
                    print(f"❌ Erro ao liberar streams: {release_response.text}")
            else:
                print("Nenhum stream atribuído encontrado.")
        else:
            print(f"❌ Erro ao verificar assignments: {response.status_code}")
            print(f"Resposta: {response.text}")
            
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    print("-" * 60)
    
    try:
        # Agora vamos enviar um heartbeat com current_streams = 0 para resetar o contador
        print("3. Enviando heartbeat para resetar contador...")
        heartbeat_response = requests.post(
            f"{ORCHESTRATOR_URL}/heartbeat",
            json={
                "server_id": SERVER_ID,
                "current_streams": 0,
                "status": "active"
            },
            timeout=10
        )
        
        print(f"Status do heartbeat: {heartbeat_response.status_code}")
        if heartbeat_response.status_code == 200:
            result = heartbeat_response.json()
            print(f"Resposta: {json.dumps(result, indent=2)}")
            print("✅ Contador resetado com sucesso!")
        else:
            print(f"❌ Erro no heartbeat: {heartbeat_response.text}")
            
    except Exception as e:
        print(f"❌ Erro no heartbeat: {e}")
    
    print("-" * 60)
    
    try:
        # Verificar o status final da instância
        print("4. Verificando status final da instância...")
        instances_response = requests.get(f"{ORCHESTRATOR_URL}/instances", timeout=10)
        
        if instances_response.status_code == 200:
            instances = instances_response.json().get('instances', [])
            instance = next((i for i in instances if i['server_id'] == SERVER_ID), None)
            
            if instance:
                print(f"Status da instância {SERVER_ID}:")
                print(f"  - current_streams: {instance['current_streams']}")
                print(f"  - max_streams: {instance['max_streams']}")
                print(f"  - status: {instance['status']}")
                print(f"  - last_heartbeat: {instance['last_heartbeat']}")
                
                if instance['current_streams'] == 0:
                    print("✅ Contador resetado com sucesso!")
                else:
                    print(f"⚠️ Contador ainda está em {instance['current_streams']}")
            else:
                print(f"❌ Instância {SERVER_ID} não encontrada")
        else:
            print(f"❌ Erro ao verificar instâncias: {instances_response.status_code}")
            
    except Exception as e:
        print(f"❌ Erro ao verificar status: {e}")

if __name__ == "__main__":
    reset_instance_streams()
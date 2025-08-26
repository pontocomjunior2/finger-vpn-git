#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from datetime import datetime

import requests


def test_orchestrator_registration():
    """Testa o registro de uma instância no orquestrador"""
    
    orchestrator_url = "http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080"
    
    # Dados da instância para registro
    instance_data = {
        "server_id": "1",
        "ip": "192.168.1.106",  # IP usado no log
        "port": 8000,
        "max_streams": 20
    }
    
    print(f"[{datetime.now()}] Testando registro da instância no orquestrador...")
    print(f"URL: {orchestrator_url}/register")
    print(f"Dados: {json.dumps(instance_data, indent=2)}")
    print("-" * 60)
    
    try:
        # Teste de registro
        print("1. Tentando registrar instância...")
        response = requests.post(
            f"{orchestrator_url}/register",
            json=instance_data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Resposta: {json.dumps(result, indent=2)}")
            print("✅ Registro bem-sucedido!")
        else:
            print(f"❌ Erro no registro: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Timeout na requisição de registro")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Erro de conexão: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False
    
    print("-" * 60)
    
    try:
        # Teste de solicitação de streams
        print("2. Tentando solicitar streams...")
        response = requests.post(
            f"{orchestrator_url}/streams/assign",
            json={"server_id": "1", "requested_count": 5},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Streams recebidos: {len(result.get('streams', []))}")
            print(f"Resposta: {json.dumps(result, indent=2)}")
            print("✅ Solicitação de streams bem-sucedida!")
        else:
            print(f"❌ Erro na solicitação: {response.status_code}")
            print(f"Resposta: {response.text}")
            
    except Exception as e:
        print(f"❌ Erro na solicitação de streams: {e}")
    
    print("-" * 60)
    
    try:
        # Teste de heartbeat
        print("3. Tentando enviar heartbeat...")
        response = requests.post(
            f"{orchestrator_url}/heartbeat",
            json={"server_id": "1", "current_streams": 0, "status": "active"},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Resposta: {json.dumps(result, indent=2)}")
            print("✅ Heartbeat bem-sucedido!")
        else:
            print(f"❌ Erro no heartbeat: {response.status_code}")
            print(f"Resposta: {response.text}")
            
    except Exception as e:
        print(f"❌ Erro no heartbeat: {e}")
    
    return True

if __name__ == "__main__":
    test_orchestrator_registration()
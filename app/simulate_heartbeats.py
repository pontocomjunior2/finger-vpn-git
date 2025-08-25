#!/usr/bin/env python3
"""
Simula heartbeats para as instâncias registradas para mantê-las ativas.
"""

import os
import sys
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

ORCHESTRATOR_URL = "http://localhost:8080"

# Instâncias para manter ativas
INSTANCES = [
    {
        "server_id": "finger_app_8",
        "ip": "127.0.0.1",
        "port": 8008,
        "current_streams": 10
    },
    {
        "server_id": "finger_app_9", 
        "ip": "127.0.0.1",
        "port": 8009,
        "current_streams": 3
    }
]

def send_heartbeat(instance):
    """Envia heartbeat para uma instância."""
    try:
        response = requests.post(
            f"{ORCHESTRATOR_URL}/heartbeat",
            json={
                "server_id": instance["server_id"],
                "current_streams": instance["current_streams"],
                "status": "active"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            return True, "OK"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, str(e)

def simulate_heartbeats():
    """Simula heartbeats continuamente para as instâncias."""
    print(f"🫀 Simulando heartbeats para {len(INSTANCES)} instâncias")
    print("Pressione Ctrl+C para parar\n")
    
    try:
        while True:
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            for instance in INSTANCES:
                success, message = send_heartbeat(instance)
                
                if success:
                    print(f"[{timestamp}] ✅ {instance['server_id']}: Heartbeat enviado")
                else:
                    print(f"[{timestamp}] ❌ {instance['server_id']}: Erro - {message}")
            
            # Aguardar 30 segundos antes do próximo heartbeat
            time.sleep(30)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Simulação de heartbeats interrompida - {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"\n❌ Erro na simulação: {e}")

if __name__ == "__main__":
    simulate_heartbeats()
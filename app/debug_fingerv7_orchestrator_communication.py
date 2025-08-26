#!/usr/bin/env python3
"""
Script para debugar a comunicação entre fingerv7 e orquestrador
Verifica se as instâncias estão se registrando corretamente com MAX_STREAMS=20
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import psycopg2
import requests
from dotenv import load_dotenv

# Carregar variáveis do arquivo .env
load_dotenv()

# Configurações do banco
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', '104.234.173.96'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'Conquista@@2'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://n8n-pontocom-finger-orchestrator.azfa0v.easypanel.host:8080')

def get_db_connection():
    """Conecta ao banco de dados"""
    try:
        return psycopg2.connect(**POSTGRES_CONFIG)
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def check_orchestrator_connectivity():
    """Verifica conectividade com o orquestrador"""
    print("\n🔍 VERIFICANDO CONECTIVIDADE COM ORQUESTRADOR")
    print("=" * 60)
    
    try:
        # Teste de conectividade básica
        response = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=10)
        print(f"✅ Orquestrador acessível: {response.status_code}")
        
        # Verificar instâncias registradas
        response = requests.get(f"{ORCHESTRATOR_URL}/instances", timeout=10)
        if response.status_code == 200:
            instances_data = response.json()
            print(f"📊 Resposta do orquestrador: {instances_data}")
            
            # Verificar se é uma lista ou dict
            if isinstance(instances_data, dict) and 'instances' in instances_data:
                instances = instances_data['instances']
            elif isinstance(instances_data, list):
                instances = instances_data
            else:
                print(f"❌ Formato de resposta inesperado: {type(instances_data)}")
                return False
            
            print(f"📊 Instâncias registradas no orquestrador: {len(instances)}")
            
            for instance in instances:
                if isinstance(instance, dict):
                    print(f"   - {instance.get('server_id', 'N/A')}: {instance.get('current_streams', 'N/A')}/{instance.get('max_streams', 'N/A')} streams")
                    
                    # Verificar se max_streams está correto
                    max_streams = instance.get('max_streams')
                    if max_streams != 20:
                        print(f"   ⚠️  PROBLEMA: max_streams={max_streams}, esperado=20")
                    else:
                        print(f"   ✅ max_streams correto: {max_streams}")
                else:
                    print(f"   - Instância em formato inesperado: {instance}")
        else:
            print(f"❌ Erro ao obter instâncias: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro de conectividade: {e}")
        return False
    
    return True

def check_database_instances():
    """Verifica instâncias no banco de dados"""
    print("\n🗄️  VERIFICANDO INSTÂNCIAS NO BANCO DE DADOS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Buscar todas as instâncias
        cursor.execute("""
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
            FROM orchestrator_instances 
            ORDER BY last_heartbeat DESC
        """)
        
        instances = cursor.fetchall()
        print(f"📊 Total de instâncias no banco: {len(instances)}")
        
        active_instances = 0
        problem_instances = []
        
        for instance in instances:
            server_id, ip, port, max_streams, current_streams, status, last_heartbeat, seconds_since = instance
            
            print(f"\n📍 Instância {server_id}:")
            print(f"   - Endereço: {ip}:{port}")
            print(f"   - Max streams: {max_streams}")
            print(f"   - Current streams: {current_streams}")
            print(f"   - Status: {status}")
            print(f"   - Último heartbeat: {last_heartbeat}")
            print(f"   - Segundos desde último heartbeat: {int(seconds_since)}")
            
            # Verificar problemas
            if max_streams != 20:
                problem_instances.append(f"Instância {server_id}: max_streams={max_streams} (esperado=20)")
                print(f"   ⚠️  PROBLEMA: max_streams incorreto")
            
            if seconds_since > 300:  # 5 minutos
                problem_instances.append(f"Instância {server_id}: heartbeat antigo ({int(seconds_since)}s)")
                print(f"   ⚠️  PROBLEMA: heartbeat muito antigo")
            elif status == 'active':
                active_instances += 1
                print(f"   ✅ Instância ativa")
        
        print(f"\n📈 RESUMO:")
        print(f"   - Instâncias ativas: {active_instances}")
        print(f"   - Problemas encontrados: {len(problem_instances)}")
        
        if problem_instances:
            print(f"\n⚠️  PROBLEMAS DETECTADOS:")
            for problem in problem_instances:
                print(f"   - {problem}")
        
    except Exception as e:
        print(f"❌ Erro ao consultar banco: {e}")
    finally:
        conn.close()

def test_instance_registration():
    """Testa o processo de registro de uma instância"""
    print("\n🧪 TESTANDO REGISTRO DE INSTÂNCIA")
    print("=" * 60)
    
    test_data = {
        "server_id": "test_debug_instance",
        "ip": "127.0.0.1",
        "port": 9999,
        "max_streams": 20
    }
    
    try:
        # Tentar registrar instância de teste
        response = requests.post(
            f"{ORCHESTRATOR_URL}/register",
            json=test_data,
            timeout=10
        )
        
        print(f"📤 Enviando registro: {test_data}")
        print(f"📥 Resposta do orquestrador: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Registro bem-sucedido: {result}")
            
            # Verificar se foi registrado corretamente
            time.sleep(1)
            response = requests.get(f"{ORCHESTRATOR_URL}/instances", timeout=10)
            if response.status_code == 200:
                instances_data = response.json()
                instances = instances_data.get('instances', [])
                test_instance = next((i for i in instances if i['server_id'] == 'test_debug_instance'), None)
                
                if test_instance:
                    print(f"✅ Instância encontrada no orquestrador: {test_instance}")
                    
                    if test_instance['max_streams'] == 20:
                        print(f"✅ max_streams correto: {test_instance['max_streams']}")
                    else:
                        print(f"❌ max_streams incorreto: {test_instance['max_streams']} (esperado: 20)")
                else:
                    print(f"❌ Instância de teste não encontrada no orquestrador")
        else:
            print(f"❌ Falha no registro: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na comunicação: {e}")

def check_fingerv7_config():
    """Verifica configuração do fingerv7"""
    print("\n⚙️  VERIFICANDO CONFIGURAÇÃO FINGERV7")
    print("=" * 60)
    
    # Verificar arquivo .env
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"✅ Arquivo .env encontrado")
        
        with open(env_file, 'r') as f:
            content = f.read()
            
        if 'MAX_STREAMS=20' in content:
            print(f"✅ MAX_STREAMS=20 configurado no .env")
        else:
            print(f"❌ MAX_STREAMS=20 NÃO encontrado no .env")
            
        if 'ORCHESTRATOR_URL=' in content:
            for line in content.split('\n'):
                if line.startswith('ORCHESTRATOR_URL='):
                    url = line.split('=', 1)[1]
                    print(f"✅ ORCHESTRATOR_URL configurado: {url}")
                    break
        else:
            print(f"❌ ORCHESTRATOR_URL não configurado")
    else:
        print(f"❌ Arquivo .env não encontrado")
    
    # Verificar variáveis de ambiente atuais
    max_streams_env = os.getenv('MAX_STREAMS')
    orchestrator_url_env = os.getenv('ORCHESTRATOR_URL')
    
    print(f"\n🌍 Variáveis de ambiente atuais:")
    print(f"   - MAX_STREAMS: {max_streams_env}")
    print(f"   - ORCHESTRATOR_URL: {orchestrator_url_env}")

def main():
    """Função principal"""
    print("🔍 DEBUG: COMUNICAÇÃO FINGERV7 ↔ ORQUESTRADOR")
    print("=" * 80)
    print(f"⏰ Executado em: {datetime.now()}")
    
    # 1. Verificar configuração do fingerv7
    check_fingerv7_config()
    
    # 2. Verificar conectividade com orquestrador
    if not check_orchestrator_connectivity():
        print("\n❌ FALHA CRÍTICA: Não foi possível conectar ao orquestrador")
        return
    
    # 3. Verificar instâncias no banco
    check_database_instances()
    
    # 4. Testar registro de instância
    test_instance_registration()
    
    print("\n" + "=" * 80)
    print("🏁 DEBUG CONCLUÍDO")

if __name__ == "__main__":
    main()
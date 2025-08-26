#!/usr/bin/env python3
"""
Script para corrigir a configuração MAX_STREAMS_PER_INSTANCE no orquestrador
Garante que todas as instâncias sejam registradas com max_streams=20
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
import requests

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

def check_current_state():
    """Verifica o estado atual das instâncias"""
    print("\n🔍 VERIFICANDO ESTADO ATUAL DAS INSTÂNCIAS")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        
        # Buscar todas as instâncias ativas
        cursor.execute("""
            SELECT server_id, ip, port, max_streams, current_streams, 
                   status, last_heartbeat,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
            FROM orchestrator_instances 
            WHERE status = 'active'
            ORDER BY last_heartbeat DESC
        """)
        
        instances = cursor.fetchall()
        print(f"📊 Instâncias ativas encontradas: {len(instances)}")
        
        problem_instances = []
        
        for instance in instances:
            server_id, ip, port, max_streams, current_streams, status, last_heartbeat, seconds_since = instance
            
            print(f"\n📍 Instância {server_id}:")
            print(f"   - Endereço: {ip}:{port}")
            print(f"   - Max streams: {max_streams}")
            print(f"   - Current streams: {current_streams}")
            print(f"   - Último heartbeat: {int(seconds_since)}s atrás")
            
            # Verificar se max_streams está incorreto
            if max_streams != 20:
                problem_instances.append({
                    'server_id': server_id,
                    'current_max_streams': max_streams,
                    'current_streams': current_streams
                })
                print(f"   ⚠️  PROBLEMA: max_streams={max_streams} (esperado=20)")
            else:
                print(f"   ✅ max_streams correto: {max_streams}")
        
        return problem_instances
        
    except Exception as e:
        print(f"❌ Erro ao consultar banco: {e}")
        return []
    finally:
        conn.close()

def fix_max_streams_in_database(problem_instances):
    """Corrige max_streams diretamente no banco de dados"""
    if not problem_instances:
        print("\n✅ Nenhuma correção necessária no banco de dados")
        return True
    
    print(f"\n🔧 CORRIGINDO {len(problem_instances)} INSTÂNCIAS NO BANCO")
    print("=" * 60)
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        for instance in problem_instances:
            server_id = instance['server_id']
            old_max = instance['current_max_streams']
            
            print(f"\n🔄 Corrigindo instância {server_id}:")
            print(f"   - max_streams: {old_max} → 20")
            
            # Atualizar max_streams para 20
            cursor.execute("""
                UPDATE orchestrator_instances 
                SET max_streams = 20
                WHERE server_id = %s
            """, (server_id,))
            
            if cursor.rowcount > 0:
                print(f"   ✅ Atualizado com sucesso")
            else:
                print(f"   ❌ Falha na atualização")
        
        conn.commit()
        print(f"\n✅ Todas as correções foram aplicadas no banco")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao corrigir banco: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def verify_orchestrator_config():
    """Verifica se o orquestrador está usando a configuração correta"""
    print("\n⚙️  VERIFICANDO CONFIGURAÇÃO DO ORQUESTRADOR")
    print("=" * 60)
    
    try:
        # Tentar acessar endpoint de health para verificar se está rodando
        response = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        print(f"✅ Orquestrador acessível: {response.status_code}")
        
        # Verificar se há algum endpoint que mostra a configuração
        try:
            response = requests.get(f"{ORCHESTRATOR_URL}/config", timeout=5)
            if response.status_code == 200:
                config = response.json()
                print(f"📊 Configuração do orquestrador: {config}")
        except:
            print("ℹ️  Endpoint /config não disponível")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao acessar orquestrador: {e}")
        return False
    
    return True

def test_instance_registration():
    """Testa se novas instâncias são registradas com max_streams=20"""
    print("\n🧪 TESTANDO REGISTRO DE NOVA INSTÂNCIA")
    print("=" * 60)
    
    test_data = {
        "server_id": "test_max_streams_fix",
        "ip": "127.0.0.1",
        "port": 9998,
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
        print(f"📥 Resposta: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Registro bem-sucedido: {result}")
            
            # Verificar no banco se foi registrado corretamente
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT max_streams FROM orchestrator_instances 
                        WHERE server_id = %s
                    """, (test_data['server_id'],))
                    
                    result = cursor.fetchone()
                    if result:
                        max_streams_db = result[0]
                        print(f"📊 max_streams no banco: {max_streams_db}")
                        
                        if max_streams_db == 20:
                            print(f"✅ Instância registrada corretamente com max_streams=20")
                        else:
                            print(f"❌ PROBLEMA: Registrada com max_streams={max_streams_db}")
                    else:
                        print(f"❌ Instância não encontrada no banco")
                        
                    # Limpar instância de teste
                    cursor.execute("""
                        DELETE FROM orchestrator_instances 
                        WHERE server_id = %s
                    """, (test_data['server_id'],))
                    conn.commit()
                    print(f"🧹 Instância de teste removida")
                    
                except Exception as e:
                    print(f"❌ Erro ao verificar banco: {e}")
                finally:
                    conn.close()
        else:
            print(f"❌ Falha no registro: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na comunicação: {e}")

def force_rebalance():
    """Força um rebalanceamento após as correções"""
    print("\n🔄 FORÇANDO REBALANCEAMENTO")
    print("=" * 60)
    
    try:
        response = requests.post(f"{ORCHESTRATOR_URL}/force-rebalance", timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Rebalanceamento iniciado: {result}")
        else:
            print(f"❌ Falha no rebalanceamento: {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao forçar rebalanceamento: {e}")

def main():
    """Função principal"""
    print("🔧 CORREÇÃO: MAX_STREAMS_PER_INSTANCE = 20")
    print("=" * 80)
    print(f"⏰ Executado em: {datetime.now()}")
    
    # 1. Verificar estado atual
    problem_instances = check_current_state()
    
    # 2. Verificar configuração do orquestrador
    if not verify_orchestrator_config():
        print("\n❌ FALHA CRÍTICA: Orquestrador não acessível")
        return
    
    # 3. Corrigir instâncias com max_streams incorreto
    if not fix_max_streams_in_database(problem_instances):
        print("\n❌ FALHA: Não foi possível corrigir o banco de dados")
        return
    
    # 4. Testar registro de nova instância
    test_instance_registration()
    
    # 5. Forçar rebalanceamento
    force_rebalance()
    
    # 6. Verificar estado final
    print("\n🔍 VERIFICAÇÃO FINAL")
    print("=" * 60)
    final_problems = check_current_state()
    
    if not final_problems:
        print("\n🎉 SUCESSO: Todas as instâncias agora têm max_streams=20")
    else:
        print(f"\n⚠️  ATENÇÃO: Ainda há {len(final_problems)} instâncias com problemas")
    
    print("\n" + "=" * 80)
    print("🏁 CORREÇÃO CONCLUÍDA")

if __name__ == "__main__":
    main()
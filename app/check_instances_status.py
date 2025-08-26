#!/usr/bin/env python3
"""
Script para verificar o estado atual das instâncias no orquestrador
"""

import json
from datetime import datetime

import requests


def check_instances():
    """Verifica o estado das instâncias"""
    try:
        response = requests.get('http://localhost:8001/instances', timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Verificar se a resposta tem a estrutura esperada
        if isinstance(data, dict) and 'instances' in data:
            instances = data['instances']
        elif isinstance(data, list):
            instances = data
        else:
            print(f"❌ Estrutura de resposta inesperada: {type(data)}")
            print(f"Dados recebidos: {json.dumps(data, indent=2)}")
            return
        
        print(f"📊 ESTADO DAS INSTÂNCIAS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        if not instances:
            print("❌ Nenhuma instância encontrada")
            return
        
        # Separar instâncias ativas e inativas
        active_instances = [i for i in instances if i['status'] == 'active']
        inactive_instances = [i for i in instances if i['status'] != 'active']
        
        print(f"\n🟢 INSTÂNCIAS ATIVAS ({len(active_instances)}):")
        print("-" * 60)
        
        total_streams = 0
        total_capacity = 0
        overloaded = []
        
        for instance in active_instances:
            server_id = instance['server_id']
            current = instance['current_streams']
            max_streams = instance['max_streams']
            utilization = (current / max_streams * 100) if max_streams > 0 else 0
            
            status_icon = "⚠️" if current > max_streams else "✅"
            
            print(f"  {status_icon} {server_id:20} | {current:3d}/{max_streams:3d} streams ({utilization:5.1f}%)")
            
            total_streams += current
            total_capacity += max_streams
            
            if current > max_streams:
                overloaded.append({
                    'server_id': server_id,
                    'current': current,
                    'max': max_streams,
                    'excess': current - max_streams
                })
        
        print(f"\n📈 RESUMO:")
        print(f"  • Total de streams: {total_streams}")
        print(f"  • Capacidade total: {total_capacity}")
        print(f"  • Utilização geral: {(total_streams/total_capacity*100):.1f}%" if total_capacity > 0 else "  • Utilização: N/A")
        
        if overloaded:
            print(f"\n⚠️  INSTÂNCIAS SOBRECARREGADAS ({len(overloaded)}):")
            for inst in overloaded:
                print(f"  • {inst['server_id']}: {inst['current']}/{inst['max']} (+{inst['excess']} streams)")
        else:
            print(f"\n✅ Nenhuma instância sobrecarregada")
        
        if inactive_instances:
            print(f"\n🔴 INSTÂNCIAS INATIVAS ({len(inactive_instances)}):")
            print("-" * 60)
            for instance in inactive_instances:
                print(f"  • {instance['server_id']:20} | {instance['current_streams']} streams")
        
        print("\n" + "=" * 80)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao conectar com o orquestrador: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")

if __name__ == "__main__":
    check_instances()
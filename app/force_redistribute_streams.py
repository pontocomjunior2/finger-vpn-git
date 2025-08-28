#!/usr/bin/env python3
import os
import time

import psycopg2
import requests
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL")
SERVER_ID = os.getenv("SERVER_ID", "3")


def force_redistribute_streams():
    """
    Força a redistribuição de streams liberando todos os assignments
    e solicitando nova distribuição.
    """
    try:
        print("🔄 FORÇANDO REDISTRIBUIÇÃO DE STREAMS")
        print("=" * 50)

        # 1. Verificar estado atual das instâncias
        print("\n1. Verificando estado atual das instâncias...")

        response = requests.get(f"{ORCHESTRATOR_URL}/instances")
        if response.status_code == 200:
            data = response.json()
            print(f"\nResposta da API: {data}")

            # Verificar se é uma lista ou dict
            if isinstance(data, dict) and "instances" in data:
                instances = data["instances"]
            elif isinstance(data, list):
                instances = data
            else:
                print(f"❌ Formato inesperado da resposta: {type(data)}")
                return

            print("\nInstâncias ativas:")
            for instance in instances:
                print(
                    f"  - Servidor {instance['server_id']}: {instance['current_streams']}/{instance['max_streams']} streams"
                )
        else:
            print(f"❌ Erro ao consultar instâncias: {response.status_code}")
            return

        # 2. Verificar assignments atuais
        print("\n2. Verificando assignments atuais...")

        response = requests.get(f"{ORCHESTRATOR_URL}/assignments")
        if response.status_code == 200:
            assignments = response.json()

            # Contar por servidor
            server_counts = {}
            for assignment in assignments:
                server_id = assignment["server_id"]
                server_counts[server_id] = server_counts.get(server_id, 0) + 1

            print("\nDistribuição atual de assignments:")
            for server_id, count in server_counts.items():
                print(f"  - Servidor {server_id}: {count} assignments")
        else:
            print(f"❌ Erro ao consultar assignments: {response.status_code}")
            return

        # 3. Liberar todos os streams de todas as instâncias
        print("\n3. Liberando todos os streams...")

        for instance in instances:
            if instance["current_streams"] > 0:
                server_id = instance["server_id"]
                print(f"   Liberando streams do servidor {server_id}...")

                # Obter streams atribuídos a esta instância
                assigned_streams = [
                    a["stream_id"] for a in assignments if a["server_id"] == server_id
                ]

                if assigned_streams:
                    release_data = {
                        "server_id": server_id,
                        "stream_ids": assigned_streams,
                    }

                    response = requests.post(
                        f"{ORCHESTRATOR_URL}/release_streams", json=release_data
                    )

                    if response.status_code == 200:
                        result = response.json()
                        print(
                            f"   ✅ {result.get('count', 0)} streams liberados do servidor {server_id}"
                        )
                    else:
                        print(
                            f"   ❌ Erro ao liberar streams do servidor {server_id}: {response.status_code}"
                        )

        # 4. Aguardar um pouco para o orquestrador processar
        print("\n4. Aguardando processamento...")
        time.sleep(2)

        # 5. Solicitar nova distribuição para todas as instâncias ativas
        print("\n5. Solicitando nova distribuição...")

        for instance in instances:
            if instance["status"] == "active":
                server_id = instance["server_id"]
                max_streams = instance["max_streams"]

                print(
                    f"   Solicitando {max_streams} streams para servidor {server_id}..."
                )

                request_data = {"server_id": server_id, "requested_count": max_streams}

                response = requests.post(
                    f"{ORCHESTRATOR_URL}/request_streams", json=request_data
                )

                if response.status_code == 200:
                    result = response.json()
                    assigned_count = len(result.get("assigned_streams", []))
                    print(
                        f"   ✅ {assigned_count} streams atribuídos ao servidor {server_id}"
                    )
                else:
                    print(
                        f"   ❌ Erro ao solicitar streams para servidor {server_id}: {response.status_code}"
                    )

        # 6. Verificar resultado final
        print("\n6. Verificando resultado final...")
        time.sleep(1)

        response = requests.get(f"{ORCHESTRATOR_URL}/assignments")
        if response.status_code == 200:
            assignments = response.json()

            # Contar por servidor
            server_counts = {}
            for assignment in assignments:
                server_id = assignment["server_id"]
                server_counts[server_id] = server_counts.get(server_id, 0) + 1

            print("\nDistribuição final de assignments:")
            for server_id, count in server_counts.items():
                print(f"  - Servidor {server_id}: {count} assignments")

        print("\n🎉 Redistribuição forçada concluída!")
        print("\n💡 Verifique se o fingerv7.py agora recebe streams para processar.")

    except Exception as e:
        print(f"❌ Erro durante redistribuição: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    force_redistribute_streams()

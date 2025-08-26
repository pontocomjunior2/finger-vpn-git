#!/usr/bin/env python3
import asyncio
import json
import os

from dotenv import load_dotenv
from orchestrator_client import create_orchestrator_client

load_dotenv()

SERVER_ID = os.getenv('SERVER_ID', '1')
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://localhost:8001')

async def test_fingerv7_stream_assignment():
    """Testa o fluxo completo de atribuição de streams como no fingerv7."""
    
    print("=== TESTE DO FLUXO COMPLETO FINGERV7 ===")
    
    try:
        # 1. Carregar streams do arquivo JSON (como no fingerv7)
        print("\n1. Carregando streams do arquivo JSON...")
        with open('streams.json', 'r', encoding='utf-8') as f:
            all_streams = json.load(f)
        print(f"   ✅ Carregados {len(all_streams)} streams")
        
        # 2. Inicializar cliente do orquestrador
        print("\n2. Inicializando cliente do orquestrador...")
        orchestrator_client = create_orchestrator_client(
            orchestrator_url=ORCHESTRATOR_URL,
            server_id=SERVER_ID
        )
        print("   ✅ Cliente inicializado")
        
        # 3. Registrar instância no orquestrador
        print("\n3. Registrando instância no orquestrador...")
        registration_success = await orchestrator_client.register()
        if registration_success:
            print(f"   ✅ Instância {SERVER_ID} registrada com sucesso")
        else:
            print("   ❌ Falha no registro")
            return False
        
        # 4. Solicitar streams do orquestrador
        print("\n4. Solicitando streams do orquestrador...")
        assigned_stream_ids = await orchestrator_client.request_streams()
        print(f"   ✅ Recebidos {len(assigned_stream_ids)} streams do orquestrador")
        print(f"   IDs recebidos: {assigned_stream_ids[:10]}{'...' if len(assigned_stream_ids) > 10 else ''}")
        
        if not assigned_stream_ids:
            print("   ❌ Nenhum stream foi atribuído")
            return False
        
        # 5. Converter IDs para string (como no fingerv7)
        print("\n5. Convertendo IDs para compatibilidade...")
        assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]
        print(f"   IDs convertidos: {assigned_stream_ids_str[:10]}{'...' if len(assigned_stream_ids_str) > 10 else ''}")
        
        # 6. Filtrar streams usando a lógica CORRIGIDA
        print("\n6. Filtrando streams com lógica corrigida...")
        assigned_streams = [
            stream for stream in all_streams 
            if stream.get("index", "") in assigned_stream_ids_str
        ]
        
        print(f"   ✅ {len(assigned_streams)} streams filtrados com sucesso")
        
        if assigned_streams:
            print("   Streams atribuídos:")
            for i, stream in enumerate(assigned_streams[:5]):
                name = stream.get('name', 'N/A')
                index = stream.get('index', 'N/A')
                url = stream.get('url', 'N/A')[:50] + '...' if len(stream.get('url', '')) > 50 else stream.get('url', 'N/A')
                print(f"     {i+1}. {name} (Index: {index})")
                print(f"        URL: {url}")
            
            if len(assigned_streams) > 5:
                print(f"     ... e mais {len(assigned_streams) - 5} streams")
            
            print(f"\n   📊 Resumo:")
            print(f"     - Total de streams disponíveis: {len(all_streams)}")
            print(f"     - Streams solicitados do orquestrador: {len(assigned_stream_ids)}")
            print(f"     - Streams efetivamente atribuídos: {len(assigned_streams)}")
            print(f"     - Taxa de sucesso: {len(assigned_streams)/len(assigned_stream_ids)*100:.1f}%")
            
            return True
        else:
            print("   ❌ Nenhum stream foi filtrado - problema na lógica de filtragem")
            return False
            
    except Exception as e:
        print(f"   ❌ Erro durante o teste: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 7. Cleanup - liberar streams
        try:
            if 'orchestrator_client' in locals():
                print("\n7. Liberando streams...")
                await orchestrator_client.release_all_streams()
                print("   ✅ Streams liberados")
        except Exception as e:
            print(f"   ⚠️  Erro ao liberar streams: {e}")

async def test_old_vs_new_logic():
    """Compara a lógica antiga (problemática) com a nova (corrigida)."""
    
    print("\n=== COMPARAÇÃO: LÓGICA ANTIGA vs NOVA ===")
    
    try:
        # Carregar streams
        with open('streams.json', 'r', encoding='utf-8') as f:
            all_streams = json.load(f)
        
        # Simular IDs do orquestrador
        assigned_stream_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]
        
        # Lógica ANTIGA (problemática)
        assigned_streams_old = [
            stream for stream in all_streams 
            if stream.get("id", stream.get("name", "")) in assigned_stream_ids_str
        ]
        
        # Lógica NOVA (corrigida)
        assigned_streams_new = [
            stream for stream in all_streams 
            if stream.get("index", "") in assigned_stream_ids_str
        ]
        
        print(f"\n📊 Resultados:")
        print(f"   Lógica ANTIGA: {len(assigned_streams_old)} streams")
        print(f"   Lógica NOVA:   {len(assigned_streams_new)} streams")
        
        if len(assigned_streams_new) > 0:
            print(f"\n✅ CORREÇÃO BEM-SUCEDIDA!")
            print(f"   A nova lógica conseguiu filtrar {len(assigned_streams_new)} streams")
            print(f"   Melhoria: +{len(assigned_streams_new) - len(assigned_streams_old)} streams")
            return True
        else:
            print(f"\n❌ CORREÇÃO FALHOU!")
            print(f"   A nova lógica ainda não consegue filtrar streams")
            return False
            
    except Exception as e:
        print(f"Erro na comparação: {e}")
        return False

async def main():
    """Executa todos os testes."""
    
    print("🚀 INICIANDO TESTES DE CORREÇÃO DO FINGERV7\n")
    
    # Teste 1: Comparação de lógicas
    comparison_success = await test_old_vs_new_logic()
    
    # Teste 2: Fluxo completo
    if comparison_success:
        flow_success = await test_fingerv7_stream_assignment()
        
        if flow_success:
            print("\n🎉 TODOS OS TESTES PASSARAM!")
            print("   ✅ A correção do fingerv7 está funcionando corretamente")
            print("   ✅ Os streams estão sendo atribuídos e filtrados adequadamente")
            print("\n📝 PRÓXIMOS PASSOS:")
            print("   1. Reiniciar o fingerv7 para aplicar a correção")
            print("   2. Monitorar os logs para confirmar que streams estão sendo processados")
            print("   3. Verificar se as identificações musicais estão funcionando")
        else:
            print("\n⚠️  TESTE DO FLUXO COMPLETO FALHOU")
            print("   A correção pode estar incompleta ou há outros problemas")
    else:
        print("\n❌ TESTE DE COMPARAÇÃO FALHOU")
        print("   A correção não está funcionando como esperado")

if __name__ == "__main__":
    asyncio.run(main())
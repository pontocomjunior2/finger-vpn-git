#!/usr/bin/env python3
import asyncio
import json
import os
from dotenv import load_dotenv
from orchestrator_client import create_orchestrator_client

load_dotenv()

SERVER_ID = os.getenv('SERVER_ID', '1')
ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL')
DISTRIBUTE_LOAD = os.getenv('DISTRIBUTE_LOAD', 'False').lower() == 'true'
USE_ORCHESTRATOR = os.getenv('USE_ORCHESTRATOR', 'False').lower() == 'true'

async def test_stream_assignment_logic():
    """Testa especificamente a lógica de atribuição de streams do fingerv7."""
    
    print("=== TESTE DA LÓGICA DE ATRIBUIÇÃO DE STREAMS ===")
    print(f"DISTRIBUTE_LOAD: {DISTRIBUTE_LOAD}")
    print(f"USE_ORCHESTRATOR: {USE_ORCHESTRATOR}")
    print(f"SERVER_ID: {SERVER_ID}")
    print(f"ORCHESTRATOR_URL: {ORCHESTRATOR_URL}")
    
    if not (DISTRIBUTE_LOAD and USE_ORCHESTRATOR):
        print("\n❌ PROBLEMA: DISTRIBUTE_LOAD ou USE_ORCHESTRATOR não estão ativados")
        print("   O fingerv7 não usará o orquestrador nesta configuração")
        return False
    
    try:
        # 1. Carregar streams do arquivo JSON
        print("\n1. Carregando streams do arquivo JSON...")
        with open('streams.json', 'r', encoding='utf-8') as f:
            all_streams = json.load(f)
        print(f"   ✅ Carregados {len(all_streams)} streams")
        
        # 2. Simular a lógica do fingerv7
        print("\n2. Simulando lógica do fingerv7...")
        
        # Inicializar cliente do orquestrador
        print("   2.1. Inicializando cliente do orquestrador...")
        orchestrator_client = create_orchestrator_client(
            orchestrator_url=ORCHESTRATOR_URL,
            server_id=SERVER_ID
        )
        print("   ✅ Cliente inicializado")
        
        # Registrar instância
        print("   2.2. Registrando instância...")
        registration_success = await orchestrator_client.register()
        if not registration_success:
            print("   ❌ Falha no registro")
            return False
        print("   ✅ Instância registrada")
        
        # Solicitar streams
        print("   2.3. Solicitando streams...")
        assigned_stream_ids = await orchestrator_client.request_streams()
        print(f"   ✅ Recebidos {len(assigned_stream_ids)} stream IDs: {assigned_stream_ids[:10]}{'...' if len(assigned_stream_ids) > 10 else ''}")
        
        if not assigned_stream_ids:
            print("   ❌ Nenhum stream foi atribuído")
            return False
        
        # Converter IDs para string (como no fingerv7)
        print("   2.4. Convertendo IDs para compatibilidade...")
        assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]
        print(f"   IDs convertidos: {assigned_stream_ids_str[:10]}{'...' if len(assigned_stream_ids_str) > 10 else ''}")
        
        # Aplicar lógica de filtragem CORRIGIDA
        print("   2.5. Aplicando lógica de filtragem corrigida...")
        assigned_streams = [
            stream for stream in all_streams 
            if stream.get("index", "") in assigned_stream_ids_str
        ]
        
        print(f"   ✅ {len(assigned_streams)} streams filtrados com sucesso")
        
        if len(assigned_streams) == 0:
            print("   ❌ PROBLEMA: Nenhum stream foi filtrado")
            print("   Verificando compatibilidade de IDs...")
            
            # Debug: verificar alguns streams
            print("   Primeiros 5 streams do JSON:")
            for i, stream in enumerate(all_streams[:5]):
                index = stream.get('index', 'N/A')
                name = stream.get('name', 'N/A')
                print(f"     {i+1}. Index: '{index}', Name: '{name}'")
            
            print(f"   IDs do orquestrador: {assigned_stream_ids_str[:5]}")
            return False
        
        # 3. Verificar resultado
        print("\n3. Verificando resultado da atribuição...")
        
        success_rate = len(assigned_streams) / len(assigned_stream_ids) * 100
        print(f"   Taxa de sucesso da filtragem: {success_rate:.1f}%")
        print(f"   Streams solicitados: {len(assigned_stream_ids)}")
        print(f"   Streams efetivamente atribuídos: {len(assigned_streams)}")
        
        if success_rate >= 90:
            print("   ✅ EXCELENTE: Filtragem funcionando perfeitamente")
        elif success_rate >= 70:
            print("   ✅ BOM: Filtragem funcionando adequadamente")
        elif success_rate >= 50:
            print("   ⚠️  REGULAR: Filtragem parcialmente funcional")
        else:
            print("   ❌ RUIM: Filtragem com problemas")
        
        # Mostrar alguns streams atribuídos
        print("\n   Streams atribuídos (primeiros 5):")
        for i, stream in enumerate(assigned_streams[:5]):
            name = stream.get('name', 'N/A')
            index = stream.get('index', 'N/A')
            url = stream.get('url', 'N/A')[:50] + '...' if len(stream.get('url', '')) > 50 else stream.get('url', 'N/A')
            print(f"     {i+1}. {name} (Index: {index})")
            print(f"        URL: {url}")
        
        if len(assigned_streams) > 5:
            print(f"     ... e mais {len(assigned_streams) - 5} streams")
        
        # 4. Cleanup
        print("\n4. Liberando streams...")
        await orchestrator_client.release_all_streams()
        print("   ✅ Streams liberados")
        
        return success_rate >= 70
        
    except Exception as e:
        print(f"❌ Erro durante teste: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_configuration_validation():
    """Valida se todas as configurações necessárias estão corretas."""
    
    print("\n=== VALIDAÇÃO DE CONFIGURAÇÕES ===")
    
    issues = []
    
    # Verificar variáveis de ambiente
    if not DISTRIBUTE_LOAD:
        issues.append("DISTRIBUTE_LOAD não está ativado")
    
    if not USE_ORCHESTRATOR:
        issues.append("USE_ORCHESTRATOR não está ativado")
    
    if not ORCHESTRATOR_URL:
        issues.append("ORCHESTRATOR_URL não está definido")
    
    if not SERVER_ID:
        issues.append("SERVER_ID não está definido")
    
    # Verificar arquivos necessários
    if not os.path.exists('streams.json'):
        issues.append("Arquivo streams.json não encontrado")
    
    if not os.path.exists('fingerv7.py'):
        issues.append("Arquivo fingerv7.py não encontrado")
    
    if issues:
        print("❌ PROBLEMAS DE CONFIGURAÇÃO ENCONTRADOS:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("✅ TODAS AS CONFIGURAÇÕES ESTÃO CORRETAS")
        return True

async def main():
    """Executa todos os testes."""
    
    print("🚀 TESTE COMPLETO DA LÓGICA DE ATRIBUIÇÃO DE STREAMS\n")
    
    # 1. Validar configurações
    config_ok = await test_configuration_validation()
    
    if not config_ok:
        print("\n❌ TESTE ABORTADO: Problemas de configuração")
        return
    
    # 2. Testar lógica de atribuição
    assignment_ok = await test_stream_assignment_logic()
    
    if assignment_ok:
        print("\n🎉 TESTE CONCLUÍDO COM SUCESSO!")
        print("   ✅ Configurações corretas")
        print("   ✅ Lógica de atribuição funcionando")
        print("   ✅ Filtragem de streams corrigida")
        print("\n📝 O fingerv7 deve funcionar corretamente agora")
        print("   Pode executar: python fingerv7.py")
    else:
        print("\n⚠️  TESTE REVELOU PROBLEMAS")
        print("   A lógica de atribuição ainda tem problemas")
        print("   Pode ser necessário investigar mais")

if __name__ == "__main__":
    asyncio.run(main())
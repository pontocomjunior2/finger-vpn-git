#!/usr/bin/env python3
import json
import os

from dotenv import load_dotenv

load_dotenv()

def debug_stream_filtering():
    """Debug da filtragem de streams para identificar incompatibilidade de IDs."""
    
    print("=== DEBUG DA FILTRAGEM DE STREAMS ===")
    
    # 1. Carregar streams do arquivo JSON
    try:
        with open('streams.json', 'r', encoding='utf-8') as f:
            all_streams = json.load(f)
        print(f"\n1. Carregados {len(all_streams)} streams do arquivo JSON")
        
        # Mostrar exemplos de streams
        print("   Exemplos de streams:")
        for i, stream in enumerate(all_streams[:5]):
            stream_id = stream.get("id", stream.get("name", ""))
            index = stream.get("index", "N/A")
            name = stream.get("name", "N/A")
            print(f"     Stream {i}: id='{stream_id}', index='{index}', name='{name}'")
            
    except Exception as e:
        print(f"   ❌ Erro ao carregar streams: {e}")
        return
    
    # 2. Simular IDs retornados pelo orquestrador
    assigned_stream_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # IDs numéricos do orquestrador
    assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]  # Convertidos para string
    
    print(f"\n2. IDs do orquestrador (numéricos): {assigned_stream_ids}")
    print(f"   IDs convertidos para string: {assigned_stream_ids_str}")
    
    # 3. Testar filtragem atual (problemática)
    print("\n3. Testando filtragem atual (problemática):")
    assigned_streams_current = [
        stream for stream in all_streams 
        if stream.get("id", stream.get("name", "")) in assigned_stream_ids_str
    ]
    print(f"   Streams filtrados com lógica atual: {len(assigned_streams_current)}")
    
    if assigned_streams_current:
        print("   Streams encontrados:")
        for stream in assigned_streams_current[:3]:
            print(f"     - {stream.get('name')} (ID: {stream.get('id', stream.get('name'))})")
    else:
        print("   ❌ Nenhum stream encontrado com a lógica atual!")
    
    # 4. Testar filtragem corrigida (usando index)
    print("\n4. Testando filtragem corrigida (usando index):")
    assigned_streams_fixed = [
        stream for stream in all_streams 
        if stream.get("index", "") in assigned_stream_ids_str
    ]
    print(f"   Streams filtrados com lógica corrigida: {len(assigned_streams_fixed)}")
    
    if assigned_streams_fixed:
        print("   Streams encontrados:")
        for stream in assigned_streams_fixed[:3]:
            print(f"     - {stream.get('name')} (Index: {stream.get('index')})")
    else:
        print("   ❌ Nenhum stream encontrado com a lógica corrigida!")
    
    # 5. Análise detalhada dos campos de identificação
    print("\n5. Análise dos campos de identificação nos streams:")
    
    has_id_field = sum(1 for stream in all_streams if 'id' in stream)
    has_index_field = sum(1 for stream in all_streams if 'index' in stream)
    has_name_field = sum(1 for stream in all_streams if 'name' in stream)
    
    print(f"   Streams com campo 'id': {has_id_field}/{len(all_streams)}")
    print(f"   Streams com campo 'index': {has_index_field}/{len(all_streams)}")
    print(f"   Streams com campo 'name': {has_name_field}/{len(all_streams)}")
    
    # Verificar tipos de valores nos campos
    if has_index_field > 0:
        index_types = set(type(stream.get('index')).__name__ for stream in all_streams if 'index' in stream)
        print(f"   Tipos de dados no campo 'index': {index_types}")
        
        # Mostrar alguns valores de index
        index_values = [stream.get('index') for stream in all_streams[:10] if 'index' in stream]
        print(f"   Primeiros valores de 'index': {index_values}")
    
    # 6. Recomendação
    print("\n6. DIAGNÓSTICO E RECOMENDAÇÃO:")
    
    if has_index_field == len(all_streams) and len(assigned_streams_fixed) > 0:
        print("   ✅ SOLUÇÃO ENCONTRADA: Usar campo 'index' para filtragem")
        print("   📝 Código corrigido:")
        print("       assigned_streams = [")
        print("           stream for stream in all_streams")
        print("           if stream.get('index', '') in assigned_stream_ids_str")
        print("       ]")
        return True
    elif has_id_field == 0 and has_index_field == len(all_streams):
        print("   ⚠️  PROBLEMA: Streams não têm campo 'id', apenas 'index'")
        print("   💡 SOLUÇÃO: Modificar lógica para usar 'index' em vez de 'id'")
        return False
    else:
        print("   ❌ PROBLEMA COMPLEXO: Estrutura inconsistente de IDs")
        print("   🔍 INVESTIGAÇÃO NECESSÁRIA: Verificar origem dos dados")
        return False

if __name__ == "__main__":
    success = debug_stream_filtering()
    
    if success:
        print("\n🎉 PROBLEMA IDENTIFICADO E SOLUÇÃO ENCONTRADA!")
        print("   A filtragem deve usar o campo 'index' em vez de 'id'")
    else:
        print("\n⚠️  PROBLEMA IDENTIFICADO - CORREÇÃO NECESSÁRIA")
        print("   A estrutura de IDs precisa ser padronizada")
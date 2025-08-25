#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Conectar ao banco do orquestrador
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB'),
        port=os.getenv('POSTGRES_PORT')
    )
    conn.autocommit = True

    cursor = conn.cursor()

    print("=== DEBUG DO ORQUESTRADOR - BUSCA DE STREAMS ===")
    
    # Verificar estrutura da tabela streams
    print("\n1. Estrutura da tabela 'streams':")
    cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'streams' ORDER BY ordinal_position")
    columns = cursor.fetchall()
    for col in columns:
        print(f'   - {col[0]}: {col[1]}')
    
    # Verificar se existe coluna 'id' na tabela streams
    has_id_column = any(col[0] == 'id' for col in columns)
    print(f"\n2. Tabela 'streams' tem coluna 'id': {has_id_column}")
    
    if not has_id_column:
        print("   ⚠️  PROBLEMA ENCONTRADO: Tabela 'streams' não tem coluna 'id'!")
        print("   O orquestrador está tentando buscar 'id' mas a coluna não existe.")
        
        # Verificar se tem coluna 'index' (que é usada no fingerv7)
        has_index_column = any(col[0] == 'index' for col in columns)
        if has_index_column:
            print("   ✅ Tabela tem coluna 'index' - esta deveria ser usada pelo orquestrador")
            
            # Mostrar alguns valores da coluna index
            cursor.execute('SELECT index FROM streams LIMIT 10')
            indexes = cursor.fetchall()
            print(f"   Primeiros valores de 'index': {[i[0] for i in indexes]}")
    else:
        print("   ✅ Coluna 'id' existe")
        
        # Testar a query do orquestrador
        print("\n3. Testando query do orquestrador:")
        try:
            cursor.execute("SELECT DISTINCT id FROM streams ORDER BY id")
            all_streams = [row[0] for row in cursor.fetchall()]
            print(f"   Query executada com sucesso: {len(all_streams)} streams encontrados")
            print(f"   Primeiros IDs: {all_streams[:10]}")
        except Exception as e:
            print(f"   ❌ Erro na query: {e}")
    
    # Verificar assignments existentes
    print("\n4. Verificando assignments existentes:")
    cursor.execute('SELECT COUNT(*) FROM orchestrator_stream_assignments WHERE status = \'active\'')
    active_assignments = cursor.fetchone()[0]
    print(f"   Assignments ativos: {active_assignments}")
    
    if active_assignments > 0:
        cursor.execute('SELECT stream_id FROM orchestrator_stream_assignments WHERE status = \'active\' LIMIT 10')
        assigned_ids = cursor.fetchall()
        print(f"   IDs de streams atribuídos: {[i[0] for i in assigned_ids]}")
    
    # Simular a lógica do orquestrador
    print("\n5. Simulando lógica do orquestrador:")
    
    try:
        # Buscar todos os streams (como o orquestrador faz)
        if has_id_column:
            cursor.execute("SELECT DISTINCT id FROM streams ORDER BY id")
            all_streams = [row[0] for row in cursor.fetchall()]
        else:
            print("   Usando 'index' ao invés de 'id'...")
            cursor.execute("SELECT DISTINCT index FROM streams ORDER BY index")
            all_streams = [row[0] for row in cursor.fetchall()]
        
        print(f"   Total de streams: {len(all_streams)}")
        
        # Buscar streams já atribuídos
        cursor.execute("SELECT stream_id FROM orchestrator_stream_assignments WHERE status = 'active'")
        assigned_streams = set(row[0] for row in cursor.fetchall())
        
        # Calcular streams disponíveis
        available_streams = [s for s in all_streams if s not in assigned_streams]
        
        print(f"   Streams atribuídos: {len(assigned_streams)}")
        print(f"   Streams disponíveis: {len(available_streams)}")
        
        if len(available_streams) == 0:
            print("   ❌ PROBLEMA: Nenhum stream disponível para atribuição!")
            if len(assigned_streams) > 0:
                print("   Isso pode indicar que todos os streams já foram atribuídos")
        else:
            print(f"   ✅ {len(available_streams)} streams disponíveis para atribuição")
            print(f"   Primeiros disponíveis: {available_streams[:10]}")
            
    except Exception as e:
        print(f"   ❌ Erro na simulação: {e}")

    conn.close()
    
except Exception as e:
    print(f"Erro: {e}")
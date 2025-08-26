#!/usr/bin/env python3
import json
import logging
import os
import sys

from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

def fix_stream_filtering():
    """Corrige a filtragem de streams para usar o campo 'index' em vez de 'id'."""
    
    logger.info("=== CORREÇÃO DA FILTRAGEM DE STREAMS ===\n")
    
    # 1. Verificar o arquivo fingerv7.py
    fingerv7_path = 'fingerv7.py'
    if not os.path.exists(fingerv7_path):
        logger.error(f"Arquivo {fingerv7_path} não encontrado!")
        return False
    
    # 2. Ler o conteúdo do arquivo
    try:
        with open(fingerv7_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"Arquivo {fingerv7_path} lido com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao ler o arquivo {fingerv7_path}: {e}")
        return False
    
    # 3. Verificar se a correção já foi aplicada
    if 'stream.get("index", "") in assigned_stream_ids_str' in content:
        logger.info("✅ A correção já foi aplicada! Nenhuma alteração necessária.")
        return True
    
    # 4. Aplicar a correção
    try:
        # Padrão a ser substituído (lógica incorreta)
        old_pattern = "stream.get(\"id\", stream.get(\"name\", \"\")) in assigned_stream_ids_str"
        # Nova lógica corrigida
        new_pattern = "stream.get(\"index\", \"\") in assigned_stream_ids_str"
        
        # Substituir no conteúdo
        if old_pattern in content:
            new_content = content.replace(old_pattern, new_pattern)
            logger.info("Padrão encontrado e substituído.")
        else:
            # Tentar encontrar um padrão similar
            logger.warning("Padrão exato não encontrado. Tentando encontrar padrão similar...")
            
            # Buscar a seção de filtragem de streams
            filter_section = "# Filtrar streams atribuídos"
            if filter_section in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if filter_section in line:
                        # Procurar a linha de filtragem nos próximos 10 linhas
                        for j in range(i+1, min(i+10, len(lines))):
                            if 'stream.get("id"' in lines[j] and 'assigned_stream_ids_str' in lines[j]:
                                logger.info(f"Encontrada linha de filtragem: {lines[j]}")
                                lines[j] = lines[j].replace('stream.get("id"', 'stream.get("index"')
                                new_content = '\n'.join(lines)
                                logger.info("Correção aplicada com sucesso!")
                                break
                        break
            else:
                logger.error("Seção de filtragem não encontrada!")
                return False
        
        # 5. Fazer backup do arquivo original
        backup_path = f"{fingerv7_path}.bak"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Backup criado em {backup_path}")
        
        # 6. Salvar o arquivo corrigido
        with open(fingerv7_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info(f"Arquivo {fingerv7_path} atualizado com sucesso!")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao aplicar correção: {e}")
        return False

def verify_correction():
    """Verifica se a correção foi aplicada corretamente."""
    
    logger.info("\n=== VERIFICAÇÃO DA CORREÇÃO ===\n")
    
    # 1. Carregar streams do arquivo JSON
    try:
        with open('streams.json', 'r', encoding='utf-8') as f:
            all_streams = json.load(f)
        logger.info(f"Carregados {len(all_streams)} streams do arquivo JSON")
    except Exception as e:
        logger.error(f"Erro ao carregar streams: {e}")
        return False
    
    # 2. Simular IDs retornados pelo orquestrador
    assigned_stream_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # IDs numéricos do orquestrador
    assigned_stream_ids_str = [str(id) for id in assigned_stream_ids]  # Convertidos para string
    
    # 3. Testar filtragem corrigida (usando index)
    assigned_streams_fixed = [
        stream for stream in all_streams 
        if stream.get("index", "") in assigned_stream_ids_str
    ]
    
    if assigned_streams_fixed:
        logger.info(f"✅ Correção verificada! {len(assigned_streams_fixed)} streams encontrados com a lógica corrigida.")
        logger.info("Exemplos de streams encontrados:")
        for i, stream in enumerate(assigned_streams_fixed[:3]):
            logger.info(f"  - {stream.get('name')} (Index: {stream.get('index')})")
        return True
    else:
        logger.error("❌ Nenhum stream encontrado com a lógica corrigida!")
        return False

def main():
    """Função principal"""
    if fix_stream_filtering():
        verify_correction()
        logger.info("\n✅ CORREÇÃO CONCLUÍDA!")
        logger.info("Para aplicar a correção, reinicie o script fingerv7.py:")
        logger.info("1. Pare o script atual")
        logger.info("2. Execute: python fingerv7.py")
    else:
        logger.error("\n❌ FALHA NA CORREÇÃO!")

if __name__ == "__main__":
    main()
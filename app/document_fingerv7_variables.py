#!/usr/bin/env python3
"""
Script para documentar as variáveis necessárias para instâncias fingerv7
"""

import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def document_fingerv7_variables():
    """Documenta todas as variáveis necessárias para instâncias fingerv7"""
    print("📋 VARIÁVEIS NECESSÁRIAS PARA INSTÂNCIAS FINGERV7\n")
    
    # Variáveis obrigatórias
    required_vars = {
        'POSTGRES_HOST': 'Host do banco PostgreSQL',
        'POSTGRES_PORT': 'Porta do banco PostgreSQL',
        'POSTGRES_DB': 'Nome do banco de dados',
        'POSTGRES_USER': 'Usuário do banco de dados',
        'POSTGRES_PASSWORD': 'Senha do banco de dados',
        'ORCHESTRATOR_URL': 'URL do orquestrador',
        'SERVER_ID': 'ID único da instância (1, 2, 3, etc.)',
        'MAX_STREAMS': 'Número máximo de streams por instância',
        'USE_ORCHESTRATOR': 'Usar orquestrador (True/False)',
        'DISTRIBUTE_LOAD': 'Distribuir carga entre instâncias (True/False)'
    }
    
    # Variáveis opcionais
    optional_vars = {
        'POOL_SIZE': 'Tamanho do pool de conexões (padrão: 20)',
        'POOL_MAX_OVERFLOW': 'Overflow máximo do pool (padrão: 30)',
        'HEARTBEAT_INTERVAL': 'Intervalo de heartbeat em segundos (padrão: 30)',
        'SYNC_INTERVAL': 'Intervalo de sincronização em segundos (padrão: 300)',
        'LOG_LEVEL': 'Nível de log (DEBUG, INFO, WARNING, ERROR)',
        'TIMEZONE': 'Fuso horário (padrão: America/Sao_Paulo)'
    }
    
    print("=== VARIÁVEIS OBRIGATÓRIAS ===")
    for var, description in required_vars.items():
        value = os.getenv(var)
        status = "✅ Configurada" if value else "❌ NÃO CONFIGURADA"
        print(f"{var:20} | {description:40} | {status}")
        if value:
            # Mascarar senhas
            display_value = "***" if 'PASSWORD' in var else value
            print(f"{' ' * 20} | Valor atual: {display_value}")
        print()
    
    print("\n=== VARIÁVEIS OPCIONAIS ===")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        status = "✅ Configurada" if value else "⚪ Usando padrão"
        print(f"{var:20} | {description:40} | {status}")
        if value:
            print(f"{' ' * 20} | Valor atual: {value}")
        print()
    
    # Verificar configurações críticas
    print("\n=== VERIFICAÇÃO DE CONFIGURAÇÕES CRÍTICAS ===")
    
    # Verificar se USE_ORCHESTRATOR está habilitado
    use_orchestrator = os.getenv('USE_ORCHESTRATOR', '').lower() == 'true'
    if use_orchestrator:
        print("✅ Orquestrador habilitado")
        
        # Verificar URL do orquestrador
        orchestrator_url = os.getenv('ORCHESTRATOR_URL')
        if orchestrator_url:
            print(f"✅ URL do orquestrador: {orchestrator_url}")
        else:
            print("❌ URL do orquestrador não configurada")
        
        # Verificar SERVER_ID
        server_id = os.getenv('SERVER_ID')
        if server_id:
            print(f"✅ ID do servidor: {server_id}")
        else:
            print("❌ ID do servidor não configurado")
    else:
        print("⚠️  Orquestrador desabilitado - funcionará em modo standalone")
    
    # Verificar MAX_STREAMS
    max_streams = os.getenv('MAX_STREAMS')
    if max_streams:
        try:
            max_streams_int = int(max_streams)
            print(f"✅ Máximo de streams: {max_streams_int}")
            if max_streams_int < 1:
                print("⚠️  Aviso: MAX_STREAMS deve ser pelo menos 1")
            elif max_streams_int > 50:
                print("⚠️  Aviso: MAX_STREAMS muito alto pode impactar performance")
        except ValueError:
            print(f"❌ MAX_STREAMS inválido: {max_streams}")
    else:
        print("❌ MAX_STREAMS não configurado")
    
    print("\n=== EXEMPLO DE ARQUIVO .env ===")
    print("""
# Configurações do Banco de Dados
POSTGRES_HOST=seu-host-postgres
POSTGRES_PORT=5432
POSTGRES_DB=seu-banco
POSTGRES_USER=seu-usuario
POSTGRES_PASSWORD=sua-senha

# Configurações do Orquestrador
ORCHESTRATOR_URL=http://seu-orquestrador:8080
USE_ORCHESTRATOR=True
DISTRIBUTE_LOAD=True

# Configurações da Instância
SERVER_ID=1
MAX_STREAMS=20

# Configurações Opcionais
POOL_SIZE=20
POOL_MAX_OVERFLOW=30
HEARTBEAT_INTERVAL=30
SYNC_INTERVAL=300
LOG_LEVEL=INFO
TIMEZONE=America/Sao_Paulo
    """)
    
    print("\n=== NOTAS IMPORTANTES ===")
    print("1. Cada instância deve ter um SERVER_ID único")
    print("2. MAX_STREAMS deve ser ajustado conforme capacidade do servidor")
    print("3. USE_ORCHESTRATOR=True é necessário para distribuição de carga")
    print("4. DISTRIBUTE_LOAD=True permite balanceamento automático")
    print("5. Todas as instâncias devem apontar para o mesmo banco de dados")
    print("6. O orquestrador deve estar rodando antes das instâncias")

if __name__ == "__main__":
    document_fingerv7_variables()
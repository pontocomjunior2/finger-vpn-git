#!/usr/bin/env python3
"""
Script de Configuração e Inicialização do Orquestrador

Este script configura o ambiente e inicializa o orquestrador central
para distribuição de streams entre instâncias.

Autor: Sistema de Fingerprinting
Data: 2024
"""

import os
import sys
import subprocess
import logging
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_python_version():
    """Verifica se a versão do Python é compatível."""
    if sys.version_info < (3, 8):
        logger.error("Python 3.8 ou superior é necessário")
        sys.exit(1)
    logger.info(f"Python {sys.version} - OK")

def install_dependencies():
    """Instala as dependências necessárias."""
    requirements_file = Path(__file__).parent / "requirements_orchestrator.txt"
    
    if not requirements_file.exists():
        logger.error(f"Arquivo de dependências não encontrado: {requirements_file}")
        return False
    
    try:
        logger.info("Instalando dependências...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ])
        logger.info("Dependências instaladas com sucesso")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erro ao instalar dependências: {e}")
        return False

def load_environment():
    """Carrega variáveis de ambiente."""
    # Primeiro tenta carregar do .env da raiz do projeto
    root_env_file = Path(__file__).parent.parent / ".env"
    app_env_file = Path(__file__).parent / ".env"
    
    env_loaded = False
    
    if root_env_file.exists():
        load_dotenv(root_env_file)
        logger.info(f"Variáveis de ambiente carregadas de {root_env_file}")
        env_loaded = True
    elif app_env_file.exists():
        load_dotenv(app_env_file)
        logger.info(f"Variáveis de ambiente carregadas de {app_env_file}")
        env_loaded = True
    else:
        logger.warning("Arquivo .env não encontrado")
    
    # Mapear variáveis POSTGRES_* para DB_* se necessário
    if os.getenv('POSTGRES_HOST') and not os.getenv('DB_HOST'):
        os.environ['DB_HOST'] = os.getenv('POSTGRES_HOST')
    if os.getenv('POSTGRES_DB') and not os.getenv('DB_NAME'):
        os.environ['DB_NAME'] = os.getenv('POSTGRES_DB')
    if os.getenv('POSTGRES_USER') and not os.getenv('DB_USER'):
        os.environ['DB_USER'] = os.getenv('POSTGRES_USER')
    if os.getenv('POSTGRES_PASSWORD') and not os.getenv('DB_PASSWORD'):
        os.environ['DB_PASSWORD'] = os.getenv('POSTGRES_PASSWORD')
    if os.getenv('POSTGRES_PORT') and not os.getenv('DB_PORT'):
        os.environ['DB_PORT'] = os.getenv('POSTGRES_PORT')
    
    # Verificar variáveis essenciais
    required_vars = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Variáveis de ambiente obrigatórias não encontradas: {missing_vars}")
        logger.info("Configure as seguintes variáveis no arquivo .env:")
        logger.info("POSTGRES_HOST=seu_host (ou DB_HOST)")
        logger.info("POSTGRES_DB=seu_banco (ou DB_NAME)")
        logger.info("POSTGRES_USER=seu_usuario (ou DB_USER)")
        logger.info("POSTGRES_PASSWORD=sua_senha (ou DB_PASSWORD)")
        logger.info("POSTGRES_PORT=5432 (ou DB_PORT)")
        logger.info("")
        logger.info("Variáveis opcionais do orquestrador:")
        logger.info("ORCHESTRATOR_HOST=0.0.0.0")
        logger.info("ORCHESTRATOR_PORT=8001")
        logger.info("MAX_STREAMS_PER_INSTANCE=20")
        logger.info("HEARTBEAT_TIMEOUT=300")
        logger.info("REBALANCE_INTERVAL=60")
        return False
    
    logger.info(f"Configuração do banco: {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")
    return True

def test_database_connection():
    """Testa a conexão com o banco de dados."""
    try:
        conn_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'radio_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
            'port': int(os.getenv('DB_PORT', 5432))
        }
        
        logger.info(f"Testando conexão com banco de dados em {conn_params['host']}:{conn_params['port']}...")
        
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        logger.info(f"Conexão com banco de dados OK - {version}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao conectar com banco de dados: {e}")
        logger.info("Verifique se:")
        logger.info("1. PostgreSQL está rodando")
        logger.info("2. Credenciais estão corretas no .env")
        logger.info("3. Banco de dados existe")
        logger.info("4. Usuário tem permissões adequadas")
        return False

def create_database_tables():
    """Cria as tabelas necessárias no banco de dados."""
    try:
        # Importar e usar o orquestrador para criar tabelas
        from orchestrator import StreamOrchestrator
        
        orchestrator = StreamOrchestrator()
        orchestrator.create_tables()
        
        logger.info("Tabelas do orquestrador criadas/verificadas com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        return False

def check_port_availability(port):
    """Verifica se a porta está disponível."""
    import socket
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', port))
            logger.info(f"Porta {port} está disponível")
            return True
    except OSError:
        logger.warning(f"Porta {port} já está em uso")
        return False

def create_systemd_service():
    """Cria arquivo de serviço systemd (Linux apenas)."""
    if os.name != 'posix':
        logger.info("Criação de serviço systemd pulada (não é Linux)")
        return
    
    service_content = f"""[Unit]
Description=Stream Orchestrator
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=radio
WorkingDirectory={Path(__file__).parent}
Environment=PATH={os.environ.get('PATH', '')}
ExecStart={sys.executable} orchestrator.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    service_file = Path("/etc/systemd/system/stream-orchestrator.service")
    
    try:
        with open(service_file, 'w') as f:
            f.write(service_content)
        
        logger.info(f"Arquivo de serviço criado: {service_file}")
        logger.info("Para habilitar o serviço:")
        logger.info("sudo systemctl daemon-reload")
        logger.info("sudo systemctl enable stream-orchestrator")
        logger.info("sudo systemctl start stream-orchestrator")
        
    except PermissionError:
        logger.warning("Sem permissão para criar arquivo de serviço systemd")
        logger.info("Execute como root ou use sudo para criar o serviço")
    except Exception as e:
        logger.error(f"Erro ao criar arquivo de serviço: {e}")

def create_startup_script():
    """Cria script de inicialização."""
    script_content = f"""#!/bin/bash
# Script de inicialização do Stream Orchestrator

cd "{Path(__file__).parent}"

# Ativar ambiente virtual se existir
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Executar orquestrador
python orchestrator.py
"""
    
    script_file = Path(__file__).parent / "start_orchestrator.sh"
    
    try:
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Tornar executável
        os.chmod(script_file, 0o755)
        
        logger.info(f"Script de inicialização criado: {script_file}")
        
    except Exception as e:
        logger.error(f"Erro ao criar script de inicialização: {e}")

def create_windows_batch():
    """Cria arquivo batch para Windows."""
    batch_content = f"""@echo off
REM Script de inicialização do Stream Orchestrator para Windows

cd /d "{Path(__file__).parent}"

REM Ativar ambiente virtual se existir
if exist "venv\\Scripts\\activate.bat" (
    call venv\\Scripts\\activate.bat
)

REM Executar orquestrador
python orchestrator.py

pause
"""
    
    batch_file = Path(__file__).parent / "start_orchestrator.bat"
    
    try:
        with open(batch_file, 'w') as f:
            f.write(batch_content)
        
        logger.info(f"Arquivo batch criado: {batch_file}")
        
    except Exception as e:
        logger.error(f"Erro ao criar arquivo batch: {e}")

def main():
    """Função principal de configuração."""
    logger.info("=== Configuração do Stream Orchestrator ===")
    
    # Verificar argumentos da linha de comando
    skip_db_test = '--skip-db-test' in sys.argv
    if skip_db_test:
        logger.info("Modo de configuração: pulando teste de conexão com banco")
    
    # Verificar versão do Python
    check_python_version()
    
    # Carregar ambiente
    if not load_environment():
        logger.error("Falha ao carregar variáveis de ambiente")
        sys.exit(1)
    
    # Instalar dependências
    if not install_dependencies():
        logger.error("Falha ao instalar dependências")
        sys.exit(1)
    
    # Testar conexão com banco (opcional)
    if not skip_db_test:
        if not test_database_connection():
            logger.warning("Falha na conexão com banco de dados")
            logger.info("\nEm ambiente de produção, as credenciais podem ser diferentes.")
            logger.info("Para pular este teste, use: python setup_orchestrator.py --skip-db-test")
            
            response = input("\nDeseja continuar mesmo assim? (s/N): ").lower().strip()
            if response not in ['s', 'sim', 'y', 'yes']:
                logger.error("Configuração cancelada pelo usuário")
                sys.exit(1)
            logger.info("Continuando configuração...")
    else:
        logger.info("Teste de conexão com banco pulado")
    
    # Criar tabelas (apenas se conexão funcionou ou foi pulada)
    if not skip_db_test:
        if not create_database_tables():
            logger.error("Falha ao criar tabelas")
            sys.exit(1)
    else:
        logger.info("Criação de tabelas pulada (será feita no primeiro boot do orquestrador)")
    
    # Verificar porta
    port = int(os.getenv('ORCHESTRATOR_PORT', 8001))
    check_port_availability(port)
    
    # Criar scripts de inicialização
    if os.name == 'posix':
        create_startup_script()
        create_systemd_service()
    else:
        create_windows_batch()
    
    logger.info("=== Configuração Concluída ===")
    logger.info(f"Orquestrador configurado para rodar na porta {port}")
    logger.info("Para iniciar o orquestrador:")
    
    if os.name == 'posix':
        logger.info(f"  ./start_orchestrator.sh")
        logger.info(f"  ou")
        logger.info(f"  python orchestrator.py")
    else:
        logger.info(f"  start_orchestrator.bat")
        logger.info(f"  ou")
        logger.info(f"  python orchestrator.py")
    
    logger.info("")
    logger.info("URLs importantes:")
    logger.info(f"  Status: http://localhost:{port}/status")
    logger.info(f"  Instâncias: http://localhost:{port}/instances")
    logger.info(f"  Atribuições: http://localhost:{port}/streams/assignments")
    logger.info(f"  Documentação: http://localhost:{port}/docs")
    
    if skip_db_test:
        logger.info("\n⚠️  IMPORTANTE: Certifique-se de que as credenciais do banco estão corretas no ambiente de produção!")

if __name__ == "__main__":
    main()
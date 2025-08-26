#!/bin/bash
# =============================================================================
# SCRIPT DE INICIALIZAÇÃO PARA EASYPANEL
# =============================================================================

set -e

echo "🚀 Iniciando Enhanced Stream Orchestrator no EasyPanel..."

# Função para aguardar serviço
wait_for_service() {
    local service=$1
    local host=$2
    local port=$3
    local max_attempts=30
    local attempt=1

    echo "⏳ Aguardando $service ($host:$port)..."
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z $host $port 2>/dev/null; then
            echo "✅ $service está pronto!"
            return 0
        fi
        
        echo "   Tentativa $attempt/$max_attempts - aguardando..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service não ficou pronto após $max_attempts tentativas"
    return 1
}

# Aguardar PostgreSQL
wait_for_service "PostgreSQL" "localhost" "5432"

# Aguardar Redis
wait_for_service "Redis" "localhost" "6379"

# Executar migrations
echo "🔄 Executando migrations do banco..."
cd /app

python -c "
import asyncio
import sys
import os
sys.path.append('/app')

# Configurar variáveis de ambiente se não estiverem definidas
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'orchestrator')
os.environ.setdefault('DB_USER', 'orchestrator_user')
os.environ.setdefault('DB_PASSWORD', 'orchestrator_pass')

from app.database.migrations import run_migrations

# Configuração do banco
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

async def main():
    try:
        print(f'🔗 Conectando ao banco: {DB_CONFIG[\"host\"]}:{DB_CONFIG[\"port\"]}/{DB_CONFIG[\"database\"]}')
        await run_migrations(DB_CONFIG)
        print('✅ Migrations executadas com sucesso!')
    except Exception as e:
        print(f'❌ Erro nas migrations: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

asyncio.run(main())
"

if [ $? -eq 0 ]; then
    echo "✅ Inicialização do banco concluída!"
else
    echo "❌ Falha na inicialização do banco"
    exit 1
fi

# Verificar se a aplicação está configurada corretamente
echo "🔍 Verificando configuração da aplicação..."

python -c "
import os
import sys

# Verificar variáveis obrigatórias
required_vars = ['SECRET_KEY']
missing_vars = []

for var in required_vars:
    if not os.getenv(var):
        missing_vars.append(var)

if missing_vars:
    print(f'❌ Variáveis obrigatórias não configuradas: {missing_vars}')
    print('   Configure no painel do EasyPanel!')
    sys.exit(1)

print('✅ Configuração da aplicação OK!')
"

echo "🎉 Enhanced Stream Orchestrator pronto para iniciar!"
echo "📊 Acesse /health para verificar o status"
echo "🌐 Dashboard disponível na raiz do domínio"
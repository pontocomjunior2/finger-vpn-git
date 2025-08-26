#!/bin/bash
set -e

echo "🚀 Iniciando serviços..."

# Iniciar PostgreSQL
echo "📊 Iniciando PostgreSQL..."
su - postgres -c '/usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/data -l /var/log/postgresql.log start'

# Aguardar PostgreSQL
echo "⏳ Aguardando PostgreSQL..."
until pg_isready -h localhost -p 5432; do
  sleep 1
done

# Criar usuário e banco
echo "🔧 Configurando banco..."
su - postgres -c "psql -c \"CREATE USER orchestrator_user WITH SUPERUSER PASSWORD '${DB_PASSWORD:-orchestrator_pass}';\""
su - postgres -c "createdb -O orchestrator_user orchestrator" || true

# Executar script SQL de inicialização
if [ -f /app/scripts/init-db.sql ]; then
    echo "📋 Executando init-db.sql..."
    su - postgres -c "psql -d orchestrator -f /app/scripts/init-db.sql"
fi

# Iniciar Redis
echo "🔴 Iniciando Redis..."
redis-server --daemonize yes --bind 0.0.0.0 --port 6379

# Aguardar Redis
echo "⏳ Aguardando Redis..."
until redis-cli ping; do
  sleep 1
done

# Executar migrations
echo "🔄 Executando migrations..."
cd /app
python -c "
import asyncio
import sys
import os
sys.path.append('/app')

# Configurar variáveis de ambiente
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'orchestrator')
os.environ.setdefault('DB_USER', 'orchestrator_user')
os.environ.setdefault('DB_PASSWORD', 'orchestrator_pass')

try:
    from app.database.migrations import run_migrations
    
    DB_CONFIG = {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }
    
    async def main():
        try:
            await run_migrations(DB_CONFIG)
            print('✅ Migrations executadas com sucesso!')
        except Exception as e:
            print(f'⚠️ Migrations falharam (continuando): {e}')
    
    asyncio.run(main())
except Exception as e:
    print(f'⚠️ Erro ao importar migrations (continuando): {e}')
"

echo "🎉 Serviços iniciados! Iniciando aplicação..."

# Iniciar aplicação
exec python -m uvicorn app.main_orchestrator:app --host 0.0.0.0 --port 8000
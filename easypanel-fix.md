# 🔧 CORREÇÃO: "No such image" no EasyPanel

## ❌ Problema
```
No such image: easypanel/n8n-pontocom/finger_orchestrator:latest
```

## ✅ Solução

### 1. **Verificar Configuração no EasyPanel**

Certifique-se de que está configurado assim:

- **Repository**: `https://github.com/pontocomjunior2/finger-vpn-git.git`
- **Branch**: `orchestrator-v1`
- **Dockerfile**: `Dockerfile.easypanel`
- **Build Context**: `.` (ponto - raiz do projeto)

### 2. **Forçar Rebuild**

No painel do EasyPanel:
1. Vá em **Settings** da aplicação
2. Clique em **Rebuild**
3. Aguarde o build completar

### 3. **Verificar Logs de Build**

Se ainda der erro, verifique os logs de build para ver onde está falhando.

### 4. **Configuração Alternativa - Dockerfile Inline**

Se o problema persistir, você pode usar esta configuração inline no EasyPanel:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    postgresql-15 \
    postgresql-client-15 \
    redis-server \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/data /var/lib/postgresql/15/main /var/run/postgresql
RUN chown -R postgres:postgres /var/lib/postgresql/ /var/run/postgresql/

USER postgres
RUN /usr/lib/postgresql/15/bin/initdb -D /var/lib/postgresql/15/main --encoding=UTF-8 --locale=C
RUN echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/15/main/pg_hba.conf
RUN echo "listen_addresses='*'" >> /var/lib/postgresql/15/main/postgresql.conf

USER root

RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
set -e

# Iniciar PostgreSQL
su - postgres -c '/usr/lib/postgresql/15/bin/pg_ctl -D /var/lib/postgresql/15/main -l /tmp/pg.log start'
until pg_isready -h localhost -p 5432; do sleep 1; done

# Configurar banco
su - postgres -c "psql -c \"CREATE USER orchestrator_user WITH SUPERUSER PASSWORD '${DB_PASSWORD:-orchestrator_pass}';\""
su - postgres -c "createdb -O orchestrator_user orchestrator" || true

# Iniciar Redis
redis-server --daemonize yes --bind 0.0.0.0 --port 6379
until redis-cli ping; do sleep 1; done

# Iniciar aplicação
exec python -m uvicorn app.main_orchestrator:app --host 0.0.0.0 --port 8000
EOF

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
```

### 5. **Variáveis de Ambiente Essenciais**

Certifique-se de que estas variáveis estão configuradas:

```env
DB_PASSWORD=SuaSenhaSegura123!
SECRET_KEY=sua_chave_secreta_32_chars
DB_HOST=localhost
REDIS_HOST=localhost
```

### 6. **Teste Rápido**

Após o deploy, teste:
```bash
curl https://seu-dominio.com/health
```

## 🎯 Checklist de Troubleshooting

- [ ] Repository URL correto
- [ ] Branch `orchestrator-v1` selecionada
- [ ] Dockerfile `Dockerfile.easypanel` especificado
- [ ] Build context é `.` (raiz)
- [ ] Variáveis de ambiente configuradas
- [ ] Rebuild forçado
- [ ] Logs de build verificados

**🚀 Com essas correções, o deploy deve funcionar!**
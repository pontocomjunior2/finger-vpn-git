# Deploy Guide - Enhanced Stream Orchestrator

## 🚀 Deploy no EasyPanel

### Pré-requisitos
- Conta no EasyPanel
- Repositório Git configurado
- Docker disponível para testes locais

### Passos para Deploy

#### 1. Preparação do Código
```bash
# Executar pipeline de CI/CD
./scripts/test-and-format.sh

# Ou no Windows PowerShell
.\scripts\test-and-format.ps1

# Para validação completa
./scripts/test-and-format.sh --full-validation
```

#### 2. Commit e Push
```bash
# Adicionar mudanças
git add .

# Commit com mensagem descritiva
git commit -m "feat: enhanced orchestrator ready for production deploy"

# Push para repositório
git push origin main
```

#### 3. Configuração no EasyPanel

##### Opção A: Usando easypanel.yml (Recomendado)
1. No EasyPanel, criar novo projeto
2. Conectar ao repositório Git
3. O EasyPanel detectará automaticamente o `easypanel.yml`
4. Configurar variáveis de ambiente:
   - `POSTGRES_PASSWORD`: Senha segura para PostgreSQL
   - `SECRET_KEY`: Chave secreta da aplicação
   - `LOG_LEVEL`: INFO (padrão)

##### Opção B: Configuração Manual
1. Criar novo serviço no EasyPanel
2. Usar `Dockerfile.orchestrator.new`
3. Configurar variáveis de ambiente (ver seção abaixo)
4. Configurar volumes e rede

### Variáveis de Ambiente Obrigatórias

```env
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=sua_senha_segura

# Application
ORCHESTRATOR_PORT=8000
SECRET_KEY=sua_chave_secreta_muito_segura

# Performance (opcionais)
IMBALANCE_THRESHOLD=0.2
MAX_STREAM_DIFFERENCE=2
HEARTBEAT_TIMEOUT=300
MAX_RETRY_ATTEMPTS=3
LOG_LEVEL=INFO
```

### Variáveis de Ambiente Opcionais

```env
# Performance Tuning
HEARTBEAT_WARNING_THRESHOLD=120
MAX_MISSED_HEARTBEATS=3
RETRY_DELAY_SECONDS=5
EXPONENTIAL_BACKOFF=true

# Features
RUN_MIGRATIONS=true
RUN_HEALTH_CHECK=true

# Scaling
MAX_WORKERS=1

# Redis (se usar cache externo)
REDIS_HOST=redis
REDIS_PORT=6379
```

## 🧪 Teste Local com Docker

### Desenvolvimento
```bash
# Build da imagem
docker build -f Dockerfile.orchestrator.new -t enhanced-orchestrator .

# Executar com docker-compose
docker-compose -f docker-compose.orchestrator.yml up -d

# Verificar logs
docker-compose -f docker-compose.orchestrator.yml logs -f orchestrator

# Parar serviços
docker-compose -f docker-compose.orchestrator.yml down
```

### Teste de Produção
```bash
# Executar apenas o orchestrator (assumindo banco externo)
docker run -d \
  --name orchestrator-test \
  -p 8000:8000 \
  -e DB_HOST=seu_db_host \
  -e DB_NAME=orchestrator \
  -e DB_USER=orchestrator_user \
  -e DB_PASSWORD=sua_senha \
  -e SECRET_KEY=sua_chave_secreta \
  enhanced-orchestrator

# Verificar saúde
curl http://localhost:8000/health

# Verificar métricas
curl http://localhost:8000/metrics
```

## 📊 Monitoramento

### Endpoints de Saúde
- `GET /health` - Status geral do sistema
- `GET /metrics` - Métricas detalhadas
- `GET /` - Documentação da API (Swagger)

### Logs
- Logs da aplicação: `/app/logs/orchestrator.log`
- Logs do sistema: stdout/stderr do container

### Métricas Prometheus (se habilitado)
- URL: `http://seu-dominio:9090`
- Métricas customizadas do orchestrator disponíveis

## 🔧 Configuração de Produção

### Banco de Dados
- PostgreSQL 15+ recomendado
- Configurar backup automático
- Monitorar performance com `pg_stat_statements`

### Segurança
- Usar HTTPS em produção
- Configurar firewall adequadamente
- Rotacionar `SECRET_KEY` regularmente
- Usar senhas fortes para banco

### Performance
- Ajustar `MAX_WORKERS` baseado na CPU disponível
- Monitorar uso de memória
- Configurar `IMBALANCE_THRESHOLD` baseado na carga

### Scaling
- O orchestrator é stateless (exceto banco)
- Pode ser escalado horizontalmente
- Usar load balancer se múltiplas instâncias

## 🚨 Troubleshooting

### Problemas Comuns

#### Container não inicia
```bash
# Verificar logs
docker logs container_name

# Verificar variáveis de ambiente
docker exec container_name env | grep -E "(DB_|SECRET_)"

# Testar conexão com banco
docker exec container_name python -c "
import psycopg2
conn = psycopg2.connect(
    host='$DB_HOST', 
    database='$DB_NAME', 
    user='$DB_USER', 
    password='$DB_PASSWORD'
)
print('Database connection OK')
"
```

#### Health check falha
```bash
# Verificar se aplicação está rodando
curl -f http://localhost:8000/health

# Verificar logs da aplicação
docker exec container_name tail -f /app/logs/orchestrator.log

# Verificar componentes
docker exec container_name python /app/app/health_check.py
```

#### Performance baixa
- Verificar métricas em `/metrics`
- Ajustar `MAX_WORKERS`
- Verificar conexões com banco
- Monitorar uso de CPU/memória

### Comandos Úteis

```bash
# Reiniciar aplicação
docker restart container_name

# Executar shell no container
docker exec -it container_name /bin/bash

# Verificar processos
docker exec container_name ps aux

# Verificar uso de recursos
docker stats container_name

# Backup do banco
docker exec postgres_container pg_dump -U orchestrator_user orchestrator > backup.sql

# Restaurar banco
docker exec -i postgres_container psql -U orchestrator_user orchestrator < backup.sql
```

## 📈 Monitoramento Avançado

### Grafana Dashboard (se habilitado)
- URL: `http://seu-dominio:3000`
- Login: admin/admin123
- Dashboards pré-configurados para métricas do orchestrator

### Alertas Recomendados
- CPU > 80% por 5 minutos
- Memória > 90% por 5 minutos
- Health check falha por 2 minutos consecutivos
- Banco de dados inacessível
- Número de workers ativos < threshold

### Métricas Importantes
- `orchestrator_active_instances` - Instâncias ativas
- `orchestrator_total_streams` - Total de streams
- `orchestrator_response_time` - Tempo de resposta
- `orchestrator_error_rate` - Taxa de erro
- `orchestrator_heartbeat_failures` - Falhas de heartbeat

## 🔄 Atualizações

### Deploy de Nova Versão
1. Executar pipeline CI/CD
2. Fazer commit e push
3. EasyPanel detectará mudanças automaticamente
4. Deploy será feito com zero downtime (se configurado)

### Rollback
```bash
# No EasyPanel, usar interface para rollback
# Ou manualmente:
git revert HEAD
git push origin main
```

## 📞 Suporte

### Logs para Análise
- Logs da aplicação: `/app/logs/orchestrator.log`
- Logs do sistema: `docker logs container_name`
- Métricas: `curl http://localhost:8000/metrics`

### Informações do Sistema
```bash
# Versão da aplicação
curl http://localhost:8000/health | jq '.system_status'

# Status dos componentes
docker exec container_name python /app/app/validate_task_10_completion.py
```

---

## ✅ Checklist de Deploy

- [ ] Pipeline CI/CD executado com sucesso
- [ ] Todos os testes passaram
- [ ] Código formatado com Black/isort
- [ ] Dockerfile validado
- [ ] Variáveis de ambiente configuradas
- [ ] Banco de dados configurado
- [ ] Health checks funcionando
- [ ] Monitoramento configurado
- [ ] Backup configurado
- [ ] Documentação atualizada

**🎉 Pronto para produção!**
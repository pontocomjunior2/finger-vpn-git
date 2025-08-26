# 🚀 Guia de Deploy EasyPanel - Enhanced Stream Orchestrator

## Problema Identificado e Solução

O erro `"Top-level object must be a mapping"` ocorre quando o EasyPanel tenta usar o Dockerfile como docker-compose. 

### ✅ Solução Implementada

Criamos múltiplos arquivos de configuração para diferentes cenários:

## 📁 Arquivos de Deploy Disponíveis

### 1. `docker-compose.yml` (Recomendado para EasyPanel)
- Stack completa com PostgreSQL, Redis e Orchestrator
- Configuração padrão docker-compose
- Variáveis de ambiente via arquivo .env

### 2. `docker-compose.simple.yml` (Para banco externo)
- Apenas o orchestrator
- Conecta a banco de dados externo
- Mais simples para deploy

### 3. `Dockerfile.orchestrator.new` (Build apenas)
- Para build customizado
- Usar quando EasyPanel suporta Dockerfile direto

## 🔧 Configuração no EasyPanel

### Opção 1: Usando docker-compose.yml (Recomendado)

1. **No EasyPanel, criar novo projeto**
2. **Conectar ao repositório Git**
3. **Selecionar `docker-compose.yml` como arquivo principal**
4. **Configurar variáveis de ambiente:**

```env
# OBRIGATÓRIAS
DB_PASSWORD=sua_senha_muito_segura
SECRET_KEY=sua_chave_secreta_de_32_caracteres_ou_mais

# OPCIONAIS
LOG_LEVEL=INFO
MAX_WORKERS=1
IMBALANCE_THRESHOLD=0.2
MAX_STREAM_DIFFERENCE=2
```

### Opção 2: Usando docker-compose.simple.yml (Banco Externo)

1. **Criar banco PostgreSQL separado no EasyPanel**
2. **Usar `docker-compose.simple.yml`**
3. **Configurar variáveis apontando para banco externo:**

```env
# Banco Externo
DB_HOST=seu-postgres-host
DB_PORT=5432
DB_NAME=orchestrator
DB_USER=orchestrator_user
DB_PASSWORD=senha_do_banco

# Aplicação
SECRET_KEY=sua_chave_secreta
LOG_LEVEL=INFO
```

### Opção 3: Build Customizado

1. **Usar apenas `Dockerfile.orchestrator.new`**
2. **Configurar serviços externos (PostgreSQL, Redis)**
3. **Configurar todas as variáveis de ambiente**

## 🚀 Passos Detalhados para Deploy

### 1. Preparar Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

```bash
cp .env.example .env
# Edite .env com suas configurações
```

### 2. No EasyPanel

1. **Criar Novo Projeto**
   - Nome: `enhanced-orchestrator`
   - Conectar ao repositório Git

2. **Configurar Build**
   - Arquivo: `docker-compose.yml`
   - Branch: `orchestrator-v1`

3. **Variáveis de Ambiente**
   ```
   DB_PASSWORD=SuaSenhaMuitoSegura123!
   SECRET_KEY=sua-chave-secreta-de-pelo-menos-32-caracteres-aqui
   LOG_LEVEL=INFO
   MAX_WORKERS=1
   ```

4. **Deploy**
   - Clique em "Deploy"
   - Aguarde build e inicialização

### 3. Verificação Pós-Deploy

```bash
# Verificar saúde
curl https://seu-dominio.easypanel.app/health

# Verificar métricas
curl https://seu-dominio.easypanel.app/metrics

# Verificar API docs
curl https://seu-dominio.easypanel.app/
```

## 🔍 Troubleshooting

### Erro: "Top-level object must be a mapping"
**Solução**: Use `docker-compose.yml` em vez de `Dockerfile.orchestrator.new`

### Erro: Database connection failed
**Solução**: Verifique variáveis de ambiente do banco:
```env
DB_HOST=postgres  # Nome do serviço no docker-compose
DB_PASSWORD=sua_senha_correta
```

### Erro: Health check failed
**Solução**: 
1. Verifique logs do container
2. Confirme que `SECRET_KEY` está configurado
3. Aguarde inicialização completa (pode levar 1-2 minutos)

### Container não inicia
**Solução**:
1. Verifique todas as variáveis obrigatórias
2. Confirme que `DB_PASSWORD` e `SECRET_KEY` estão definidos
3. Verifique logs para erros específicos

## 📊 Monitoramento

### Endpoints Disponíveis
- **Health Check**: `/health`
- **Métricas**: `/metrics`
- **API Docs**: `/` (Swagger UI)
- **Prometheus**: `:9090` (se habilitado)

### Logs
- Container logs no EasyPanel
- Logs da aplicação em `/app/logs/orchestrator.log`

## 🔐 Segurança

### Variáveis Sensíveis
```env
# Use senhas fortes
DB_PASSWORD=senha_muito_segura_com_simbolos_123!

# Chave secreta longa
SECRET_KEY=chave-secreta-aleatoria-de-pelo-menos-32-caracteres-para-seguranca
```

### Recomendações
- Use HTTPS em produção
- Configure firewall adequadamente
- Monitore logs regularmente
- Faça backup do banco regularmente

## 📈 Scaling

### Horizontal Scaling
- O orchestrator é stateless (exceto banco)
- Pode ser escalado horizontalmente
- Use load balancer se múltiplas instâncias

### Vertical Scaling
```env
# Ajustar conforme recursos disponíveis
MAX_WORKERS=2  # Para mais CPU cores
```

## 🆘 Suporte

### Logs para Análise
1. **Logs do EasyPanel**: Interface web
2. **Logs da aplicação**: `/app/logs/orchestrator.log`
3. **Health status**: `GET /health`
4. **Métricas**: `GET /metrics`

### Comandos Úteis
```bash
# Verificar status
curl /health

# Reiniciar via EasyPanel
# Use interface web para restart

# Verificar métricas
curl /metrics | grep orchestrator
```

---

## ✅ Checklist de Deploy

- [ ] Repositório conectado no EasyPanel
- [ ] Arquivo `docker-compose.yml` selecionado
- [ ] Variável `DB_PASSWORD` configurada
- [ ] Variável `SECRET_KEY` configurada
- [ ] Deploy realizado com sucesso
- [ ] Health check `/health` retorna OK
- [ ] Métricas `/metrics` acessíveis
- [ ] Logs sem erros críticos

**🎉 Sistema pronto para produção!**
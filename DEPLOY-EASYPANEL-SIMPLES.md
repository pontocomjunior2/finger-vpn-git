# 🚀 Deploy no EasyPanel - Passo a Passo SIMPLES

## 📋 RESUMO RÁPIDO

**Use: `Dockerfile.simple`** ← Este é o recomendado!

## 🎯 PASSO A PASSO

### 1. **No EasyPanel - Criar Aplicação**

1. Faça login no EasyPanel
2. Clique em **"New Service"** ou **"Add Application"**
3. Escolha **"Docker"**

### 2. **Configurar Repositório**

```
Repository URL: https://github.com/pontocomjunior2/finger-vpn-git.git
Branch: orchestrator-v1
```

### 3. **Configurar Build**

```
Dockerfile: Dockerfile.simple
Build Context: .
Port: 8000
```

### 4. **Configurar Variáveis de Ambiente**

**COPIE E COLE EXATAMENTE ISTO:**

```env
# Banco PostgreSQL Externo (Tabela de Streams)
POSTGRES_HOST=104.234.173.96
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Conquista@@2
POSTGRES_DB=music_log
POSTGRES_PORT=5432
DB_TABLE_NAME=streams

# Banco Local do Orchestrator (Interno)
DB_PASSWORD=MinhaSenh@Segura123!
SECRET_KEY=minha_chave_secreta_muito_longa_32_caracteres_ou_mais
DB_HOST=localhost
DB_NAME=orchestrator
DB_USER=orchestrator_user
REDIS_HOST=localhost
REDIS_PORT=6379
ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8000
LOG_LEVEL=INFO
```

**⚠️ IMPORTANTE:** 
- As configurações `POSTGRES_*` são para a tabela de streams externa
- As configurações `DB_*` são para o banco interno do orchestrator
- Altere `DB_PASSWORD` e `SECRET_KEY` para valores únicos!

### 5. **Configurar Domínio**

- Adicione seu domínio personalizado
- Ou use o domínio fornecido pelo EasyPanel

### 6. **Deploy**

1. Clique em **"Deploy"** ou **"Create"**
2. Aguarde o build (pode levar 5-10 minutos)
3. Monitore os logs

## ✅ VERIFICAÇÃO

### Teste o Health Check:
```bash
curl https://seu-dominio.com/health
```

### Resposta Esperada:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-XX..."
}
```

## 🚨 SE DER PROBLEMA

### 1. **Build Failed**
- Verifique se está usando `Dockerfile.simple`
- Verifique se o branch é `orchestrator-v1`

### 2. **App não inicia**
- Verifique se as variáveis de ambiente estão configuradas
- Especialmente `SECRET_KEY` (deve ter 32+ caracteres)

### 3. **Health check falha**
- Aguarde 2-3 minutos para inicialização completa
- Verifique logs no painel do EasyPanel

## 📊 CONFIGURAÇÃO FINAL

```
✅ Repository: https://github.com/pontocomjunior2/finger-vpn-git.git
✅ Branch: orchestrator-v1  
✅ Dockerfile: Dockerfile.simple
✅ Port: 8000
✅ Variáveis: Configuradas conforme acima
```

## 🎉 PRONTO!

Após o deploy, sua aplicação estará disponível em:
- **Dashboard**: https://seu-dominio.com/
- **Health**: https://seu-dominio.com/health
- **API**: https://seu-dominio.com/api/status

**🚀 É só isso! Simples e direto.**
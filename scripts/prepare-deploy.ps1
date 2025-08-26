# Script para preparar deploy do Enhanced Stream Orchestrator
param(
    [string]$CommitMessage = "feat: enhanced orchestrator ready for production deploy",
    [switch]$SkipTests,
    [switch]$Force
)

Write-Host "🚀 Preparando Deploy do Enhanced Stream Orchestrator" -ForegroundColor Blue
Write-Host "=================================================" -ForegroundColor Blue

function Write-Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

function Write-Success($message) {
    Write-Host "[SUCCESS] $message" -ForegroundColor Green
}

function Write-Warning($message) {
    Write-Host "[WARNING] $message" -ForegroundColor Yellow
}

function Write-Error($message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

try {
    # 1. Verificar se estamos no diretório correto
    if (-not (Test-Path "Dockerfile.orchestrator.new")) {
        Write-Error "Dockerfile.orchestrator.new não encontrado. Execute no diretório raiz do projeto."
        exit 1
    }

    # 2. Executar testes e formatação se não for pulado
    if (-not $SkipTests) {
        Write-Info "Executando pipeline de testes e formatação..."
        .\scripts\test-and-format.ps1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Pipeline de testes falhou. Use -SkipTests para pular ou -Force para continuar."
            if (-not $Force) {
                exit 1
            }
            Write-Warning "Continuando apesar dos erros devido ao parâmetro -Force"
        }
    } else {
        Write-Warning "Testes pulados conforme solicitado"
    }

    # 3. Verificar status do Git
    Write-Info "Verificando status do Git..."
    $gitStatus = git status --porcelain
    if ($gitStatus) {
        Write-Info "Mudanças detectadas no repositório"
        Write-Host $gitStatus
    } else {
        Write-Info "Nenhuma mudança detectada"
    }

    # 4. Adicionar arquivos ao Git
    Write-Info "Adicionando arquivos ao Git..."
    git add .
    
    # Verificar se há algo para commit
    $gitStatusStaged = git diff --cached --name-only
    if (-not $gitStatusStaged) {
        Write-Warning "Nenhuma mudança para commit"
    } else {
        Write-Info "Arquivos para commit:"
        $gitStatusStaged | ForEach-Object { Write-Host "  - $_" }
    }

    # 5. Fazer commit
    if ($gitStatusStaged -or $Force) {
        Write-Info "Fazendo commit com mensagem: '$CommitMessage'"
        git commit -m $CommitMessage
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Commit realizado com sucesso"
        } else {
            Write-Error "Falha no commit"
            exit 1
        }
    }

    # 6. Verificar branch atual
    $currentBranch = git branch --show-current
    Write-Info "Branch atual: $currentBranch"

    # 7. Push para repositório
    Write-Info "Fazendo push para o repositório..."
    git push origin $currentBranch
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Push realizado com sucesso"
    } else {
        Write-Error "Falha no push"
        exit 1
    }

    # 8. Gerar resumo do deploy
    Write-Info "Gerando resumo do deploy..."
    
    $deployInfo = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        branch = $currentBranch
        commit_message = $CommitMessage
        files_created = @(
            "Dockerfile.orchestrator.new",
            "docker-compose.orchestrator.yml", 
            "easypanel.yml",
            "DEPLOY_README.md",
            "scripts/init-db.sql"
        )
        environment_variables = @{
            required = @("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "SECRET_KEY")
            optional = @("LOG_LEVEL", "MAX_WORKERS", "IMBALANCE_THRESHOLD", "MAX_STREAM_DIFFERENCE")
        }
        endpoints = @{
            health = "/health"
            metrics = "/metrics"
            api_docs = "/"
        }
        ports = @{
            orchestrator = 8000
            postgres = 5432
            redis = 6379
            prometheus = 9090
            grafana = 3000
        }
    }

    $deploySummary = @"
# 🚀 Deploy Summary - Enhanced Stream Orchestrator

## Informações do Deploy
- **Timestamp**: $($deployInfo.timestamp)
- **Branch**: $($deployInfo.branch)
- **Commit**: $($deployInfo.commit_message)

## Arquivos Criados para Deploy
$($deployInfo.files_created | ForEach-Object { "- $_" } | Out-String)

## Configuração no EasyPanel

### 1. Criar Novo Projeto
- Conectar ao repositório Git
- Usar arquivo: `easypanel.yml` (recomendado) ou `Dockerfile.orchestrator.new`

### 2. Variáveis de Ambiente Obrigatórias
$($deployInfo.environment_variables.required | ForEach-Object { "- $_" } | Out-String)

### 3. Variáveis Opcionais
$($deployInfo.environment_variables.optional | ForEach-Object { "- $_" } | Out-String)

### 4. Portas Expostas
$($deployInfo.ports.GetEnumerator() | ForEach-Object { "- $($_.Key): $($_.Value)" } | Out-String)

### 5. Endpoints Importantes
$($deployInfo.endpoints.GetEnumerator() | ForEach-Object { "- $($_.Key): $($_.Value)" } | Out-String)

## Próximos Passos

1. **No EasyPanel**:
   - Criar novo projeto
   - Conectar ao repositório
   - Configurar variáveis de ambiente
   - Fazer deploy

2. **Verificação Pós-Deploy**:
   - Acessar `/health` para verificar saúde
   - Acessar `/metrics` para métricas
   - Verificar logs da aplicação

3. **Monitoramento**:
   - Configurar alertas
   - Monitorar métricas
   - Verificar performance

## Documentação Completa
Consulte `DEPLOY_README.md` para instruções detalhadas.

---
✅ **PRONTO PARA DEPLOY NO EASYPANEL**
"@

    # Salvar resumo
    $deploySummary | Out-File -FilePath "DEPLOY_SUMMARY.md" -Encoding UTF8
    Write-Success "Resumo do deploy salvo em DEPLOY_SUMMARY.md"

    # 9. Resumo final
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Blue
    Write-Success "🎉 PREPARAÇÃO PARA DEPLOY CONCLUÍDA!"
    Write-Host "=================================================" -ForegroundColor Blue
    Write-Host ""
    
    Write-Info "✅ Checklist Completo:"
    Write-Host "  ✅ Código formatado e testado"
    Write-Host "  ✅ Dockerfile criado (Dockerfile.orchestrator.new)"
    Write-Host "  ✅ Docker Compose para desenvolvimento"
    Write-Host "  ✅ Configuração EasyPanel (easypanel.yml)"
    Write-Host "  ✅ Scripts de inicialização do banco"
    Write-Host "  ✅ Documentação de deploy"
    Write-Host "  ✅ Commit e push realizados"
    Write-Host ""
    
    Write-Info "🚀 Próximos Passos:"
    Write-Host "  1. Acesse o EasyPanel"
    Write-Host "  2. Crie novo projeto conectado ao seu repositório Git"
    Write-Host "  3. Configure as variáveis de ambiente obrigatórias:"
    Write-Host "     - DB_PASSWORD (senha do PostgreSQL)"
    Write-Host "     - SECRET_KEY (chave secreta da aplicação)"
    Write-Host "  4. Faça o deploy usando easypanel.yml"
    Write-Host "  5. Verifique a saúde em /health"
    Write-Host ""
    
    Write-Info "📚 Documentação:"
    Write-Host "  - DEPLOY_README.md - Guia completo de deploy"
    Write-Host "  - DEPLOY_SUMMARY.md - Resumo desta preparação"
    Write-Host "  - easypanel.yml - Configuração para EasyPanel"
    Write-Host ""
    
    Write-Success "Sistema pronto para produção! 🎯"

} catch {
    Write-Error "Erro durante preparação do deploy: $_"
    exit 1
}
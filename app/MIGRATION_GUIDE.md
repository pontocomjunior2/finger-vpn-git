# Guia de Migração para Arquitetura com Orquestrador Central

Este guia descreve como migrar gradualmente as instâncias do sistema de identificação de música de uma arquitetura baseada em consistent hashing para uma arquitetura centralizada com orquestrador.

## 📋 Pré-requisitos

### 1. Infraestrutura
- PostgreSQL configurado e acessível
- Servidor dedicado para o orquestrador
- Rede estável entre instâncias e orquestrador

### 2. Dependências
```bash
pip install -r requirements_orchestrator.txt
```

### 3. Configuração do Banco de Dados
```bash
python setup_orchestrator.py
```

## 🚀 Processo de Migração

### Fase 1: Preparação (Tempo estimado: 30 minutos)

#### 1.1 Configurar o Orquestrador
```bash
# 1. Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com configurações do orquestrador

# 2. Inicializar banco de dados
python setup_orchestrator.py

# 3. Iniciar orquestrador
python orchestrator.py
```

#### 1.2 Validar Funcionamento
```bash
# Testar saúde do orquestrador
curl http://localhost:8001/health

# Executar testes de migração
python test_migration.py
```

### Fase 2: Migração Gradual (Tempo estimado: 2-4 horas)

#### 2.1 Migração da Primeira Instância

1. **Escolher instância piloto** (preferencialmente com menor carga)

2. **Configurar variáveis de ambiente:**
```bash
# Na instância piloto
export USE_ORCHESTRATOR=true
export ORCHESTRATOR_URL=http://orchestrator-server:8001
```

3. **Reiniciar a instância:**
```bash
# Parar instância atual
pkill -f fingerv7.py

# Iniciar com nova configuração
python fingerv7.py
```

4. **Monitorar logs:**
```bash
tail -f logs/fingerv7.log | grep -i orchestrator
```

5. **Validar funcionamento:**
- Verificar registro no orquestrador
- Confirmar recebimento de streams
- Monitorar identificações

#### 2.2 Migração Incremental

**Aguardar 30 minutos** entre cada migração para validar estabilidade.

**Para cada instância subsequente:**

1. **Verificar saúde do sistema:**
```bash
curl http://orchestrator-server:8001/status
```

2. **Migrar próxima instância:**
```bash
# Configurar e reiniciar
export USE_ORCHESTRATOR=true
export ORCHESTRATOR_URL=http://orchestrator-server:8001
pkill -f fingerv7.py
python fingerv7.py
```

3. **Monitorar distribuição:**
- Verificar balanceamento de carga
- Confirmar que não há streams órfãos
- Validar heartbeats

#### 2.3 Cronograma Sugerido

| Tempo | Ação | Instâncias Migradas |
|-------|------|--------------------|
| T+0   | Migrar instância piloto | 1 |
| T+30min | Migrar 2ª instância | 2 |
| T+1h  | Migrar 3ª e 4ª instâncias | 4 |
| T+1h30min | Migrar 5ª e 6ª instâncias | 6 |
| T+2h  | Migrar instâncias restantes | Todas |

### Fase 3: Validação Final (Tempo estimado: 1 hora)

#### 3.1 Testes de Funcionalidade
```bash
# Executar suite completa de testes
python test_migration.py

# Verificar métricas de performance
curl http://orchestrator-server:8001/metrics
```

#### 3.2 Teste de Failover
1. **Simular falha de instância:**
```bash
# Parar uma instância temporariamente
pkill -f fingerv7.py  # em uma instância específica
```

2. **Verificar reatribuição automática:**
```bash
# Monitorar logs do orquestrador
tail -f logs/orchestrator.log | grep -i failover
```

3. **Restaurar instância:**
```bash
python fingerv7.py
```

#### 3.3 Monitoramento Contínuo
- Verificar logs de erro
- Monitorar latência de identificação
- Validar distribuição equilibrada
- Confirmar heartbeats regulares

## 🔧 Configurações Importantes

### Variáveis de Ambiente

#### Para Instâncias (fingerv7.py)
```bash
# Habilitar orquestrador
USE_ORCHESTRATOR=true

# URL do orquestrador
ORCHESTRATOR_URL=http://orchestrator-server:8001

# Manter configurações existentes
SERVER_ID=hostname  # Será usado automaticamente
DISTRIBUTE_LOAD=true
```

#### Para Orquestrador
```bash
# Porta do orquestrador
ORCHESTRATOR_PORT=8001
ORCHESTRATOR_HOST=0.0.0.0

# Configurações de timeout
HEARTBEAT_TIMEOUT=120  # segundos
REBALANCE_INTERVAL=300  # segundos

# Banco de dados
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fingerprint_db
DB_USER=postgres
DB_PASSWORD=sua_senha
```

## 🚨 Plano de Rollback

### Rollback Rápido (< 5 minutos)

Se houver problemas críticos:

1. **Desabilitar orquestrador em todas as instâncias:**
```bash
# Em cada servidor
export USE_ORCHESTRATOR=false
pkill -f fingerv7.py
python fingerv7.py
```

2. **Verificar funcionamento legado:**
```bash
# Confirmar que consistent hashing está funcionando
tail -f logs/fingerv7.log | grep -i "stream assignment"
```

### Rollback Gradual (30-60 minutos)

Para problemas menos críticos:

1. **Migrar instâncias de volta uma por vez**
2. **Manter orquestrador funcionando para instâncias que estão estáveis**
3. **Investigar e corrigir problemas específicos**

## 📊 Monitoramento e Métricas

### Métricas Importantes

1. **Saúde do Orquestrador:**
   - Tempo de resposta da API
   - Número de instâncias ativas
   - Frequência de failovers

2. **Distribuição de Streams:**
   - Balanceamento de carga
   - Streams órfãos
   - Tempo de reatribuição

3. **Performance das Instâncias:**
   - Latência de identificação
   - Taxa de sucesso
   - Uso de recursos

### Comandos de Monitoramento

```bash
# Status geral do orquestrador
curl http://orchestrator-server:8001/status

# Métricas detalhadas
curl http://orchestrator-server:8001/metrics

# Logs em tempo real
tail -f logs/orchestrator.log
tail -f logs/fingerv7.log

# Verificar conexões de banco
psql -h localhost -U postgres -d fingerprint_db -c "SELECT * FROM orchestrator_instances;"
```

## ⚠️ Problemas Comuns e Soluções

### 1. Instância não consegue se registrar
**Sintomas:** Logs mostram erro de conexão com orquestrador

**Soluções:**
- Verificar conectividade de rede
- Confirmar URL do orquestrador
- Verificar se orquestrador está rodando

### 2. Streams não são distribuídos
**Sintomas:** Instâncias registradas mas sem streams atribuídos

**Soluções:**
- Verificar se `DISTRIBUTE_LOAD=true`
- Confirmar que streams estão disponíveis
- Reiniciar processo de distribuição

### 3. Failover não funciona
**Sintomas:** Streams órfãos não são reatribuídos

**Soluções:**
- Verificar logs do orquestrador
- Confirmar configurações de timeout
- Reiniciar tarefa de failover

### 4. Performance degradada
**Sintomas:** Identificações mais lentas após migração

**Soluções:**
- Verificar latência de rede
- Otimizar configurações de heartbeat
- Considerar cache local

## 📞 Suporte e Contatos

- **Logs importantes:** `/logs/orchestrator.log`, `/logs/fingerv7.log`
- **Configurações:** `.env`, `config/`
- **Banco de dados:** Tabelas `orchestrator_*`
- **Monitoramento:** `http://orchestrator-server:8001/status`

## ✅ Checklist de Migração

### Pré-migração
- [ ] Orquestrador instalado e configurado
- [ ] Banco de dados inicializado
- [ ] Testes de migração executados com sucesso
- [ ] Plano de rollback definido
- [ ] Equipe notificada

### Durante a migração
- [ ] Instância piloto migrada e validada
- [ ] Migração incremental executada
- [ ] Monitoramento contínuo ativo
- [ ] Logs sendo acompanhados

### Pós-migração
- [ ] Todas as instâncias migradas
- [ ] Testes de failover executados
- [ ] Performance validada
- [ ] Documentação atualizada
- [ ] Equipe treinada no novo sistema

---

**Nota:** Este guia deve ser seguido cuidadosamente. Em caso de dúvidas ou problemas, consulte os logs e execute os testes de validação antes de prosseguir.
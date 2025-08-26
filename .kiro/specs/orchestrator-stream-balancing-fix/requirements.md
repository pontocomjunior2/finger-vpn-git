# Requirements Document

## Introduction

O sistema de fingerprinting de música possui um orquestrador central que deve distribuir streams entre múltiplas instâncias de workers (fingerv7.py). Atualmente, o sistema apresenta problemas críticos de balanceamento, travamentos de tabela e falhas na comunicação entre orquestrador e workers. Esta especificação visa corrigir esses problemas para garantir operação estável e eficiente.

## Requirements

### Requirement 1

**User Story:** Como administrador do sistema, quero que o orquestrador distribua streams de forma equilibrada entre todas as instâncias ativas, para que nenhuma instância fique sobrecarregada ou ociosa.

#### Acceptance Criteria

1. WHEN uma nova instância se registra THEN o orquestrador SHALL redistribuir streams automaticamente para balancear a carga
2. WHEN uma instância se desconecta THEN o orquestrador SHALL reatribuir seus streams para outras instâncias ativas dentro de 60 segundos
3. WHEN há diferença de mais de 20% na carga entre instâncias THEN o orquestrador SHALL executar rebalanceamento automático
4. WHEN o sistema está em operação normal THEN cada instância SHALL ter uma diferença máxima de 2 streams em relação à média

### Requirement 2

**User Story:** Como desenvolvedor, quero que o sistema previna travamentos de tabela e deadlocks, para que as operações de banco de dados sejam sempre responsivas.

#### Acceptance Criteria

1. WHEN múltiplas instâncias acessam tabelas simultaneamente THEN o sistema SHALL usar timeouts apropriados para evitar deadlocks
2. WHEN uma transação excede 30 segundos THEN o sistema SHALL cancelar automaticamente a operação
3. WHEN há contenção de locks THEN o sistema SHALL implementar retry com backoff exponencial
4. WHEN operações de banco falham THEN o sistema SHALL registrar logs detalhados para diagnóstico

### Requirement 3

**User Story:** Como administrador, quero que o sistema detecte e corrija inconsistências automaticamente, para que o estado entre orquestrador e workers permaneça sincronizado.

#### Acceptance Criteria

1. WHEN há inconsistência entre estado local e orquestrador THEN o worker SHALL tentar auto-recuperação em até 3 tentativas
2. WHEN auto-recuperação falha THEN o worker SHALL forçar re-registro no orquestrador
3. WHEN um stream está atribuído a múltiplas instâncias THEN o orquestrador SHALL resolver o conflito mantendo apenas uma atribuição
4. WHEN uma instância reporta streams que não estão no orquestrador THEN o sistema SHALL sincronizar automaticamente

### Requirement 4

**User Story:** Como operador do sistema, quero monitoramento proativo de falhas e alertas, para que problemas sejam identificados antes de afetar a operação.

#### Acceptance Criteria

1. WHEN uma instância não envia heartbeat por mais de 5 minutos THEN o orquestrador SHALL marcar como inativa e redistribuir streams
2. WHEN há mais de 5 falhas consecutivas de comunicação THEN o sistema SHALL gerar alerta crítico
3. WHEN a taxa de falhas excede 10 por minuto THEN o sistema SHALL ativar modo de recuperação
4. WHEN há padrões de erro recorrentes THEN o sistema SHALL registrar para análise posterior

### Requirement 5

**User Story:** Como administrador, quero que o sistema seja resiliente a falhas de rede e banco de dados, para que continue operando mesmo com problemas temporários.

#### Acceptance Criteria

1. WHEN há falha de conexão com banco THEN o sistema SHALL tentar reconectar com backoff exponencial até 3 vezes
2. WHEN o orquestrador está inacessível THEN workers SHALL continuar processando streams já atribuídos
3. WHEN há timeout de rede THEN o sistema SHALL usar timeouts configuráveis (30s padrão)
4. WHEN conexões são perdidas THEN o sistema SHALL implementar circuit breaker para evitar cascata de falhas

### Requirement 6

**User Story:** Como desenvolvedor, quero APIs de diagnóstico e status detalhado, para que problemas possam ser identificados e corrigidos rapidamente.

#### Acceptance Criteria

1. WHEN solicitado diagnóstico THEN o sistema SHALL retornar estado completo de instâncias e atribuições
2. WHEN há inconsistências THEN o sistema SHALL fornecer recomendações específicas de correção
3. WHEN executando verificação de saúde THEN o sistema SHALL testar conectividade e integridade de dados
4. WHEN há problemas de performance THEN o sistema SHALL expor métricas detalhadas de timing e throughput
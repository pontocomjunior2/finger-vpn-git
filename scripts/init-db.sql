-- Inicialização do banco de dados para Enhanced Stream Orchestrator
-- Este script é executado automaticamente na criação do container PostgreSQL

-- Criar extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Criar schema principal
CREATE SCHEMA IF NOT EXISTS orchestrator;

-- Tabela de instâncias worker
CREATE TABLE IF NOT EXISTS orchestrator.worker_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    server_id VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET NOT NULL,
    port INTEGER NOT NULL,
    max_streams INTEGER NOT NULL DEFAULT 0,
    current_streams INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_port CHECK (port > 0 AND port <= 65535),
    CONSTRAINT valid_streams CHECK (current_streams >= 0 AND current_streams <= max_streams)
);

-- Tabela de streams
CREATE TABLE IF NOT EXISTS orchestrator.streams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stream_id INTEGER UNIQUE NOT NULL,
    worker_instance_id UUID REFERENCES orchestrator.worker_instances(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabela de heartbeats
CREATE TABLE IF NOT EXISTS orchestrator.heartbeats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_instance_id UUID REFERENCES orchestrator.worker_instances(id) ON DELETE CASCADE,
    heartbeat_data JSONB,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Índice para consultas por worker e tempo
    INDEX idx_heartbeats_worker_time (worker_instance_id, received_at DESC)
);

-- Tabela de eventos do sistema
CREATE TABLE IF NOT EXISTS orchestrator.system_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    source VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Índice para consultas por tipo e tempo
    INDEX idx_events_type_time (event_type, created_at DESC),
    INDEX idx_events_severity_time (severity, created_at DESC)
);

-- Tabela de métricas de performance
CREATE TABLE IF NOT EXISTS orchestrator.performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC NOT NULL,
    metric_type VARCHAR(50) NOT NULL DEFAULT 'gauge',
    tags JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Índice para consultas por métrica e tempo
    INDEX idx_metrics_name_time (metric_name, recorded_at DESC)
);

-- Tabela de configurações
CREATE TABLE IF NOT EXISTS orchestrator.configurations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Inserir configurações padrão
INSERT INTO orchestrator.configurations (config_key, config_value, description) VALUES
    ('load_balance_threshold', '0.2', 'Threshold para detecção de desbalanceamento de carga'),
    ('max_stream_difference', '2', 'Diferença máxima de streams entre instâncias'),
    ('heartbeat_timeout', '300', 'Timeout para heartbeat em segundos'),
    ('max_retry_attempts', '3', 'Número máximo de tentativas de retry'),
    ('retry_delay_seconds', '5', 'Delay entre tentativas de retry em segundos')
ON CONFLICT (config_key) DO NOTHING;

-- Função para atualizar timestamp automaticamente
CREATE OR REPLACE FUNCTION orchestrator.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para atualizar updated_at automaticamente
CREATE TRIGGER update_worker_instances_updated_at 
    BEFORE UPDATE ON orchestrator.worker_instances 
    FOR EACH ROW EXECUTE FUNCTION orchestrator.update_updated_at_column();

CREATE TRIGGER update_streams_updated_at 
    BEFORE UPDATE ON orchestrator.streams 
    FOR EACH ROW EXECUTE FUNCTION orchestrator.update_updated_at_column();

CREATE TRIGGER update_configurations_updated_at 
    BEFORE UPDATE ON orchestrator.configurations 
    FOR EACH ROW EXECUTE FUNCTION orchestrator.update_updated_at_column();

-- Função para limpeza automática de dados antigos
CREATE OR REPLACE FUNCTION orchestrator.cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Limpar heartbeats mais antigos que 7 dias
    DELETE FROM orchestrator.heartbeats 
    WHERE received_at < NOW() - INTERVAL '7 days';
    
    -- Limpar eventos mais antigos que 30 dias
    DELETE FROM orchestrator.system_events 
    WHERE created_at < NOW() - INTERVAL '30 days';
    
    -- Limpar métricas mais antigas que 30 dias
    DELETE FROM orchestrator.performance_metrics 
    WHERE recorded_at < NOW() - INTERVAL '30 days';
    
    -- Log da limpeza
    INSERT INTO orchestrator.system_events (event_type, event_data, severity, source)
    VALUES ('data_cleanup', '{"action": "cleanup_completed"}', 'info', 'database');
END;
$$ LANGUAGE plpgsql;

-- Criar usuário para a aplicação (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'orchestrator_app') THEN
        CREATE ROLE orchestrator_app WITH LOGIN PASSWORD 'app_password';
    END IF;
END
$$;

-- Conceder permissões para o usuário da aplicação
GRANT USAGE ON SCHEMA orchestrator TO orchestrator_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA orchestrator TO orchestrator_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA orchestrator TO orchestrator_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA orchestrator TO orchestrator_app;

-- Configurar permissões padrão para objetos futuros
ALTER DEFAULT PRIVILEGES IN SCHEMA orchestrator 
    GRANT ALL PRIVILEGES ON TABLES TO orchestrator_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA orchestrator 
    GRANT ALL PRIVILEGES ON SEQUENCES TO orchestrator_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA orchestrator 
    GRANT EXECUTE ON FUNCTIONS TO orchestrator_app;

-- Criar índices para performance
CREATE INDEX IF NOT EXISTS idx_worker_instances_status ON orchestrator.worker_instances(status);
CREATE INDEX IF NOT EXISTS idx_worker_instances_last_heartbeat ON orchestrator.worker_instances(last_heartbeat DESC);
CREATE INDEX IF NOT EXISTS idx_streams_status ON orchestrator.streams(status);
CREATE INDEX IF NOT EXISTS idx_streams_worker ON orchestrator.streams(worker_instance_id);

-- View para estatísticas do sistema
CREATE OR REPLACE VIEW orchestrator.system_stats AS
SELECT 
    (SELECT COUNT(*) FROM orchestrator.worker_instances WHERE status = 'active') as active_workers,
    (SELECT COUNT(*) FROM orchestrator.worker_instances) as total_workers,
    (SELECT COUNT(*) FROM orchestrator.streams WHERE status = 'active') as active_streams,
    (SELECT COUNT(*) FROM orchestrator.streams) as total_streams,
    (SELECT AVG(current_streams) FROM orchestrator.worker_instances WHERE status = 'active') as avg_streams_per_worker,
    (SELECT MAX(current_streams) FROM orchestrator.worker_instances WHERE status = 'active') as max_streams_per_worker,
    (SELECT MIN(current_streams) FROM orchestrator.worker_instances WHERE status = 'active') as min_streams_per_worker;

-- View para workers com problemas de heartbeat
CREATE OR REPLACE VIEW orchestrator.unhealthy_workers AS
SELECT 
    server_id,
    ip_address,
    port,
    status,
    last_heartbeat,
    EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_since_heartbeat
FROM orchestrator.worker_instances
WHERE 
    status = 'active' 
    AND last_heartbeat < NOW() - INTERVAL '5 minutes';

-- Inserir evento de inicialização
INSERT INTO orchestrator.system_events (event_type, event_data, severity, source)
VALUES ('database_initialized', '{"version": "1.0.0", "timestamp": "' || NOW() || '"}', 'info', 'database');

-- Log de sucesso
\echo 'Database initialization completed successfully!'
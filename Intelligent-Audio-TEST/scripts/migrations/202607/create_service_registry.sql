-- 服务注册表（DB 版，作为 Redis 注册中心的持久化备份）
CREATE TABLE IF NOT EXISTS service_registry (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    grpc_port INTEGER,
    status VARCHAR(20) DEFAULT 'offline',
    capabilities JSONB,
    metadata JSONB,
    running_tasks INTEGER DEFAULT 0,
    cpu_load FLOAT DEFAULT 0.0,
    last_dispatch_at TIMESTAMP,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_registry_type ON service_registry(type);
CREATE INDEX IF NOT EXISTS idx_service_registry_status ON service_registry(status);

-- 日志表添加 service_name 字段（如果不存在）
ALTER TABLE logs ADD COLUMN IF NOT EXISTS service_name VARCHAR(50) NOT NULL DEFAULT 'backend';
CREATE INDEX IF NOT EXISTS idx_logs_service_name ON logs(service_name);

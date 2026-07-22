CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    asr_ref TEXT,
    asr_hyp TEXT,
    task_type TEXT DEFAULT 'wer',
    source_lang TEXT,
    target_lang TEXT,
    translate_direct TEXT,
    task_params TEXT,
    status TEXT DEFAULT 'pending',
    result TEXT,
    error_msg TEXT,
    endpoints TEXT,
    endpoint_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    name TEXT,
    capabilities TEXT, -- JSON格式，存储每种任务类型的最大并发数
    task_types TEXT, -- JSON格式，兼容旧的任务类型列表
    max_process INTEGER DEFAULT 1, -- 兼容旧的全局最大并发数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_endpoints_url ON endpoints(url);

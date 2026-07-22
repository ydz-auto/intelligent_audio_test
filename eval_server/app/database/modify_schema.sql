-- 修改tasks表，移除source_lang、target_lang和translate_direct的非空约束
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- 创建临时表
CREATE TABLE IF NOT EXISTS tasks_temp (
    task_id TEXT PRIMARY KEY,
    asr_ref TEXT NOT NULL,
    asr_hyp TEXT NOT NULL,
    task_type TEXT DEFAULT 'wer',
    source_lang TEXT,
    target_lang TEXT,
    translate_direct TEXT,
    status TEXT DEFAULT 'pending',
    result TEXT,
    error_msg TEXT,
    endpoints TEXT,
    endpoint_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 复制数据到临时表
INSERT INTO tasks_temp SELECT * FROM tasks;

-- 删除原表
DROP TABLE tasks;

-- 重命名临时表为原表
ALTER TABLE tasks_temp RENAME TO tasks;

-- 重新创建索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

COMMIT;
PRAGMA foreign_keys=on;
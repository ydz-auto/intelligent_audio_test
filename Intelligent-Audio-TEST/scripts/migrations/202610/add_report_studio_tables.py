# -*- coding: utf-8 -*-
"""迁移脚本：Report Studio 业务资产 4 表（INT-673，设计文档 §15.4）

功能：
- 建 report_studio_documents 表（文档真相源：当前 Markdown + 乐观锁 current_version）
- 建 report_studio_document_versions 表（不可变版本快照，doc_id+version 唯一）
- 建 report_studio_chart_specs 表（图表定义源，服务端重新校验权限/指标/归属）
- 建 report_studio_export_jobs 表（导出异步作业，状态持久化）

DDL 与 report_service ORM 元数据
（report_service/infrastructure/persistence/models/report_studio_models.py）逐列对齐。

幂等，可重复执行。全新库 create_all 已含四表，执行为全 [SKIP]。

用法:
    python scripts/migrations/202610/add_report_studio_tables.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _index_exists(cur, index):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


TABLE_DDL = {
    'report_studio_documents': """
        CREATE TABLE report_studio_documents (
            doc_id VARCHAR(36) PRIMARY KEY,
            report_id BIGINT NOT NULL,
            agent_session_id VARCHAR(64),
            title VARCHAR(255) NOT NULL,
            markdown_content TEXT NOT NULL DEFAULT '',
            chart_refs JSONB NOT NULL DEFAULT '[]',
            style_prefs JSONB NOT NULL DEFAULT '{}',
            current_version INTEGER NOT NULL DEFAULT 1,
            etag_hash VARCHAR(64) NOT NULL DEFAULT '',
            created_by BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'report_studio_document_versions': """
        CREATE TABLE report_studio_document_versions (
            id SERIAL PRIMARY KEY,
            doc_id VARCHAR(36) NOT NULL,
            version INTEGER NOT NULL,
            markdown_content TEXT NOT NULL DEFAULT '',
            chart_specs JSONB NOT NULL DEFAULT '{}',
            parent_version INTEGER,
            snapshot_reason VARCHAR(20) NOT NULL DEFAULT 'manual_edit',
            created_by BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_rs_doc_version UNIQUE (doc_id, version)
        )
    """,
    'report_studio_chart_specs': """
        CREATE TABLE report_studio_chart_specs (
            chart_id VARCHAR(36) PRIMARY KEY,
            doc_id VARCHAR(36) NOT NULL,
            report_id BIGINT NOT NULL,
            metric_params JSONB NOT NULL DEFAULT '{}',
            style JSONB NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            created_by BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
    'report_studio_export_jobs': """
        CREATE TABLE report_studio_export_jobs (
            export_id VARCHAR(36) PRIMARY KEY,
            doc_id VARCHAR(36) NOT NULL,
            version INTEGER NOT NULL,
            format VARCHAR(10) NOT NULL,
            theme VARCHAR(60),
            status VARCHAR(10) NOT NULL DEFAULT 'pending',
            file_path VARCHAR(512),
            error TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            created_by BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
}

INDEX_DDL = [
    ('idx_rs_doc_report_id',
     'CREATE INDEX idx_rs_doc_report_id ON report_studio_documents (report_id)'),
    ('idx_rs_doc_created_by',
     'CREATE INDEX idx_rs_doc_created_by ON report_studio_documents (created_by)'),
    ('idx_rs_version_doc',
     'CREATE INDEX idx_rs_version_doc ON report_studio_document_versions (doc_id)'),
    ('idx_rs_chart_doc',
     'CREATE INDEX idx_rs_chart_doc ON report_studio_chart_specs (doc_id)'),
    ('idx_rs_chart_report',
     'CREATE INDEX idx_rs_chart_report ON report_studio_chart_specs (report_id)'),
    ('idx_rs_export_doc',
     'CREATE INDEX idx_rs_export_doc ON report_studio_export_jobs (doc_id)'),
    ('idx_rs_export_created_by',
     'CREATE INDEX idx_rs_export_created_by ON report_studio_export_jobs (created_by)'),
]


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    # 1. 建表
    for table, ddl in TABLE_DDL.items():
        if _table_exists(cur, table):
            print(f'SKIP: 表 {table} 已存在')
            continue
        print(f'APPLY: 创建表 {table}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    # 2. 建索引
    for index, ddl in INDEX_DDL:
        if _index_exists(cur, index):
            print(f'SKIP: 索引 {index} 已存在')
            continue
        print(f'APPLY: 创建索引 {index}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    if dry_run:
        conn.rollback()
        print(f'[DRY-RUN] 共 {total_steps} 步待执行')
    else:
        conn.commit()
        print(f'完成：共执行 {total_steps} 步')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Report Studio 业务资产 4 表迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)

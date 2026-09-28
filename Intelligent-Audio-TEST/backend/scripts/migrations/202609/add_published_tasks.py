# -*- coding: utf-8 -*-
"""
新增 published_tasks 表 + test_tasks 追溯字段（已发布任务功能）。
幂等，可重复执行。

用法:
    cd Intelligent-Audio-TEST
    python backend/scripts/migrations/202609/add_published_tasks.py

    # 另一个库：
    DATABASE_URI=postgresql://user:pwd@host:5432/db \
        python backend/scripts/migrations/202609/add_published_tasks.py
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _table_exists(conn, table):
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
    ), {'t': table}).fetchone()
    return row is not None


def _col_exists(conn, table, column):
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {'t': table, 'c': column}).fetchone()
    return row is not None


def main():
    engine = create_engine(POSTGRES_URI)
    with engine.begin() as conn:
        # 1. 已发布任务表
        if not _table_exists(conn, 'published_tasks'):
            conn.execute(text("""
                CREATE TABLE published_tasks (
                    id SERIAL PRIMARY KEY,
                    task_group_id INTEGER,
                    source_task_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'published',
                    version INTEGER NOT NULL DEFAULT 1,
                    is_current BOOLEAN NOT NULL DEFAULT true,
                    snapshot_config JSON,
                    publish_reason TEXT,
                    published_by VARCHAR(50),
                    published_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                    archived_by VARCHAR(50),
                    archived_at TIMESTAMP WITHOUT TIME ZONE,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text(
                "CREATE INDEX idx_published_task_status ON published_tasks (status)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_published_task_source ON published_tasks (source_task_id)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_published_task_is_current ON published_tasks (is_current)"
            ))
            print("[OK] 新增表: published_tasks")
        else:
            print("[SKIP] published_tasks 表已存在")

        # 2. 日常任务追溯字段
        for col in ('published_task_id', 'published_task_version', 'execution_source'):
            if not _col_exists(conn, 'test_tasks', col):
                conn.execute(text(
                    f"ALTER TABLE test_tasks ADD COLUMN {col} "
                    f"{'VARCHAR(20) DEFAULT \'manual\'' if col == 'execution_source' else 'INTEGER'}"
                ))
                print(f"[OK] 新增列: test_tasks.{col}")
            else:
                print(f"[SKIP] test_tasks.{col} 列已存在")

        # 3. 已发布任务报告快照列（冻结执行产物：报告/用例结果/评估数据/日志）
        if not _col_exists(conn, 'published_tasks', 'report_snapshot'):
            conn.execute(text(
                "ALTER TABLE published_tasks ADD COLUMN report_snapshot JSON"
            ))
            print("[OK] 新增列: published_tasks.report_snapshot")
        else:
            print("[SKIP] published_tasks.report_snapshot 列已存在")


if __name__ == '__main__':
    print("=" * 60)
    print("新增 published_tasks 表 + test_tasks 追溯字段迁移")
    print("=" * 60)
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@...")
    main()

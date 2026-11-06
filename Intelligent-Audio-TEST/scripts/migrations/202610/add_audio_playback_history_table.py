# -*- coding: utf-8 -*-
"""迁移脚本：audio_playback_history 表（INT-782#2 播放历史链路）

功能：
- 建 audio_playback_history 表（音频播放历史：播放时间/测试用例/播放设备/结果/时长）
- 建 (audio_id, created_at) 与 created_at 索引

DDL 与 audio_service/infrastructure/persistence/models/audio_models.py
的 AudioPlaybackHistory ORM 元数据逐列对齐（client-side default 不入
DDL，server_default 仅 func.now() 时间戳列），保证全新库（create_all_tables.py）
与既有库（本脚本）结构一致。

幂等，可重复执行（表/索引已存在即 SKIP）。

用法:
    python scripts/migrations/202610/add_audio_playback_history_table.py [--dry-run]

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


def _column_type(cur, table, column):
    cur.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    row = cur.fetchone()
    return row[0] if row else None


TABLE_DDL = {
    'audio_playback_history': """
        CREATE TABLE audio_playback_history (
            id BIGSERIAL PRIMARY KEY,
            audio_id INTEGER NOT NULL,
            testcase_id VARCHAR(50),
            testcase_name VARCHAR(255),
            device_id VARCHAR(100),
            device_name VARCHAR(255) NOT NULL,
            result VARCHAR(20) NOT NULL,
            duration DOUBLE PRECISION,
            source VARCHAR(20) NOT NULL,
            created_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
}

INDEX_DDL = [
    ('idx_aph_audio_played_at',
     'CREATE INDEX idx_aph_audio_played_at '
     'ON audio_playback_history (audio_id, created_at)'),
    ('idx_aph_created_at',
     'CREATE INDEX idx_aph_created_at '
     'ON audio_playback_history (created_at)'),
]


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    for table, ddl in TABLE_DDL.items():
        if _table_exists(cur, table):
            print(f'SKIP: 表 {table} 已存在')
            # INT-819 返工：既有库 testcase_id 为 BIGINT 时迁移为 VARCHAR(50)（支持 UUID）
            if _column_type(cur, table, 'testcase_id') in ('bigint', 'integer'):
                print(f'APPLY: 变更 {table}.testcase_id BIGINT → VARCHAR(50)')
                if not dry_run:
                    cur.execute(
                        f'ALTER TABLE {table} ALTER COLUMN testcase_id TYPE VARCHAR(50)'
                    )
                total_steps += 1
            continue
        print(f'APPLY: 创建表 {table}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

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
    parser = argparse.ArgumentParser(
        description='audio_playback_history 表迁移（INT-782#2）'
    )
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)

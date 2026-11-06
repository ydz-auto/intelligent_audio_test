# -*- coding: utf-8 -*-
"""迁移脚本：新建 api_rms_spl_mappings 表 + apis 表补 rms_spl_mapping_id 列

背景（INT-61 Realtime 执行链路，见 doc/功能设计文档/01_测试执行/04_类设计.md §5.7a）：
- api_rms_spl_mappings：被测 API 的数字域 RMS→SPL 映射（API 1:N），
  与 E2E SPLMapping（物理设备）对称，校准 API 输入灵敏度与输出实测口径。
- apis.rms_spl_mapping_id：API 当前默认映射选择（可空，未指定时取最新映射）。

用法:
    python scripts/migrations/202610/add_api_rms_spl_mappings.py [--dry-run]

幂等性:
    重复执行安全：表/列已存在即 [SKIP]，索引已存在即跳过，不产生重复数据。
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password

MAPPING_TABLE = 'api_rms_spl_mappings'
API_TABLE = 'apis'

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {MAPPING_TABLE} (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    api_id INTEGER NOT NULL,
    vendor VARCHAR(50),
    protocol VARCHAR(20) DEFAULT 'websocket',
    reference_spl DOUBLE PRECISION NOT NULL DEFAULT 65.0,
    reference_gain_linear DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    calibration_status VARCHAR(20) NOT NULL DEFAULT 'uncalibrated',
    calibration_data JSONB DEFAULT '{{}}'::jsonb,
    min_gain_linear DOUBLE PRECISION NOT NULL DEFAULT 0.001,
    max_gain_linear DOUBLE PRECISION NOT NULL DEFAULT 10.0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
)
"""

COLUMNS = [
    (API_TABLE, 'rms_spl_mapping_id', 'INTEGER'),
]

INDEXES = [
    (f'idx_{MAPPING_TABLE}_api_id', MAPPING_TABLE, 'api_id'),
]


def _column_exists(cur, table, column):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    sql = CREATE_TABLE_SQL.strip()
    if dry_run:
        print(f"[DRY-RUN] CREATE TABLE IF NOT EXISTS {MAPPING_TABLE}")
    else:
        print(f"[EXEC] CREATE TABLE IF NOT EXISTS {MAPPING_TABLE}")
        cur.execute(sql)
        print(f"[DONE] 表 {MAPPING_TABLE} 已就绪")

    for table, col_name, col_type in COLUMNS:
        if _column_exists(cur, table, col_name):
            print(f"[SKIP] {table}.{col_name} 已存在")
            continue
        alter = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {alter}")
        else:
            print(f"[EXEC] {alter}")
            cur.execute(alter)
            print(f"[DONE] {table}.{col_name} 已添加")

    for index_name, table, col_name in INDEXES:
        idx_sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({col_name})"
        if dry_run:
            print(f"[DRY-RUN] {idx_sql}")
        else:
            print(f"[EXEC] {idx_sql}")
            cur.execute(idx_sql)
            print(f"[DONE] 索引 {index_name} 已就绪")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)

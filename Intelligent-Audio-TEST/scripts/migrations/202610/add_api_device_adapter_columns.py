# -*- coding: utf-8 -*-
"""迁移脚本：apis 表补 UC-0901 三列（device_type / adapter_class / audio_config）

背景（INT-68 数据基座，见 doc/功能设计文档/01_测试执行/01_UseCase总览.md §0.4、
08_混音与SPL映射.md §2.2）：
- apis.device_type：被测设备类型（DeviceType 枚举 physical/http_api/websocket_api），
  决定执行路由；存量行默认 http_api 与既有 API 测试语义一致。
- apis.adapter_class：指定适配器类名（未指定时按 protocol+vendor 自动匹配）。
- apis.audio_config：目标音频格式声明 JSON
  {"sample_rate","bit_depth","channels","container"}（未配置回退 24000/s16/mono/pcm）。
（output_types / rms_spl_mapping_id 已由 INT-74 / INT-61 落列，本脚本不重复处理。）

用法:
    python scripts/migrations/202610/add_api_device_adapter_columns.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]。
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
# 懒解析：未配置 DATABASE_URL 时保留 None，让 __main__ 给出友好报错，
# 而不是在模块导入期 urlparse(None) 直接崩溃
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None
DB_HOST = parsed.hostname if parsed else None
DB_PORT = (parsed.port or 5432) if parsed else 5432
DB_NAME = parsed.path.lstrip('/') if parsed else None
DB_USER = parsed.username if parsed else None
DB_PASS = parsed.password if parsed else None

API_TABLE = 'apis'

COLUMNS = [
    (API_TABLE, 'device_type', "VARCHAR(20) NOT NULL DEFAULT 'http_api'"),
    (API_TABLE, 'adapter_class', 'VARCHAR(100)'),
    (API_TABLE, 'audio_config', "JSONB DEFAULT NULL"),
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

    cur.close()
    conn.close()


if __name__ == '__main__':
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')

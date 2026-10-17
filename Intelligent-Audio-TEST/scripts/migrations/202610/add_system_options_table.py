# -*- coding: utf-8 -*-
"""迁移脚本：建 system_options 表 + 系统选项默认值种子（INT-620）

功能：
- 建 system_options 表（key VARCHAR(255) 主键 / value JSONB / updated_at）
- 种子默认系统选项 KV（对位前端 frontend-react domain/models/option.ts
  SYSTEM_OPTION_DEFAULTS + settings-mock MOCK_SYSTEM_OPTIONS 当前可视稿基线）

幂等，可重复执行：表已存在即 SKIP；种子按 key 已存在即 SKIP。
值列用 JSONB（对应 PO 的可移植 JSON 列类型；SQLite 测试环境由 PO 建表）。

用法:
    python scripts/migrations/202610/add_system_options_table.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse
import json

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


# 系统选项默认种子（与 api_gateway/domain/entities/system_option.py
# SYSTEM_OPTION_DEFAULTS 保持同一基线：前端 settings-mock 当前可视稿）
SYSTEM_OPTION_SEED = [
    ('site.name', '智能语音测试平台'),
    ('site.logo', ''),
    ('site.footer', '© 2026 智能语音测试平台'),
    ('site.notice', ''),
    ('site.navigation.show_breadcrumb', True),
    ('site.navigation.show_algorithm_switcher', True),
    ('auth.password_login', True),
    ('auth.registration', True),
    ('auth.email_verification', False),
    ('security.rate_limit', True),
    ('operations.log_retention_days', 30),
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
    if _table_exists(cur, 'system_options'):
        print('SKIP: 表 system_options 已存在')
    else:
        print('APPLY: 创建表 system_options')
        if not dry_run:
            cur.execute("""
                CREATE TABLE system_options (
                    key VARCHAR(255) PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
        total_steps += 1

    # 2. 默认值种子（幂等：按 key 去重，ON CONFLICT 兜底）
    if _table_exists(cur, 'system_options'):
        for key, value in SYSTEM_OPTION_SEED:
            cur.execute(
                "SELECT 1 FROM system_options WHERE key = %s", (key,))
            if cur.fetchone():
                print(f'SKIP: 选项 {key} 已存在')
                continue
            print(f'APPLY: 选项种子 {key} = {value!r}')
            if not dry_run:
                cur.execute(
                    """
                    INSERT INTO system_options (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    (key, json.dumps(value, ensure_ascii=False)),
                )
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
        description='建 system_options 表 + 系统选项默认值种子（INT-620）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)

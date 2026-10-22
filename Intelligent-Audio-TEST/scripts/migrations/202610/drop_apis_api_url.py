# -*- coding: utf-8 -*-
"""迁移脚本：移除被测 API Master 入口 URL（apis.api_url）—— 先回填 api_endpoints，后删列

背景（INT-1361，父卡 INT-1223 足迹 + 方案一致性审计员 INT-1359 可行性评审）：
- 负责人 2026-10-22 裁定「直接移除 api url 不再开放填写，前后端都移除」，
  `api_endpoints` 为唯一端点配置入口。
- `apis.api_url`（Master 入口 URL）前后端全量移除；存量仅填 api_url 的记录
  迁移前回填为首个 endpoint（保历史可执行）。
- 回填结构对齐 api_test_service `_build_endpoints_list` 产物：
  endpoint/name/max_process/max_timeout/max_audio_duration/status/health_score/
  priority/description，缺省值取 default_max_process/default_max_timeout/
  default_max_audio_duration。

用法:
    python scripts/migrations/202610/drop_apis_api_url.py [--dry-run]

幂等性:
    重复执行安全：回填仅处理 api_endpoints 为空的存量行；列已不存在即 [SKIP]。
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


def column_exists(cur, table, column):
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

    # ① 回填 api_url → api_endpoints 首项（必须在删列之前执行）
    if column_exists(cur, 'apis', 'api_url'):
        backfill_sql = """
            UPDATE apis
            SET api_endpoints = json_build_array(
                    json_build_object(
                        'endpoint', api_url,
                        'name', '',
                        'max_process', COALESCE(default_max_process, 5),
                        'max_timeout', COALESCE(default_max_timeout, 30),
                        'max_audio_duration', COALESCE(default_max_audio_duration, 60),
                        'status', 'online',
                        'health_score', 100,
                        'priority', 0,
                        'description', ''
                    )
                ),
                updated_at = NOW()
            WHERE api_url IS NOT NULL
              AND api_url <> ''
              AND (api_endpoints IS NULL OR json_array_length(api_endpoints) = 0)
        """
        if dry_run:
            cur.execute("""
                SELECT count(*) FROM apis
                WHERE api_url IS NOT NULL
                  AND api_url <> ''
                  AND (api_endpoints IS NULL OR json_array_length(api_endpoints) = 0)
                """)
            print(f"[DRY-RUN] 将回填 {cur.fetchone()[0]} 行 apis.api_url → api_endpoints 首项")
        else:
            print("[EXEC] 回填 apis.api_url → api_endpoints 首项（仅 api_endpoints 为空的存量行）")
            cur.execute(backfill_sql)
            print(f"[DONE] 回填完成，涉及 {cur.rowcount} 行")
    else:
        print("[SKIP] apis.api_url 已删除，无回填需求")

    # ② 删除废弃列
    if not column_exists(cur, 'apis', 'api_url'):
        print("[SKIP] apis.api_url 已不存在")
    else:
        sql = "ALTER TABLE apis DROP COLUMN api_url"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print("[DONE] apis.api_url 已删除")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)

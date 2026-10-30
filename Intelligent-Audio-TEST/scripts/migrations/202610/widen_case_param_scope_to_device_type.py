# -*- coding: utf-8 -*-
"""迁移脚本：用例参数作用域词表由 common/api/e2e 改为 common/device_type

背景：
- 用例不再区分 api/e2e，执行方式唯一依据 task_case_relations.device_type；
  用例参数的适用范围也随之为「common（通用）+ DeviceType 值」。
- 旧词表 'api' / 'e2e' 不再写入；存量值按语义等价映射：
    'e2e' → 'physical'（物理设备用例）
    'api' → 'http_api'（API 用例；原本同值覆盖 HTTP 与 WebSocket 两类，
            本脚本按 HTTP 落库，WebSocket 专属参数需人工复核补行）
- 列宽必须 >= 13（'websocket_api'）：旧列为 VARCHAR(10)，不改宽则写入会失败。

用法：
    python scripts/migrations/202610/widen_case_param_scope_to_device_type.py --dry-run
    python scripts/migrations/202610/widen_case_param_scope_to_device_type.py

幂等：
    列宽已达要求即 [SKIP]；值映射重复执行命中 0 行。
"""
import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')

TABLE = 'case_algorithm_params'
COLUMN = 'scope'
TARGET_LENGTH = 20

# 旧值 → 新值（用例参数适用范围）
LEGACY_VALUE_MAP = {
    'e2e': 'physical',
    'api': 'http_api',
}


def _current_length(cur):
    """返回 scope 列当前长度（character_maximum_length），列不存在返回 None。"""
    cur.execute("""
        SELECT character_maximum_length FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (TABLE, COLUMN))
    row = cur.fetchone()
    return row[0] if row else None


def migrate(dry_run=False):
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    parsed = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    conn.autocommit = True
    cur = conn.cursor()

    length = _current_length(cur)
    if length is None:
        print(f"[SKIP] {TABLE}.{COLUMN} 列不存在")
        cur.close()
        conn.close()
        return
    if length >= TARGET_LENGTH:
        print(f"[SKIP] {TABLE}.{COLUMN} 列宽已为 {length}")
    else:
        sql = f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} TYPE VARCHAR({TARGET_LENGTH})"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}（{length} → {TARGET_LENGTH}）")
            cur.execute(sql)

    for old_value, new_value in LEGACY_VALUE_MAP.items():
        if dry_run:
            cur.execute(
                f"SELECT count(*) FROM {TABLE} WHERE {COLUMN} = %s AND deleted = false",
                (old_value,))
            count = cur.fetchone()[0]
            print(f"[DRY-RUN] {COLUMN} '{old_value}' → '{new_value}'：{count} 行")
            continue
        sql = (f"UPDATE {TABLE} SET {COLUMN} = %s "
               f"WHERE {COLUMN} = %s AND deleted = false")
        cur.execute(sql, (new_value, old_value))
        print(f"[EXEC] {COLUMN} '{old_value}' → '{new_value}'：{cur.rowcount} 行")

    if not dry_run:
        print("[WARN] 'api' 曾同时覆盖 HTTP 与 WebSocket 两类 API，"
              "如需保留 WebSocket 专属参数请人工补行（scope='websocket_api'）")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')

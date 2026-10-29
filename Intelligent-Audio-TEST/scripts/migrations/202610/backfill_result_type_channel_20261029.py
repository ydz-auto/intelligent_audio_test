"""迁移脚本：按执行通道回填 test_results.result_type（「结果类型待补充」治理）

背景：
- `test_results.result_type` 列可空、无默认值（缺值 = UX「结果类型待补充」桶，
  读侧统一输出 `default`，`shared/utils/status_constants.py:RESULT_TYPE_PENDING`）；
- 写入链路此前未透传 result_type（`_save_result` / api_result_processor /
  设备重提均不带），导致存量行 100% 为 NULL；
- 本次写入链路已补值（api / e2e / final），存量按通道回填。

回填口径（只写当前 NULL/空串的行，幂等）：
- `api_id IS NOT NULL` → `api`（API 通道结果）
- 仅 `device_id IS NOT NULL` → `e2e`（设备 E2E 结果）
- 两者皆空 → 保持 NULL（仍归「结果类型待补充」桶）

用法：
    python scripts/migrations/202610/backfill_result_type_channel_20261029.py           # 预览
    python scripts/migrations/202610/backfill_result_type_channel_20261029.py --apply   # 执行
"""
import argparse
import os
import sys
from urllib.parse import urlparse

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from shared.utils.status_constants import (  # noqa: E402
    RESULT_TYPE_API,
    RESULT_TYPE_E2E,
)

TABLE = 'test_results'
COLUMN = 'result_type'

# (目标值, 命中条件)：顺序执行，互斥（api 优先）
_RULES = (
    (RESULT_TYPE_API,
     f"({COLUMN} IS NULL OR {COLUMN} = '') AND api_id IS NOT NULL"),
    (RESULT_TYPE_E2E,
     f"({COLUMN} IS NULL OR {COLUMN} = '') AND api_id IS NULL AND device_id IS NOT NULL"),
)


def _to_dsn(database_url: str) -> str:
    """SQLAlchemy 风格 URL → psycopg2 DSN（去掉 +psycopg2 等驱动后缀）。"""
    parsed = urlparse(database_url)
    return (f"host={parsed.hostname} port={parsed.port or 5432} "
            f"dbname={parsed.path.lstrip('/')} user={parsed.username} "
            f"password={parsed.password}")


def _connect():
    default = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')
    return psycopg2.connect(_to_dsn(os.environ.get('DATABASE_URL') or default))


def migrate(dry_run: bool = True) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT count(*) FROM {TABLE} WHERE {COLUMN} IS NULL OR {COLUMN} = ''")
        before = cur.fetchone()[0]
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填前缺值行：{before}")

        for value, condition in _RULES:
            cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {condition}")
            hit = cur.fetchone()[0]
            print(f"[{'DRY' if dry_run else 'APPLY'}] → {value}：{hit} 行")
            if not dry_run and hit:
                cur.execute(
                    f"UPDATE {TABLE} SET {COLUMN} = %s WHERE {condition}", (value,))
        if not dry_run:
            conn.commit()

        cur.execute(
            f"SELECT count(*) FROM {TABLE} WHERE {COLUMN} IS NULL OR {COLUMN} = ''")
        after = cur.fetchone()[0]
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填后缺值行：{after}")
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='按执行通道回填 result_type')
    parser.add_argument('--apply', action='store_true', help='执行（缺省仅预览）')
    args = parser.parse_args()
    migrate(dry_run=not args.apply)

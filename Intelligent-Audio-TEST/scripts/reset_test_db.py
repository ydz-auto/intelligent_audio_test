# -*- coding: utf-8 -*-
"""INT-246 隔离测试库清库（冒烟后）：scripts/reset_test_db.py

用途：`python stack.py up --test-db` 起栈做实机链路回归 / 集成冒烟 / 验收后，
把隔离测试库 intelligent_audio_test_test 全量清空（TRUNCATE 全部业务表 +
RESTART IDENTITY，回收冒烟产生的任务/用例/结果/音频等残留），下次冒烟从
干净库开始。种子数据（维度/裁判/用户）需要时用 scripts/migrations 下
seed_*.py 以 DATABASE_URI 指向隔离库重播。

安全红线（硬编码双保险）：
  - 目标库名恒为 shared.constants.database.ISOLATED_TEST_DB_NAME，不受
    DATABASE_URL/DATABASE_URI 环境变量影响；任何指向共享业务库的请求
    （含误把共享库名写进 --db-name）一律拒绝退出。

用法（项目环境 python，仓库任意位置）：
    python scripts/reset_test_db.py [--host localhost] [--port 5432]
                                    [--user ...] [--password ...]

退出码：0 清库完成；1 拒绝执行或连接失败。
"""
import argparse
import os
import sys

import psycopg2
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.constants.database import (  # noqa: E402
    ISOLATED_TEST_DB_NAME, SHARED_BUSINESS_DB_NAME,
)

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 5432
DEFAULT_USER = 'intelligent_audio_test'
DEFAULT_PASSWORD = 'intelligent_audio_test666'


def main():
    parser = argparse.ArgumentParser(description='INT-246 隔离测试库冒烟后清库')
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--user', default=DEFAULT_USER)
    parser.add_argument('--password', default=DEFAULT_PASSWORD)
    parser.add_argument(
        '--db-name', default=ISOLATED_TEST_DB_NAME,
        help='目标库名（仅允许隔离测试库；传共享业务库名会被拒绝）')
    args = parser.parse_args()

    if args.db_name != ISOLATED_TEST_DB_NAME:
        print(f"[ABORT] 拒绝清库：目标库名 {args.db_name!r} 不是隔离测试库 "
              f"'{ISOLATED_TEST_DB_NAME}'（共享业务库 '{SHARED_BUSINESS_DB_NAME}' "
              "为负责人数据，永不触碰）。")
        return 1

    conn = psycopg2.connect(
        host=args.host, port=args.port, dbname=args.db_name,
        user=args.user, password=args.password, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename")
            tables = [r[0] for r in cur.fetchall()]
            if not tables:
                print(f"[OK] {args.db_name} 无业务表，无需清库。")
                return 0
            cur.execute(sql.SQL('TRUNCATE TABLE {} RESTART IDENTITY CASCADE').format(
                sql.SQL(', ').join(sql.Identifier(t) for t in tables)))
            conn.commit()
            print(f"[OK] 已清空隔离测试库 {args.db_name}：TRUNCATE {len(tables)} 张表"
                  "（RESTART IDENTITY CASCADE）。")
            return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

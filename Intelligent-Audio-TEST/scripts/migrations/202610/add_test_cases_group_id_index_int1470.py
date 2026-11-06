# -*- coding: utf-8 -*-
"""
分组用例计数索引（INT-1470）
============================

背景：
    `GET /groups` 每次请求都会下发 `GetTestCaseStats(group_by='group_id')`，
    对应 SQL 为 `SELECT group_id, count(id) FROM test_cases WHERE deleted = false
    GROUP BY group_id`。test_cases 上没有 group_id 索引（仅 pkey / created_by /
    visibility / strategy_id），数据量增长后只能全表顺序扫描：
    10k 用例实测 7.4ms（EXPLAIN HashAggregate over Seq Scan，shared hit=1084）。

变更：
    新增部分索引 `idx_test_cases_group_id_active ON test_cases (group_id)
    WHERE deleted = false`。覆盖统计口径（只统计未删除用例）的索引扫描 /
    index-only scan，且仅索引活跃行，体积远小于全量索引。

幂等性：
    CREATE INDEX ... IF NOT EXISTS，可重复执行。

用法：
    python add_test_cases_group_id_index_int1470.py                 # 正式执行
    python add_test_cases_group_id_index_int1470.py --dry-run       # 仅预览
    python add_test_cases_group_id_index_int1470.py --analyze       # 执行后 EXPLAIN 复核

依赖：psycopg2-binary（DATABASE_URL 或 DATABASE_URI 指向目标库）
"""
import argparse
import os
import sys

import psycopg2

DB_URL = os.environ.get('DATABASE_URL') or os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test',
)
INDEX_NAME = 'idx_test_cases_group_id_active'
DDL = (
    f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} '
    'ON test_cases (group_id) WHERE deleted = false'
)
EXPLAIN_SQL = (
    'EXPLAIN (ANALYZE, BUFFERS) '
    'SELECT group_id, count(id) FROM test_cases WHERE deleted = false GROUP BY group_id'
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--analyze', action='store_true', help='建索引后 ANALYZE 并打印 EXPLAIN')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_indexes WHERE tablename = 'test_cases' AND indexname = %s",
                (INDEX_NAME,),
            )
            existed = cur.fetchone() is not None
            if args.dry_run:
                print(f'[dry-run] {INDEX_NAME} 已存在：{existed}；将执行：{DDL}')
                return 0
            cur.execute(DDL)
            print(f'{INDEX_NAME}：{"已存在，跳过" if existed else "创建完成"}')
            if args.analyze:
                cur.execute('ANALYZE test_cases')
                cur.execute(EXPLAIN_SQL)
                for row in cur.fetchall():
                    print(row[0])
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())

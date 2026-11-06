# -*- coding: utf-8 -*-
"""迁移脚本：用例移除排除标记列（INT-305）

背景：任务执行详情模态窗支持删除用例（待执行/执行中/已完成/评估完成四阶段）。
终态任务删除用例时 TestResult 不物理删除（保审计），以 excluded 标记剔除——
报告/聚合按 excluded=1 过滤，通过率/总数剔除被删用例。

功能（幂等，可重复执行）：
- test_results 补 excluded（Integer NOT NULL DEFAULT 0）
- test_results 补 excluded_by_user_id / excluded_at
- 补三列注释（COMMENT ON COLUMN，PostgreSQL 无列内联 COMMENT 语法）
- 补 excluded 索引（幂等）

新建库由 PO 模型 create_all 直接带出（模型已同步补列）；
本脚本针对既有环境，对已存在列自动 [SKIP]。

用法:
    python scripts/migrations/202610/add_result_excluded_columns_int305.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)


def _col_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column)
    )
    return cur.fetchone() is not None


def _index_exists(cur, index_name):
    cur.execute(
        "SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,)
    )
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    cur = conn.cursor()
    statements = []

    if not _col_exists(cur, 'test_results', 'excluded'):
        statements.append(
            "ALTER TABLE test_results ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0")
        statements.append(
            "COMMENT ON COLUMN test_results.excluded IS "
            "'结果排除标记 (0=正常 1=被删用例排除，报告/聚合剔除)'")
    else:
        print("[SKIP] test_results.excluded 已存在")

    if not _col_exists(cur, 'test_results', 'excluded_by_user_id'):
        statements.append(
            "ALTER TABLE test_results ADD COLUMN excluded_by_user_id BIGINT")
        statements.append(
            "COMMENT ON COLUMN test_results.excluded_by_user_id IS "
            "'标记排除的操作人（INT-305，JWT 透传）'")
    else:
        print("[SKIP] test_results.excluded_by_user_id 已存在")

    if not _col_exists(cur, 'test_results', 'excluded_at'):
        statements.append(
            "ALTER TABLE test_results ADD COLUMN excluded_at TIMESTAMP")
        statements.append(
            "COMMENT ON COLUMN test_results.excluded_at IS '排除标记时间'")
    else:
        print("[SKIP] test_results.excluded_at 已存在")

    if not _index_exists(cur, 'idx_test_results_excluded'):
        statements.append(
            "CREATE INDEX idx_test_results_excluded ON test_results (excluded)")
    else:
        print("[SKIP] idx_test_results_excluded 已存在")

    if not statements:
        print('所有列/索引已存在，无需迁移')
        cur.close()
        conn.close()
        return

    for sql in statements:
        print(f"[EXEC] {sql[:120]}{'...' if len(sql) > 120 else ''}")
        if not dry_run:
            cur.execute(sql)
    if not dry_run:
        conn.commit()
        print('迁移完成')
    else:
        print('[DRY-RUN] 未提交')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='只打印不执行')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)

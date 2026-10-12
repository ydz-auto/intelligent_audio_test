# -*- coding: utf-8 -*-
"""迁移脚本：published_tasks 补 type / algorithm_type 两列并回填历史数据（INT-148）

背景（V9.7.10 对齐缺陷包，已发布任务列表筛选端到端缺失）：
- published_tasks.type：任务类型 (api/e2e)。新架构 task.type 已废弃（用例级
  device_type 路由），发布时由快照派生：caseDevices 任一 device_type 为
  http_api/websocket_api → 'api'，否则 'e2e'（无 caseDevices 的历史快照
  回退 apiIds 判断）。
- published_tasks.algorithm_type：发布时从快照 algorithmType 冻结的冗余列，
  列表按算法筛选直查本列（对齐 V9.7.10 add_published_task_algorithm_type 迁移）。

用法:
    python scripts/migrations/202610/add_published_task_type_algorithm_type.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]；回填仅更新 NULL 行。
"""
import sys
import os
import json

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None
DB_HOST = parsed.hostname if parsed else None
DB_PORT = (parsed.port or 5432) if parsed else 5432
DB_NAME = parsed.path.lstrip('/') if parsed else None
DB_USER = parsed.username if parsed else None
DB_PASS = parsed.password if parsed else None

TABLE = 'published_tasks'

COLUMNS = [
    ('type', 'VARCHAR(50)'),
    ('algorithm_type', 'VARCHAR(50)'),
]

API_DEVICE_TYPES = ('http_api', 'websocket_api')


def derive_task_type(snapshot):
    """快照 → 任务类型（与发布链路派生规则一致）。"""
    if not isinstance(snapshot, dict):
        return 'e2e'
    case_devices = snapshot.get('caseDevices') or []
    for item in case_devices:
        if isinstance(item, dict) and (item.get('device_type') or '') in API_DEVICE_TYPES:
            return 'api'
    if case_devices:
        return 'e2e'
    # 历史快照兜底：无 caseDevices 时按 apiIds 判断
    if snapshot.get('apiIds'):
        return 'api'
    return 'e2e'


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

    for col_name, col_type in COLUMNS:
        if _column_exists(cur, TABLE, col_name):
            print(f"[SKIP] {TABLE}.{col_name} 已存在")
            continue
        alter = f"ALTER TABLE {TABLE} ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {alter}")
        else:
            print(f"[EXEC] {alter}")
            cur.execute(alter)
            print(f"[DONE] {TABLE}.{col_name} 已添加")

    if not dry_run:
        # 索引（列创建后建；对齐 V9.7.10 idx_published_task_algorithm_type）
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_task_algorithm_type
            ON published_tasks(algorithm_type)
        """)
        # 回填：仅处理两列为 NULL 的历史行
        cur.execute(f"""
            SELECT id, snapshot_config FROM {TABLE}
            WHERE type IS NULL OR algorithm_type IS NULL
        """)
        rows = cur.fetchall()
        updated = 0
        for row_id, snapshot_raw in rows:
            try:
                snapshot = snapshot_raw if isinstance(snapshot_raw, dict) else (
                    json.loads(snapshot_raw) if snapshot_raw else {})
            except (TypeError, ValueError):
                snapshot = {}
            task_type = derive_task_type(snapshot)
            algorithm_type = snapshot.get('algorithmType') if isinstance(snapshot, dict) else None
            cur.execute(f"""
                UPDATE {TABLE}
                SET type = %s, algorithm_type = %s
                WHERE id = %s
            """, (task_type, algorithm_type, row_id))
            updated += 1
        print(f"[DONE] 历史数据回填 {updated} 行")

    cur.close()
    conn.close()


if __name__ == '__main__':
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')

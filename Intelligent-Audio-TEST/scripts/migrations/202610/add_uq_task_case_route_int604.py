# -*- coding: utf-8 -*-
"""迁移脚本：task_case_relations 建 (task, case, 路由) 唯一索引（INT-604）

背景（INT-604 混选前置 + 路由唯一索引评审①补录）：
- 多路由下同一用例可同时存在设备侧 + API 侧多条 TaskCase（device_type/device_id
  各自区分），但同一 (task, case, 路由) 不得重复；
- 历史无 DB 层唯一约束，理论存在 (task, case) 重复行——建索引前先检测重复，
  存在则中止并列出重复行（交人工去重），避免唯一索引创建失败；
- 路由身份 = (device_type, device_id)，NULL 归一为空串（COALESCE），与派发侧
  NULL 兜底 physical 口径一致，避免 NULL 行与 physical 行被 COALESCE 视为
  不同路由而并存。

用法:
    python scripts/migrations/202610/add_uq_task_case_route_int604.py [--dry-run]

幂等性:
    索引已存在即 [SKIP]；重复执行安全，不产生重复数据。
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

TABLE = 'task_case_relations'
INDEX_NAME = 'uq_task_case_route'
INDEX_SQL = (
    f"CREATE UNIQUE INDEX {INDEX_NAME} ON {TABLE} "
    f"(task_id, test_case_id, COALESCE(device_type, ''), COALESCE(device_id, ''))"
)
# 路由重复检测：按归一化路由键分组计数
DUPLICATE_SQL = f"""
SELECT task_id, test_case_id,
       COALESCE(device_type, '') AS device_type,
       COALESCE(device_id, '') AS device_id,
       COUNT(*) AS dup_count
FROM {TABLE}
GROUP BY task_id, test_case_id, COALESCE(device_type, ''), COALESCE(device_id, '')
HAVING COUNT(*) > 1
ORDER BY task_id, test_case_id
"""


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 0) 索引已存在 → 跳过
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = %s AND indexname = %s
    """, (TABLE, INDEX_NAME))
    if cur.fetchone():
        print(f"[SKIP] {TABLE} 已存在唯一索引 {INDEX_NAME}")
        cur.close()
        conn.close()
        return

    # 1) 建索引前查重：存在 (task, case, 路由) 重复行则中止，交人工去重
    cur.execute(DUPLICATE_SQL)
    duplicates = cur.fetchall()
    if duplicates:
        print(f"[ABORT] 检测到 {len(duplicates)} 组 (task, case, 路由) 重复行，"
              f"需人工去重后再建唯一索引。重复行清单（task_id, test_case_id, "
              f"device_type, device_id, 行数）：")
        for task_id, case_id, dtype, did, cnt in duplicates:
            print(f"  task_id={task_id} test_case_id={case_id} "
                  f"device_type={dtype or '(NULL)'} device_id={did or '(NULL)'} 行数={cnt}")
        cur.close()
        conn.close()
        sys.exit(2)

    # 2) 建唯一索引
    if dry_run:
        print(f"[DRY-RUN] {INDEX_SQL}")
    else:
        print(f"[EXEC] {INDEX_SQL}")
        cur.execute(INDEX_SQL)
        print(f"[DONE] 唯一索引 {INDEX_NAME} 已创建")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)

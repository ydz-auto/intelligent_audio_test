# -*- coding: utf-8 -*-
"""
logs 表过滤索引补齐（INT-1468）
================================

背景（2026-10-23 日志域压测基线核验）：
    logs 是主库最大增长表（约 30 万行 / 260MB）。读侧 LogRepository.list_logs /
    get_stats 的过滤条件一律带 lower()（level / module / category 大小写不敏感，
    INT-100 语义），而表上现有索引是裸列索引（idx_level / idx_module /
    idx_category），`WHERE lower(level) = 'error'` 这类表达式匹配不上，planner
    只能全表扫描或按 pkey 倒序逐行过滤：
        - lower(level)='error'（0.3% 命中）单页查询 26ms
        - lower(module)=... 与 stats 的 group by 全表扫描 150~290ms

设计依据：
    1. 新建函数索引 lower(level) / lower(module) / lower(category)，
       列尾追加 id 以同时覆盖 `ORDER BY id DESC` 的分页序，避免过滤后额外排序。
    2. task_id 维度补充 (task_id, id)：任务日志合并视图按 task_id 过滤后按
       id 倒序拉取，idx_task_time(task_id, time) 不覆盖该排序。
    3. 不新增 created_at 索引：读侧从不按 created_at 过滤/排序（业务时间用
       time 列，已有 idx_time），加了只会增加写放大。
    4. 不删除既有裸列索引：本轮只补缺，收缩索引另开卡评估（避免与在办写路径
       抢锁）。

幂等性：全部 `CREATE INDEX IF NOT EXISTS`，可重复执行。
执行建议：logs 表写量大，生产库请在低峰执行；本脚本用普通 CREATE INDEX
（非 CONCURRENTLY，事务内可重复执行）；需要在线建索引的库，可手工把语句改成
CREATE INDEX CONCURRENTLY 后单独执行。

用法:
    python add_logs_query_indexes_int1468.py              # 正式执行
    python add_logs_query_indexes_int1468.py --dry-run    # 仅预览
"""

import argparse
import os
import sys
import time

from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')

INDEXES = [
    ('idx_logs_lower_level_id',
     'CREATE INDEX IF NOT EXISTS idx_logs_lower_level_id ON logs (lower(level), id)'),
    ('idx_logs_lower_module_id',
     'CREATE INDEX IF NOT EXISTS idx_logs_lower_module_id ON logs (lower(module), id)'),
    ('idx_logs_lower_category_id',
     'CREATE INDEX IF NOT EXISTS idx_logs_lower_category_id ON logs (lower(category), id)'),
    ('idx_logs_task_id_id',
     'CREATE INDEX IF NOT EXISTS idx_logs_task_id_id ON logs (task_id, id)'),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    engine = create_engine(POSTGRES_URI)
    applied, skipped = [], []
    with engine.begin() as conn:
        existing = {
            r[0] for r in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'logs'"))
        }
        for name, ddl in INDEXES:
            if name in existing:
                skipped.append(name)
                print(f'[SKIP] {name} 已存在')
                continue
            if args.dry_run:
                print(f'[DRY-RUN] {ddl}')
                continue
            started = time.time()
            conn.execute(text(ddl))
            applied.append(name)
            print(f'[OK] {name} 创建完成（{time.time() - started:.1f}s）')

    if not args.dry_run:
        print(f'\n完成：新建 {len(applied)} 个，跳过 {len(skipped)} 个')
    return 0


if __name__ == '__main__':
    sys.exit(main())

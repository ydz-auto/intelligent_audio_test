# -*- coding: utf-8 -*-
"""迁移脚本：新建增量回导合并快照两表（INT-1762 D4，D0-A8 裁定）

背景：
- D4 新增两条跨服务合并 gRPC（evaluation.MergeDimensions / report.ReplaceReports），
  按 A8 要求「旧值快照落各服务自有库」，用于批次回滚（RollbackDimensionMerge /
  RollbackReportReplacement）。
- A8 写的是 evaluation / report 各一张同构表 `data_transfer_merge_snapshots`；
  本工作区两服务共用同一个 Postgres 库（docker/docker-compose.yml 各服务
  DATABASE_URL 相同），同名表无法各建一份，故按服务前缀区分：
  `evaluation_merge_snapshots` / `report_merge_snapshots`，列结构完全一致。
- create_all 只建「缺失的表」，建库早于本卡的存量库（真实库 / 隔离库）需要在
  引导链里自愈；全新库 create_all 已含两表，执行本脚本为全 [SKIP]。

DDL 与两个 ORM PO 逐列对齐：
    evaluation_service/infrastructure/persistence/models/merge_snapshot_models.py
    report_service/infrastructure/persistence/models/merge_snapshot_models.py
    id BIGSERIAL PK / batch_id VARCHAR(64) NOT NULL /
    entity_table VARCHAR(64) NOT NULL / entity_pk BIGINT NULL /
    old_row JSON NULL / created_at TIMESTAMP NOT NULL DEFAULT NOW()
索引 idx_*_merge_snapshot_batch(batch_id) / idx_*_merge_snapshot_created_at(created_at)
（batch_id 供回滚按批次取快照；created_at 供 7 天 TTL 清理扫描）
无外键：202608 基线后引用完整性由应用层管理。

步骤（幂等）：
    ① CREATE TABLE IF NOT EXISTS 两张表
    ② CREATE INDEX IF NOT EXISTS 四个索引
    ③ 结构自检（information_schema 回读列 + 索引）

用法:
    python scripts/migrations/202610/add_merge_snapshots_int1762.py           # dry-run（默认）
    python scripts/migrations/202610/add_merge_snapshots_int1762.py --apply   # 执行

幂等性:
    表 / 索引已存在即 [SKIP]，重复执行不报错、不产生重复数据。
"""
import argparse
import os

import psycopg2

TABLES = ('evaluation_merge_snapshots', 'report_merge_snapshots')

INDEXES = [
    ('idx_eval_merge_snapshot_batch', 'evaluation_merge_snapshots', 'batch_id'),
    ('idx_eval_merge_snapshot_created_at', 'evaluation_merge_snapshots', 'created_at'),
    ('idx_report_merge_snapshot_batch', 'report_merge_snapshots', 'batch_id'),
    ('idx_report_merge_snapshot_created_at', 'report_merge_snapshots', 'created_at'),
]

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')


def _create_table_sql(table):
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(64) NOT NULL,
    entity_table VARCHAR(64) NOT NULL,
    entity_pk BIGINT NULL,
    old_row JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,))
    return cur.fetchone() is not None


def _index_exists(cur, table, index):
    cur.execute(
        "SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s",
        (table, index))
    return cur.fetchone() is not None


def migrate(dry_run=True):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    # ① 建表
    for table in TABLES:
        if _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 已存在')
        elif dry_run:
            print(f'[DRY-RUN] CREATE TABLE IF NOT EXISTS {table}')
        else:
            print(f'[EXEC] CREATE TABLE IF NOT EXISTS {table}')
            cur.execute(_create_table_sql(table).strip())
            print(f'[DONE] 表 {table} 已就绪')

    # ② 索引
    for index_name, table, col_name in INDEXES:
        if _index_exists(cur, table, index_name):
            print(f'[SKIP] 索引 {index_name} 已存在')
            continue
        idx_sql = (f'CREATE INDEX IF NOT EXISTS {index_name} '
                   f'ON {table} ({col_name})')
        if dry_run:
            print(f'[DRY-RUN] {idx_sql}')
        else:
            print(f'[EXEC] {idx_sql}')
            cur.execute(idx_sql)
            print(f'[DONE] 索引 {index_name} 已就绪')

    # ③ 结构自检
    if not dry_run:
        for table in TABLES:
            cur.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = %s "
                "ORDER BY ordinal_position", (table,))
            cols = cur.fetchall()
            print(f'[VERIFY] {table}: {len(cols)} 列')
            for name, dtype, nullable in cols:
                print(f'  - {name} {dtype}{" NULL" if nullable == "YES" else " NOT NULL"}')

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='增量回导合并快照两表（INT-1762 D4）迁移')
    parser.add_argument('--apply', action='store_true', help='执行 DDL（缺省 dry-run）')
    args = parser.parse_args()
    migrate(dry_run=not args.apply)

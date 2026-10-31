# -*- coding: utf-8 -*-
"""迁移脚本：audios 补 md5 / file_path 局部索引（INT-2280）

背景（INT-2278 SQL 抽检 2026-11-01，docker 栈主库 ``audios``）：
    按 md5 / file_path 等值过滤的三条查询在仓库里此前**没有任何索引可命中**，
    每次都是整表顺序扫描（1968 行 / 161 buffers，``seq_tup_read = 1057 × 1968``，
    无提前退出）：

    - ``audio_repository.get_audio_by_md5``        WHERE md5 = :v AND deleted = false
    - ``audio_repository.get_audios_by_md5_list``  WHERE md5 IN (...) AND deleted = false
    - ``audio_repository.get_audio_by_file_path``  WHERE file_path = :v AND deleted = false

    调用点都是请求级的逐文件路径（上传按 md5 去重、ZIP 回导 INT-2215 逐文件去重、
    stream/download 的路径可见性校验），所以是 O(文件数 × 表行数) 的增长曲线，
    涨到 10 万行时单次顺序扫描约 8MB / 数千 buffers。

DDL（与 audio_service/infrastructure/persistence/models/audio_models.py 的
``Audio.__table_args__`` 对齐 —— 本仓库有 create_all 先建表导致两侧漂移的前例）：
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audios_md5
        ON audios (md5) WHERE deleted = false
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audios_file_path
        ON audios (file_path) WHERE deleted = false

设计取舍：
- **局部索引**（``WHERE deleted = false``）：仓库内三条等值查询全部由
  AudioRepository 发出、且都带 ``deleted = false``（软删语义在仓储层统一收口），
  局部索引能被 planner 直接命中，同时不收录软删行、体积更小。
- ``file_path LIKE '%/<tail>'``（前导通配）btree 用不上，本卡**不改匹配语义**、
  不建 pg_trgm；该分支保持现状，需要优化另开卡。
- 不加 deleted_at / created_at 等无关列，避免与可见性查询的现有索引口径打岔。

``CREATE INDEX CONCURRENTLY`` 不能在事务块里执行：本脚本用 autocommit 连接，
每条 DDL 独立提交，失败不会连带回滚其它索引。

执行语义：
- 默认 dry-run：打印待执行 DDL、索引现状与库内现状，不改库；
- ``--apply``：autocommit 下逐条执行（CONCURRENTLY，不长时间阻塞写）；
- ``--rollback``：``DROP INDEX CONCURRENTLY IF EXISTS`` 两条索引；
- 幂等：索引已存在即 SKIP；CONCURRENTLY 中途失败会留下 indisvalid=false 的
  **invalid 索引**，本脚本检出后打印需人工执行的 ``DROP INDEX CONCURRENTLY``
  命令并以非零码退出（否则 IF NOT EXISTS 会一直跳过、索引永远修不好）。

用法：
    python scripts/migrations/202611/add_audios_md5_filepath_index.py            # 预览
    python scripts/migrations/202611/add_audios_md5_filepath_index.py --apply    # 执行
    python scripts/migrations/202611/add_audios_md5_filepath_index.py --rollback --apply
"""
import argparse
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

TABLE = 'audios'

# (索引名, 列, 建索引 DDL, 回滚 DDL)
INDEXES = (
    (
        'idx_audios_md5',
        'md5',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audios_md5 '
        'ON audios (md5) WHERE deleted = false',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_audios_md5',
    ),
    (
        'idx_audios_file_path',
        'file_path',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audios_file_path '
        'ON audios (file_path) WHERE deleted = false',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_audios_file_path',
    ),
)


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_audios_md5_idx')
    # CREATE INDEX CONCURRENTLY / DROP INDEX CONCURRENTLY 不能在事务块内执行
    conn.autocommit = True
    return conn


def _lock_timeout():
    """等锁预算（毫秒写入 SET lock_timeout），与其它迁移脚本同一口径。"""
    raw = os.environ.get('DB_MIGRATION_LOCK_TIMEOUT_MS', '5000')
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        ms = 5000
    return max(ms, 1000)


def _table_exists(cur):
    cur.execute('SELECT to_regclass(%s)', (TABLE,))
    return cur.fetchone()[0] is not None


def _index_state(cur, name):
    """返回 None（不存在）或 {'valid': bool, 'ready': bool, 'def': str}。"""
    cur.execute(
        "SELECT i.indisvalid, i.indisready, pg_get_indexdef(i.indexrelid) "
        "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = %s", (name,))
    row = cur.fetchone()
    if row is None:
        return None
    return {'valid': bool(row[0]), 'ready': bool(row[1]), 'def': row[2]}


def _count_rows(cur):
    cur.execute(f'SELECT COUNT(*), COUNT(*) FILTER (WHERE deleted = false) '
                f'FROM {TABLE}')
    return cur.fetchone()


def _precheck(cur):
    """只读现状：表 / 行数 / 两条索引的当前状态。"""
    if not _table_exists(cur):
        print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
        return False
    total, alive = _count_rows(cur)
    print(f'[INFO] {TABLE}: 总 {total} 行 / 未删除 {alive} 行')
    for name, _col, _ddl, _rb in INDEXES:
        state = _index_state(cur, name)
        if state is None:
            print(f'[INFO] {name}: 不存在')
        else:
            flag = 'OK' if state['valid'] else 'INVALID（CONCURRENTLY 中途失败）'
            print(f'[INFO] {name}: {flag} :: {state["def"]}')
    return True


def _invalid_indexes(cur):
    return [name for name, _c, _d, _r in INDEXES
            if (_index_state(cur, name) or {}).get('valid') is False]


def _plan(cur):
    """待执行的建索引 DDL（已存在且有效即跳过）。"""
    stmts = []
    for name, _col, ddl, _rb in INDEXES:
        state = _index_state(cur, name)
        if state is None:
            stmts.append((name, ddl))
        else:
            print(f'[SKIP] {name} 已存在')
    return stmts


def _verify(cur):
    for name, col, _ddl, _rb in INDEXES:
        state = _index_state(cur, name)
        if state is None:
            print(f'[VERIFY] {name}: 不存在')
        else:
            print(f'[VERIFY] {name}: {"有效" if state["valid"] else "INVALID"} '
                  f':: {state["def"]}')
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = %s AND indexname = %s", (TABLE, name))
        row = cur.fetchone()
        if row is None:
            print(f'[VERIFY] pg_indexes 无 {name}')
    # 抽样确认 planner 能按 md5 / file_path 走索引（日志辅助，不作断言）
    for col in ('md5', 'file_path'):
        probe = cur.mogrify(
            f'EXPLAIN SELECT id FROM {TABLE} WHERE {col} = %s '
            'AND deleted = false', ('__migration_probe__',)).decode()
        cur.execute(probe)
        plan = ' | '.join(r[0].strip() for r in cur.fetchall())
        hit = [n for n, _c, _d, _r in INDEXES
               if n in plan]
        print(f'[VERIFY] EXPLAIN {col}: {plan}'
              f'{"  => 命中 " + ",".join(hit) if hit else "  => 未命中索引"}')


def _report_invalid(cur):
    invalid = _invalid_indexes(cur)
    if not invalid:
        return False
    for name in invalid:
        print(f'[FAIL] {name} 是 invalid 索引（上次 CONCURRENTLY 被中断），'
              'IF NOT EXISTS 会一直跳过它，索引永远无法生效。请先执行：')
        print(f'       DROP INDEX CONCURRENTLY IF EXISTS {name};')
        print('       然后重跑本脚本 --apply。')
    return True


def _run(apply, statements_factory, label):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SET lock_timeout = '{_lock_timeout()}ms'")
        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return 0
        if _report_invalid(cur):
            return 2
        stmts = statements_factory(cur)
        if not stmts:
            print(f'[SKIP] 结构已是{label}后形态，无需执行')
            _verify(cur)
            return 0
        for name, sql in stmts:
            print(f"[{'DRY' if not apply else 'APPLY'}] {sql}")
        if not apply:
            print('[DRY] 未执行；加 --apply 生效')
            return 0

        started = time.time()
        for name, sql in stmts:
            step = time.time()
            try:
                cur.execute(sql)
            except psycopg2.Error as exc:
                print(f'[FAIL] {name} 执行失败'
                      f'（pgcode={getattr(exc, "pgcode", None)}）：{exc}',
                      flush=True)
                if _report_invalid(cur):
                    return 2
                return 1
            print(f'[OK] {name} 完成（{time.time() - step:.2f}s）')
        _verify(cur)
        print(f'[APPLY] {label}完成，耗时 {time.time() - started:.2f}s')
        return 0
    finally:
        conn.close()


def _rollback_statements(cur):
    stmts = []
    for name, _col, _ddl, drop_ddl in INDEXES:
        if _index_state(cur, name) is not None:
            stmts.append((name, drop_ddl))
    return stmts


def main():
    ap = argparse.ArgumentParser(
        description='audios 补 md5 / file_path 局部索引（INT-2280）')
    ap.add_argument('--apply', action='store_true',
                    help='执行（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true',
                    help='删除两条索引（默认 dry-run，配 --apply 执行）')
    args = ap.parse_args()

    conn = _connect()
    try:
        cur = conn.cursor()
        if not _precheck(cur):
            return 0
    finally:
        conn.close()

    if args.rollback:
        return _run(args.apply, _rollback_statements, '回滚')
    return _run(args.apply, _plan, '迁移')


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""迁移脚本：核心查询路径补索引（任务/用例/评估/维度）

背景（2026-11-21 查询性能排查）：
    任务、用例、音频、报告、实验室等列表页接口慢，抽检主库后确认多条高频
    查询路径没有可用索引，逐条全表顺序扫描：

    - ``test_results.task_id``：用例结果按任务拉取（``task_read_model_case_results``
      的 list_cases / 用例详情），表无 task_id 索引；
    - ``test_result_dimensions.dimension_id``：评估维度结果按维度批量反查
      （``evaluation_dimension_repository``），仅 ``idx_trd_round`` 覆盖
      test_result_id 前缀，dimension_id 侧无索引；
    - ``test_cases.algorithm_type``：用例列表按算法类型过滤
      （``/api/v1/testcases?algorithm_type=...``），无索引；
    - ``dimensions.parent_dimension_id``：维度树 BFS 逐层查询
      （``evaluation_repository.list_descendant_ids``），无索引。

DDL 与各服务 ORM 模型的列定义对齐：
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_test_results_task_id
        ON test_results (task_id)
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trd_dimension_id
        ON test_result_dimensions (dimension_id)
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_test_cases_algorithm_type_active
        ON test_cases (algorithm_type) WHERE deleted = false
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dimensions_parent_dimension_id
        ON dimensions (parent_dimension_id)

设计取舍：
- ``idx_test_cases_algorithm_type_active`` 用局部索引（``WHERE deleted = false``）：
  仓库查询全部带软删过滤，局部索引可被 planner 命中且体积更小。
- 其余三列单列 btree：覆盖当前查询路径（等值/前缀），不做多列复合，
  避免与既有索引（idx_trd_round / idx_test_cases_group_id_active 等）冗余。

``CREATE INDEX CONCURRENTLY`` 不能在事务块里执行：本脚本用 autocommit 连接，
每条 DDL 独立提交，失败不会连带回滚其它索引。

执行语义：
- 默认 dry-run：打印待执行 DDL、索引现状，不改库；
- ``--apply``：autocommit 下逐条执行（CONCURRENTLY，不长时间阻塞写）；
- ``--rollback``：``DROP INDEX CONCURRENTLY IF EXISTS`` 各索引；
- 幂等：索引已存在即 SKIP；CONCURRENTLY 中途失败会留下 indisvalid=false 的
  **invalid 索引**，本脚本检出后打印需人工执行的 ``DROP INDEX CONCURRENTLY``
  命令并以非零码退出（否则 IF NOT EXISTS 会一直跳过、索引永远修不好）。

用法：
    python scripts/migrations/202611/add_query_perf_indexes.py            # 预览
    python scripts/migrations/202611/add_query_perf_indexes.py --apply    # 执行
    python scripts/migrations/202611/add_query_perf_indexes.py --rollback --apply
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

# (索引名, 表名, 建索引 DDL, 回滚 DDL)
INDEXES = (
    (
        'idx_test_results_task_id', 'test_results',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_test_results_task_id '
        'ON test_results (task_id)',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_test_results_task_id',
    ),
    (
        'idx_trd_dimension_id', 'test_result_dimensions',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trd_dimension_id '
        'ON test_result_dimensions (dimension_id)',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_trd_dimension_id',
    ),
    (
        'idx_test_cases_algorithm_type_active', 'test_cases',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_test_cases_algorithm_type_active '
        'ON test_cases (algorithm_type) WHERE deleted = false',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_test_cases_algorithm_type_active',
    ),
    (
        'idx_dimensions_parent_dimension_id', 'dimensions',
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dimensions_parent_dimension_id '
        'ON dimensions (parent_dimension_id)',
        'DROP INDEX CONCURRENTLY IF EXISTS idx_dimensions_parent_dimension_id',
    ),
)


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_query_perf_idx')
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


def _table_exists(cur, table):
    cur.execute('SELECT to_regclass(%s)', (table,))
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


def _precheck(cur):
    """只读现状：各表是否存在、索引当前状态。"""
    missing_table = False
    for name, table, _ddl, _rb in INDEXES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 不存在（空库请先 create_all）')
            missing_table = True
            continue
        state = _index_state(cur, name)
        if state is None:
            print(f'[INFO] {name}（{table}）: 不存在')
        else:
            flag = 'OK' if state['valid'] else 'INVALID（CONCURRENTLY 中途失败）'
            print(f'[INFO] {name}: {flag} :: {state["def"]}')
    return not missing_table


def _invalid_indexes(cur):
    return [name for name, _t, _d, _r in INDEXES
            if (_index_state(cur, name) or {}).get('valid') is False]


def _plan(cur):
    """待执行的建索引 DDL（已存在且有效即跳过）。"""
    stmts = []
    for name, _t, ddl, _rb in INDEXES:
        state = _index_state(cur, name)
        if state is None:
            stmts.append((name, ddl))
        else:
            print(f'[SKIP] {name} 已存在')
    return stmts


def _verify(cur):
    for name, _t, _ddl, _rb in INDEXES:
        state = _index_state(cur, name)
        if state is None:
            print(f'[VERIFY] {name}: 不存在')
        else:
            print(f'[VERIFY] {name}: {"有效" if state["valid"] else "INVALID"} '
                  f':: {state["def"]}')


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
        if not _precheck(cur):
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
    for name, _t, _ddl, drop_ddl in INDEXES:
        if _index_state(cur, name) is not None:
            stmts.append((name, drop_ddl))
    return stmts


def main():
    ap = argparse.ArgumentParser(
        description='核心查询路径补索引（test_results/test_result_dimensions/'
                    'test_cases/dimensions）')
    ap.add_argument('--apply', action='store_true',
                    help='执行（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true',
                    help='删除索引（默认 dry-run，配 --apply 执行）')
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

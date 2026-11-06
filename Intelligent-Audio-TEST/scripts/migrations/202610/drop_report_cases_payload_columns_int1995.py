# -*- coding: utf-8 -*-
"""迁移脚本：DROP report_cases 九字段 payload 列 + idx_report_cases_category + VACUUM FULL（INT-1995 / 档4 M1）

背景（档4 报告用例快照外置分阶段，设计见
`doc/功能设计文档/01_测试执行/10_报告用例快照外置.md` §6.2 / §7）：
R1（INT-1994）建 ``report_case_snapshots`` + 4 个指针列 + 双写 + 读侧解引用 +
回填；**M1（本卡）删九字段 payload 列**。``report_cases`` 是报告级用例行，主库
实测 33,925 行 / 258MB，九字段 payload 去重后仅 10,843 个不同值（已外置快照表）。

九字段边界（设计文档 §2）：``name`` / ``description`` / ``category`` / ``tags`` /
``metrics`` / ``results`` / ``audios`` / ``reference_params`` / ``algorithm_results``。
**行上保留** ``id`` / ``report_id`` / ``test_case_id`` / ``algorithm_type`` /
``logs`` 五列（前两个是键；``test_case_id`` 有 SQL 投影、``algorithm_type`` 有 SQL
谓词、``logs`` 体积可忽略）与 4 个指针列。因此 ``idx_report_cases_report_id`` /
``idx_report_cases_test_case_id`` 不动；``idx_report_cases_category`` 随 ``category``
一起删（该索引无其它用途）。

PG 16 的关键事实（**不按此执行会白干**）：``ALTER TABLE ... DROP COLUMN`` 只改
系统目录、**不重写数据**，被删列的 TOAST 块要等行重写才释放——只 DROP 不
``VACUUM FULL``，磁盘一个字节都不会少。本脚本因此是 ``DROP → VACUUM FULL →
ANALYZE`` 三步，并打印执行前后 ``pg_total_relation_size`` / ``pg_relation_size`` /
``pg_table_size`` / TOAST 关系大小。

前置门禁（缺一不可，``--apply`` 全部通过才动手；``--gate`` 只查不写）：

1. **回填门禁归零**：``snapshot_sha256 IS NULL`` 的行数为 0，且无悬空指针
   （``snapshot_sha256`` 引用的快照行不存在）——R1 回填 / 门禁验收的落点。
2. **读路径已切快照**：``REPORT_CASE_SNAPSHOT_SOURCE=snapshot`` 四类读路径已验证
   （DB 里查不出来，由操作人用 ``--confirm-read-path`` 显式确认）。
3. **近 N 小时无内容列写入**：窗口内九字段内容列必须全为 NULL——证明 M1 写路径
   （不再写内容列）已上线。窗口内**没有任何行**时无法证明，须加
   ``--ack-no-recent-traffic`` 明确承认（主库执行建议加 ``--strict-24h``）。
4. **VACUUM FULL 前留逻辑备份**：M1 之后无列可回退，切换前必须具备「按备份恢复」
   预案；操作人须以 ``--confirm-backup`` 确认已留一份 ``report_cases`` 逻辑备份。

锁与窗口（卡面风险项）：

- 执行前查 ``pg_stat_activity``：存在 **idle in transaction** / 持锁阻塞别人的会话
  就拒绝执行（锁队列会把 report_service 的 gRPC 拖成 400/60s）；确认无关可加
  ``--ignore-lock-risks``。
- ``ALTER`` 只拿一次 ACCESS EXCLUSIVE，``lock_timeout`` 默认 5s
  （``--lock-timeout-ms``）——拿不到即失败退出、打印持锁者，**绝不排队**。
- ``VACUUM FULL`` 需要额外约一个表大小的临时磁盘（33,925 行 / 约 258MB）并全程持
  ACCESS EXCLUSIVE → 必须有低峰窗口；``--no-vacuum`` 只删列不回收（不建议）。
- ``VACUUM`` 不能跑在事务块里，本脚本全程 autocommit。

幂等性：列已不存在即 ``[SKIP]``，不重复 DROP；此时 ``--apply`` 会按 TOAST 体积
判断上次 ``VACUUM FULL`` 是否真的跑完——TOAST 仍偏大（被 ``statement_timeout`` /
``lock_timeout`` 顶掉，或上次用了 ``--no-vacuum``）就 **exit 3** 并明确要求
``--force-vacuum`` 重跑，绝不静默成功；``--gate`` 在列已删时仍打印门禁（N/A）与
指针分布，是删列后唯一可复现的复查命令。

用法::

    # 只查门禁与体积（只读，可重复执行）
    python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --gate
    # 预览（打印将执行的 DDL / VACUUM 与前后体积口径，不动库）
    python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py
    # 执行（门禁全绿 + 操作人确认读路径 / 备份）
    python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --apply \
        --confirm-read-path --confirm-backup --strict-24h
    # VACUUM FULL 被超时 / 锁顶掉之后的续跑（列已删，只重试压缩）
    python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --apply \
        --force-vacuum --confirm-read-path --confirm-backup --strict-24h
    # 删列后的复查（只读；照样打印门禁 N/A 与指针分布）
    python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --gate

环境：``DATABASE_URL``（或 ``DATABASE_URI``）。纯 DROP 路径不需要 OSS。

退出码：0 完成；1 门禁未通过；2 未拿到锁；3 执行后校验失败（含列已删但 TOAST
未回收）；4 前置确认缺失。

**不纳入 ``docker/db_bootstrap_entrypoint.py`` 引导链**：本步是破坏性 DDL +
``VACUUM FULL``，须低峰独立窗口 + 备份预案，由部署卡单独执行（INT-1995 卡面硬约束）。
"""
import argparse
import os
import sys
import time

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

TABLE = 'report_cases'
SNAPSHOT_TABLE = 'report_case_snapshots'
# 九字段 payload 列（快照边界，与 report_case_snapshot_store.PAYLOAD_FIELDS 一致）
PAYLOAD_COLUMNS = (
    'name', 'description', 'category', 'tags', 'metrics', 'results',
    'audios', 'reference_params', 'algorithm_results',
)
# 随 category 列一起删的索引（无其它用途）
CATEGORY_INDEX = 'idx_report_cases_category'

DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 30000
DEFAULT_VACUUM_TIMEOUT_MS = 900000
DEFAULT_RECENT_HOURS = 24
# 列已删后 TOAST 残留判据：report_cases 只剩 logs(73KB) / test_case_id 等小字段，
# VACUUM FULL 后 TOAST 应接近 0；残留超过 16MB 不可能是正常形态（删列前的量级是
# 200MB+），只能是 VACUUM FULL 没跑完 / 上次用了 --no-vacuum。
DEFAULT_VACUUM_RESIDUAL_BYTES = 16 * 1024 * 1024


# ------------------------------------------------------------------ 连接 / 元数据
def _int_env(name, default):
    """读取正整数环境变量，非法值回落默认。"""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_int1995')


def _table_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (TABLE,))
    return cur.fetchone() is not None


def _existing_columns(cur) -> dict:
    cur.execute(
        'SELECT column_name, data_type FROM information_schema.columns '
        'WHERE table_name = %s', (TABLE,))
    return {row[0]: row[1] for row in cur.fetchall()}


def _pending_columns(columns: dict) -> list:
    return [name for name in PAYLOAD_COLUMNS if name in columns]


def _sizes(cur) -> dict:
    """表体积四指标（字节）。TOAST 关系不存在（表无 toast）时记 0。"""
    cur.execute(
        'SELECT pg_total_relation_size(%s), pg_relation_size(%s), '
        'pg_table_size(%s), coalesce((SELECT pg_total_relation_size(reltoastrelid) '
        'FROM pg_class WHERE oid = %s::regclass), 0)',
        (TABLE, TABLE, TABLE, TABLE))
    total, heap, table_size, toast = cur.fetchone()
    return {
        'pg_total_relation_size': int(total or 0),
        'pg_relation_size': int(heap or 0),
        'pg_table_size': int(table_size or 0),
        'toast_size': int(toast or 0),
    }


def _mb(value: int) -> str:
    return f'{value / 1024.0 / 1024.0:.2f} MB'


def vacuum_still_pending(sizes: dict,
                         threshold_bytes: int = DEFAULT_VACUUM_RESIDUAL_BYTES) -> bool:
    """列已删但 TOAST 仍偏大 → 上次 VACUUM FULL 没跑成功（判据同上一条注释）。"""
    return int(sizes.get('toast_size') or 0) > int(threshold_bytes)


def print_delta(before: dict, after: dict) -> None:
    """前后体积差（卡面验收：下降幅度应与 TOAST 体积相符）。"""
    print(f'[DELTA] {TABLE}:')
    for key in ('pg_total_relation_size', 'pg_relation_size',
                'pg_table_size', 'toast_size'):
        delta = after[key] - before[key]
        print(f'  {key:<24} {before[key]} B → {after[key]} B '
              f'（{"+ " if delta >= 0 else "- "}{_mb(abs(delta))}）')


def print_sizes(title: str, sizes: dict) -> None:
    print(f'[{title}] {TABLE}:')
    print(f'  pg_total_relation_size = {sizes["pg_total_relation_size"]} B '
          f'({_mb(sizes["pg_total_relation_size"])})')
    print(f'  pg_relation_size       = {sizes["pg_relation_size"]} B '
          f'({_mb(sizes["pg_relation_size"])})')
    print(f'  pg_table_size          = {sizes["pg_table_size"]} B '
          f'({_mb(sizes["pg_table_size"])})')
    print(f'  TOAST 关系大小          = {sizes["toast_size"]} B '
          f'({_mb(sizes["toast_size"])})')


# ------------------------------------------------------------------ 门禁
def gate_counts(cur, columns: dict) -> dict:
    """回填门禁（卡面前置 1）：没指针 / 指针悬空的行数。

    列已删（M1 之后）→ 该组为 ``None``（N/A），不再拼已不存在的列名。
    """
    result = {
        'no_pointer': None,
        'dangling': None,
    }
    if 'snapshot_sha256' not in columns:
        return result
    cur.execute(
        f'SELECT count(*) FROM {TABLE} WHERE snapshot_sha256 IS NULL')
    result['no_pointer'] = int(cur.fetchone()[0])
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (SNAPSHOT_TABLE,))
    if cur.fetchone() is None:
        # 快照表不存在：所有有指针的行都悬空
        cur.execute(
            f'SELECT count(*) FROM {TABLE} WHERE snapshot_sha256 IS NOT NULL')
        result['dangling'] = int(cur.fetchone()[0])
    else:
        cur.execute(
            f'SELECT count(*) FROM {TABLE} c '
            f'WHERE c.snapshot_sha256 IS NOT NULL AND NOT EXISTS ('
            f'  SELECT 1 FROM {SNAPSHOT_TABLE} s WHERE s.sha256 = c.snapshot_sha256)')
        result['dangling'] = int(cur.fetchone()[0])
    return result


def recent_write_violations(cur, columns: dict, hours: int = DEFAULT_RECENT_HOURS) -> dict:
    """近 N 小时内容列非空的行数（卡面前置 3）。

    返回 ``{'rows': 窗口内行数, 'violations': 内容列非空行数, 'window': hours}``。
    窗口内无行时 ``rows == 0``——「没有流量」本身不能证明「新写入都不写内容列」，
    由 ``--ack-no-recent-traffic`` 承认。
    """
    present = [name for name in PAYLOAD_COLUMNS if name in columns]
    cur.execute(
        f'SELECT count(*) FROM {TABLE} '
        f'WHERE created_at >= now() - interval \'{int(hours)} hours\'')
    rows = int(cur.fetchone()[0])
    if not present:
        return {'rows': rows, 'violations': None, 'window': hours}
    # 逐列 IS NOT NULL 判空（COALESCE 跨 varchar/jsonb 类型无法匹配）
    any_non_null = ' OR '.join(f'{name} IS NOT NULL' for name in present)
    cur.execute(
        f'SELECT count(*) FROM {TABLE} '
        f'WHERE created_at >= now() - interval \'{int(hours)} hours\' '
        f'AND ({any_non_null})')
    violations = int(cur.fetchone()[0])
    return {'rows': rows, 'violations': violations, 'window': hours}


def pointer_stats(cur, columns: dict) -> dict:
    """指针列分布（删列后唯一的完整性判据：有 sha 无 uri / 有 uri 无 sha 均为断链）。"""
    stats = {'with_sha': None, 'sha_without_uri': None, 'uri_without_sha': None}
    if 'snapshot_sha256' not in columns or 'snapshot_uri' not in columns:
        return stats
    cur.execute(
        f'SELECT count(*) FILTER (WHERE snapshot_sha256 IS NOT NULL), '
        f'count(*) FILTER (WHERE snapshot_sha256 IS NOT NULL '
        f'                 AND snapshot_uri IS NULL), '
        f'count(*) FILTER (WHERE snapshot_uri IS NOT NULL '
        f'                 AND snapshot_sha256 IS NULL) '
        f'FROM {TABLE}')
    with_sha, sha_no_uri, uri_no_sha = cur.fetchone()
    return {
        'with_sha': int(with_sha or 0),
        'sha_without_uri': int(sha_no_uri or 0),
        'uri_without_sha': int(uri_no_sha or 0),
    }


def lock_risks(cur) -> list:
    """执行前的锁风险会话（卡面风险项）：idle in transaction / 正等锁的后端。"""
    cur.execute(
        "SELECT pid, state, wait_event_type, left(coalesce(query, ''), 80) "
        'FROM pg_stat_activity '
        'WHERE datname = current_database() '
        "  AND pid <> pg_backend_pid() "
        "  AND (state = 'idle in transaction' "
        "       OR state = 'idle in transaction (aborted)' "
        "       OR wait_event_type = 'Lock') "
        'ORDER BY pid')
    return [tuple(row) for row in cur.fetchall()]


def run_gates(cur, columns: dict, args, require_confirmations: bool = True) -> list:
    """跑全部可机器校验的门禁，返回失败项（空 = 全绿）。

    ``require_confirmations=False``：只读复查（``--gate``）用——操作人确认项照常
    打印提示，但不计入失败（复查的人可能没有当时的确认语境）。
    """
    failures = []

    gate = gate_counts(cur, columns)
    for label, missing in gate.items():
        if missing is None:
            print(f'[GATE-1] {label}: 指针列已删 / 快照表不存在 → N/A')
        elif missing == 0:
            print(f'[GATE-1] {label}: 0 → OK')
        else:
            print(f'[GATE-1] {label}: {missing} → FAIL（先跑 R1 回填 --gate 归零）')
            failures.append(f'回填门禁未归零：{label}={missing}')

    recent = recent_write_violations(cur, columns)
    if recent['violations'] is None:
        print(f'[GATE-3] 内容列已删 → N/A（窗口内 {recent["rows"]} 行；'
              f'内容列形态已不存在）')
    elif recent['rows'] == 0:
        print(f'[GATE-3] 近 {recent["window"]}h 无用例行 → 无法证明「新写入都不写内容列」')
        if getattr(args, 'strict_24h', False) and not getattr(args, 'ack_no_recent_traffic', False):
            failures.append(
                f'近 {recent["window"]}h 无用例行，--strict-24h 要求有流量证据')
        elif not getattr(args, 'ack_no_recent_traffic', False):
            failures.append(
                f'近 {recent["window"]}h 无用例行；确认为空跑窗口请加 --ack-no-recent-traffic')
    elif recent['violations'] == 0:
        print(f'[GATE-3] 近 {recent["window"]}h 内容列非空 0 → OK'
              f'（窗口内 {recent["rows"]} 行全部只写指针）')
    else:
        print(f'[GATE-3] 近 {recent["window"]}h 仍有 {recent["violations"]} 行写内容列 → FAIL'
              f'（M1 写路径未生效，先部署不再写内容列的代码再执行）')
        failures.append(f'近 {recent["window"]}h 仍有内容列写入：{recent["violations"]}')

    stats = pointer_stats(cur, columns)
    if stats['with_sha'] is not None:
        if stats['sha_without_uri'] or stats['uri_without_sha']:
            print(f'[GATE-2] 指针断链（sha 无 uri {stats["sha_without_uri"]} / '
                  f'uri 无 sha {stats["uri_without_sha"]}）→ FAIL')
            failures.append('指针断链')
        else:
            print(f'[GATE-2] 指针 {stats["with_sha"]} 行、无断链 → OK')

    if not getattr(args, 'confirm_read_path', False):
        print('[GATE-2] 未确认读路径已切快照（--confirm-read-path）')
        if require_confirmations:
            failures.append('未确认读路径已切快照（--confirm-read-path）')
    else:
        print('[GATE-2] 读路径已由操作人确认切快照（--confirm-read-path）')

    if not getattr(args, 'confirm_backup', False):
        print('[GATE-4] 未确认 report_cases 逻辑备份（--confirm-backup）')
        if require_confirmations:
            failures.append('未确认 report_cases 逻辑备份（--confirm-backup）')
    else:
        print('[GATE-4] 逻辑备份已由操作人确认（--confirm-backup）')

    return failures


# ------------------------------------------------------------------ 执行步骤
def build_drop_ddl(pending) -> str:
    """把待删列合成**一条** ALTER TABLE（只拿一次 ACCESS EXCLUSIVE 锁）。"""
    parts = [f'DROP COLUMN IF EXISTS {name}' for name in pending]
    return f'ALTER TABLE {TABLE} ' + ', '.join(parts)


def _blocking_pids(cur):
    """当前持锁阻塞别人的后端 pid（诊断用）。"""
    cur.execute(
        'SELECT DISTINCT l.pid FROM pg_locks l '
        'JOIN pg_stat_activity a ON a.pid = l.pid '
        'WHERE l.granted AND l.relation = %s::regclass AND a.pid <> pg_backend_pid()',
        (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _waiting_lock_pids(cur):
    cur.execute(
        'SELECT pid FROM pg_locks WHERE NOT granted AND relation = %s::regclass', (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _run_ddl(cur, ddl, lock_timeout_ms, statement_timeout_ms=None):
    """执行 DDL；拿不到锁抛 SystemExit(2)，绝不排队。

    ``statement_timeout_ms`` 只罩住 DDL 本身（拿到锁后卡住也会被取消），跑完立刻
    复位成 0，避免把 VACUUM FULL 的预算一起改掉。
    """
    cur.execute(f'SET lock_timeout = {int(lock_timeout_ms)}')
    if statement_timeout_ms:
        cur.execute(f'SET statement_timeout = {int(statement_timeout_ms)}')
    started = time.monotonic()
    try:
        cur.execute(ddl)
    except psycopg2.errors.LockNotAvailable:
        print(f'[FAIL] {lock_timeout_ms}ms 内未拿到 ACCESS EXCLUSIVE 锁；'
              f'持锁者 pid={_blocking_pids(cur)} 等锁者 pid={_waiting_lock_pids(cur)}')
        raise SystemExit(2)
    except psycopg2.errors.QueryCanceled:
        print(f'[FAIL] DDL 超过 statement_timeout={statement_timeout_ms}ms 未完成'
              f'（列可能已改了一半——DROP 幂等，重跑会继续）')
        raise SystemExit(3)
    finally:
        if statement_timeout_ms:
            try:
                cur.execute('SET statement_timeout = 0')
            except Exception:  # noqa: BLE001  连接已坏时别再掩盖原始错误
                pass
    elapsed_ms = int((time.monotonic() - started) * 1000)
    print(f'[APPLY] {ddl} → 完成，耗时 {elapsed_ms}ms'
          f'（lock_timeout={lock_timeout_ms}ms 未触发 = 等锁低于预算）')


def drop_columns(conn, pending, lock_timeout_ms, statement_timeout_ms=None) -> None:
    """删列 + 删 category 索引。索引先行（列删时 PG 也会连带，显式删更可控）。"""
    cur = conn.cursor()
    _run_ddl(cur, f'DROP INDEX IF EXISTS {CATEGORY_INDEX}',
             lock_timeout_ms, statement_timeout_ms)
    if pending:
        _run_ddl(cur, build_drop_ddl(pending), lock_timeout_ms, statement_timeout_ms)
    cur.close()


def vacuum_full(conn, vacuum_timeout_ms) -> int:
    """VACUUM FULL：重写表、真正释放被删列的 TOAST；不能进事务块（autocommit）。"""
    cur = conn.cursor()
    cur.execute(f'SET statement_timeout = {int(vacuum_timeout_ms)}')
    started = time.monotonic()
    try:
        cur.execute(f'VACUUM FULL {TABLE}')
    except psycopg2.errors.LockNotAvailable:
        print('[FAIL] VACUUM FULL 未拿到 ACCESS EXCLUSIVE 锁（锁队列风险），已中止')
        raise SystemExit(2)
    except psycopg2.errors.QueryCanceled:
        print(f'[FAIL] VACUUM FULL 超过 statement_timeout={vacuum_timeout_ms}ms 未完成；'
              f'表已重写一部分，磁盘不会退回去——请在窗口内重跑 '
              f'`--apply --force-vacuum`（列已删，只会重试 VACUUM FULL）')
        raise SystemExit(3)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    cur.close()
    print(f'[APPLY] VACUUM FULL {TABLE} 完成，耗时 {elapsed_ms}ms')
    return elapsed_ms


def analyze(conn) -> None:
    cur = conn.cursor()
    started = time.monotonic()
    cur.execute(f'ANALYZE {TABLE}')
    print(f'[APPLY] ANALYZE {TABLE} 完成，耗时 {int((time.monotonic() - started) * 1000)}ms')
    cur.close()


# ------------------------------------------------------------------ 列已删后的重跑 / 复查
def _after_drop(conn, cur, columns, args, before_sizes, vacuum_timeout_ms) -> int:
    """DROP 已完成时的路径（幂等重跑 + 删列后复查）。

    - ``--gate``（只读）：照常打印门禁（列已删 → N/A）与指针分布——这是删列后唯一
      可复现的复查命令；不查锁风险、不把「未确认」判成失败。
    - ``--apply``：门禁按 ``--apply`` 口径全量判定；TOAST 仍偏大说明上次 VACUUM FULL
      没跑成功 → exit 3 并明确要求 ``--force-vacuum``（绝不静默 exit 0）。
    - ``--apply --force-vacuum``：补跑一次 VACUUM FULL + ANALYZE，打印前后体积与差值。
    """
    read_only = not args.apply
    failures = run_gates(cur, columns, args, require_confirmations=not read_only)
    if failures:
        print(f'[FAIL] 门禁未通过（{len(failures)} 项），不做任何改动：')
        for item in failures:
            print(f'  - {item}')
        return 1

    if read_only:
        print('[SKIP] 只读复查：列已删，不重复 DROP / 不重复 VACUUM；'
              '磁盘回收看上面的体积口径（AFTER / DELTA 在 --apply 日志里）')
        return 0

    residual = int(before_sizes.get('toast_size') or 0)
    if args.no_vacuum:
        print('[SKIP] --no-vacuum：不重复 VACUUM FULL（磁盘一个字节都不会少）')
        return 0
    if not args.force_vacuum:
        if vacuum_still_pending(before_sizes):
            print(f'[FAIL] 列已删但 TOAST 未回收（{_mb(residual)}；VACUUM FULL 后应接近 0）'
                  f'——上次 VACUUM FULL 可能被 statement_timeout / lock_timeout 顶掉，'
                  f'或用了 --no-vacuum。请加 --force-vacuum 在窗口内重跑')
            return 3
        print(f'[SKIP] TOAST 已回收（{_mb(residual)}），无需重跑 VACUUM FULL'
              f'（--force-vacuum 可强制再压一次）')
        return 0

    risks = lock_risks(cur)
    if risks:
        print(f'[LOCK] 发现 {len(risks)} 个高锁风险会话：')
        for pid, state, wait_type, query in risks:
            print(f'  pid={pid} state={state} wait={wait_type} query={query}')
        if not args.ignore_lock_risks:
            print('[FAIL] 先清掉 idle in transaction / 等锁会话再执行（卡面风险项）；'
                  '确认无关加 --ignore-lock-risks')
            return 1
    else:
        print('[LOCK] 无 idle in transaction / 等锁会话 → OK')

    print(f'[APPLY] --force-vacuum：列已删，重跑一次 VACUUM FULL'
          f'（statement_timeout={vacuum_timeout_ms}ms）')
    vacuum_full(conn, vacuum_timeout_ms)
    analyze(conn)
    after = _sizes(cur)
    print_sizes('AFTER', after)
    print_delta(before_sizes, after)
    if vacuum_still_pending(after):
        print(f'[FAIL] VACUUM FULL 之后 TOAST 仍有 {_mb(after["toast_size"])}，'
              f'磁盘回收未达预期')
        return 3
    print('[VERIFY] 磁盘已回收（AFTER / DELTA 为准）')
    return 0


# ------------------------------------------------------------------ 主流程
def migrate(args):
    lock_timeout_ms = args.lock_timeout_ms or _int_env(
        'DB_MIGRATION_LOCK_TIMEOUT_MS', DEFAULT_LOCK_TIMEOUT_MS)
    statement_timeout_ms = args.statement_timeout_ms or _int_env(
        'DB_MIGRATION_STATEMENT_TIMEOUT_MS', DEFAULT_STATEMENT_TIMEOUT_MS)
    vacuum_timeout_ms = args.vacuum_timeout_ms or _int_env(
        'DB_MIGRATION_VACUUM_TIMEOUT_MS', DEFAULT_VACUUM_TIMEOUT_MS)

    conn = _connect()
    try:
        conn.autocommit = True
        cur = conn.cursor()

        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return 0

        columns = _existing_columns(cur)
        pending = _pending_columns(columns)
        before_sizes = _sizes(cur)
        print_sizes('BEFORE', before_sizes)

        if not pending and CATEGORY_INDEX not in _existing_indexes(cur):
            print(f'[SKIP] 九列均已不存在（{", ".join(PAYLOAD_COLUMNS)}）'
                  f'且 {CATEGORY_INDEX} 已删——M1 的 DROP 已完成')
            return _after_drop(conn, cur, columns, args, before_sizes,
                               vacuum_timeout_ms)

        if CATEGORY_INDEX not in _existing_indexes(cur):
            print(f'[SKIP] 索引 {CATEGORY_INDEX} 已删（列删时 PG 连带）')
        print(f'[PLAN] 待删列：{", ".join(pending)}（json 列，TOAST 需 VACUUM FULL 才释放）')

        risks = lock_risks(cur)
        if risks:
            print(f'[LOCK] 发现 {len(risks)} 个高锁风险会话：')
            for pid, state, wait_type, query in risks:
                print(f'  pid={pid} state={state} wait={wait_type} query={query}')
            if args.apply and not args.ignore_lock_risks:
                print('[FAIL] 先清掉 idle in transaction / 等锁会话再执行（卡面风险项）；'
                      '确认无关加 --ignore-lock-risks')
                return 1
            if not args.apply:
                print('[WARN] 本次只读（--gate / dry-run），不取 ACCESS EXCLUSIVE、继续')
        else:
            print('[LOCK] 无 idle in transaction / 等锁会话 → OK')

        # 只读（--gate / dry-run）不把「未确认」判成失败：这是给人看的门禁报告，
        # 真正动手（--apply）时才硬拦。
        failures = run_gates(cur, columns, args,
                             require_confirmations=bool(getattr(args, 'apply', False)))
        if failures:
            print(f'[FAIL] 门禁未通过（{len(failures)} 项），不做任何改动：')
            for item in failures:
                print(f'  - {item}')
            return 1

        if not getattr(args, 'confirm_read_path', False) and args.apply:
            print('[FAIL] 缺 --confirm-read-path：卡面前置 2（读路径已切快照）'
                  'DB 里查不出来，必须由操作人确认')
            return 4
        if not getattr(args, 'confirm_backup', False) and args.apply:
            print('[FAIL] 缺 --confirm-backup：卡面前置 4（VACUUM FULL 前须留一份 '
                  'report_cases 逻辑备份；M1 之后无列可回退）')
            return 4

        print(f'[PLAN] 步骤：① DROP INDEX IF EXISTS {CATEGORY_INDEX}'
              f'（lock_timeout={lock_timeout_ms}ms）')
        print(f'[PLAN] 步骤：② {build_drop_ddl(pending)}'
              f'（lock_timeout={lock_timeout_ms}ms）')
        if args.no_vacuum:
            print('[PLAN] ③ 跳过 VACUUM FULL（--no-vacuum：只改目录，磁盘一个字节都不会少）')
        else:
            print(f'[PLAN] ③ VACUUM FULL {TABLE}（AccessExclusiveLock，'
                  f'需额外约一个表大小的临时磁盘；statement_timeout={vacuum_timeout_ms}ms）')
        print('[PLAN] ④ ANALYZE 刷新统计信息')

        if not args.apply:
            print('[DRY] 未执行；--apply 时按上述步骤落地')
            return 0

        drop_columns(conn, pending, lock_timeout_ms, statement_timeout_ms)
        columns = _existing_columns(cur)
        if _pending_columns(columns):
            print('[FAIL] DROP 后仍有列存在 → 校验失败')
            return 3
        print('[VERIFY] 九列已不存在 → OK')

        if not args.no_vacuum:
            vacuum_full(conn, vacuum_timeout_ms)
        analyze(conn)

        after = _sizes(cur)
        print_sizes('AFTER', after)
        print_delta(before_sizes, after)
        print(f'[VERIFY] 删列后门禁：{gate_counts(cur, columns)}'
              f'（"no_pointer"/"dangling" 为 None = 列已删，M1 完成）')
        print(f'[VERIFY] 指针分布：{pointer_stats(cur, columns)}')
        if not args.no_vacuum and vacuum_still_pending(after):
            print(f'[FAIL] VACUUM FULL 完成后 TOAST 仍有 {_mb(after["toast_size"])}，'
                  f'磁盘回收未达预期（列已删、可 --force-vacuum 重跑）')
            return 3
        print('[VERIFY] 磁盘回收以上面 AFTER / DELTA 为准')
        return 0
    finally:
        conn.close()


def _existing_indexes(cur) -> set:
    """当前表上的索引名集合（判断 category 索引是否已删）。"""
    cur.execute(
        'SELECT indexname FROM pg_indexes WHERE tablename = %s', (TABLE,))
    return {row[0] for row in cur.fetchall()}


def build_parser() -> argparse.ArgumentParser:
    """命令行开关（``main`` 与单测共用一处，防开关名漂移）。"""
    ap = argparse.ArgumentParser(
        description='DROP report_cases 九字段 payload 列 + idx_report_cases_category'
                    ' + VACUUM FULL + ANALYZE（INT-1995 / M1）')
    ap.add_argument('--apply', action='store_true',
                    help='执行（默认 dry-run：只打印门禁、DDL 与体积口径）')
    ap.add_argument('--gate', action='store_true',
                    help='只跑门禁与体积查询（只读；列已删时仍打印门禁与指针分布）')
    ap.add_argument('--confirm-read-path', action='store_true',
                    help='确认读路径已切 REPORT_CASE_SNAPSHOT_SOURCE=snapshot（前置 2）')
    ap.add_argument('--confirm-backup', action='store_true',
                    help='确认 VACUUM FULL 前已留 report_cases 逻辑备份（前置 4）')
    ap.add_argument('--ack-no-recent-traffic', action='store_true',
                    help='承认近 24h 无用例行（空跑窗口）——否则前置 3 不算通过')
    ap.add_argument('--strict-24h', action='store_true',
                    help='要求近 24h 必须有流量证据（主库执行建议加）')
    ap.add_argument('--no-vacuum', action='store_true',
                    help='只删列不 VACUUM FULL（不回收磁盘，不建议）')
    ap.add_argument('--force-vacuum', action='store_true',
                    help='列已删除时重跑一次 VACUUM FULL（VACUUM FULL 失败后的续跑路径）')
    ap.add_argument('--ignore-lock-risks', action='store_true',
                    help='忽略 idle in transaction / 等锁会话告警（确认无关时用）')
    ap.add_argument('--lock-timeout-ms', type=int, default=0)
    ap.add_argument('--statement-timeout-ms', type=int, default=0,
                    help='DDL 语句超时（默认 %d ms / DB_MIGRATION_STATEMENT_TIMEOUT_MS）'
                         % DEFAULT_STATEMENT_TIMEOUT_MS)
    ap.add_argument('--vacuum-timeout-ms', type=int, default=0)
    return ap


def main():
    args = build_parser().parse_args()

    if args.gate:
        args.apply = False

    try:
        code = migrate(args)
    except SystemExit as exc:  # 锁超时等已打印原因
        code = exc.code if isinstance(exc.code, int) else 1
    sys.exit(code)


if __name__ == '__main__':
    main()

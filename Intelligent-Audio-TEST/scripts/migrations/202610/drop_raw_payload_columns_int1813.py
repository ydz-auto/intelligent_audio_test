# -*- coding: utf-8 -*-
"""迁移脚本：DROP 原始报文 JSON 两列 + VACUUM FULL + ANALYZE（INT-1813 / M1）

背景（档3 分阶段落地，设计见 `doc/功能设计文档/01_测试执行/09_原始报文外置对象存储.md` §5）：
C1（INT-1807）建指针列 + 回填 + 切换门禁 → C2（INT-1809）/A1（INT-1811）切读写路径 →
**M1（本卡）删旧列**。`test_result_dimensions.api_raw_response` / `api_request_body`
是 JSON 列，同一份厂商报文按「维度 × 轮」重复落库，主库实测 51,857 行、TOAST 约 232MB。

PG 16 的关键事实（**不按此执行会白干**）：
``ALTER TABLE ... DROP COLUMN`` 只改系统目录、**不重写数据**，被删列的 TOAST 块要等
行重写才释放——只 DROP 不 VACUUM FULL，磁盘一个字节都不会少。本脚本因此是
``DROP → VACUUM FULL → ANALYZE`` 三步，并打印执行前后
``pg_total_relation_size`` / ``pg_relation_size`` / ``pg_table_size`` / TOAST 关系大小。

前置门禁（缺一不可，``--apply`` 全部通过才动手；``--gate`` 只查不写）：

1. **C2 与 A1 已同批部署，且已观察 ≥1 个完整测试轮次**——DB 里查不出来，由操作人用
   ``--confirm-deployed-round`` 显式确认（不给就拒绝执行并打印原因）。
2. **回填门禁为 0**：``api_raw_response IS NOT NULL AND api_raw_response_uri IS NULL``
   （request 同理）——按列存在性判定；两列都已删时该门禁为 N/A。
3. **近 24h 无新写入**：近 24h 的维度行里两列必须全为 SQL NULL。窗口内**没有任何行**
   时无法证明「新写入都是 uri-only」，须操作人加 ``--ack-no-recent-traffic`` 明确承认
   （主库执行建议加 ``--strict-24h`` 直接要求窗口内有流量证据）。
4. **报告侧读路径已全部走对象**（含 INT-1752 的 include_body 路径）。可用
   ``--verify-objects N`` 在本脚本内抽样下载 N 个不同 sha 的对象、校验 sha256 与 JSON
   解析（证明读侧拿到的是对象），否则由操作人 ``--confirm-read-path`` 承认。

锁与窗口（卡面风险项）：

- 执行前查 ``pg_stat_activity``：存在 **idle in transaction** / 持锁阻塞别人的会话就拒绝
  执行（锁队列会把整个域的 gRPC 拖成 400/60s）；确认无关可加 ``--ignore-lock-risks``。
- ``ALTER`` 只拿一次 ACCESS EXCLUSIVE，``lock_timeout`` 默认 5s（``--lock-timeout-ms``）
  ——拿不到即失败退出、打印持锁者，**绝不排队**。
- ``VACUUM FULL`` 需要额外约一个表大小的临时磁盘（5 万行 / 约 275MB）并全程持
  ACCESS EXCLUSIVE → 必须有窗口；``--no-vacuum`` 只删列不回收（不建议，等于没回收）。
- ``VACUUM`` 不能跑在事务块里，本脚本全程 autocommit。

反向回填（窗口内回滚路径，卡面验收 5）：内容寻址对象全部保留，``--restore`` 重新加回
两列并按行上 ``uri + sha256`` 下载对象、校验 sha 后写回 JSON。对象是派生物，所以
**恢复不需要备份**——只要对象还在，列可以随时重建（与 C1 回填同口径：None 即无报文）。

用法::

    # 只查门禁与体积（只读，可重复执行）
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --gate
    # 预览（打印将执行的 DDL / VACUUM 与前后体积口径，不动库）
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py
    # 执行（门禁全绿 + 操作人确认 C2/A1 已部署并跑过一轮）
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --apply \
        --confirm-deployed-round --confirm-read-path --strict-24h
    # VACUUM FULL 被超时 / 锁顶掉之后的续跑（列已删，只重试压缩）
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --apply --force-vacuum \
        --confirm-deployed-round --confirm-read-path --strict-24h
    # 删列后的复查（只读；照样打印门禁 N/A 与指针分布）
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --gate
    # 窗口内回滚：从对象按 uri 解压写回两列
    python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --restore --apply

环境：``DATABASE_URL``（或 ``DATABASE_URI``）。``--verify-objects`` / ``--restore`` 需要
与在线服务一致的 ``OSS_*``（单桶模式必须带 ``OSS_BUCKET_NAME`` / ``OSS_KEY_PREFIX``，
否则会传到别的桶、服务侧读不到——见 INT-1645）；纯 DROP 路径不需要 OSS。

退出码：0 完成；1 门禁未通过；2 未拿到锁；3 执行后校验失败（含列已删但 TOAST
未回收）；4 前置确认缺失。

幂等性：列已不存在即 ``[SKIP]``，不重复 DROP；此时 ``--apply`` 会按 TOAST 体积判断
上次 ``VACUUM FULL`` 是否真的跑完——TOAST 仍偏大（被 ``statement_timeout`` /
``lock_timeout`` 顶掉，或上次用了 ``--no-vacuum``）就 **exit 3 并明确要求
``--force-vacuum`` 重跑**，绝不静默成功；``--gate`` 在列已删时仍打印门禁（N/A）与
指针分布，是删列后唯一可复现的复查命令。``--restore`` 只回填
``json IS NULL AND uri IS NOT NULL`` 的行。
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

# 列词表唯一来源：指针五列 / JSON 源列的名字只在这里定义一处（shared/utils/raw_payload.py），
# 迁移脚本、在线读写路径、离线搬运共用，避免删列时词表漂移。
from shared.utils.raw_payload import RAW_PAYLOAD_SPECS  # noqa: E402

TABLE = 'test_result_dimensions'
DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 30000
DEFAULT_VACUUM_TIMEOUT_MS = 900000
DEFAULT_BATCH_SIZE = 500
DEFAULT_RECENT_HOURS = 24
# 列已删后 TOAST 残留判据（P2-1）：两列删掉后这张表的 TOAST 只剩 error_message 之类
# 小字段，副本 VACUUM FULL 后实测 8KB；残留超过 16MB 不可能是正常形态（删列前的量级
# 是 230MB），只能是 VACUUM FULL 没跑完 / 上次用了 --no-vacuum。
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
        password=parsed.password, application_name='migration_int1813')


def _table_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (TABLE,))
    return cur.fetchone() is not None


def _existing_columns(cur) -> dict:
    cur.execute(
        'SELECT column_name, data_type FROM information_schema.columns '
        'WHERE table_name = %s', (TABLE,))
    return {row[0]: row[1] for row in cur.fetchall()}


def _target_columns() -> tuple:
    """待删的 JSON 源列（列词表来自 shared/utils/raw_payload.py）。"""
    return tuple(spec.json_column for spec in RAW_PAYLOAD_SPECS)


def _pending_columns(columns: dict) -> list:
    return [name for name in _target_columns() if name in columns]


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
    """列已删但 TOAST 仍偏大 → 上次 VACUUM FULL 没跑成功（P2-1 的判据）。

    ``DROP COLUMN`` 只改目录，磁盘回收全靠 VACUUM FULL；如果它被
    ``statement_timeout`` / ``lock_timeout`` 顶掉，或者上次是 ``--no-vacuum`` 跑的，
    重跑必须能识别出来——否则环境操作卡会记「执行成功」而磁盘一个字节没退。
    """
    return int(sizes.get('toast_size') or 0) > int(threshold_bytes)


def print_delta(before: dict, after: dict) -> None:
    """前后体积差（卡面验收 1：下降幅度应与 TOAST 体积相符）。"""
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
    """回填门禁（卡面前置 2）：内联非空而指针为空的悬空行数。

    列已删（M1 之后）→ 该组为 ``None``（N/A），不再拼已不存在的列名。
    """
    result = {}
    for spec in RAW_PAYLOAD_SPECS:
        if spec.json_column not in columns or spec.uri_column not in columns:
            result[spec.kind] = None
            continue
        cur.execute(
            f'SELECT count(*) FROM {TABLE} '
            f'WHERE {spec.json_column} IS NOT NULL AND {spec.uri_column} IS NULL')
        result[spec.kind] = int(cur.fetchone()[0])
    return result


def recent_write_violations(cur, columns: dict, hours: int = DEFAULT_RECENT_HOURS) -> dict:
    """近 N 小时维度行里两列的非空行数（卡面前置 3）。

    返回 ``{'rows': 窗口内行数, 'violations': {kind: 非空行数}, 'window': hours}``。
    窗口内无行时 ``rows == 0``——「没有流量」本身不能证明「新写入都是 uri-only」，
    由 ``--ack-no-recent-traffic`` 承认。
    """
    present = [spec for spec in RAW_PAYLOAD_SPECS
               if spec.json_column in columns and spec.uri_column in columns]
    cur.execute(
        f'SELECT count(*) FROM {TABLE} '
        f'WHERE created_at >= now() - interval \'{int(hours)} hours\'')
    rows = int(cur.fetchone()[0])
    violations = {}
    for spec in present:
        cur.execute(
            f'SELECT count(*) FROM {TABLE} '
            f'WHERE created_at >= now() - interval \'{int(hours)} hours\' '
            f'AND {spec.json_column} IS NOT NULL')
        violations[spec.kind] = int(cur.fetchone()[0])
    return {'rows': rows, 'violations': violations, 'window': hours}


def pointer_stats(cur, columns: dict) -> dict:
    """指针列分布（删列后唯一的完整性判据：有 sha 无 uri / 有 uri 无 sha 均为断链）。"""
    stats = {}
    for spec in RAW_PAYLOAD_SPECS:
        if spec.uri_column not in columns or spec.sha256_column not in columns:
            continue
        cur.execute(
            f'SELECT count(*) FILTER (WHERE {spec.uri_column} IS NOT NULL), '
            f'count(*) FILTER (WHERE {spec.uri_column} IS NOT NULL '
            f'                 AND {spec.sha256_column} IS NULL), '
            f'count(*) FILTER (WHERE {spec.uri_column} IS NULL '
            f'                 AND {spec.sha256_column} IS NOT NULL), '
            f'max({spec.created_at_column}) '
            f'FROM {TABLE}')
        with_uri, uri_no_sha, sha_no_uri, latest = cur.fetchone()
        stats[spec.kind] = {
            'with_uri': int(with_uri or 0),
            'uri_without_sha': int(uri_no_sha or 0),
            'sha_without_uri': int(sha_no_uri or 0),
            'latest_created_at': latest,
        }
    return stats


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


def verify_objects(cur, columns: dict, samples: int) -> list:
    """抽样读对象（卡面前置 4 的机器可查部分）：下载 → 校验 sha256 → 解析 JSON。

    同一 sha 只读一次（内容寻址），因此样本按 sha 去重取前 ``samples`` 个。
    返回失败描述列表；空列表 = 全部通过。
    """
    from shared.infrastructure.raw_payload_store import raw_payload_store

    failures = []
    for spec in RAW_PAYLOAD_SPECS:
        if spec.uri_column not in columns or spec.sha256_column not in columns:
            continue
        cur.execute(
            f'SELECT DISTINCT {spec.sha256_column} FROM {TABLE} '
            f'WHERE {spec.uri_column} IS NOT NULL AND {spec.sha256_column} IS NOT NULL '
            f'LIMIT %s', (samples,))
        shas = [row[0] for row in cur.fetchall()]
        if not shas:
            failures.append(f'{spec.kind}: 指针列全空，无可抽样对象')
            continue
        for sha in shas:
            cur.execute(
                f'SELECT {spec.uri_column} FROM {TABLE} '
                f'WHERE {spec.sha256_column} = %s AND {spec.uri_column} IS NOT NULL '
                f'LIMIT 1', (sha,))
            row = cur.fetchone()
            uri = row[0] if row else None
            try:
                raw_payload_store.load(spec.kind, uri, sha)
            except Exception as exc:  # noqa: BLE001  (对象缺失 / sha 不符 / 存储不可用)
                failures.append(f'{spec.kind}/{sha[:12]}: {exc}')
        print(f'[OBJECT] {spec.kind}: 抽样 {len(shas)} 个不同 sha '
              f'（失败 {len([f for f in failures if f.startswith(spec.kind)])}）')
    return failures


def run_gates(cur, columns: dict, args, require_read_path: bool = True) -> list:
    """跑全部可机器校验的门禁，返回失败项（空 = 全绿）。

    ``require_read_path=False``：只读复查（``--gate``）用——读路径门禁照常打印提示，
    但不计入失败（复查的人可能没有 OSS 凭据，门禁别的项才是复查目标）。
    """
    failures = []

    gate = gate_counts(cur, columns)
    for kind, missing in gate.items():
        label = {'resp': 'api_raw_response', 'req': 'api_request_body'}.get(kind, kind)
        if missing is None:
            print(f'[GATE-2] {label}: 列已删 → N/A（M1 已完成）')
        elif missing == 0:
            print(f'[GATE-2] {label}: 悬空行 0 → OK')
        else:
            print(f'[GATE-2] {label}: 悬空行 {missing} → FAIL（先跑 C1 回填 --gate 归零）')
            failures.append(f'回填门禁未归零：{label} missing={missing}')

    recent = recent_write_violations(cur, columns)
    inline_left = [spec for spec in RAW_PAYLOAD_SPECS if spec.json_column in columns]
    if not inline_left:
        # 列已删：内联报文形态不可能再写入，窗口内有无流量都不影响这条门禁。
        print(f'[GATE-3] 两列已删 → N/A（窗口内 {recent["rows"]} 行；'
              f'内联报文形态已不存在）')
    elif recent['rows'] == 0:
        print(f'[GATE-3] 近 {recent["window"]}h 无维度行 → 无法证明「新写入都是 uri-only」')
        if getattr(args, 'strict_24h', False) and not getattr(args, 'ack_no_recent_traffic', False):
            failures.append(
                f'近 {recent["window"]}h 无维度行，--strict-24h 要求有流量证据')
        elif not getattr(args, 'ack_no_recent_traffic', False):
            failures.append(
                f'近 {recent["window"]}h 无维度行；确认为空跑窗口请加 --ack-no-recent-traffic')
    elif not recent['violations']:
        print(f'[GATE-3] 两列已删 → N/A（窗口内 {recent["rows"]} 行的内联报文形态已不存在）')
    else:
        for kind, bad in recent['violations'].items():
            if bad:
                print(f'[GATE-3] {kind}: 近 {recent["window"]}h 仍有 {bad} 行内联报文 → FAIL')
                failures.append(f'近 {recent["window"]}h 仍有内联报文写入：{kind}={bad}')
            else:
                print(f'[GATE-3] {kind}: 近 {recent["window"]}h 内联报文 0 → OK')

    stats = pointer_stats(cur, columns)
    for kind, item in stats.items():
        if item['uri_without_sha'] or item['sha_without_uri']:
            print(f'[GATE-2/3] {kind}: 指针断链（uri 无 sha {item["uri_without_sha"]} / '
                  f'sha 无 uri {item["sha_without_uri"]}）→ FAIL')
            failures.append(f'指针断链：{kind}')
        else:
            print(f'[GATE-2/3] {kind}: 指针 {item["with_uri"]} 行、无断链，'
                  f'最新对象写入 {item["latest_created_at"]}')

    samples = getattr(args, 'verify_objects', 0) or 0
    if samples > 0:
        object_failures = verify_objects(cur, columns, samples)
        if object_failures:
            for item in object_failures[:10]:
                print(f'[GATE-4] 对象读取失败：{item}')
            failures.append(f'对象抽样读取失败 {len(object_failures)} 个（读路径门禁）')
        else:
            print('[GATE-4] 对象抽样读取 + sha256 校验全部通过 → OK')
    elif not getattr(args, 'confirm_read_path', False):
        print('[GATE-4] 未抽样对象：报告读路径须由操作人确认（--confirm-read-path）'
              '或用 --verify-objects N 在本脚本内抽样')
        if require_read_path:
            failures.append('未确认报告读路径已走对象（--confirm-read-path / --verify-objects N）')
    else:
        print('[GATE-4] 报告读路径已由操作人确认（--confirm-read-path）')

    return failures


# ------------------------------------------------------------------ 执行步骤
def build_drop_ddl(pending) -> str:
    """把待删列合成**一条** ALTER TABLE（只拿一次 ACCESS EXCLUSIVE 锁）。"""
    parts = [f'DROP COLUMN IF EXISTS {name}' for name in pending]
    return f'ALTER TABLE {TABLE} ' + ', '.join(parts)


def build_add_ddl(pending) -> str:
    """反向回填用：把两列加回来（全部可空、无默认值，与 C1 加列同口径）。"""
    parts = [f'ADD COLUMN IF NOT EXISTS {name} json' for name in pending]
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
    复位成 0，避免把 VACUUM FULL / 回填的预算一起改掉（P3-3：这个开关以前算了不用）。
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
    cur = conn.cursor()
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


def restore_columns(conn, pending, batch_size, lock_timeout_ms, limit_rows=0,
                    statement_timeout_ms=None) -> dict:
    """反向回填：加回两列并按行上 uri + sha256 从对象写回 JSON（窗口内回滚路径）。

    单趟按 id 扫描「有待回填指针」的行（两组任一为空即算一条），一行一次 UPDATE 同时
    写回两列——比按 kind 各扫一遍少一半语句，``--limit-rows`` 也才能对同一批行生效。
    读取口径与在线读路径同一实现（下载 → 解压 → 校验 sha256 → 解析 JSON）。
    """
    from psycopg2.extras import Json

    from shared.infrastructure.raw_payload_store import raw_payload_store

    if pending:
        cur = conn.cursor()
        _run_ddl(cur, build_add_ddl(pending), lock_timeout_ms, statement_timeout_ms)
        cur.close()

    pending_sql = ' OR '.join(
        f'({spec.uri_column} IS NOT NULL AND {spec.json_column} IS NULL)'
        for spec in RAW_PAYLOAD_SPECS)
    select_cols = ', '.join(
        f'{spec.uri_column}, {spec.sha256_column}' for spec in RAW_PAYLOAD_SPECS)
    set_sql = ', '.join(
        f'{spec.json_column} = coalesce(%s, {spec.json_column})'
        for spec in RAW_PAYLOAD_SPECS)

    sql = f'SELECT id, {select_cols} FROM {TABLE} WHERE {pending_sql} ORDER BY id'
    params = ()
    if limit_rows:
        sql += ' LIMIT %s'
        params = (int(limit_rows),)

    restored = {spec.kind: 0 for spec in RAW_PAYLOAD_SPECS}
    rows_done = 0
    started = time.monotonic()
    cur = conn.cursor()
    cur.execute(sql, params)
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            row_id = row[0]
            values = []
            for index, spec in enumerate(RAW_PAYLOAD_SPECS):
                uri, sha = row[1 + index * 2], row[2 + index * 2]
                if uri is None or sha is None:
                    values.append(None)
                    continue
                values.append(Json(raw_payload_store.load(spec.kind, uri, sha)))
                restored[spec.kind] += 1
            cur2 = conn.cursor()
            cur2.execute(f'UPDATE {TABLE} SET {set_sql} WHERE id = %s',
                         (*values, row_id))
            cur2.close()
        conn.commit()
        rows_done += len(rows)
    cur.close()
    elapsed = time.monotonic() - started
    print(f'[RESTORE] 处理 {rows_done} 行（resp {restored["resp"]} / req '
          f'{restored["req"]} 个值写回），耗时 {elapsed:.1f}s'
          f'（对象下载 {raw_payload_store.read_count} 次 / 进程内缓存命中后）')
    return restored


# ------------------------------------------------------------------ 列已删后的重跑 / 复查
def _after_drop(conn, cur, columns, args, before_sizes, vacuum_timeout_ms) -> int:
    """DROP 已完成时的路径（幂等重跑 + 删列后复查，P2-1 / P3-1）。

    - ``--gate``（只读）：照常打印门禁（列已删 → N/A）与指针分布——这是删列后唯一
      可复现的复查命令；不查锁风险、不把「未确认读路径」判成失败（只读复查不该被
      idle in transaction 或一张 OSS 凭据挡下）。
    - ``--apply``：门禁按 ``--apply`` 口径全量判定；TOAST 仍偏大说明上次 VACUUM FULL
      没跑成功 → exit 3 并明确要求 ``--force-vacuum``（绝不静默 exit 0）。
    - ``--apply --force-vacuum``：补跑一次 VACUUM FULL + ANALYZE，打印前后体积与差值。
    """
    read_only = not args.apply
    failures = run_gates(cur, columns, args, require_read_path=not read_only)
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

        if args.restore:
            return _do_restore(conn, args, lock_timeout_ms, statement_timeout_ms)

        if not pending:
            print(f'[SKIP] 两列均已不存在（{", ".join(_target_columns())}）'
                  f'——M1 的 DROP 已完成')
            return _after_drop(conn, cur, columns, args, before_sizes,
                               vacuum_timeout_ms)

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

        # 只读（--gate / dry-run）不把「未确认读路径」判成失败：这是给人看的门禁报告，
        # 真正动手（--apply）时才硬拦。
        failures = run_gates(cur, columns, args,
                             require_read_path=bool(getattr(args, 'apply', False)))
        if failures:
            print(f'[FAIL] 门禁未通过（{len(failures)} 项），不做任何改动：')
            for item in failures:
                print(f'  - {item}')
            return 1

        if not args.confirm_deployed_round and args.apply:
            print('[FAIL] 缺 --confirm-deployed-round：卡面前置 1（C2+A1 同批部署且已观察'
                  '≥1 个完整测试轮次）DB 里查不出来，必须由操作人确认')
            return 4

        print(f'[PLAN] 步骤：① {build_drop_ddl(pending)}'
              f'（lock_timeout={lock_timeout_ms}ms）')
        if args.no_vacuum:
            print('[PLAN] ② 跳过 VACUUM FULL（--no-vacuum：只改目录，磁盘一个字节都不会少）')
        else:
            print(f'[PLAN] ② VACUUM FULL {TABLE}（AccessExclusiveLock，'
                  f'需额外约一个表大小的临时磁盘；statement_timeout={vacuum_timeout_ms}ms）')
        print('[PLAN] ③ ANALYZE 刷新统计信息')

        if not args.apply:
            print('[DRY] 未执行；--apply 时按上述步骤落地')
            return 0

        drop_columns(conn, pending, lock_timeout_ms, statement_timeout_ms)
        columns = _existing_columns(cur)
        if _pending_columns(columns):
            print('[FAIL] DROP 后仍有列存在 → 校验失败')
            return 3
        print('[VERIFY] 两列已不存在 → OK')

        if not args.no_vacuum:
            vacuum_full(conn, vacuum_timeout_ms)
        analyze(conn)

        after = _sizes(cur)
        print_sizes('AFTER', after)
        print_delta(before_sizes, after)
        print(f'[VERIFY] 删列后回填门禁：{gate_counts(cur, columns)}'
              f'（"resp"/"req" 为 None = 列已删，M1 完成）')
        print(f'[VERIFY] 指针分布：{pointer_stats(cur, columns)}')
        if not args.no_vacuum and vacuum_still_pending(after):
            print(f'[FAIL] VACUUM FULL 完成后 TOAST 仍有 {_mb(after["toast_size"])}，'
                  f'磁盘回收未达预期（列已删、可 --force-vacuum 重跑）')
            return 3
        print('[VERIFY] 磁盘回收以上面 AFTER / DELTA 为准')
        return 0
    finally:
        conn.close()


def _do_restore(conn, args, lock_timeout_ms, statement_timeout_ms=None) -> int:
    """--restore 分支：先补齐列，再按对象回填。"""
    cur = conn.cursor()
    columns = _existing_columns(cur)
    missing = [name for name in _target_columns() if name not in columns]
    if args.apply:
        if missing:
            print(f'[RESTORE] 待加回列：{", ".join(missing)}（json，可空、无默认值）')
        else:
            print('[RESTORE] 两列已存在，只回填空值行（幂等）')
        restored = restore_columns(conn, missing, args.batch_size, lock_timeout_ms,
                                   limit_rows=args.limit_rows,
                                   statement_timeout_ms=statement_timeout_ms)
        columns = _existing_columns(cur)
        still_empty = 0
        for spec in RAW_PAYLOAD_SPECS:
            cur.execute(
                f'SELECT count(*) FROM {TABLE} '
                f'WHERE {spec.uri_column} IS NOT NULL AND {spec.json_column} IS NULL')
            still_empty += int(cur.fetchone()[0])
        print(f'[RESTORE] 写回统计 {restored}；残留「有指针但未写回」= {still_empty}'
              f'（0 = 恢复完成）')
        print_sizes('AFTER-RESTORE', _sizes(cur))
        return 0 if still_empty == 0 else 3

    print(f'[PLAN] --restore：{"加回 " + ", ".join(missing) if missing else "列已存在"}，'
          f'再按 uri + sha256 下载对象写回（批 {args.batch_size} 行）')
    print('[DRY] 未执行；--restore --apply 时落地')
    return 0


def build_parser() -> argparse.ArgumentParser:
    """命令行开关（``main`` 与单测共用一处，防开关名漂移）。"""
    ap = argparse.ArgumentParser(
        description='DROP test_result_dimensions 原始报文 JSON 两列 + VACUUM FULL + ANALYZE'
                    '（INT-1813 / M1）')
    ap.add_argument('--apply', action='store_true',
                    help='执行（默认 dry-run：只打印门禁、DDL 与体积口径）')
    ap.add_argument('--gate', action='store_true',
                    help='只跑门禁与体积查询（只读；列已删时仍打印门禁与指针分布）')
    ap.add_argument('--restore', action='store_true',
                    help='反向回填：加回两列并从对象写回 JSON（窗口内回滚路径）')
    ap.add_argument('--confirm-deployed-round', action='store_true',
                    help='确认 C2+A1 已同批部署且已观察 ≥1 个完整测试轮次（前置 1）')
    ap.add_argument('--confirm-read-path', action='store_true',
                    help='确认报告侧读路径已全部走对象（前置 4；或用 --verify-objects）')
    ap.add_argument('--verify-objects', type=int, default=0, metavar='N',
                    help='抽样下载 N 个不同 sha 的对象并校验 sha256（需要 OSS_* 配置）')
    ap.add_argument('--ack-no-recent-traffic', action='store_true',
                    help='承认近 24h 无维度行（空跑窗口）——否则前置 3 不算通过')
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
    ap.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument('--limit-rows', type=int, default=0,
                    help='--restore 单次最多处理的行数（0 = 全量；分批跑时分段验证用）')
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

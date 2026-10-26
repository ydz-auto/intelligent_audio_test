# -*- coding: utf-8 -*-
"""回填脚本：report_cases 九字段 payload → report_case_snapshots + 4 个指针列
（INT-1994 / 档4 R1）

背景：``report_cases`` 存 33,925 行 / 258MB，每行把用例配置整份再落一次库；九字段
payload 去重后只有 **10,843** 个不同值（与 12 个内容列整行去重数完全相同 → 去重
无损）。本脚本把 payload 按 ``sha256(规范化 JSON)`` 内容寻址写进
``report_case_snapshots``，行上只回写 4 个指针列（表与列由
``add_report_case_snapshots_int1994.py`` 建）。R1 **不删内容列**——双写期间列还在，
``REPORT_CASE_SNAPSHOT_SOURCE=column`` 可随时切回列读。

口径（唯一实现在 ``shared/utils/raw_payload.py``，在线读写路径共用，改口径先改卡）：
    规范化  json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            .encode('utf-8')；sha256 对这串**未压缩**字节算
    压缩    gzip level 9 / mtime=0（压缩确定），``payload_bytes`` 记压缩后大小
    指针    snapshot_uri = db://report_case_snapshots/{sha256}

三个必须守住的口径：
1. **payload 从列值原样构造**，不做任何 falsy 归一（``metrics`` 为 ``[]`` 的
   2,095 行折成 ``{}`` 就不是逐字节冻结）；
2. ``snapshot_created_at`` 回填取**源行 ``created_at``**，不能 ``now()``——否则
   33,925 行历史报告的「生成时间」全变成回填时刻；
3. 同值只产生**一行**快照：``INSERT … ON CONFLICT (sha256) DO NOTHING``。

流程（可中断、天然幂等，不需要 checkpoint 表）：
    1. 判据 ``snapshot_sha256 IS NULL``，按 ``id`` 游标分页（``id > 上一批最大 id``），
       重跑只处理剩下的；
    2. 批内逐行取值 → 规范化 → sha → 写快照（冲突即跳过，跨批 / 跨行复用同一行）；
       **先写快照、再写指针**（反序会出现「行上有指针、表里没内容」）；
    3. 每 ``--batch`` 行 commit 一次并 sleep 限流（主库要解压 258MB 表，别和在线
       报告生成抢 IO）。

门禁（切换唯一硬条件，``--gate``）：
    SELECT count(*) FROM report_cases rc
     WHERE rc.snapshot_sha256 IS NULL
        OR NOT EXISTS (SELECT 1 FROM report_case_snapshots s
                        WHERE s.sha256 = rc.snapshot_sha256);
为 0 才允许把读写切到快照口径。``--gate`` 有缺口时退出码 1。

用法：
    # 只看门禁（只读、可重复执行）
    python scripts/migrations/202610/backfill_report_case_snapshots_int1994.py --gate
    # 预览：待回填行数 / 进度 / 目标去重数
    python scripts/migrations/202610/backfill_report_case_snapshots_int1994.py
    # 执行（分批跑时用 --limit 控制单次时长，进度自动保留）
    python scripts/migrations/202610/backfill_report_case_snapshots_int1994.py --apply
    python scripts/migrations/202610/backfill_report_case_snapshots_int1994.py --apply \
        --limit 5000 --batch 200 --sleep 0.5
    # 只回填某份报告（调试 / 验收取样）
    python scripts/migrations/202610/backfill_report_case_snapshots_int1994.py --apply \
        --report-id 123

环境：DATABASE_URL（或 DATABASE_URI）。

退出码：0 完成且门禁归零；1 门禁未归零 / 有失败行；2 连续失败超阈值中止。
"""
import argparse
import json
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

CASES_TABLE = 'report_cases'
SNAPSHOT_TABLE = 'report_case_snapshots'

DEFAULT_BATCH = 200
DEFAULT_SLEEP_SECONDS = 0.5
DEFAULT_MAX_CONSECUTIVE_FAILURES = 20
DEFAULT_STATEMENT_TIMEOUT_MS = 600000

#: 快照 payload 的九字段（口径唯一实现在 shared 侧，这里只取列名名单）
from shared.utils.raw_payload import (  # noqa: E402  (sys.path 已在上面注入仓库根)
    canonical_bytes,
    compress,
    sha256_of_bytes,
)

PAYLOAD_FIELDS = (
    'name', 'description', 'category', 'tags', 'metrics', 'results',
    'audios', 'reference_params', 'algorithm_results',
)

#: 其中三列是文本列（原样取值），其余是 jsonb 列（``::text`` 后 json.loads）
TEXT_FIELDS = ('name', 'description', 'category')
JSON_FIELDS = tuple(f for f in PAYLOAD_FIELDS if f not in TEXT_FIELDS)

URI_SCHEME = 'db://report_case_snapshots/'

GATE_SQL = (
    f'SELECT count(*) FROM {CASES_TABLE} rc '
    f'WHERE rc.snapshot_sha256 IS NULL '
    f'   OR NOT EXISTS (SELECT 1 FROM {SNAPSHOT_TABLE} s '
    f'                   WHERE s.sha256 = rc.snapshot_sha256)'
)


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='backfill_int1994')


def _statement_timeout_ms():
    raw = os.environ.get('DB_BACKFILL_STATEMENT_TIMEOUT_MS')
    try:
        value = int(str(raw).strip()) if raw else DEFAULT_STATEMENT_TIMEOUT_MS
    except (TypeError, ValueError):
        value = DEFAULT_STATEMENT_TIMEOUT_MS
    return value if value > 0 else DEFAULT_STATEMENT_TIMEOUT_MS


# ---------------------------------------------------------------- 计数

def gate_count(conn) -> int:
    """门禁：缺指针 / 指针悬空的用例行数（必须为 0）。"""
    with conn.cursor() as cur:
        cur.execute(GATE_SQL)
        return int(cur.fetchone()[0])


def progress_counts(conn):
    """进度：(已回填行数, 总行数, 快照行数)。"""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT count(*) FILTER (WHERE snapshot_sha256 IS NOT NULL), count(*) '
            f'FROM {CASES_TABLE}')
        done, total = cur.fetchone()
        cur.execute(f'SELECT count(*) FROM {SNAPSHOT_TABLE}')
        snapshots = cur.fetchone()[0]
    return int(done), int(total), int(snapshots)


def pending_count(conn, report_id=None) -> int:
    """待回填行数（``snapshot_sha256 IS NULL``）。"""
    sql = f'SELECT count(*) FROM {CASES_TABLE} WHERE snapshot_sha256 IS NULL'
    params = ()
    if report_id:
        sql += ' AND report_id = %s'
        params = (report_id,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


# ---------------------------------------------------------------- 取数

def _parse_json(text, field):
    """JSON 列文本 → Python 对象（``null`` → None；保持 ``[]`` / ``{}`` 原形）。"""
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ValueError(f'列 {field} 不是合法 JSON: {exc}') from exc


def fetch_page(conn, after_id: int, limit: int, report_id=None):
    """取一页待回填行：``[(id, created_at, payload_dict)]``，按 id 升序。"""
    json_cols = ', '.join(f'rc.{field}::text' for field in JSON_FIELDS)
    text_cols = ', '.join(f'rc.{field}' for field in TEXT_FIELDS)
    sql = (f'SELECT rc.id, rc.created_at, {text_cols}, {json_cols} FROM {CASES_TABLE} rc '
           f'WHERE rc.snapshot_sha256 IS NULL AND rc.id > %s')
    params = [after_id]
    if report_id:
        sql += ' AND rc.report_id = %s'
        params.append(report_id)
    sql += ' ORDER BY rc.id LIMIT %s'
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = []
        for row in cur.fetchall():
            row_id, created_at = row[0], row[1]
            text_values = row[2:2 + len(TEXT_FIELDS)]
            json_values = row[2 + len(TEXT_FIELDS):]
            payload = dict(zip(TEXT_FIELDS, text_values))
            payload.update({field: _parse_json(text, field)
                            for field, text in zip(JSON_FIELDS, json_values)})
            rows.append((row_id, created_at, payload))
        return rows


# ---------------------------------------------------------------- 写入

def store_payload(conn, payload, cache):
    """写一份快照（内容寻址幂等）。返回 (sha, 压缩后字节数, 是否新写入)。

    ``ON CONFLICT (sha256) DO NOTHING``：同值并发 / 重跑天然收敛；
    已存在的快照行不改写（内容寻址下同 sha 必同内容）。
    """
    raw = canonical_bytes(payload)
    sha = sha256_of_bytes(raw)
    hit = cache.get(sha)
    if hit is not None:
        return sha, hit, False
    data = compress(raw)
    sql = (f'INSERT INTO {SNAPSHOT_TABLE} (sha256, payload_gz, payload_bytes) '
           f'VALUES (%s, %s, %s) ON CONFLICT (sha256) DO NOTHING')
    with conn.cursor() as cur:
        cur.execute(sql, (sha, data, len(data)))
        created = cur.rowcount > 0  # ON CONFLICT DO NOTHING 命中已有行时 rowcount=0
    cache[sha] = len(data)
    return sha, len(data), created


def update_pointer(conn, row_id, sha, size, created_at) -> int:
    """回写 4 个指针列；``snapshot_sha256 IS NULL`` 保证重复执行不覆写。"""
    sql = (f'UPDATE {CASES_TABLE} SET '
           f'snapshot_uri = %s, snapshot_sha256 = %s, snapshot_bytes = %s, '
           f'snapshot_created_at = %s '
           f'WHERE id = %s AND snapshot_sha256 IS NULL')
    with conn.cursor() as cur:
        cur.execute(sql, (f'{URI_SCHEME}{sha}', sha, size, created_at, row_id))
        return cur.rowcount


class _Stats:
    def __init__(self):
        self.rows = 0
        self.stored = 0
        self.reused = 0
        self.failed_rows = 0

    def summary(self):
        return (f'行 {self.rows} / 新写快照 {self.stored} / 命中已有 {self.reused} / '
                f'失败行 {self.failed_rows}')


def process_page(conn, page, cache, stats):
    """处理一页：先写全部快照、再统一回写指针（同批一个 savepoint）。"""
    planned = []
    for row_id, created_at, payload in page:
        try:
            sha, size, created = store_payload(conn, payload, cache)
        except Exception as exc:  # noqa: BLE001 - 单行失败不中断整批
            stats.failed_rows += 1
            print(f'[FAIL] 行 id={row_id} 写快照失败：{exc}')
            continue
        if created:
            stats.stored += 1
        else:
            stats.reused += 1
        planned.append((row_id, sha, size, created_at))
    for row_id, sha, size, created_at in planned:
        stats.rows += update_pointer(conn, row_id, sha, size, created_at)
    return stats


def run(apply=False, batch=DEFAULT_BATCH, sleep_seconds=DEFAULT_SLEEP_SECONDS,
        limit=0, report_id=None,
        max_consecutive_failures=DEFAULT_MAX_CONSECUTIVE_FAILURES):
    """主循环。返回退出码（0 完成 / 1 有失败行或门禁未归零 / 2 连续失败中止）。"""
    conn = _connect()
    stats = _Stats()
    consecutive_failures = 0
    aborted = False
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(f'SET statement_timeout = {_statement_timeout_ms()}')
        done, total, snapshots = progress_counts(conn)
        pending = pending_count(conn, report_id)
        print(f'[SCAN] 已回填 {done}/{total} 行，快照 {snapshots} 个，'
              f'本次待回填 {pending} 行'
              + (f'（report_id={report_id}）' if report_id else ''))
        print(f'[GATE] 回填前缺口={gate_count(conn)}')
        if not apply:
            print('[DRY] 未写快照与指针；加 --apply 执行')
            return 0
        if pending == 0:
            gate = gate_count(conn)
            print(f'[DONE] 无待回填行；缺口={gate}')
            return 0 if gate == 0 else 1

        cache = {}
        after_id = 0
        batch_index = 1
        started = time.monotonic()
        while True:
            page_limit = batch
            if limit:
                remaining = limit - stats.rows - stats.failed_rows
                if remaining <= 0:
                    print(f'[LIMIT] 达到 --limit={limit}，本轮提前结束'
                          f'（进度已提交，可重跑续跑）')
                    break
                page_limit = min(page_limit, remaining)
            page = fetch_page(conn, after_id, page_limit, report_id)
            if not page:
                break
            with conn.cursor() as cur:
                cur.execute('SAVEPOINT backfill_page')
            try:
                process_page(conn, page, cache, stats)
            except Exception as exc:  # noqa: BLE001 - 单页失败不中断整批
                with conn.cursor() as cur:
                    cur.execute('ROLLBACK TO SAVEPOINT backfill_page')
                consecutive_failures += 1
                print(f'[FAIL] 页（id > {after_id}）回填失败，未写指针：{exc}')
                if consecutive_failures >= max_consecutive_failures:
                    print(f'[ABORT] 连续失败 {consecutive_failures} 页，停止续跑')
                    aborted = True
                    break
            else:
                with conn.cursor() as cur:
                    cur.execute('RELEASE SAVEPOINT backfill_page')
                consecutive_failures = 0
            conn.commit()
            after_id = page[-1][0]
            if sleep_seconds:
                time.sleep(sleep_seconds)
            elapsed = time.monotonic() - started
            # 进度是对 258MB 表的 count(*)：每 10 批核一次，避免扫描开销压过回填本身
            if (batch_index % 10 == 0):
                done_now, total_now, snap_now = progress_counts(conn)
                print(f'[BATCH] {stats.summary()} | 进度 {done_now}/{total_now} '
                      f'快照 {snap_now} | 累计 {elapsed:.1f}s')
            else:
                print(f'[BATCH] {stats.summary()} | 累计 {elapsed:.1f}s')
            batch_index += 1

        gate = gate_count(conn)
        done, total, snapshots = progress_counts(conn)
        print(f'[GATE] 回填后缺口={gate}')
        print(f'[DONE] {stats.summary()} | 回填后 {done}/{total} 行，快照 {snapshots} 个')
        if aborted:
            return 2
        if stats.failed_rows:
            return 1
        return 0 if gate == 0 else 1
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='report_cases 九字段 payload 内容寻址回填 + 切换门禁'
                    '（INT-1994 / 档4 R1）')
    ap.add_argument('--gate', action='store_true',
                    help='只打印切换门禁计数（只读），有缺口退出码 1')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    ap.add_argument('--batch', type=int, default=DEFAULT_BATCH,
                    help=f'每批行数（默认 {DEFAULT_BATCH}）')
    ap.add_argument('--sleep', type=float, default=DEFAULT_SLEEP_SECONDS,
                    help=f'批间 sleep 秒数（默认 {DEFAULT_SLEEP_SECONDS}）')
    ap.add_argument('--limit', type=int, default=0,
                    help='本轮最多处理多少行（0=不限；用于分次续跑）')
    ap.add_argument('--report-id', type=int, default=None,
                    help='只回填指定报告（调试 / 验收取样）')
    ap.add_argument('--max-consecutive-failures', type=int,
                    default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
                    help=f'连续失败多少页中止（默认 {DEFAULT_MAX_CONSECUTIVE_FAILURES}）')
    args = ap.parse_args()

    if args.gate:
        conn = _connect()
        try:
            gate = gate_count(conn)
        finally:
            conn.close()
        print(f'snapshot_missing={gate}')
        raise SystemExit(0 if gate == 0 else 1)

    raise SystemExit(run(
        apply=args.apply,
        batch=max(1, args.batch),
        sleep_seconds=max(0.0, args.sleep),
        limit=max(0, args.limit),
        report_id=args.report_id,
        max_consecutive_failures=max(1, args.max_consecutive_failures),
    ))


if __name__ == '__main__':
    main()

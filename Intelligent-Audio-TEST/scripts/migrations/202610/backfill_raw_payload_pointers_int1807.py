# -*- coding: utf-8 -*-
"""回填脚本：test_result_dimensions 原始报文 → 内容寻址对象 + 指针列（INT-1807 / C1）

背景：``api_raw_response`` / ``api_request_body`` 与维度评分行耦合，同一份厂商报文
按「维度 × 轮」重复落库（主库实测 51,857 行、去重后 6,506 个响应 + 6,259 个请求体，
TOAST 合计约 695MB）。本脚本把报文按**内容寻址**搬到对象存储，只把指针回写到
``api_raw_*_uri`` 等列（列由 ``add_raw_payload_pointers_int1807.py`` 建）。

对象口径（与 C2 读写路径共用，改口径先改卡）：
    key      raw/resp/{sha[:2]}/{sha}.json.gz  /  raw/req/{sha[:2]}/{sha}.json.gz
    category case_result（多桶模式免新增配置；单桶模式自动落
             {OSS_KEY_PREFIX}/case_result/raw/...）
    字节     规范化 JSON：json.dumps(v, sort_keys=True, separators=(',', ':'),
             ensure_ascii=False).encode('utf-8')  →  sha256 对这串**未压缩**字节算；
             gzip 压缩后上传，content_type=application/json+gzip，bytes 记压缩后大小。
    写入     一律 storage.save_bytes(..., allow_fallback=False)（D1 / INT-1805）：
             OSS 不可用即抛 StorageUnavailableError，**不落本地盘、不写 local://**，
             该组按失败记录、不写 uri。

为什么 request / response 分成两组对象：两者是独立取值空间（实测 response 6,506 /
request 6,259 个不同值），打包成一份会丢掉跨值去重。

流程（可中断、天然幂等）：
    1. 按 ``(test_result_id, round_number)`` 分组流式取待处理行——进度判据就是
       ``api_raw_response_uri IS NULL`` / ``api_request_body_uri IS NULL``，
       不需要 checkpoint 表，重跑只处理剩下的；
    2. 组内逐行取值 → 规范化 → sha256 → 值缓存命中即复用 uri（内容寻址 key 重复
       上传天然幂等，跨组也复用）；
    3. 整组上传全部成功后才写 uri（任一行上传失败 → 该组不写任何 uri）；
    4. 每 ``--batch-groups``（默认 200）组 commit 一次并 sleep 限流——主库要解压
       约 695MB TOAST，避免和在线评估抢 IO。

门禁（切换唯一硬条件，``--gate``）：
    SELECT count(*) FILTER (WHERE api_raw_response IS NOT NULL
                             AND api_raw_response_uri IS NULL) AS resp_missing,
           count(*) FILTER (WHERE api_request_body IS NOT NULL
                             AND api_request_body_uri IS NULL) AS req_missing
      FROM test_result_dimensions;
    两项都为 0 才算可以切换读写路径（C2）。``--gate`` 在有缺口时退出码 1。

用法：
    # 只看门禁（可重复执行、只读）
    python scripts/migrations/202610/backfill_raw_payload_pointers_int1807.py --gate
    # 预览：待处理组数 / 行数
    python scripts/migrations/202610/backfill_raw_payload_pointers_int1807.py
    # 执行；分批跑时用 --limit-groups 控制单次时长（进度自动保留）
    python scripts/migrations/202610/backfill_raw_payload_pointers_int1807.py --apply
    python scripts/migrations/202610/backfill_raw_payload_pointers_int1807.py --apply \
        --limit-groups 2000 --batch-groups 100 --sleep 1.0

环境：DATABASE_URL（或 DATABASE_URI）；OSS_ENDPOINT / OSS_ACCESS_KEY /
OSS_SECRET_KEY / OSS_BUCKET_NAME / OSS_KEY_PREFIX 必须与服务侧一致（单桶模式下
不配 OSS_BUCKET_NAME 会传进多桶的 case-result 桶，服务侧读不到）。

退出码：0 完成且无失败组；1 存在失败组 / 门禁未归零；2 连续失败超阈值中止。
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

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

TABLE = 'test_result_dimensions'
CATEGORY = 'case_result'
CONTENT_TYPE = 'application/json+gzip'
GZIP_COMPRESS_LEVEL = 9

DEFAULT_BATCH_GROUPS = 200
DEFAULT_SLEEP_SECONDS = 0.5
DEFAULT_MAX_CONSECUTIVE_FAILURES = 20
DEFAULT_STATEMENT_TIMEOUT_MS = 600000

# (kind, JSON 源列, 指针列前缀)
PAYLOADS = (
    ('resp', 'api_raw_response', 'api_raw_response'),
    ('req', 'api_request_body', 'api_request_body'),
)

PENDING_PREDICATE = (
    '(api_raw_response IS NOT NULL AND api_raw_response_uri IS NULL) '
    'OR (api_request_body IS NOT NULL AND api_request_body_uri IS NULL)'
)

GATE_SQL = (
    'SELECT '
    'count(*) FILTER (WHERE api_raw_response IS NOT NULL '
    '                   AND api_raw_response_uri IS NULL) AS resp_missing, '
    'count(*) FILTER (WHERE api_request_body IS NOT NULL '
    '                   AND api_request_body_uri IS NULL) AS req_missing '
    f'FROM {TABLE}'
)


# ---------------------------------------------------------------- 对象口径

def canonical_bytes(value) -> bytes:
    """规范化 JSON 字节：键序 / 分隔符固定，否则键序不同会产出重复对象。"""
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def sha256_hex(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def object_key(kind: str, sha: str) -> str:
    """内容寻址 key：raw/resp/{sha[:2]}/{sha}.json.gz（req 同理）。"""
    return f'raw/{kind}/{sha[:2]}/{sha}.json.gz'


def compress(raw: bytes) -> bytes:
    """gzip 压缩；mtime 固定为 0（sha 对未压缩字节算，压缩差异不影响 key）。"""
    return gzip.compress(raw, compresslevel=GZIP_COMPRESS_LEVEL, mtime=0)


def _default_uploader(data: bytes, key: str) -> str:
    """写对象存储：allow_fallback=False，绝不允许落本地盘 / 返回 local://。"""
    from shared.infrastructure.storage import storage, StorageUnavailableError
    uri = storage.save_bytes(data, CATEGORY, key,
                             content_type=CONTENT_TYPE, allow_fallback=False)
    if uri.startswith('local://'):
        raise StorageUnavailableError(
            f'禁止本地降级却拿到 local:// 路径: {uri}')
    return uri


# ---------------------------------------------------------------- 分组取数

def _after_predicate(tid, rn):
    """严格晚于 (tid, rn) 的键（ORDER BY tid, rn NULLS FIRST 口径）。"""
    if rn is None:
        return ('(test_result_id > %s OR (test_result_id = %s '
                'AND round_number IS NOT NULL))', (tid, tid))
    return ('(test_result_id > %s OR (test_result_id = %s '
            'AND round_number > %s))', (tid, tid, rn))


def fetch_group_page(conn, after, limit):
    """取下一页待处理分组键（上一页最后一组的键之后），按处理顺序返回。

    分组键在 ORDER BY 上与提交边界一致：页与页之间不会漏组、不会重复。
    """
    after_sql = ''
    params = []
    if after is not None:
        after_sql, params = _after_predicate(*after)
        after_sql = f'AND {after_sql}'
    sql = (f'SELECT test_result_id, round_number FROM {TABLE} '
           f'WHERE ({PENDING_PREDICATE}) {after_sql} '
           f'GROUP BY test_result_id, round_number '
           f'ORDER BY test_result_id, round_number NULLS FIRST '
           f'LIMIT %s')
    with conn.cursor() as cur:
        cur.execute(sql, [*params, limit])
        return [(row[0], row[1]) for row in cur.fetchall()]


def fetch_group_rows(conn, tid, rn):
    """取一组的待处理行：[(id, 响应 dict|None, 请求 dict|None)]。

    已回填过的那一侧取 NULL——既避免重复上传，也避免二次解压该列的 TOAST。
    """
    sql = (f'SELECT id, '
           f'CASE WHEN api_raw_response IS NOT NULL '
           f'AND api_raw_response_uri IS NULL '
           f'THEN api_raw_response::text END, '
           f'CASE WHEN api_request_body IS NOT NULL '
           f'AND api_request_body_uri IS NULL '
           f'THEN api_request_body::text END '
           f'FROM {TABLE} '
           f'WHERE test_result_id = %s AND round_number IS NOT DISTINCT FROM %s '
           f'AND ({PENDING_PREDICATE}) ORDER BY id')
    with conn.cursor() as cur:
        cur.execute(sql, (tid, rn))
        rows = []
        for row_id, resp_text, req_text in cur.fetchall():
            rows.append((row_id, _parse_payload(resp_text), _parse_payload(req_text)))
        return rows


def _parse_payload(text):
    """JSON 列文本 → Python 对象；``null`` 视同空值（不建对象、不写 uri）。"""
    if text is None:
        return None
    value = json.loads(text)
    return None if value is None else value


# ---------------------------------------------------------------- 回填

class _Stats:
    def __init__(self):
        self.groups = 0
        self.rows = 0
        self.uploaded = 0
        self.reused = 0
        self.skipped_empty = 0
        self.failed_groups = 0

    def summary(self):
        return (f'组 {self.groups} / 行 {self.rows} / 上传 {self.uploaded} / '
                f'复用缓存 {self.reused} / 空值跳过 {self.skipped_empty} / '
                f'失败组 {self.failed_groups}')


def gate_counts(conn):
    """门禁计数：返回 (resp_missing, req_missing)。"""
    with conn.cursor() as cur:
        cur.execute(GATE_SQL)
        resp_missing, req_missing = cur.fetchone()
    return int(resp_missing), int(req_missing)


def pending_counts(conn):
    """预览口径：待处理组数 / 行数。"""
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM {TABLE} WHERE ({PENDING_PREDICATE})')
        rows = cur.fetchone()[0]
        cur.execute(
            f'SELECT count(*) FROM (SELECT 1 FROM {TABLE} '
            f'WHERE ({PENDING_PREDICATE}) '
            f'GROUP BY test_result_id, round_number) t')
        groups = cur.fetchone()[0]
    return int(groups), int(rows)


def _store_payload(value, kind, cache, stats, uploader):
    """规范化 → sha → 缓存命中即复用；否则 gzip 上传。返回 (uri, sha, size)。"""
    from shared.infrastructure.storage import StorageUnavailableError
    sha = sha256_hex(value)
    hit = cache.get((kind, sha))
    if hit is not None:
        stats.reused += 1
        return hit
    data = compress(canonical_bytes(value))
    try:
        uri = uploader(data, object_key(kind, sha))
    except StorageUnavailableError as exc:
        raise StorageUnavailableError(
            f'{kind} 对象上传失败（不允许本地降级）{object_key(kind, sha)}: {exc}') from exc
    if not uri or uri.startswith('local://'):
        raise StorageUnavailableError(f'禁止本地降级却拿到 local:// 路径: {uri}')
    record = (uri, sha, len(data))
    cache[(kind, sha)] = record
    stats.uploaded += 1
    return record


def _update_row(conn, row_id, prefix, record):
    """按 id 回写指针列；``prefix_uri IS NULL`` 保证重复执行不覆写已有指针。"""
    uri, sha, size = record
    sql = (f'UPDATE {TABLE} SET '
           f'{prefix}_uri = %s, {prefix}_sha256 = %s, {prefix}_bytes = %s, '
           f'{prefix}_content_type = %s, {prefix}_created_at = %s '
           f'WHERE id = %s AND {prefix}_uri IS NULL')
    with conn.cursor() as cur:
        cur.execute(sql, (uri, sha, size, CONTENT_TYPE,
                          datetime.now(timezone.utc), row_id))
        return cur.rowcount


def process_group(conn, tid, rn, cache, stats, uploader):
    """处理一组：全部上传成功后才写 uri；任一失败则整组不写（可重跑）。"""
    rows = fetch_group_rows(conn, tid, rn)
    planned = []  # [(row_id, prefix, record)]
    for row_id, resp, req in rows:
        for kind, _col, prefix in PAYLOADS:
            value = resp if kind == 'resp' else req
            if value is None:
                stats.skipped_empty += 1
                continue
            record = _store_payload(value, kind, cache, stats, uploader)
            planned.append((row_id, prefix, record))
    for row_id, prefix, record in planned:
        stats.rows += _update_row(conn, row_id, prefix, record)
    stats.groups += 1
    return stats


def run(apply=False, batch_groups=DEFAULT_BATCH_GROUPS,
        sleep_seconds=DEFAULT_SLEEP_SECONDS, limit_groups=0,
        max_consecutive_failures=DEFAULT_MAX_CONSECUTIVE_FAILURES,
        uploader=None):
    """主循环。返回退出码（0 完成 / 1 有失败组 / 2 连续失败中止）。"""
    uploader = uploader or _default_uploader
    conn = _connect()
    stats = _Stats()
    consecutive_failures = 0
    aborted = False
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(f'SET statement_timeout = {_statement_timeout_ms()}')
        gate_before = gate_counts(conn)
        print(f'[GATE] 回填前 resp_missing={gate_before[0]} '
              f'req_missing={gate_before[1]}')
        pending_groups, pending_rows = pending_counts(conn)
        print(f'[SCAN] 待处理组 {pending_groups} / 行 {pending_rows}')
        if not apply:
            print('[DRY] 未执行上传与 UPDATE；加 --apply 执行')
            return 0
        if pending_groups == 0:
            gate = gate_counts(conn)
            print(f'[DONE] 无待处理组；resp_missing={gate[0]} req_missing={gate[1]}')
            return 0 if gate == (0, 0) else 1

        cache = {}
        after = None
        started = time.monotonic()
        while True:
            page_limit = batch_groups
            if limit_groups:
                remaining = limit_groups - stats.groups
                if remaining <= 0:
                    print(f'[LIMIT] 达到 --limit-groups={limit_groups}，'
                          f'本轮提前结束（进度已提交，可重跑续跑）')
                    break
                page_limit = min(page_limit, remaining)
            groups = fetch_group_page(conn, after, page_limit)
            if not groups:
                break
            for tid, rn in groups:
                # 每组一个 savepoint：单组失败只回滚本组，同批已成功组不丢
                with conn.cursor() as cur:
                    cur.execute('SAVEPOINT backfill_group')
                try:
                    process_group(conn, tid, rn, cache, stats, uploader)
                except Exception as exc:  # noqa: BLE001 - 单组失败不中断整批
                    with conn.cursor() as cur:
                        cur.execute('ROLLBACK TO SAVEPOINT backfill_group')
                    stats.failed_groups += 1
                    consecutive_failures += 1
                    print(f'[FAIL] 组 (test_result_id={tid}, round_number={rn}) '
                          f'回填失败，未写 uri：{exc}')
                    if consecutive_failures >= max_consecutive_failures:
                        print(f'[ABORT] 连续失败 {consecutive_failures} 组，'
                              f'疑似存储整体不可用，停止续跑')
                        aborted = True
                        break
                else:
                    with conn.cursor() as cur:
                        cur.execute('RELEASE SAVEPOINT backfill_group')
                    consecutive_failures = 0
            conn.commit()
            after = groups[-1]
            elapsed = time.monotonic() - started
            print(f'[BATCH] {stats.summary()} | 累计 {elapsed:.1f}s')
            if aborted:
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)

        gate_after = gate_counts(conn)
        print(f'[GATE] 回填后 resp_missing={gate_after[0]} '
              f'req_missing={gate_after[1]}')
        print(f'[DONE] {stats.summary()}')
        if aborted:
            return 2
        if stats.failed_groups:
            return 1
        return 0 if gate_after == (0, 0) else 1
    finally:
        conn.close()


def _statement_timeout_ms():
    raw = os.environ.get('DB_BACKFILL_STATEMENT_TIMEOUT_MS')
    try:
        value = int(str(raw).strip()) if raw else DEFAULT_STATEMENT_TIMEOUT_MS
    except (TypeError, ValueError):
        value = DEFAULT_STATEMENT_TIMEOUT_MS
    return value if value > 0 else DEFAULT_STATEMENT_TIMEOUT_MS


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='backfill_int1807')


def main():
    ap = argparse.ArgumentParser(
        description='test_result_dimensions 原始报文内容寻址回填 + 切换门禁'
                    '（INT-1807 / C1）')
    ap.add_argument('--gate', action='store_true',
                    help='只打印切换门禁两项计数（只读），有缺口退出码 1')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    ap.add_argument('--batch-groups', type=int, default=DEFAULT_BATCH_GROUPS,
                    help=f'每批组数（默认 {DEFAULT_BATCH_GROUPS}）')
    ap.add_argument('--sleep', type=float, default=DEFAULT_SLEEP_SECONDS,
                    help=f'批间 sleep 秒数（默认 {DEFAULT_SLEEP_SECONDS}）')
    ap.add_argument('--limit-groups', type=int, default=0,
                    help='本轮最多处理多少组（0=不限；用于分次续跑）')
    ap.add_argument('--max-consecutive-failures', type=int,
                    default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
                    help=f'连续失败多少组判定存储不可用并中止（默认 '
                         f'{DEFAULT_MAX_CONSECUTIVE_FAILURES}）')
    args = ap.parse_args()

    if args.gate:
        conn = _connect()
        try:
            resp_missing, req_missing = gate_counts(conn)
        finally:
            conn.close()
        print(f'resp_missing={resp_missing}')
        print(f'req_missing={req_missing}')
        raise SystemExit(0 if (resp_missing, req_missing) == (0, 0) else 1)

    raise SystemExit(run(
        apply=args.apply,
        batch_groups=max(1, args.batch_groups),
        sleep_seconds=max(0.0, args.sleep),
        limit_groups=max(0, args.limit_groups),
        max_consecutive_failures=max(1, args.max_consecutive_failures),
    ))


if __name__ == '__main__':
    main()

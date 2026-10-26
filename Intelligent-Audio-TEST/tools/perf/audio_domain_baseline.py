# -*- coding: utf-8 -*-
"""INT-1471 音频域性能基线核验脚本（只读）。

三个子命令：

1. `sql` —— 在本地进程内直接调用 audio_service 读侧 QueryHandler，统计
   /audios 列表、/audios/{id} 详情、/audios/tags 各自实际发出的 SQL 条数与
   语句原文，用于确认页级批量化（无 N+1）与标签聚合冷路径无全表扫描。
   只读：SELECT 计数 + 语句文本，不写库。需要 DATABASE_URL 等 .env 变量。

2. `http` —— 对运行中的栈打并发，复用同一个 keep-alive 连接池测
   /audios、/audios/{id}、/audios/tags 的 avg / p50 / p95 / p99 / max，
   并测同栈 /health 作为本机负载地板。
   必须用 127.0.0.1：本机 localhost 每次新建连接解析约 2s（实测），会把
   连接建立时间误算进接口时延。
   默认目标是负责人 2026-10-23 环境铁律指定的 docker 栈
   http://127.0.0.1:15000（database=intelligent_audio_test）；要打 5000 段
   开发栈时显式传 --base http://127.0.0.1:5000 --expect-db intelligent_audio_test_test。

3. `grpc` —— 直连 audio_service gRPC 打并发，剥离网关与 HTTP 层，只看音频域
   自身（含 DB）的成本；与 http 对照可判断瓶颈在网关/主机还是在音频域。

用法（本 run worktree 内，先加载 .env）：

    python tools/perf/audio_domain_baseline.py sql
    python tools/perf/audio_domain_baseline.py http \
        --concurrency 1 10 40 --requests 300
    python tools/perf/audio_domain_baseline.py grpc --target 127.0.0.1:50052 \
        --concurrency 1 10 40 --audio-id <id>

只读约束：本脚本不发任何写请求；库名由 /health 打印，跑完核对是
intelligent_audio_test_test。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

# ==================== SQL 审计 ====================


def _sql_audit() -> int:
    from sqlalchemy import event

    from shared.models.database import get_engine, init_db

    from audio_service.application.handlers.audio_query_handler import AudioQueryHandler
    from audio_service.application.queries.audio_queries import (
        GetAllAudioTagsQuery,
        GetAudioQuery,
        ListAudiosQuery,
    )

    if get_engine() is None:
        init_db()
    engine = get_engine()
    collected: List[str] = []

    def _on_exec(conn, cursor, statement, parameters, context, executemany):
        collected.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", _on_exec)
    handler = AudioQueryHandler()
    try:
        def _measure(label: str, fn) -> None:
            collected.clear()
            started = time.perf_counter()
            result = fn()
            elapsed_ms = (time.perf_counter() - started) * 1000
            data = (result or {}).get('data') or {}
            total = data.get('total', len(data.get('items', [])) if isinstance(data, dict) else '')
            print(f'\n### {label}: {elapsed_ms:.1f} ms, SQL={len(collected)}, total={total}')
            for i, sql in enumerate(collected, 1):
                print(f'  [{i}] {sql[:400]}')

        for per_page in (1, 10, 100):
            _measure(
                f'ListAudios per_page={per_page}',
                lambda pp=per_page: handler.handle_list_audios(
                    ListAudiosQuery(params={'page': 1, 'per_page': pp, 'tags_data': []})),
            )

        first_id = None
        probe = handler.handle_list_audios(
            ListAudiosQuery(params={'page': 1, 'per_page': 1, 'tags_data': []}))
        items = (probe.get('data') or {}).get('items') or []
        if items:
            first_id = items[0]['id']
        if first_id is not None:
            _measure(f'GetAudio id={first_id}', lambda: handler.handle_get_audio(
                GetAudioQuery(audio_id=first_id)))

        _measure('GetAllAudioTags', lambda: handler.handle_get_all_tags(
            GetAllAudioTagsQuery()))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)
    return 0


# ==================== HTTP 并发基线 ====================


def _health(base: str) -> Dict:
    import requests
    resp = requests.get(f'{base}/health', timeout=10)
    return resp.json()


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[idx]


def _bench(base: str, path: str, concurrency: int, total: int,
           health_floor: bool = False) -> Dict:
    """复用同一 Session（keep-alive 连接池）跑 total 个请求。

    预热线：Windows 上并发新建 40 条 TCP 连接本身要 ~2s（SYN/accept 排队），
    若计入测量会把连接建立时间误算成接口时延。故先做一轮与并发数同宽的
    突发请求把连接池填满并丢弃计时，再开始正式测量。
    """
    import requests

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=concurrency, pool_maxsize=concurrency, max_retries=0)
    session.mount('http://', adapter)

    def _ok(resp) -> bool:
        if resp.status_code != 200:
            return False
        payload = resp.json() or {}
        if health_floor:
            return payload.get('status') == 'ok'
        return payload.get('success') is True

    latencies: List[float] = []
    errors: List[str] = []
    lock = threading.Lock()

    def _one() -> None:
        started = time.perf_counter()
        try:
            resp = session.get(f'{base}{path}', timeout=60)
            elapsed = (time.perf_counter() - started) * 1000
            ok = _ok(resp)
            with lock:
                if ok:
                    latencies.append(elapsed)
                else:
                    errors.append(f'HTTP {resp.status_code}: {resp.text[:120]}')
        except Exception as exc:  # noqa: BLE001 - 基线脚本记录全部异常
            with lock:
                errors.append(f'{type(exc).__name__}: {exc}')

    def _burst(count: int) -> None:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(lambda _: _one(), range(count)))

    # 预热：填满连接池，丢弃这一轮计时（含首次连接/首次请求的冷启动成本）
    cold_started = time.perf_counter()
    session.get(f'{base}{path}', timeout=60)
    cold_ms = (time.perf_counter() - cold_started) * 1000
    latencies.clear()
    errors.clear()
    _burst(concurrency)

    latencies.clear()
    errors.clear()
    started = time.perf_counter()
    _burst(total)
    wall_s = time.perf_counter() - started

    return {
        'path': path,
        'concurrency': concurrency,
        'requests': total,
        'ok': len(latencies),
        'errors': errors[:5],
        'cold_ms': round(cold_ms, 1),
        'avg_ms': round(statistics.fmean(latencies), 1) if latencies else None,
        'p50_ms': round(_percentile(latencies, 50), 1),
        'p95_ms': round(_percentile(latencies, 95), 1),
        'p99_ms': round(_percentile(latencies, 99), 1),
        'max_ms': round(max(latencies), 1) if latencies else None,
        'qps': round(len(latencies) / wall_s, 1) if wall_s else None,
    }


def _http_baseline(args) -> int:
    health = _health(args.base)
    print(f'# /health: {health}')
    db = health.get('database')
    if args.expect_db and db != args.expect_db:
        print(f'!! 库名不符：期望 {args.expect_db}，实际 {db}，拒绝继续', file=sys.stderr)
        return 2

    import requests
    audio_id = args.audio_id
    if audio_id is None:
        resp = requests.get(f'{args.base}/api/v1/audios?page=1&per_page=1', timeout=30).json()
        items = ((resp.get('data') or {}).get('items')) or []
        if not items:
            print('!! 音频库为空，无法测详情', file=sys.stderr)
            return 2
        audio_id = items[0]['id']

    targets = [
        ('/api/v1/audios?page=1&per_page=20', args.requests),
        (f'/api/v1/audios/{audio_id}', args.requests),
        ('/api/v1/audios/tags', args.requests),
    ]

    results = []
    for conc in args.concurrency:
        # 每档并发前先测同栈 /health 地板（排除机器整体负载漂移）
        floor = _bench(args.base, '/health', conc, min(args.requests, 60),
                       health_floor=True)
        print(f'\n## concurrency={conc}  /health 地板 avg={floor["avg_ms"]} ms '
              f'p50={floor["p50_ms"]} ms p95={floor["p95_ms"]} ms')
        for path, count in targets:
            row = _bench(args.base, path, conc, count)
            results.append(row)
            print(f'  {path:38s} avg={row["avg_ms"]:>7} ms  p50={row["p50_ms"]:>7} ms  '
                  f'p95={row["p95_ms"]:>7} ms  p99={row["p99_ms"]:>7} ms  '
                  f'max={row["max_ms"]:>7} ms  cold={row["cold_ms"]:>7} ms  '
                  f'qps={row["qps"]}  ok={row["ok"]}/{row["requests"]}')
            if row['errors']:
                print(f'    errors: {row["errors"]}')

    print('\n# JSON 汇总')
    print(json.dumps({'health': health, 'audio_id': audio_id, 'results': results},
                     ensure_ascii=False, indent=2))
    return 0


def _grpc_baseline(args) -> int:
    """直连 audio_service gRPC 打并发，剥离网关与 HTTP 层，只看音频域自身成本。"""
    import grpc

    from shared.proto import audio_service_pb2 as apb
    from shared.proto import audio_service_pb2_grpc as apbg

    channel = grpc.insecure_channel(args.target)
    stub = apbg.AudioConfigServiceStub(channel)

    payloads = {
        'ListAudios per_page=20': lambda: stub.ListAudios(
            apb.ListAudiosRequest(data=json.dumps({'page': 1, 'per_page': 20}))),
        'GetAudio': lambda: stub.GetAudio(
            apb.GetAudioRequest(audio_id=args.audio_id)),
    }
    if args.audio_id is None:
        print('!! 需要 --audio-id', file=sys.stderr)
        return 2

    for label, call in payloads.items():
        cold_started = time.perf_counter()
        call()
        cold_ms = (time.perf_counter() - cold_started) * 1000
        for conc in args.concurrency:
            durations: List[float] = []
            lock = threading.Lock()

            def _one() -> None:
                started = time.perf_counter()
                call()
                elapsed = (time.perf_counter() - started) * 1000
                with lock:
                    durations.append(elapsed)

            with ThreadPoolExecutor(max_workers=conc) as pool:
                list(pool.map(lambda _: _one(), range(conc)))  # 预热/建连
            durations.clear()
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=conc) as pool:
                list(pool.map(lambda _: _one(), range(args.requests)))
            wall_s = time.perf_counter() - started
            print(f'{label:26s} conc={conc:<3d} avg={statistics.fmean(durations):7.1f} ms  '
                  f'p50={_percentile(durations, 50):7.1f}  p95={_percentile(durations, 95):7.1f}  '
                  f'p99={_percentile(durations, 99):7.1f}  max={max(durations):7.1f}  '
                  f'cold={cold_ms:7.1f} ms  qps={len(durations)/wall_s:6.1f}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='INT-1471 音频域性能基线')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('sql', help='本地进程内统计读路径 SQL 条数（只读）')
    http = sub.add_parser('http', help='对运行中的栈打并发（只读）')
    http.add_argument('--base', default='http://127.0.0.1:15000',
                      help='默认 docker 栈 :15000（环境铁律）；5000 段开发栈传 '
                           'http://127.0.0.1:5000。必须用 127.0.0.1：本机 localhost '
                           '每次新建连接解析约 2s，会把连接建立时间误算成接口时延')
    http.add_argument('--concurrency', type=int, nargs='+', default=[10, 40])
    http.add_argument('--requests', type=int, default=200, help='每个接口总请求数')
    http.add_argument('--audio-id', type=int, default=None)
    http.add_argument('--expect-db', default=None,
                      help='给出时校验 /health 的 database，不符即拒绝压测')
    grpc_p = sub.add_parser('grpc', help='直连 audio_service gRPC 打并发（只读）')
    grpc_p.add_argument('--target', default='127.0.0.1:50052')
    grpc_p.add_argument('--concurrency', type=int, nargs='+', default=[10, 40])
    grpc_p.add_argument('--requests', type=int, default=300)
    grpc_p.add_argument('--audio-id', type=int, default=None)
    args = parser.parse_args()

    if args.cmd == 'sql':
        return _sql_audit()
    if args.cmd == 'grpc':
        return _grpc_baseline(args)
    return _http_baseline(args)


if __name__ == '__main__':
    raise SystemExit(main())

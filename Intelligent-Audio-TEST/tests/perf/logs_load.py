# -*- coding: utf-8 -*-
"""日志域接口压测脚本（INT-1468）。

用途：在指定网关地址上，以给定并发数请求日志域只读接口，输出 avg / p95 / p99。

用法：
    python tests/perf/logs_load.py --base http://127.0.0.1:5700 \
        --username 接线测试_admin --password 'JieXianTest@2026' \
        --concurrency 10,40 --requests 200

只发 GET（/logs、/logs/stats），不写库；账号需具备 log:read 权限。
登录口径与 tests/ui/utils/api_client.py 一致（RSA-OAEP/SHA-256 加密）。
"""
import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

sys.path.insert(0, __file__.rsplit('tests', 1)[0])

from tests.ui.utils.api_client import ApiClient  # noqa: E402

_CLIENT = dict(timeout=60, trust_env=False)


def _percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100.0 * (len(ordered) - 1))))
    return ordered[idx]


def _run(target: str, token: str, concurrency: int, requests: int) -> dict:
    url = target
    latencies = []
    errors = []
    lock = threading.Lock()
    counter = {'done': 0}

    def worker():
        with httpx.Client(**_CLIENT) as client:
            while True:
                with lock:
                    if counter['done'] >= requests:
                        return
                    counter['done'] += 1
                t0 = time.perf_counter()
                try:
                    resp = client.get(url, headers={'Authorization': f'Bearer {token}'})
                    dt = (time.perf_counter() - t0) * 1000
                    if resp.status_code != 200:
                        with lock:
                            errors.append(f'{resp.status_code}:{resp.text[:80]}')
                    else:
                        with lock:
                            latencies.append(dt)
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(f'{type(exc).__name__}:{exc}')

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for _ in range(concurrency):
            pool.submit(worker)
    elapsed = time.perf_counter() - t0
    return {
        'url': url,
        'concurrency': concurrency,
        'requests': requests,
        'ok': len(latencies),
        'errors': len(errors),
        'error_sample': errors[:3],
        'avg_ms': round(statistics.fmean(latencies), 1) if latencies else 0,
        'p95_ms': round(_percentile(latencies, 95), 1),
        'p99_ms': round(_percentile(latencies, 99), 1),
        'max_ms': round(max(latencies), 1) if latencies else 0,
        'qps': round(len(latencies) / elapsed, 1) if elapsed else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5700')
    ap.add_argument('--username', default='接线测试_admin')
    ap.add_argument('--password', default='JieXianTest@2026')
    ap.add_argument('--concurrency', default='10,40')
    ap.add_argument('--requests', type=int, default=200)
    ap.add_argument('--path', default=('/api/v1/logs?page=1&per_page=20',
                                       '/api/v1/logs/stats'))
    ap.add_argument('--report', default='')
    args = ap.parse_args()

    client = ApiClient(args.base)
    client.login(args.username, args.password)
    token = client.token

    levels = [int(x) for x in args.concurrency.split(',') if x.strip()]
    results = []
    for path in args.path:
        url = args.base.rstrip('/') + path
        # 预热一次，避免首请求建连计入
        httpx.get(url, headers={'Authorization': f'Bearer {token}'}, **_CLIENT)
        for conc in levels:
            res = _run(url, token, conc, args.requests)
            results.append(res)
            print(json.dumps(res, ensure_ascii=False))

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

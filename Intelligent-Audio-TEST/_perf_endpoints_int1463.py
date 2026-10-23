# -*- coding: utf-8 -*-
"""临时探针（INT-1463）：不同端点在同并发下的基线，用于区分网关/鉴权/服务端瓶颈。"""
import statistics
import sys
import threading
import time

import httpx

sys.path.insert(0, '.')
from tests.ui.utils.api_client import ApiClient  # noqa: E402

ROOT = 'http://127.0.0.1:5700'
PATHS = [
    '/health',
    '/api/v1/reports/statistics',
    '/api/v1/reports/tab-counts',
    '/api/v1/reports?page=1&per_page=20',
]


def run(path, token, concurrency, seconds):
    lat, errs = [], [0]
    lock = threading.Lock()
    stop = time.time() + seconds
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    def worker():
        with httpx.Client(timeout=30, trust_env=False) as c:
            while time.time() < stop:
                t0 = time.perf_counter()
                try:
                    r = c.get(ROOT + path, headers=headers)
                    ok = r.status_code == 200
                except Exception:
                    ok = False
                dt = (time.perf_counter() - t0) * 1000
                with lock:
                    if ok:
                        lat.append(dt)
                    else:
                        errs[0] += 1

    ths = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    s = sorted(lat)
    avg = statistics.mean(s) if s else 0
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))] if s else 0
    print(f'{path:40s} n={len(s):4d} err={errs[0]} rps={len(s)/seconds:6.1f} '
          f'avg={avg:7.1f}ms p50={s[len(s)//2] if s else 0:7.1f} p95={p95:7.1f} max={s[-1] if s else 0:7.1f}')


def main():
    conc = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    only = sys.argv[3].split(',') if len(sys.argv) > 3 else None
    cli = ApiClient(ROOT)
    cli.login('接线测试_admin', 'JieXianTest@2026')
    for p in PATHS:
        if only and p not in only:
            continue
        run(p, cli.token, conc, secs)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""临时压测脚本（INT-1463）：/reports 与 /reports/tab-counts 基线 / 复测。

只读 GET，连真实库栈网关。用法：python _perf_probe_int1463.py [concurrency] [seconds]
"""
import statistics
import sys
import threading
import time

import httpx

sys.path.insert(0, '.')
from tests.ui.utils.api_client import ApiClient  # noqa: E402

ROOT = 'http://127.0.0.1:5700'
PATHS = ['/api/v1/reports?page=1&per_page=20', '/api/v1/reports/tab-counts']


def pct(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    i = min(len(s) - 1, int(len(s) * p))
    return s[i]


def run(path, token, concurrency, seconds):
    lat = []
    errs = [0]
    lock = threading.Lock()
    stop = time.time() + seconds
    headers = {'Authorization': f'Bearer {token}'}
    kw = dict(timeout=30, trust_env=False)

    def worker():
        with httpx.Client(**kw) as c:
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
    avg = statistics.mean(lat) if lat else 0
    print(f'{path}  n={len(lat)} err={errs[0]} avg={avg:.0f}ms '
          f'p50={pct(lat, 0.5):.0f} p95={pct(lat, 0.95):.0f} max={max(lat) if lat else 0:.0f}')


def main():
    conc = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    cli = ApiClient(ROOT)
    cli.login('接线测试_admin', 'JieXianTest@2026')
    print(f'login ok user={cli.user.get("username")} concurrency={conc} seconds={secs}')
    for p in PATHS:
        run(p, cli.token, conc, secs)


if __name__ == '__main__':
    main()

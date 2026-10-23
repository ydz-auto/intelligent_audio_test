# -*- coding: utf-8 -*-
"""临时压测（INT-1463）：asyncio + httpx.AsyncClient 固定并发压端点。

用法：python _perf_async_int1463.py <root> <concurrency> <seconds> <path> [path...]
只读 GET；输出 n / rps / avg / p50 / p95 / max。
"""
import asyncio
import statistics
import sys
import time

import httpx

sys.path.insert(0, '.')
from tests.ui.utils.api_client import ApiClient  # noqa: E402


async def _worker(client, path, headers, deadline, lat, errs, lock):
    while time.perf_counter() < deadline:
        t0 = time.perf_counter()
        try:
            r = await client.get(path, headers=headers)
            ok = r.status_code == 200
        except Exception:
            ok = False
        dt = (time.perf_counter() - t0) * 1000
        async with lock:
            if ok:
                lat.append(dt)
            else:
                errs[0] += 1


async def run(root, path, token, conc, secs):
    lat, errs = [], [0]
    lock = asyncio.Lock()
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    limits = httpx.Limits(max_connections=conc + 20, max_keepalive_connections=conc + 20)
    deadline = time.perf_counter() + secs
    url = root + path
    async with httpx.AsyncClient(timeout=60, trust_env=False, limits=limits) as client:
        await asyncio.gather(*[
            _worker(client, url, headers, deadline, lat, errs, lock)
            for _ in range(conc)])
    s = sorted(lat)
    avg = statistics.mean(s) if s else 0
    p50 = s[len(s) // 2] if s else 0
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))] if s else 0
    print(f'{path:42s} n={len(s):4d} err={errs[0]} rps={len(s)/secs:6.1f} '
          f'avg={avg:7.1f}ms p50={p50:7.1f} p95={p95:7.1f} max={s[-1] if s else 0:7.1f}',
          flush=True)


def main():
    root = sys.argv[1].rstrip('/')
    conc = int(sys.argv[2])
    secs = int(sys.argv[3])
    paths = sys.argv[4:]
    cli = ApiClient(root)
    cli.login('接线测试_admin', 'JieXianTest@2026')
    print(f'root={root} concurrency={conc} seconds={secs}', flush=True)
    for p in paths:
        asyncio.run(run(root, p, cli.token, conc, secs))


if __name__ == '__main__':
    main()

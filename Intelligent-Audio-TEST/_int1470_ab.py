# -*- coding: utf-8 -*-
"""INT-1470 时延配对 A/B：默认口径 vs 旧路径代理（favorite=true，仍走全量+聚合）vs /health。"""
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

API = 'http://127.0.0.1:7600/api/v1'
cli = httpx.Client(base_url=API, timeout=120, trust_env=False,
                   limits=httpx.Limits(max_connections=64, max_keepalive_connections=64,
                                       keepalive_expiry=60))


def timed(path):
    t0 = time.perf_counter()
    r = cli.get(path)
    dt = (time.perf_counter() - t0) * 1000
    r.read()
    return dt


def round_stats(path):
    with ThreadPoolExecutor(max_workers=40) as ex:
        lats = sorted(ex.map(lambda _: timed(path), range(40)))
    return {'avg': round(statistics.mean(lats), 2),
            'median': round(statistics.median(lats), 2),
            'p95': round(lats[37], 2)}


for p in ('/groups', '/health', '/groups?favorite=true'):
    for _ in range(5):
        timed(p)

res = {'groups': [], 'health': [], 'old_path': []}
for i in range(7):
    if i % 2 == 0:
        order = [('groups', '/groups'), ('old_path', '/groups?favorite=true'),
                 ('health', '/health')]
    else:
        order = [('health', '/health'), ('old_path', '/groups?favorite=true'),
                 ('groups', '/groups')]
    for k, p in order:
        res[k].append(round_stats(p))

g = [r['avg'] for r in res['groups']]
h = [r['avg'] for r in res['health']]
o = [r['avg'] for r in res['old_path']]
print(json.dumps({
    'rounds': res,
    'medians': {'groups': round(statistics.median(g), 2),
                'health': round(statistics.median(h), 2),
                'old_path': round(statistics.median(o), 2)},
    'ratio_groups_over_health': round(statistics.median(g) / statistics.median(h), 3),
    'paired_ratio_median': round(statistics.median(
        [a / b for a, b in zip(g, h)]), 3),
    'improvement_same_stack_vs_old_path': round(
        statistics.median(o) / statistics.median(g), 2),
    'improvement_vs_recorded_336': round(336.1 / statistics.median(g), 2),
}, ensure_ascii=False, indent=1))
cli.close()

# -*- coding: utf-8 -*-
"""INT-1470 测试 run 实测探针（临时，run 结束删除）。

测点：响应体积 / 分页信封与收敛 / 下推生效 / 单次 RPC / 计数一致性 /
时延（串行 + 并发 40 对同栈地板）/ 筛选态回归 / 旧调用方兼容。
"""
import glob
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg2
from google.protobuf.json_format import MessageToDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'shared', 'proto'))

from shared.proto import task_service_pb2 as task_pb  # noqa: E402
from shared.proto import task_service_pb2_grpc as task_grpc  # noqa: E402

GW = 'http://127.0.0.1:7600'
API = GW + '/api/v1'
GRPC = '127.0.0.1:53661'
META = [('x-user-is-admin', 'true')]

out = {}


def get(client, path):
    r = client.get(path)
    try:
        body = r.json()
    except Exception:
        body = {}
    data = body.get('data') if isinstance(body, dict) else None
    if not isinstance(data, dict):
        data = {}
    items = data.get('items') or []
    return {
        'status': r.status_code,
        'bytes': len(r.content),
        'items': len(items),
        'total': data.get('total'),
        'page': data.get('page'),
        'per_page': data.get('per_page'),
        'pages': data.get('pages'),
        'ids': [i.get('id') for i in items],
        'counts': {str(i.get('id')): i.get('test_case_count') for i in items},
        'raw_body': body,
    }


def httpx_client(**kw):
    return httpx.Client(base_url=API, timeout=60, trust_env=False, **kw)


def main():
    cli = httpx_client()
    # ---------- A. 请求矩阵 ----------
    cases = [
        ('default', '/groups'),
        ('per_page=40', '/groups?per_page=40'),
        ('per_page=200', '/groups?per_page=200'),
        ('per_page=1000', '/groups?per_page=1000'),
        ('fields=summary', '/groups?fields=summary'),
        ('fields=summary&per_page=200', '/groups?fields=summary&per_page=200'),
        ('page=4', '/groups?page=4'),
        ('page=5(超末页)', '/groups?page=5'),
        ('page=0&per_page=0', '/groups?page=0&per_page=0'),
        ('per_page=-1', '/groups?per_page=-1'),
        ('keyword=ui405', '/groups?keyword=ui405'),
        ('type=api', '/groups?type=api'),
        ('dimension_id=1', '/groups?dimension_id=1'),
        ('algorithm_type=x', '/groups?algorithm_type=x'),
        ('favorite=true', '/groups?favorite=true'),
        ('only_deleted=true', '/groups?only_deleted=true'),
    ]
    matrix = {}
    for name, path in cases:
        m = get(cli, path)
        matrix[name] = {k: m[k] for k in
                        ('status', 'bytes', 'items', 'total', 'page', 'per_page', 'pages')}
        if name == 'per_page=200':
            full = m
        if name == 'fields=summary&per_page=200':
            summary_full = m
        if name == 'default':
            default_items = m
    out['matrix'] = matrix

    # ---------- B. 翻页收敛 ----------
    seen = {}
    page_sizes = []
    for p in range(1, 5):
        m = get(cli, f'/groups?page={p}&per_page=40')
        page_sizes.append(m['items'])
        for gid in m['ids']:
            seen[gid] = seen.get(gid, 0) + 1
    dup = {k: v for k, v in seen.items() if v > 1}
    full_ids = set(full['ids'])
    union = set(seen)
    out['pagination'] = {
        'page_sizes': page_sizes,
        'unique_ids': len(union),
        'total': full['total'],
        'duplicates': dup,
        'missing_vs_full': sorted(full_ids - union),
        'extra_vs_full': sorted(union - full_ids),
    }

    # ---------- C. 计数一致性（网关全量投影 vs summary vs DB vs 分页各页） ----------
    dsn = dict(host='localhost', port=5432, user='intelligent_audio_test',
               password='intelligent_audio_test666', dbname='intelligent_audio_test_test')
    conn = psycopg2.connect(**dsn)
    cur = conn.cursor()
    cur.execute("select group_id, count(*) from test_cases where deleted=false "
                "group by group_id")
    sql_counts = {str(g): int(c) for g, c in cur.fetchall()}
    cur.execute("select count(*) from test_case_groups where deleted=false")
    db_groups = cur.fetchone()[0]
    cur.close()
    conn.close()
    diffs_full = {g['id']: (g['test_case_count'], sql_counts.get(g['id'], 0))
                  for g in full_items(full) if g['test_case_count'] != sql_counts.get(g['id'], 0)}
    out['counts_vs_sql'] = {'db_groups': db_groups, 'diffs': diffs_full,
                            'checked': len(full['ids'])}
    # summary 与完整投影逐项比对
    samp = {k: v for k, v in summary_full['counts'].items()}
    diffs_summary = {gid: (samp[gid], full['counts'].get(gid))
                     for gid in samp if samp[gid] != full['counts'].get(gid)}
    out['summary_vs_full'] = {'checked': len(samp), 'diffs': diffs_summary,
                              'summary_keys_sample': None}
    # 各页计数 vs 全量投影
    page_diffs = {}
    for p in range(1, 5):
        m = get(cli, f'/groups?page={p}&per_page=40')
        for gid, c in m['counts'].items():
            if full['counts'].get(gid) != c:
                page_diffs[gid] = (c, full['counts'].get(gid))
    out['page_counts_vs_full'] = {'checked': sum(page_sizes), 'diffs': page_diffs}

    # ---------- D. gRPC 直连：下推生效 / 旧调用方 / 统计口径 ----------
    import grpc
    ch = grpc.insecure_channel(GRPC)
    stub = task_grpc.TaskDataServiceStub(ch)

    def rpc_groups(page=0, per_page=0, algorithm_type=''):
        resp = stub.ListTestCaseGroups(task_pb.ListTestCaseGroupsRequest(
            algorithm_type=algorithm_type, search='', page=page, per_page=per_page),
            metadata=META, timeout=60)
        data = json.loads(resp.data) if resp.data else {}
        return {'success': resp.success, 'items': len(data.get('items') or []),
                'total': data.get('total'), 'payload_chars': len(resp.data or ''),
                'data': data}

    grpc_full = rpc_groups()
    grpc_p1 = rpc_groups(1, 40)
    grpc_p4 = rpc_groups(4, 40)
    grpc_p5 = rpc_groups(5, 40)
    grpc_big = rpc_groups(1, 200)
    stats = stub.GetTestCaseStats(task_pb.TestCaseAggStatsRequest(
        group_by='group_id', deleted=False), metadata=META, timeout=120)
    stats_data = json.loads(stats.data) if stats.data else {}
    stats_counts = {str(i.get('key')): int(i.get('count') or 0)
                    for i in (stats_data.get('items') or [])}
    grpc_all = {str(i['id']): int(i.get('test_case_count') or 0)
                for i in grpc_full['data'].get('items') or []}
    diff_stats = {gid: (grpc_all.get(gid, 0), stats_counts.get(gid, 0))
                  for gid in grpc_all
                  if grpc_all.get(gid, 0) != stats_counts.get(gid, 0)}
    stats_only_groups = sorted(set(stats_counts) - set(grpc_all))
    out['grpc'] = {
        'full': {k: grpc_full[k] for k in ('success', 'items', 'total', 'payload_chars')},
        'page1_40': {k: grpc_p1[k] for k in ('success', 'items', 'total', 'payload_chars')},
        'page4_40': {k: grpc_p4[k] for k in ('success', 'items', 'total', 'payload_chars')},
        'page5_40': {k: grpc_p5[k] for k in ('success', 'items', 'total', 'payload_chars')},
        'page1_200': {k: grpc_big[k] for k in ('success', 'items', 'total', 'payload_chars')},
        'legacy_total_eq_len': grpc_full['total'] == grpc_full['items'],
        'counts_vs_GetTestCaseStats': {'groups': len(grpc_all), 'diffs': diff_stats,
                                       'stats_only_groups(已删组等)': len(stats_only_groups)},
        'stats_total_cases': sum(stats_counts.values()),
    }
    # 下推页 id 与网关页 id 是否同序同集
    gw_p1 = get(cli, '/groups?page=1&per_page=40')
    out['grpc']['page1_ids_match_gateway'] = (
        [str(i['id']) for i in grpc_p1['data'].get('items') or []] == gw_p1['ids'])
    gw_p4 = get(cli, '/groups?page=4&per_page=40')
    out['grpc']['page4_ids_match_gateway'] = (
        [str(i['id']) for i in grpc_p4['data'].get('items') or []] == gw_p4['ids'])
    ch.close()

    # ---------- E. 单次 RPC（日志口径） ----------
    log_files = sorted(glob.glob(os.path.join(HERE, 'logs', 'ui_stack', 'shift2600',
                                              'ui_task_service', 'app-*.log')),
                       key=os.path.getmtime)
    logf = log_files[-1]
    before = os.path.getsize(logf)
    get(cli, '/groups')
    with open(logf, 'r', encoding='utf-8', errors='replace') as fh:
        fh.seek(before)
        chunk = fh.read()
    out['rpc_per_request'] = {
        'log': os.path.basename(logf),
        'ListTestCaseGroups': chunk.count('[gRPC-recv] /task_service.TaskDataService/ListTestCaseGroups  request:'),
        'GetTestCaseStats': chunk.count('[gRPC-recv] /task_service.TaskDataService/GetTestCaseStats  request:'),
    }

    # ---------- F. 时延 ----------
    lat_cli = httpx.Client(base_url=API, timeout=120, trust_env=False,
                           limits=httpx.Limits(max_connections=64,
                                               max_keepalive_connections=64,
                                               keepalive_expiry=60))

    def timed(path):
        t0 = time.perf_counter()
        r = lat_cli.get(path)
        dt = (time.perf_counter() - t0) * 1000
        r.read()
        return dt

    def warm(path, n=5):
        for _ in range(n):
            timed(path)

    warm('/groups')
    warm('/health')
    serial = {}
    for name, path in [('groups', '/groups'), ('health', '/health'),
                       ('old_path_favorite', '/groups?favorite=true')]:
        times = sorted(timed(path) for _ in range(20))
        serial[name] = {'avg': round(statistics.mean(times), 2),
                        'median': round(statistics.median(times), 2),
                        'min': round(times[0], 2), 'max': round(times[-1], 2)}

    def round_stats(path):
        """并发 40：返回（逐请求时延均值, 中位数, p95, 墙钟）。"""
        with ThreadPoolExecutor(max_workers=40) as ex:
            t0 = time.perf_counter()
            lats = list(ex.map(lambda _: timed(path), range(40)))
            wall = (time.perf_counter() - t0) * 1000
        lats.sort()
        return {'avg': round(statistics.mean(lats), 2),
                'median': round(statistics.median(lats), 2),
                'p95': round(lats[int(len(lats) * 0.95) - 1], 2),
                'max': round(lats[-1], 2),
                'wall': round(wall, 1)}

    conc = {'groups': [], 'health': [], 'old_path': []}
    for i in range(5):
        if i % 2 == 0:
            conc['groups'].append(round_stats('/groups'))
            conc['health'].append(round_stats('/health'))
        else:
            conc['health'].append(round_stats('/health'))
            conc['groups'].append(round_stats('/groups'))
    for _ in range(3):
        conc['old_path'].append(round_stats('/groups?favorite=true'))
    g_med = statistics.median([r['avg'] for r in conc['groups']])
    h_med = statistics.median([r['avg'] for r in conc['health']])
    out['latency'] = {
        'serial': serial,
        'concurrency40': conc,
        'conc40_groups_avg_median': round(g_med, 2),
        'conc40_health_avg_median': round(h_med, 2),
        'ratio_median': round(g_med / h_med, 3),
        'per_round_ratio_median': round(statistics.median(
            [g['avg'] / h['avg'] for g, h in zip(conc['groups'], conc['health'])]), 3),
        'old_path_avg_median': round(statistics.median(
            [r['avg'] for r in conc['old_path']]), 2),
        'improvement_vs_old_path': round(
            statistics.median([r['avg'] for r in conc['old_path']]) / g_med, 2),
    }

    # ---------- G. 兼容链路 ----------
    compat = {}
    for path in ['/home/stats/details', '/home/stats/summary', '/tags', '/tags/categories']:
        r = lat_cli.get(path)
        compat[path] = {'status': r.status_code, 'bytes': len(r.content)}
    out['compat'] = compat
    lat_cli.close()
    cli.close()

    print(json.dumps(out, ensure_ascii=False, indent=1))


def full_items(m):
    """从 get() 返回体取 items（保留完整字段）。"""
    return ((m.get('raw_body') or {}).get('data') or {}).get('items') or []


if __name__ == '__main__':
    main()

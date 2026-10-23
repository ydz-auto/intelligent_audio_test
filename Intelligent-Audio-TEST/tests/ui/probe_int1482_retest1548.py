# -*- coding: utf-8 -*-
"""INT-1482 / INT-1548 复测：报告生成、报告对比、case-averages（统计页评估维度依赖）。

先经浏览器登录取 token，再用 requests 直连 docker 网关 15000，逐项记录真实请求/响应与耗时。
输出 JSON 到 tests/ui/artifacts/int1482/retest_1548.json
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1482_lib as L  # noqa: E402

BACKEND = 'http://localhost:15000/api/v1'
ART = L.ART
OUT = os.path.join(ART, 'retest_1548.json')


def token_from_browser():
    d = L.driver()
    try:
        L.login(d)
        tok = d.execute_script(
            "return (window.localStorage.getItem('iatp:auth:token:v1')||'').replace(/^\"|\"$/g,'')"
        )
        return tok
    finally:
        try:
            d.quit()
        except Exception:
            pass


def call(s, method, path, body=None, timeout=130):
    t0 = time.time()
    try:
        r = s.request(method, BACKEND + path, json=body, timeout=timeout)
        dur = round(time.time() - t0, 1)
        try:
            data = r.json()
        except Exception:
            data = r.text[:2000]
        return {'path': path, 'method': method, 'status': r.status_code, 'dur_s': dur,
                'body': body, 'resp': data}
    except Exception as e:
        return {'path': path, 'method': method, 'status': 'EXC', 'dur_s': round(time.time() - t0, 1),
                'body': body, 'error': str(e)[:500]}


def main():
    tok = token_from_browser()
    print('token len', len(tok))
    s = requests.Session()
    s.headers.update({'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    res = {'token': bool(tok), 'env': {}}

    env = requests.get('http://localhost:15000/health', timeout=15).json()
    res['env']['health'] = env

    res['tab_counts'] = call(s, 'GET', '/reports/tab-counts', timeout=60)
    print('tab-counts', res['tab_counts'].get('status'), res['tab_counts'].get('dur_s'))

    # 报告生成（任务 397：INT-1548 修复后仍卡 result_data.json 的任务）
    res['gen_397'] = call(s, 'POST', '/reports/generate-task', {'task_id': 397}, timeout=180)
    print('generate 397', res['gen_397'].get('status'), res['gen_397'].get('dur_s'), str(res['gen_397'].get('resp'))[:200])

    # 报告生成（任务 527：另一条复现任务）
    res['gen_527'] = call(s, 'POST', '/reports/generate-task', {'task_id': 527}, timeout=180)
    print('generate 527', res['gen_527'].get('status'), res['gen_527'].get('dur_s'), str(res['gen_527'].get('resp'))[:200])

    # 报告对比（418? 用 412+390，INT-1548 记录的组合）
    res['compare'] = call(s, 'POST', '/reports/compare', {'task_ids': [412, 390]}, timeout=130)
    print('compare', res['compare'].get('status'), res['compare'].get('dur_s'), str(res['compare'].get('resp'))[:200])

    # case-averages（统计页依赖）
    for tid in (413, 418, 397):
        r = call(s, 'POST', '/reports/case-averages', {'task_id': tid}, timeout=130)
        res['case_avg_%s' % tid] = r
        print('case-averages', tid, r.get('status'), r.get('dur_s'))

    os.makedirs(ART, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('WROTE', OUT)


if __name__ == '__main__':
    main()

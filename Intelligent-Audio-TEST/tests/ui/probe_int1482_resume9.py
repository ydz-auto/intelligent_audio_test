# -*- coding: utf-8 -*-
"""INT-1482 续测探针9：/tasks?status=completed 可用性定时（生成/对比任务选择器数据源）。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        for i in (1, 2):
            t0 = time.time()
            r = L.api(d, '/tasks?status=completed&per_page=100&deleted=false', timeout=180)
            body = r.get('json') or {}
            data = body.get('data') or {}
            OUT['tasks_%d' % i] = {
                'status': r['status'], 'secs': round(time.time() - t0, 2),
                'total': data.get('total'), 'items_n': len(data.get('items') or []),
                'text': (r.get('text') or '')[:200] if r['status'] != 200 else None,
            }
            t0 = time.time()
            r2 = L.api(d, '/tasks?page=1&per_page=20', timeout=180)
            OUT['tasks_all_%d' % i] = {'status': r2['status'], 'secs': round(time.time() - t0, 2)}
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe9_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

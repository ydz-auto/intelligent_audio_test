# -*- coding: utf-8 -*-
"""INT-1482 续测探针8：DB 筛出的「有结果且无报告」任务 case-averages 实测。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def summarize(body):
    if not isinstance(body, dict):
        return None
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    if not isinstance(data, dict):
        return None
    oa = data.get('overall_averages') or []
    return {'total_cases': data.get('total_cases'), 'total_results': data.get('total_results'),
            'overall_n': len(oa), 'overall_names': [x.get('metric') for x in oa[:8]],
            'resources_n': len(data.get('resources') or []),
            'metric_data_n': len(data.get('metric_data') or []), 'partial': data.get('partial')}


def main():
    d = L.driver()
    try:
        L.login(d)
        for tid in (218, 214, 310, 270):
            t0 = time.time()
            resp = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=120)
            OUT['avg_%d' % tid] = {'status': resp['status'], 'secs': round(time.time() - t0, 2),
                                   'summary': summarize(resp.get('json')),
                                   'text': None if summarize(resp.get('json')) else (resp.get('text') or '')[:200]}
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe8_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1482 续测探针6：生成夹具任务(290/286) case-averages + 任务 412 状态。"""
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
            'overall_n': len(oa), 'overall_names': [x.get('metric') for x in oa[:5]],
            'resources_n': len(data.get('resources') or []), 'partial': data.get('partial')}


def main():
    d = L.driver()
    try:
        L.login(d)
        r = L.api(d, '/tasks?page=1&per_page=5&keyword=412')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['task412_search'] = [(t.get('id'), t.get('name'), t.get('status')) for t in items]
        r = L.api(d, '/tasks?page=1&per_page=100&status=completed&deleted=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['completed_ids'] = [t.get('id') for t in items]
        OUT['has_412'] = 412 in OUT['completed_ids']
        OUT['has_290'] = 290 in OUT['completed_ids']
        OUT['has_585'] = 585 in OUT['completed_ids']
        for tid in (290, 286):
            t0 = time.time()
            resp = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=240)
            OUT['avg_%s' % tid] = {'status': resp['status'], 'secs': round(time.time() - t0, 2),
                                   'summary': summarize(resp.get('json'))}
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe6_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

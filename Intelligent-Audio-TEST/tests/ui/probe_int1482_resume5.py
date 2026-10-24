# -*- coding: utf-8 -*-
"""INT-1482 续测探针5：找出「有评估结果但还没有报告」的小任务，作为生成链路夹具。"""
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
    return {
        'total_cases': data.get('total_cases'),
        'total_results': data.get('total_results'),
        'overall_n': len(oa),
        'overall_names': [x.get('metric') for x in oa[:5]],
        'resources_n': len(data.get('resources') or []),
        'metric_data_n': len(data.get('metric_data') or []),
        'partial': data.get('partial'),
    }


def main():
    d = L.driver()
    try:
        L.login(d)
        r = L.api(d, '/reports?page=1&per_page=200&deleted=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        task_ids_with_report = set(int(i['task_id']) for i in items if i.get('task_id'))
        OUT['with_report_n'] = len(task_ids_with_report)

        r = L.api(d, '/tasks?page=1&per_page=100')
        tasks = ((r.get('json') or {}).get('data') or {}).get('items') or []
        cands = [t for t in tasks if t.get('status') == 'completed'
                 and int(t.get('id') or 0) not in task_ids_with_report
                 and 0 < int(t.get('case_count') or 0) <= 20]
        OUT['candidates'] = [(t['id'], t.get('case_count'), (t.get('name') or '')[:40]) for t in cands]

        for t in cands[:6]:
            tid = int(t['id'])
            t0 = time.time()
            resp = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=240)
            s = summarize(resp.get('json'))
            OUT['avg_%s' % tid] = {'status': resp['status'], 'secs': round(time.time() - t0, 2),
                                   'summary': s,
                                   'text': None if s else (resp.get('text') or '')[:200]}
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe5_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

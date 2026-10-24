# -*- coding: utf-8 -*-
"""INT-1482 续测探针：登录后列出报告/任务，直连三条剩余项的接口取基线与夹具。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def timed(fn):
    t = time.time()
    r = fn()
    return r, round(time.time() - t, 2)


def main():
    d = L.driver()
    try:
        L.login(d)

        r = L.api(d, '/reports?page=1&per_page=100')
        OUT['reports_status'] = r['status']
        data = (r.get('json') or {}).get('data') or {}
        items = data.get('items') or []
        OUT['reports_total'] = data.get('total')
        OUT['reports'] = [
            {
                'id': i.get('id'),
                'name': (i.get('name') or '')[:60],
                'status': i.get('status'),
                'task_id': i.get('task_id'),
                'deleted': i.get('deleted'),
                'created_at': i.get('created_at'),
                'total_cases': (i.get('summary') or {}).get('total_cases'),
            }
            for i in items[:40]
        ]

        r = L.api(d, '/reports/tab-counts')
        OUT['tab_counts'] = {'status': r['status'], 'json': r.get('json')}

        # 候选：完成任务
        r = L.api(d, '/tasks?page=1&per_page=50')
        OUT['tasks_status'] = r['status']
        tdata = (r.get('json') or {}).get('data') or {}
        titems = tdata.get('items') or []
        OUT['tasks_total'] = tdata.get('total')
        OUT['tasks'] = [
            {
                'id': t.get('id'),
                'name': (t.get('name') or '')[:50],
                'status': t.get('status'),
                'test_type': t.get('test_type'),
                'case_count': t.get('case_count') or t.get('total_cases'),
            }
            for t in titems[:30]
        ]

        # case-averages 直连（评估维度/散点·热力图数据源）
        cand = [i for i in items if i.get('task_id') and not i.get('deleted')]
        if cand:
            tid = cand[0]['task_id']
            OUT['case_avg_task'] = tid
            resp, secs = timed(lambda: L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=180))
            OUT['case_avg'] = {'status': resp['status'], 'secs': secs, 'text': (resp.get('text') or '')[:1500]}
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str)[:12000])
    finally:
        with open(os.path.join(L.ART, 'probe_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

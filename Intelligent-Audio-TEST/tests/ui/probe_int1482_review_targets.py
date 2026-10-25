# -*- coding: utf-8 -*-
"""INT-1482 补图轮：确认复核历史夹具报告(484/387/493)的 task_id 与复核条目。"""
import json
import sys

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}

d = L.driver()
try:
    L.login(d)
    for rid in ('484', '387', '493'):
        r = L.api(d, '/reports/%s' % rid)
        rep = (r.get('json') or {}).get('data') or (r.get('json') or {})
        item = rep.get('report') or rep
        tid = item.get('task_id') or item.get('taskId')
        OUT['report_%s' % rid] = {'status': r['status'], 'task_id': tid,
                                  'name': item.get('name'), 'keys': list(item.keys())[:25]}
        if tid:
            h = L.api(d, '/tasks/results/%s/review-history' % tid)
            hj = h.get('json') or {}
            rows = hj.get('data') if isinstance(hj.get('data'), list) else hj.get('items') or hj.get('records') or []
            OUT['history_%s' % tid] = {'status': h['status'], 'n': len(rows) if isinstance(rows, list) else None,
                                       'sample': rows[:4] if isinstance(rows, list) else str(hj)[:400]}
            a = L.api(d, '/tasks/results/%s/ai-review-history' % tid)
            aj = a.get('json') or {}
            arows = aj.get('data') if isinstance(aj.get('data'), list) else aj.get('items') or aj.get('records') or []
            OUT['ai_%s' % tid] = {'status': a['status'], 'n': len(arows) if isinstance(arows, list) else None,
                                  'sample': arows[:2] if isinstance(arows, list) else str(aj)[:300]}
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
finally:
    d.quit()

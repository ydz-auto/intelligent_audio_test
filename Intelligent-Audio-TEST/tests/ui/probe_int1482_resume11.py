# -*- coding: utf-8 -*-
"""INT-1482 续测探针11：确认新夹具任务是否在生成弹窗数据源里、统计页当前最新 task_id、case-averages 对新夹具的响应。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}
CAND = [396, 397, 398, 377, 394, 319, 318, 316, 315]


def main():
    d = L.driver()
    try:
        L.login(d)
        r = L.api(d, '/tasks?status=completed&per_page=100&deleted=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        ids = [i.get('id') for i in items]
        OUT['tasks_http'] = r['status']
        OUT['tasks_total'] = len(items)
        OUT['cands_present'] = [c for c in CAND if c in ids]
        OUT['cands_missing'] = [c for c in CAND if c not in ids]

        r2 = L.api(d, '/reports?page=1&per_page=1000&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items2 = ((r2.get('json') or {}).get('data') or {}).get('items') or []
        OUT['reports_http'] = r2['status']
        OUT['reports_n'] = len(items2)
        OUT['latest_reports'] = [
            {'id': i.get('id'), 'task_id': i.get('task_id'), 'status': i.get('status'),
             'type': i.get('report_type') or i.get('type'), 'created_at': i.get('created_at')}
            for i in items2[:5]
        ]
        first_task = next((i for i in items2 if isinstance(i.get('task_id'), int) and i.get('task_id') > 0), None)
        OUT['first_task_report'] = {'id': first_task.get('id'), 'task_id': first_task.get('task_id')} if first_task else None

        OUT['case_avg'] = {}
        for tid in (396, 397, 398):
            t0 = time.time()
            ra = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=180)
            j = ra.get('json') or {}
            data = j.get('data') or {}
            OUT['case_avg'][str(tid)] = {
                'http': ra['status'], 'secs': round(time.time() - t0, 1),
                'overall_n': len(data.get('overall_averages') or []),
                'resources_n': len(data.get('resources') or []),
                'metric_data_n': len(data.get('metric_data') or []),
                'keys': list(data.keys())[:12],
                'msg': j.get('message'),
            }
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe11_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

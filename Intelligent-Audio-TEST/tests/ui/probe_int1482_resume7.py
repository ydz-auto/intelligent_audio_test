# -*- coding: utf-8 -*-
"""INT-1482 续测探针7：在「已完成且无报告」的任务里找一个 case-averages 真有数据的，作为生成/统计夹具。"""
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
        r = L.api(d, '/reports?page=1&per_page=200&deleted=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        with_report = set(int(i['task_id']) for i in items if i.get('task_id'))
        r = L.api(d, '/tasks?page=1&per_page=100&status=completed&deleted=false')
        tasks = ((r.get('json') or {}).get('data') or {}).get('items') or []
        cands = [int(t['id']) for t in tasks if int(t.get('id')) not in with_report]
        OUT['cands_n'] = len(cands)
        OUT['cands'] = cands[:40]
        hits = []
        for tid in cands[:28]:
            t0 = time.time()
            try:
                resp = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=45)
            except Exception as e:
                OUT['err_%d' % tid] = str(e)[:100]
                continue
            s = summarize(resp.get('json'))
            rec = {'id': tid, 'status': resp['status'], 'secs': round(time.time() - t0, 2), 'summary': s}
            OUT['t_%d' % tid] = rec
            if s and (s.get('total_results') or 0) > 0:
                hits.append(rec)
                if len(hits) >= 3:
                    break
        OUT['hits'] = hits
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe7_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1482 续测探针4：真实任务 case-averages（评估维度）+ 对比报告 583 回读。"""
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
        'overall_first': oa[0] if oa else None,
        'resources_n': len(data.get('resources') or []),
        'metric_data_n': len(data.get('metric_data') or []),
        'partial': data.get('partial'),
        'missing_n': len(data.get('missing_case_ids') or []),
    }


def main():
    d = L.driver()
    try:
        L.login(d)
        for tid in (413, 418):
            resp, secs = timed(lambda: L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=240))
            s = summarize(resp.get('json'))
            OUT['case_avg_%s' % tid] = {'status': resp['status'], 'secs': secs, 'summary': s,
                                        'text': None if s else (resp.get('text') or '')[:300]}
        r = L.api(d, '/reports/583')
        det = ((r.get('json') or {}).get('data') or {})
        OUT['report583'] = {
            'status': r['status'], 'id': det.get('id'), 'name': det.get('name'),
            'report_type': det.get('report_type'), 'task_id': det.get('task_id'),
            'summary_keys': sorted(list((det.get('summary') or {}).keys())),
            'summary': det.get('summary'),
            'result_count': len(det.get('results') or det.get('case_results') or []),
            'top_keys': sorted(list(det.keys()))[:25],
        }
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe4_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

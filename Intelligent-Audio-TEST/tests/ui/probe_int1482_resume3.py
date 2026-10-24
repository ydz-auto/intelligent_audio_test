# -*- coding: utf-8 -*-
"""INT-1482 续测探针3：小任务 case-averages 复测 + 对比 412+390 定时。"""
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
    return {
        'total_cases': data.get('total_cases'),
        'total_results': data.get('total_results'),
        'overall_n': len(data.get('overall_averages') or []),
        'resources_n': len(data.get('resources') or []),
        'metric_data_n': len(data.get('metric_data') or []),
        'partial': data.get('partial'),
        'missing_n': len(data.get('missing_case_ids') or []),
    }


def main():
    d = L.driver()
    try:
        L.login(d)
        for i in (1, 2):
            resp, secs = timed(lambda: L.api(d, '/reports/case-averages', 'POST', {'task_id': 397}, timeout=240))
            OUT['case_avg_397_%d' % i] = {'status': resp['status'], 'secs': secs,
                                          'summary': summarize(resp.get('json')),
                                          'text': None if summarize(resp.get('json')) else (resp.get('text') or '')[:300]}
        # 对比 412+390（真实提交，记 report_id 后续清理）
        resp, secs = timed(lambda: L.api(d, '/reports/compare', 'POST',
                                         {'task_ids': [412, 390], 'name': '接线测试_INT1482_对比_%s' % time.strftime('%H%M%S')},
                                         timeout=300))
        OUT['compare'] = {'status': resp['status'], 'secs': secs, 'text': (resp.get('text') or '')[:800]}
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str)[:5000])
    finally:
        with open(os.path.join(L.ART, 'probe3_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

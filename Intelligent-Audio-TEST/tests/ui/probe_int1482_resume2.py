# -*- coding: utf-8 -*-
"""INT-1482 续测探针2：case-averages / compare 直连定时复测（只读，不写库）。"""
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
        for tid in (413, 418, 417, 527, 397):
            resp, secs = timed(lambda: L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=240))
            body = resp.get('json')
            summary = None
            if isinstance(body, dict):
                data = body.get('data') or body
                if isinstance(data, dict):
                    summary = {
                        'overall_n': len(data.get('overall_averages') or []),
                        'resources_n': len(data.get('resources') or []),
                        'metric_data_n': len(data.get('metric_data') or []),
                        'keys': sorted(list(data.keys()))[:12],
                        'overall_first': (data.get('overall_averages') or [None])[0],
                    }
            OUT['case_avg_%s' % tid] = {
                'status': resp['status'], 'secs': secs,
                'summary': summary,
                'text': (resp.get('text') or '')[:400] if not summary else None,
            }
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str)[:6000])
    finally:
        with open(os.path.join(L.ART, 'probe2_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

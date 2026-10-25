# -*- coding: utf-8 -*-
"""INT-1482 续测 E 轮探针16：INT-1825 解阻后核对报告列表与统计页任务上下文。

只读：确认当前最新报告（566/task527 陈旧）是否仍是统计页 case-averages 的上下文来源，
并预判用任务 411 自建「接线测试_」报告做统计页指标层夹具的可行性。
"""
import json
import os
import sys

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    d = L.driver()
    try:
        L.login(d)
        r = L.api(d, '/reports?page=1&per_page=10&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['list_http'] = r['status']
        OUT['list_items'] = [
            {'id': i.get('id'), 'task_id': i.get('task_id'), 'task_name': i.get('task_name'),
             'type': i.get('report_type') or i.get('type'), 'created_at': i.get('created_at'),
             'status': i.get('status')}
            for i in items
        ]
        tc = ((r.get('json') or {}).get('data') or {}).get('total')
        OUT['list_total'] = tc
        for rid in (564, 566):
            rr = L.api(d, '/reports/%d' % rid)
            dj = ((rr.get('json') or {}).get('data') or {})
            OUT['detail_%d' % rid] = {'http': rr['status'], 'task_id': dj.get('task_id'),
                                      'task_name': dj.get('task_name'),
                                      'status': dj.get('status'), 'name': dj.get('name')}
        for tid in (527, 411):
            ar = L.api(d, '/reports/case-averages', 'POST', {'task_id': tid}, timeout=180)
            j = ar.get('json') or {}
            data = j.get('data') or {}
            OUT['avg_%d' % tid] = {
                'http': ar['status'], 'msg': j.get('message'),
                'total_cases': data.get('total_cases'), 'resources_n': len(data.get('resources') or []),
                'overall_n': len(data.get('overall_averages') or []),
                'metric_data_n': len(data.get('metric_data') or []),
            }
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    finally:
        os.makedirs(L.ART, exist_ok=True)
        with open(os.path.join(L.ART, 'probe16_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1482 续测探针12：核对报告列表/详情 DTO 是否返回 task_name（任务名空白取证）。"""
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
        r = L.api(d, '/reports?page=1&per_page=5&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['list_http'] = r['status']
        OUT['list_items'] = [
            {'id': i.get('id'), 'task_id': i.get('task_id'),
             'has_task_name': 'task_name' in i, 'task_name': i.get('task_name'),
             'keys': sorted(i.keys())}
            for i in items
        ]
        for rid in (588, 564, 566):
            rr = L.api(d, '/reports/%d' % rid)
            dj = ((rr.get('json') or {}).get('data') or {})
            OUT['detail_%d' % rid] = {
                'http': rr['status'], 'task_id': dj.get('task_id'),
                'has_task_name': 'task_name' in dj, 'task_name': dj.get('task_name'),
                'top_keys': sorted(dj.keys()),
            }
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'probe12_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

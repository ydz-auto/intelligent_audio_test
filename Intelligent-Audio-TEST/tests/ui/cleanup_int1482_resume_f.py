# -*- coding: utf-8 -*-
"""INT-1482 F 轮清理：软删 + 彻底删除本轮夹具报告（接线测试_ 前缀），回读 404 并核残留。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    path = os.path.join(L.ART, 'resumeF_result.json')
    ids = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
            ids = [int(x) for x in (d.get('created') or [])]
            if d.get('fixture_id'):
                ids.append(int(d['fixture_id']))
    ids = sorted(set(ids))
    d = L.driver()
    try:
        L.login(d)
        OUT['targets'] = ids
        for rid in ids:
            r = L.api(d, '/reports/%d' % rid)
            OUT['id_%d_pre' % rid] = r['status']
            if r['status'] != 200:
                continue
            rd = L.api(d, '/reports/%d' % rid, 'DELETE')
            time.sleep(1)
            rp = L.api(d, '/reports/%d/purge' % rid, 'DELETE')
            time.sleep(1)
            rr = L.api(d, '/reports/%d' % rid)
            OUT['id_%d' % rid] = {'delete': rd['status'], 'purge': rp['status'],
                                  'after_get': rr['status'],
                                  'after_text': (rr.get('text') or '')[:120]}
        # 列表 / 回收站残留复核
        for q, key in (('/reports?page=1&per_page=100&deleted=false', 'residual_list'),
                       ('/reports?page=1&per_page=100&deleted=true', 'residual_trash')):
            r = L.api(d, q)
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            OUT[key] = [i['id'] for i in items if '接线测试_' in (i.get('name') or '')]
        r = L.api(d, '/reports?page=1&per_page=3&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['list_head_after'] = [{'id': i.get('id'), 'task_id': i.get('task_id')} for i in items]
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    finally:
        with open(os.path.join(L.ART, 'cleanup_f_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1482 续测 C 轮清理：软删 + 彻底删除本轮自建报告（仅 resumeC_result.json 记录的 id）。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    ids = set()
    p = os.path.join(L.ART, 'resumeC_result.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        ids.update(int(x) for x in (data.get('created') or []))
    d = L.driver()
    try:
        L.login(d)
        OUT['targets'] = sorted(ids)
        for rid in sorted(ids):
            r = L.api(d, '/reports/%d' % rid)
            if r['status'] != 200:
                OUT['id_%d' % rid] = {'precheck': r['status']}
                continue
            rd = L.api(d, '/reports/%d' % rid, 'DELETE')
            time.sleep(1)
            rp = L.api(d, '/reports/%d/purge' % rid, 'DELETE')
            time.sleep(1)
            rr = L.api(d, '/reports/%d' % rid)
            OUT['id_%d' % rid] = {'delete': rd['status'], 'purge': rp['status'],
                                  'after_get': rr['status'],
                                  'after_text': (rr.get('text') or '')[:120]}
        r = L.api(d, '/reports?page=1&per_page=100&deleted=true')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['residual_deleted'] = [(i['id'], i['name']) for i in items
                                   if '接线测试_INT1482_' in (i.get('name') or '')]
        r2 = L.api(d, '/reports?page=1&per_page=100&deleted=false')
        items2 = ((r2.get('json') or {}).get('data') or {}).get('items') or []
        OUT['residual_live'] = [(i['id'], i['name']) for i in items2
                                if '接线测试_INT1482_' in (i.get('name') or '')]
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'cleanupC_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

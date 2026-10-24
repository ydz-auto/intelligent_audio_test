# -*- coding: utf-8 -*-
"""INT-1482 续测清理：软删 + 彻底删除本轮自建报告（接线测试_ 前缀），并回读确认。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    ids = set()
    for name in ('resume_result.json', 'resumeB_result.json', 'final_result.json', 'cmpui_result.json'):
        p = os.path.join(L.ART, name)
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            ids.update(int(x) for x in (data.get('created') or []))
    # 已知探针创建的对比报告
    ids.add(583)
    # 只清理本脚本记录 + 探针创建的 583；不按名称前缀兜底，避免误删并发 run 的在途报告
    d = L.driver()
    try:
        L.login(d)
        OUT['targets'] = sorted(ids)
        for rid in sorted(ids):
            r = L.api(d, '/reports/%d' % rid)
            st = r['status']
            if st != 200:
                OUT['id_%d' % rid] = {'precheck': st}
                continue
            rd = L.api(d, '/reports/%d' % rid, 'DELETE')
            time.sleep(1)
            rp = L.api(d, '/reports/%d/purge' % rid, 'DELETE')
            time.sleep(1)
            rr = L.api(d, '/reports/%d' % rid)
            OUT['id_%d' % rid] = {'delete': rd['status'], 'purge': rp['status'],
                                  'after_get': rr['status'], 'after_text': (rr.get('text') or '')[:120]}
        # 复核列表残留
        r = L.api(d, '/reports?page=1&per_page=100&deleted=true')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['residual'] = [(i['id'], i['name']) for i in items if '接线测试_INT1482_' in (i.get('name') or '')]
        print('ok')
    finally:
        with open(os.path.join(L.ART, 'cleanup_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

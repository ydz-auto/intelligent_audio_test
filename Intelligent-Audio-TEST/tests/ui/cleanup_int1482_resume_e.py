# -*- coding: utf-8 -*-
"""INT-1482 E 轮清理：软删 + 彻底删除本轮自建夹具报告（接线测试_ 前缀），回读 404。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

OUT = {}


def main():
    path = os.path.join(L.ART, 'resumeE_result.json')
    ids = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            ids = [int(x) for x in (json.load(f).get('created') or [])]
    # 本轮夹具（resumeE 结果里 created 可能被二次运行的 merge 覆盖，按显式 id 兜底）
    ids = sorted(set(ids) | {589})
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
        # 回收站 / 列表复核残留
        for q in ('/reports?page=1&per_page=100&deleted=false',
                  '/reports?page=1&per_page=100&deleted=true'):
            r = L.api(d, q)
            items = ((r.get('json') or {}).get('data') or {}).get('items') or []
            OUT['residual' + ('_deleted' if 'deleted=true' in q else '')] = [
                i['id'] for i in items if '接线测试_INT1482_' in (i.get('name') or '')]
        # 统计页上下文回到 566 的现状记录（只读）
        r = L.api(d, '/reports?page=1&per_page=3&sort_by=created_at&order=desc&deleted=false&favorite=false')
        items = ((r.get('json') or {}).get('data') or {}).get('items') or []
        OUT['list_head_after'] = [{'id': i.get('id'), 'task_id': i.get('task_id')} for i in items]
        print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    finally:
        with open(os.path.join(L.ART, 'cleanup_e_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()


if __name__ == '__main__':
    main()

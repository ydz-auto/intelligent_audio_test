# -*- coding: utf-8 -*-
"""INT-1482 复核历史抽屉浅色补证：接口侧 GET 回读（计数与抽屉「共 N 条」对照）。

走浏览器登录态（登录链 RSA 加密，直接 POST 明文不可用），在页内 fetch 调 GET，只读不写库。
用法：REACT_BASE=http://localhost:15282 python tests/ui/probe_int1482_h3_readback.py
"""
import json
import os
import sys

sys.path.insert(0, 'tests/ui')
import int1482_lib as L

TARGETS = [(484, 407), (387, 415), (481, 418)]


def rows(payload):
    d = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(d, dict):
        for k in ('items', 'records', 'list'):
            if isinstance(d.get(k), list):
                return d[k]
        return d
    return d if isinstance(d, list) else []


def main():
    d = L.driver()
    out = {'base': L.BASE, 'backend': L.BACKEND, 'targets': {}}
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        for rid, tid in TARGETS:
            item = {}
            for kind in ('review-history', 'ai-review-history'):
                r = L.api(d, '/tasks/results/%d/%s' % (tid, kind))
                rs = rows(r.get('json') or {})
                by_case = {}
                for row in rs:
                    cid = row.get('test_case_id') or '?'
                    by_case[cid] = by_case.get(cid, 0) + 1
                item[kind] = {'status': r.get('status'), 'count': len(rs),
                              'by_case': by_case,
                              'first': (rs[0] if rs else None)}
            out['targets']['report_%d_task_%d' % (rid, tid)] = item
            print('报告 %d / 任务 %d：人工 %d 条, AI %d 条' % (
                rid, tid, item['review-history']['count'], item['ai-review-history']['count']))
    finally:
        try:
            d.quit()
        except Exception:
            pass
    path = os.path.join('tests', 'ui', 'artifacts', 'int1482', 'h3_readback.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print('saved', path)


if __name__ == '__main__':
    main()

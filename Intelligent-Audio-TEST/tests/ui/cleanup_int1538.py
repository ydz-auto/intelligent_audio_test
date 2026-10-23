# -*- coding: utf-8 -*-
"""INT-1538 收尾：清理本 card 自建用例/分组/标签（软删 + purge），回报残留。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L

OUT = {}
d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(4)
    ids = []
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&keyword=' + '接线测试_INT1538')
    items = ((p or {}).get('data') or {}).get('items') or []
    ids = [(x['id'], x['name'], x.get('deleted')) for x in items if x.get('name', '').startswith('接线测试_INT1538')]
    OUT['found'] = ids
    OUT['cleanup'] = []
    for cid, name, deleted in ids:
        r1 = L.api_json(d, '/testcases/' + cid, 'DELETE')
        if r1[0] not in (200, 204):
            r1 = L.api_json(d, '/testcases/' + cid, 'DELETE')
        r2 = L.api_json(d, '/testcases/' + cid + '/purge', 'DELETE')
        OUT['cleanup'].append({'id': cid, 'name': name, 'del': r1[0], 'purge': r2[0], 'purge_body': r2[2][:120]})
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&keyword=' + '接线测试_INT1538')
    items = ((p or {}).get('data') or {}).get('items') or []
    OUT['remaining_cases'] = [(x['name'], x.get('deleted')) for x in items]
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=200&keyword=' + '接线测试_INT1538' + '&only_deleted=1')
    items = ((p or {}).get('data') or {}).get('items') or []
    OUT['remaining_trash'] = [(x['name'], x.get('deleted')) for x in items]
    # 分组
    st, p, _ = L.api_json(d, '/groups?page=1&per_page=200')
    gs = ((p or {}).get('data') or {}).get('items') or []
    g = next((x for x in gs if x.get('name', '').startswith('接线测试_INT1538')), None)
    OUT['group_before_delete'] = g
    if g:
        st, p, raw = L.api_json(d, '/groups/' + g['id'], 'DELETE')
        OUT['group_delete'] = (st, raw[:200])
    st, p, _ = L.api_json(d, '/groups?page=1&per_page=200')
    gs = ((p or {}).get('data') or {}).get('items') or []
    OUT['group_remaining'] = [x['name'] for x in gs if x.get('name', '').startswith('接线测试_INT1538')]
    # 标签
    st, p, _ = L.api_json(d, '/tags?page=1&per_page=200')
    ts = ((p or {}).get('data') or {}).get('items') or ((p or {}).get('items') or [])
    OUT['tags_status'] = st
    t = next((x for x in ts if x.get('name') == '接线测试_INT1538'), None)
    OUT['tag_found'] = t
    if t:
        st, p, raw = L.api_json(d, '/tags/' + str(t['id']), 'DELETE')
        OUT['tag_delete'] = (st, raw[:200])
    # 最终抽样
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=1')
    OUT['final_total'] = ((p or {}).get('data') or {}).get('total')
finally:
    L.save_evidence('cleanup_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

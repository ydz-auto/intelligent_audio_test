# -*- coding: utf-8 -*-
"""INT-1483 清理本 run 自建的接线测试算法与分组。"""
import json
import int1483_helpers as H

d = H.driver()
try:
    H.login(d); H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/groups')
    items = (pay or {}).get('data', {}).get('items') or []
    for g in items:
        if '接线测试_INT1483' in (g.get('name') or ''):
            r = H.api(d, f"/algorithm/groups/{g['id']}", 'DELETE')
            print('DEL GROUP', g['id'], g['name'], r['status'])
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    for it in (pay or {}).get('data', {}).get('items') or []:
        if 'itest1483' in (it.get('type') or ''):
            r = H.api(d, f"/algorithm/definitions/{it['type']}", 'DELETE')
            print('DEL DEF', it['id'], it['type'], r['status'])
    st, pay, _ = H.api_json(d, '/algorithm/groups')
    print('GROUPS LEFT', [(g['id'], g['name']) for g in ((pay or {}).get('data', {}).get('items') or [])])
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    print('DEFS LEFT', [(i['id'], i['type']) for i in ((pay or {}).get('data', {}).get('items') or [])])
finally:
    d.quit()

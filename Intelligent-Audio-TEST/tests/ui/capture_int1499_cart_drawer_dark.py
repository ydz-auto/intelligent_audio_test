# -*- coding: utf-8 -*-
"""INT-1499 取证补 3：深色购物车抽屉截图（API 加购 → 打开购物车抽屉 → 截图 → 清空）。"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_int1499_resulttype_btn as base  # noqa: E402


def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base.API + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if base.TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + base.TOKEN['v'])
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b'{}')


def main():
    d = base.driver()
    out = {}
    try:
        d.get(base.BASE + '/')
        base.login(d)
        cand = api('GET', '/tasks/cherry-picks/candidates?per_page=20')
        ids = [c['result_id'] for c in cand['data']['items'][:10]]
        out['cand_types'] = sorted({c.get('result_type') for c in cand['data']['items']})
        out['add'] = api('POST', '/tasks/cherry-picks/cart/items', {'result_ids': ids})

        base.set_theme(d, 'dark')
        d.get(base.BASE + '/tasks?tab=cherry-picks')
        time.sleep(2)
        base.click_button(d, '挑选合并', contains=True, timeout=60)
        time.sleep(3)
        base.click_button(d, '打开购物车', contains=True, timeout=60)
        time.sleep(2)
        base.WebDriverWait(d, 40).until(lambda x: '我的购物车' in (x.page_source or ''))
        time.sleep(2)
        out['drawer_views_dark'] = base.view_buttons(d)
        out['shot'] = base.shot(d, 'p6_cart_drawer_dark')
    finally:
        d.quit()
    out['clear'] = api('DELETE', '/tasks/cherry-picks/cart/items')
    out['cart_after'] = len(((api('GET', '/tasks/cherry-picks/cart').get('data') or {}).get('items')) or [])
    with open(os.path.join(base.ART, 'cart_drawer_dark.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=True, indent=2)[:2500])


if __name__ == '__main__':
    main()

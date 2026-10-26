# -*- coding: utf-8 -*-
"""INT-1499 取证补 2：深色购物车步骤视图切换器（真实库栈 15000 / dev 5321），结尾清空购物车。"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_int1499_resulttype_btn as base  # noqa: E402


def main():
    d = base.driver()
    out = {}
    try:
        d.get(base.BASE + '/')
        base.login(d)
        base.set_theme(d, 'dark')
        out['stage2_dark'] = base.open_stage2(d)
        out['stage2_views_dark'] = base.view_buttons(d)
        base.click_button(d, '全选当前筛选', timeout=30)
        time.sleep(2)
        out['add_btn'] = base.click_button(d, '加入购物车', contains=True, timeout=30)
        time.sleep(4)
        for b in d.find_elements(base.By.CSS_SELECTOR, "[data-testid='wizard-step-cart']"):
            base.js_click(d, b)
        time.sleep(3)
        out['cart_views_dark'] = base.view_buttons(d)
        out['cart_empty'] = '购物车为空' in (d.page_source or '')
        out['shot'] = base.shot(d, 'p5_cart_dark')
    finally:
        d.quit()

    req = urllib.request.Request(base.API + '/tasks/cherry-picks/cart/items', method='DELETE')
    if base.TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + base.TOKEN['v'])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out['clear'] = json.loads(r.read() or b'{}')
    except Exception as exc:  # noqa: BLE001
        out['clear'] = 'failed: %s' % exc

    req = urllib.request.Request(base.API + '/tasks/cherry-picks/cart')
    if base.TOKEN['v']:
        req.add_header('Authorization', 'Bearer ' + base.TOKEN['v'])
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read() or b'{}')
    out['cart_after'] = len(((data.get('data') or {}).get('items')) or [])

    with open(os.path.join(base.ART, 'cart_dark.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=True, indent=2)[:3000])


if __name__ == '__main__':
    main()

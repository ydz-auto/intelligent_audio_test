# -*- coding: utf-8 -*-
import json
import int1483_helpers as H

d = H.driver()
try:
    H.login(d)
    H.goto_page(d)
    st, pay, _ = H.api_json(d, '/algorithm/definitions')
    items = (pay or {}).get('data', {}).get('items') or []
    print('STATUS', st, 'COUNT', len(items))
    for i in items:
        print(' ', i.get('id'), i.get('type'), i.get('name'), i.get('status'), i.get('display_order'), i.get('description'))
finally:
    d.quit()

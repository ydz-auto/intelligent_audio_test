# -*- coding: utf-8 -*-
"""INT-1199 走查数据抽样：登录真实库栈(5700)，抽样 audios/devices/spl 行数 + health。"""
import sys
sys.path.insert(0, 'tests/ui/utils')
from api_client import ApiClient

GW = 'http://127.0.0.1:5700'
c = ApiClient(GW)
h = c.health()
print('HEALTH:', h.get('status'), h.get('database'))

c.login('接线测试_admin', 'JieXianTest@2026')
print('LOGIN OK, user:', c.user.get('username'), 'role:', c.user.get('role'))

# audios list (POST /audios)
try:
    r = c.request('POST', '/audios', {'page': 1, 'per_page': 5})
    data = r.get('data') if isinstance(r, dict) else r
    total = data.get('total') or data.get('total_count') if isinstance(data, dict) else None
    print('AUDIOS total:', total, '| first items:', len(data.get('items', data.get('rows', []))) if isinstance(data, dict) else 'n/a')
    if isinstance(data, dict):
        items = data.get('items') or data.get('rows') or []
        if items:
            print('AUDIO sample:', {k: items[0].get(k) for k in list(items[0].keys())[:12]})
except Exception as e:
    print('AUDIOS ERR:', e)

# devices list
try:
    r = c.request('GET', '/test-devices', params={'per_page': 10})
    print('DEVICES response keys:', list(r.keys())[:10] if isinstance(r, dict) else type(r))
    data = r.get('data') if isinstance(r, dict) else r
    if isinstance(data, dict):
        items = data.get('items') or data.get('rows') or []
        print('DEVICES total:', data.get('total') or data.get('total_count'), '| count:', len(items))
        for it in items[:5]:
            print('DEVICE:', it)
except Exception as e:
    print('DEVICES ERR:', e)

# spl list
try:
    r = c.request('GET', '/spl', params={'page': 1, 'per_page': 10})
    print('SPL response keys:', list(r.keys())[:10] if isinstance(r, dict) else type(r))
    data = r.get('data') if isinstance(r, dict) else r
    if isinstance(data, dict):
        items = data.get('items') or data.get('rows') or []
        print('SPL total:', data.get('total') or data.get('total_count'), '| count:', len(items))
        for it in items[:5]:
            print('SPL:', it)
except Exception as e:
    print('SPL ERR:', e)

# spl stats
try:
    r = c.request('GET', '/spl/stats')
    print('SPL STATS:', r)
except Exception as e:
    print('SPL STATS ERR:', e)

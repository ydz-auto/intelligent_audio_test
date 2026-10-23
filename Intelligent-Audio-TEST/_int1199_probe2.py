# -*- coding: utf-8 -*-
"""INT-1199 probe: query real stack for apis/playback-devices/groups + verify audios sample columns."""
import sys
sys.path.insert(0, 'tests/ui/utils')
from api_client import ApiClient

GW = 'http://127.0.0.1:5700'
c = ApiClient(GW)
h = c.health()
print('HEALTH:', h.get('status'), h.get('database'))

c.login('接线测试_admin', 'JieXianTest@2026')
print('LOGIN OK:', c.user.get('username'), c.user.get('role'))

for path, params in [
    ('/apis', {'page': 1, 'per_page': 5}),
    ('/playback-devices', {'page': 1, 'per_page': 5}),
    ('/test-devices', {'page': 1, 'per_page': 5}),
    ('/device-groups', {'page': 1, 'per_page': 50}),
]:
    try:
        r = c.request('GET', path, params=params)
        data = r.get('data') if isinstance(r, dict) else r
        if isinstance(data, dict):
            items = data.get('items') or data.get('rows') or []
            total = data.get('total') or data.get('total_count')
            print(f'{path}: total={total} count={len(items)}')
            for it in items[:3]:
                keys = list(it.keys())[:8] if isinstance(it, dict) else 'n/a'
                if isinstance(it, dict):
                    print('   ', {k: it.get(k) for k in keys})
                else:
                    print('   ', it)
        else:
            print(f'{path}: {str(r)[:200]}')
    except Exception as e:
        print(f'{path} ERR: {e}')

# audio page sample: verify columns (format/sample_rate/duration/audio_type)
try:
    r = c.request('POST', '/audios', {'page': 1, 'per_page': 5})
    data = r.get('data') if isinstance(r, dict) else r
    items = (data or {}).get('items') or (data or {}).get('rows') or []
    print('AUDIOS total:', (data or {}).get('total'))
    for it in items[:3]:
        print('AUDIO cols:', {k: it.get(k) for k in ['id','name','format','sample_rate','duration','audio_type','source_language','visibility','status']})
except Exception as e:
    print('AUDIOS ERR:', e)

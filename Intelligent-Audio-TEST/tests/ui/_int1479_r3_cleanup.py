# -*- coding: utf-8 -*-
"""INT-1479 R3 数据清理：自建用例/分组/音频。"""
import json
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_api import API, H  # noqa: E402

CASES = ['c94af25d-5264-45c1-bbf5-951fe957f1cc', '91dcf845-2cff-4a37-9963-148ff2c948c6',
         'c06e6f59-9810-4900-b009-20dcbc9491a7']
GROUPS = ['00b8ff0b-bd26-473d-a2df-2b716d6bb8bd', '038654f2-982f-406c-8dac-5fdd97083d2f',
          '8d0e69aa-60c0-46ce-8947-614c47dd832a']
AUDIOS = [2325, 2326, 2327]

if __name__ == '__main__':
    s = requests.Session(); s.headers.update(H())
    for cid in CASES:
        r = s.delete(f'{API}/testcases/{cid}', timeout=60)
        print('DEL CASE', cid, r.status_code, (r.text or '')[:200])
    r = s.post(f'{API}/testcases/purge', json={'ids': CASES}, timeout=120)
    print('PURGE CASES', r.status_code, (r.text or '')[:300])
    for gid in GROUPS:
        r = s.delete(f'{API}/groups/{gid}', timeout=60)
        print('DEL GROUP', gid, r.status_code, (r.text or '')[:200])
    r = s.post(f'{API}/audios/batch-action',
               json={'action': 'delete', 'audio_ids': AUDIOS}, timeout=120)
    print('DEL AUDIOS', r.status_code, (r.text or '')[:300])
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': 'INT1479'}, timeout=120)
    d = r.json().get('data') or {}
    print('AUDIO LEFT', d.get('total'), json.dumps([{'id': i.get('id'), 'name': i.get('name')}
                                                    for i in (d.get('items') or [])], ensure_ascii=False))
    r = s.get(f'{API}/testcases', params={'keyword': 'INT1479', 'page': 1, 'per_page': 10}, timeout=120)
    d = r.json().get('data') or {}
    print('CASE LEFT', d.get('total'), json.dumps([{'id': i.get('id'), 'name': i.get('name')}
                                                   for i in (d.get('items') or [])], ensure_ascii=False))

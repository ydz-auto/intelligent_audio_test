# -*- coding: utf-8 -*-
"""INT-1479 第三轮探针：确认 50052 恢复后音频域接口不再 UNAVAILABLE。"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_api import API, H, show  # noqa: E402


def main():
    s = requests.Session()
    s.headers.update(H())

    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 3}, timeout=60)
    show('POST /audios 列表', r)
    total = None
    try:
        j = r.json()
        total = j.get('total') or j.get('data', {}).get('total')
        items = j.get('items') or j.get('data', {}).get('items') or []
        print('TOTAL', total)
        print('FIRST3', json.dumps([{'id': i.get('id'), 'name': i.get('filename') or i.get('name'),
                                    'type': i.get('audio_type')} for i in items[:3]],
                                   ensure_ascii=False))
    except Exception as e:
        print('parse err', e)

    show('GET /audios/tags', s.get(f'{API}/audios/tags', timeout=60))

    show('POST /audios/batch-action 空数组探针',
         s.post(f'{API}/audios/batch-action',
                json={'action': 'tags', 'audio_ids': [], 'tags': []}, timeout=60))

    show('GET /audios/statistics', s.get(f'{API}/audios/statistics', timeout=60))


if __name__ == '__main__':
    main()

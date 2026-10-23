# -*- coding: utf-8 -*-
"""INT-1479 R4 数据清理：删除本卡自建音频并回读确认。"""
import json
import sys
import os
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_api import API, H  # noqa: E402

IDS = [2341, 2342, 2343]


def main():
    s = requests.Session(); s.headers.update(H())
    for aid in IDS:
        try:
            r = s.delete(f'{API}/audios/{aid}', timeout=120)
            print('DELETE', aid, r.status_code, (r.text or '')[:200])
        except Exception as exc:
            print('DELETE', aid, 'EXC', type(exc).__name__, str(exc)[:120])
        time.sleep(1)
    for _ in range(4):
        try:
            r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 20, 'keyword': '接线测试_INT1479R4'}, timeout=120)
            if r.status_code == 200:
                items = (r.json().get('data') or {}).get('items') or []
                print('READBACK', json.dumps([{'id': i['id'], 'name': i['name']} for i in items], ensure_ascii=False))
                if not items:
                    print('CLEAN_OK')
                    return
        except Exception as exc:
            print('READBACK EXC', type(exc).__name__)
        time.sleep(4)


if __name__ == '__main__':
    main()

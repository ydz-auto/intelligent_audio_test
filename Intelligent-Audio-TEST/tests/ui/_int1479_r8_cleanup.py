# -*- coding: utf-8 -*-
"""INT-1479 R8 收尾：删除本 run 自建音频并复核无残留。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_api as A
import requests

KW = '接线测试_INT1479_'


def items():
    r = requests.post(A.API + '/audios', headers={**A.H(), 'Content-Type': 'application/json'},
                      json={'page': 1, 'per_page': 50, 'keyword': KW}, timeout=180)
    return ((r.json().get('data') or {}).get('items')) or []


def main():
    found = items()
    print('found', [(i['id'], i['name']) for i in found], flush=True)
    for i in found:
        d = requests.delete('%s/audios/%s' % (A.API, i['id']), headers=A.H(), timeout=300)
        print('DELETE', i['id'], d.status_code, (d.text or '')[:160], flush=True)
    left = items()
    print('left', [(i['id'], i['name']) for i in left], flush=True)


if __name__ == '__main__':
    main()

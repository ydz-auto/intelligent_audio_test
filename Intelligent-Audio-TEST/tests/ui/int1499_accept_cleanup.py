# -*- coding: utf-8 -*-
"""INT-1499 验收收尾：查/清本 run 下单创建的容器任务（崩溃残留），并打印购物车现状。

用法：python tests/ui/int1499_accept_cleanup.py [--purge]
"""
import base64
import json
import sys
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API = 'http://127.0.0.1:15000'
USER = '接线测试_int1499t'
PASS = 'JieXianTest@2026'
NEEDLE = '接线测试_INT1499_验收'
TOKEN = None


def req(url, data=None, method=None, ct=None):
    r = urllib.request.Request(url, data=data, method=method)
    if TOKEN:
        r.add_header('Authorization', 'Bearer ' + TOKEN)
    if ct:
        r.add_header('Content-Type', ct)
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, {'raw': raw[:300].decode('utf-8', 'replace')}


def login():
    global TOKEN
    st, k = req(API + '/api/v1/auth/login/encryption-key')
    d = k.get('data', k)
    pub = serialization.load_pem_public_key(d['public_key'].encode())
    ct = pub.encrypt(PASS.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    body = urllib.parse.urlencode({'username': USER,
                                   'password_encrypted': base64.b64encode(ct).decode(),
                                   'encryption_key_id': d['kid']}).encode()
    st, res = req(API + '/api/v1/auth/login', body, method='POST',
                  ct='application/x-www-form-urlencoded')
    TOKEN = (res or {}).get('access_token')


def main():
    purge = '--purge' in sys.argv
    login()
    st, res = req(API + '/api/v1/tasks?page=1&per_page=100&keyword=' + urllib.parse.quote(NEEDLE))
    d = res.get('data', res)
    rows = d.get('items') or d.get('list') or []
    hits = [r for r in rows if NEEDLE in (r.get('name') or r.get('task_name') or '')]
    print('TASKS status=%s total=%s hits=%s' % (st, d.get('total'), len(hits)))
    for r in hits:
        print('  HIT', json.dumps({k: r.get(k) for k in
                                   ('id', 'name', 'status', 'cherry_pick', 'result_count',
                                    'created_at', 'is_deleted')}, ensure_ascii=False))
    st, cart = req(API + '/api/v1/tasks/cherry-picks/cart')
    cd = cart.get('data', cart)
    print('CART status=%s total=%s groups=%s' % (st, cd.get('total'), len(cd.get('groups') or [])))
    if purge:
        for r in hits:
            tid = r.get('id')
            print('DELETE', tid, req(API + '/api/v1/tasks/%d' % tid, method='DELETE')[0])
            print('PURGE', tid, req(API + '/api/v1/tasks/%d/purge' % tid, method='DELETE')[0])
        print('CLEAR_CART', req(API + '/api/v1/tasks/cherry-picks/cart/items', method='DELETE')[0])


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1499 验收：独立核对阶段 1 后端口径（pickable-tasks 总数 + execution_status 分布）。"""
import json
import urllib.request
from collections import Counter

API = 'http://127.0.0.1:15000'
TOKEN = None


def req(url, data=None, method=None, ct=None):
    r = urllib.request.Request(url, data=data, method=method)
    if TOKEN:
        r.add_header('Authorization', 'Bearer ' + TOKEN)
    if ct:
        r.add_header('Content-Type', ct)
    with urllib.request.urlopen(r, timeout=120) as x:
        return x.status, json.loads(x.read() or b'{}')


def main():
    global TOKEN
    import base64
    import urllib.parse
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    st, k = req(API + '/api/v1/auth/login/encryption-key')
    d = k.get('data', k)
    pub = serialization.load_pem_public_key(d['public_key'].encode())
    ct = pub.encrypt('JieXianTest@2026'.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    body = urllib.parse.urlencode({'username': '接线测试_int1499t',
                                   'password_encrypted': base64.b64encode(ct).decode(),
                                   'encryption_key_id': d['kid']}).encode()
    st, res = req(API + '/api/v1/auth/login', body, method='POST',
                  ct='application/x-www-form-urlencoded')
    TOKEN = res['access_token']

    st, p = req(API + '/api/v1/tasks/cherry-picks/pickable-tasks'
                '?page=1&per_page=200&sort_by=status&sort_order=asc')
    dd = p.get('data', p)
    items = dd.get('items') or []
    dist = Counter((i.get('execution_status') or '?') for i in items)
    ids = {i.get('id') for i in items}
    print(json.dumps({
        'status': st, 'total': dd.get('total'), 'loaded': len(items),
        'dist': dict(dist), 'has_311': 311 in ids, 'has_312': 312 in ids,
        'has_418': 418 in ids, 'has_419': 419 in ids,
        'sample': {k2: items[0].get(k2) for k2 in ('id', 'name', 'execution_status', 'result_count')}
        if items else None,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

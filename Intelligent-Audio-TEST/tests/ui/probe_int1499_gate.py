# -*- coding: utf-8 -*-
"""INT-1499 复跑前置探针：15173 真实镜像 + 15000 网关。

用途：拿真实 token，查 pickable-tasks 任务集合（终态/失败/停止）、购物车现状，
供全链路复跑前核对清单与清理。
用法：python tests/ui/probe_int1499_gate.py
"""
import base64
import json
import os
import sys
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

BASE = os.environ.get('INT1499_BASE', 'http://127.0.0.1:15173')
API = os.environ.get('INT1499_API', 'http://127.0.0.1:15000')
USER = os.environ.get('INT1499_USER', '接线测试_admin')
PASS = os.environ.get('INT1499_PASS', 'JieXianTest@2026')


def req(url, data=None, token=None, method=None, content_type=None):
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    if content_type:
        r.add_header('Content-Type', content_type)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body or b'{}')
            except ValueError:
                return resp.status, body[:300]
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, raw[:300]


def login():
    st, key = req(BASE + '/api/v1/auth/login/encryption-key')
    d = key.get('data', key) if isinstance(key, dict) else {}
    pem = d.get('public_key', '')
    pub = serialization.load_pem_public_key(pem.encode())
    ct = pub.encrypt(PASS.encode(), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                algorithm=hashes.SHA256(), label=None))
    body = urllib.parse.urlencode({
        'username': USER,
        'password_encrypted': base64.b64encode(ct).decode(),
        'encryption_key_id': d.get('kid', ''),
    }).encode()
    st, res = req(BASE + '/api/v1/auth/login', body, method='POST',
                  content_type='application/x-www-form-urlencoded')
    tok = (res or {}).get('access_token') if isinstance(res, dict) else None
    return st, tok, res


def main():
    st, tok, res = login()
    print('LOGIN', st, 'token=%s' % bool(tok), '' if tok else str(res)[:300])
    if not tok:
        sys.exit(2)
    print('HEALTH', req(API + '/health')[1])
    st, p = req(BASE + '/api/v1/tasks/cherry-picks/pickable-tasks?page=1&per_page=200&sort_by=status&sort_order=asc',
                token=tok)
    d = p.get('data', p) if isinstance(p, dict) else {}
    items = d.get('items') or d.get('list') or []
    print('PICKABLE status=%s total=%s items=%s' % (st, d.get('total'), len(items)))
    from collections import Counter
    sts = Counter((i.get('status') or '?') for i in items)
    print('STATUS_DIST', dict(sts))
    ids = [i.get('id') for i in items]
    for want in (311, 312, 418, 419):
        row = next((i for i in items if i.get('id') == want), None)
        print('TASK', want, 'present=%s' % bool(row),
              ('' if not row else 'status=%s name=%s results=%s' %
               (row.get('status'), row.get('name') or row.get('task_name'),
                row.get('result_count') or row.get('total') or row.get('pickable_count'))))
    print('FIRST_ROWS', json.dumps([{k: r.get(k) for k in ('id', 'status', 'name', 'task_name')}
                                    for r in items[:5]], ensure_ascii=False))
    st, cart = req(BASE + '/api/v1/tasks/cherry-picks/cart', token=tok)
    cd = cart.get('data', cart) if isinstance(cart, dict) else {}
    print('CART status=%s total=%s groups=%s invalid=%s' %
          (st, cd.get('total'), len(cd.get('groups') or []), cd.get('invalid_item_ids')))


if __name__ == '__main__':
    import urllib.parse  # noqa: E402
    main()

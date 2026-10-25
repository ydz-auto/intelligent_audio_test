# -*- coding: utf-8 -*-
"""INT-1499 复跑：建/复用独立测试账号，避免与其他并发 run 共用购物车（cart 是 per-user）。

输出一行 JSON：{user, pass, user_id, token, cart_total}
用法：python tests/ui/setup_int1499_user.py [--delete]
"""
import base64
import json
import sys
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

BASE = 'http://127.0.0.1:15173'
ADMIN_USER = '接线测试_admin'
ADMIN_PASS = 'JieXianTest@2026'
NEW_USER = '接线测试_int1499b'
NEW_PASS = 'JieXianTest@2026'
NEW_EMAIL = 'int1499b@jiexian.test'


def req(url, data=None, token=None, method=None, ct=None):
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    if ct:
        r.add_header('Content-Type', ct)
    try:
        with urllib.request.urlopen(r, timeout=60) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, raw[:300]


def login(user, password):
    st, k = req(BASE + '/api/v1/auth/login/encryption-key')
    d = k.get('data', k)
    pub = serialization.load_pem_public_key(d['public_key'].encode())
    ct = pub.encrypt(password.encode(), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                     algorithm=hashes.SHA256(), label=None))
    body = urllib.parse.urlencode({
        'username': user,
        'password_encrypted': base64.b64encode(ct).decode(),
        'encryption_key_id': d['kid'],
    }).encode()
    st, res = req(BASE + '/api/v1/auth/login', body, method='POST',
                  ct='application/x-www-form-urlencoded')
    return st, (res.get('access_token') if isinstance(res, dict) else None), res


def find_user(token, name):
    st, res = req(BASE + '/api/v1/auth/users?page=1&per_page=100&keyword=' +
                  urllib.parse.quote(name), token=token)
    d = res.get('data', res) if isinstance(res, dict) else {}
    rows = d.get('items') or d.get('users') or d.get('list') or []
    return next((r for r in rows if r.get('username') == name), None), rows


def main():
    admin_st, atok, _ = login(ADMIN_USER, ADMIN_PASS)
    if not atok:
        print(json.dumps({'error': 'admin login failed', 'status': admin_st}))
        sys.exit(2)
    admin_row, _ = find_user(atok, ADMIN_USER)
    role_id = 0
    if admin_row:
        role_id = admin_row.get('role_id') or 0
        if not role_id:
            roles = admin_row.get('roles') or admin_row.get('role_ids') or []
            if roles:
                role_id = roles[0] if isinstance(roles[0], int) else roles[0].get('role_id') or 0

    existing, _ = find_user(atok, NEW_USER)
    if existing and '--delete' in sys.argv:
        st, _ = req(BASE + '/api/v1/auth/users/%s' % existing.get('id'), token=atok, method='DELETE')
        print(json.dumps({'deleted': existing.get('id'), 'status': st}, ensure_ascii=False))
        return

    created = None
    if not existing:
        st, res = req(BASE + '/api/v1/auth/users',
                      data=json.dumps({'username': NEW_USER, 'email': NEW_EMAIL,
                                       'password': NEW_PASS, 'role_id': role_id}).encode(),
                      token=atok, method='POST', ct='application/json')
        created = {'status': st, 'res': res}
        existing, _ = find_user(atok, NEW_USER)

    st, tok, res = login(NEW_USER, NEW_PASS)
    if not tok:
        print(json.dumps({'error': 'login failed', 'status': st, 'body': str(res)[:300],
                          'role_id': role_id, 'created': created, 'existing': existing},
                         ensure_ascii=False))
        sys.exit(3)
    st, cart = req(BASE + '/api/v1/tasks/cherry-picks/cart', token=tok)
    cd = cart.get('data', cart) if isinstance(cart, dict) else {}
    print(json.dumps({'user': NEW_USER, 'pass': NEW_PASS,
                      'user_id': (existing or {}).get('id'), 'role_id': role_id,
                      'token': tok, 'cart_total': cd.get('total'),
                      'cart_status': st}, ensure_ascii=False))


if __name__ == '__main__':
    main()

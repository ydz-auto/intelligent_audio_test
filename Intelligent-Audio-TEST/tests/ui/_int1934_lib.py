# -*- coding: utf-8 -*-
"""INT-1934 公共件：登录 + 后端只读探测（docker 真实栈 :15000 / 主库 intelligent_audio_test）。

账号与密码取 INT-1478/INT-1592 同口径：接线测试_admin / JieXianTest@2026。
只读探测用；写操作请在各自脚本内显式做并在结论里列清理。
"""
import base64
import json
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API = 'http://127.0.0.1:15000'
BASE_FE = 'http://127.0.0.1:15173'
USER = '接线测试_admin'
PASS = 'JieXianTest@2026'


class Api:
    def __init__(self, user=USER, password=PASS, api=API):
        self.api = api
        self.token = None
        self.user = user
        self.password = password

    def login(self):
        st, k = self.raw('/api/v1/auth/login/encryption-key')
        d = k.get('data', k) if isinstance(k, dict) else k
        if d.get('enabled'):
            pub = serialization.load_pem_public_key(d['public_key'].encode())
            ct = pub.encrypt(self.password.encode(), padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
            body = urllib.parse.urlencode({
                'username': self.user,
                'password_encrypted': base64.b64encode(ct).decode(),
                'encryption_key_id': d['kid'],
            }).encode()
        else:
            body = urllib.parse.urlencode({
                'username': self.user, 'password': self.password}).encode()
        req = urllib.request.Request(self.api + '/api/v1/auth/login', data=body, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with urllib.request.urlopen(req, timeout=60) as x:
            j = json.loads(x.read())
        self.token = j['access_token']
        return self.token

    def raw(self, path, method=None, body=None, headers=None, timeout=180):
        url = path if path.startswith('http') else self.api + path
        data = None
        hdrs = dict(headers or {})
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode('utf-8')
                hdrs['Content-Type'] = 'application/json'
            else:
                data = body
        req = urllib.request.Request(url, data=data, method=method)
        if self.token:
            req.add_header('Authorization', 'Bearer ' + self.token)
        for k, v in hdrs.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as x:
                raw = x.read()
                try:
                    return x.status, json.loads(raw)
                except ValueError:
                    return x.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw or b'{}')
            except ValueError:
                return e.code, {'raw': raw[:400].decode('utf-8', 'replace')}

    def get(self, path, **kw):
        return self.raw(path, **kw)

    def post(self, path, body=None, **kw):
        return self.raw(path, method='POST', body=body, **kw)


def unwrap(res):
    if isinstance(res, dict) and 'data' in res:
        return res['data']
    return res


def quote(s):
    return urllib.parse.quote(s, safe='')


def find_user(api, name):
    st, res = api.get('/api/v1/auth/users?page=1&per_page=100&keyword=' + quote(name))
    rows = (unwrap(res) or {}).get('items') or []
    return next((r for r in rows if r.get('username') == name), None)


def ensure_user(api, name, email, password, role_id=1):
    """建/复用隔离账号（购物车 per-user，避免与并发 run 共用 接线测试_admin 互清）。"""
    row = find_user(api, name)
    if row:
        return row, False
    api.post('/api/v1/auth/users', {'username': name, 'email': email,
                                    'password': password, 'role_id': role_id})
    return find_user(api, name), True

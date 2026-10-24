# -*- coding: utf-8 -*-
"""INT-1479 第三轮：加密登录 + 音频域接口探针（docker 真实库栈 15000）。"""
import base64
import json
import os
import sys

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API = os.environ.get('INT1479_API', 'http://127.0.0.1:15000/api/v1')
USER = '接线测试_admin'
PWD = 'JieXianTest@2026'
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_token.txt')


def login():
    key = requests.get(f'{API}/auth/login/encryption-key', timeout=20).json()
    pub = serialization.load_pem_public_key(key['public_key'].encode())
    enc = base64.b64encode(pub.encrypt(PWD.encode(), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))).decode()
    r = requests.post(f'{API}/auth/login', data={
        'username': USER, 'password_encrypted': enc, 'encryption_key_id': key['kid']}, timeout=30)
    r.raise_for_status()
    j = r.json()
    tok = j.get('access_token') or j.get('token') or (j.get('data') or {}).get('access_token')
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        f.write(tok or '')
    return tok


def token():
    if os.path.isfile(TOKEN_FILE):
        t = open(TOKEN_FILE, encoding='utf-8').read().strip()
        if t:
            return t
    return login()


def H():
    return {'Authorization': f'Bearer {token()}'}


def show(label, r):
    body = (r.text or '')[:500]
    print(f'--- {label}\n{r.request.method} {r.request.url} -> {r.status_code}\n{body}\n')


if __name__ == '__main__':
    if '--login' in sys.argv:
        t = login()
        print('token len', len(t))
    else:
        print(json.dumps({'ok': True}))

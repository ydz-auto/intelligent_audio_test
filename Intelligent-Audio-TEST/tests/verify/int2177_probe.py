# -*- coding: utf-8 -*-
"""INT-2177 返工探针：docker 栈 HTTP 直连取证。

用法（在仓库根执行，PYTHONIOENCODING=utf-8）：
  python tests/verify/int2177_probe.py login
  python tests/verify/int2177_probe.py get /api/v1/tasks/789
  python tests/verify/int2177_probe.py post /api/v1/tasks '<jsonfile>'
每条输出带 UTC 时间戳，便于与 docker logs -t 对拍。
"""
import base64
import datetime
import json
import sys

import httpx

BASE = 'http://localhost:15000'
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def login(client):
    r = client.get('/api/v1/auth/login/encryption-key')
    info = r.json()
    if isinstance(info.get('data'), dict) and info['data'].get('kid'):
        info = info['data']
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(info['public_key'].encode())
    ct = base64.b64encode(pub.encrypt(
        PASSWORD.encode(),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))).decode()
    r = client.post('/api/v1/auth/login', data={
        'username': USER, 'password_encrypted': ct,
        'encryption_key_id': info['kid']})
    body = r.json()
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    token = data.get('access_token') or data.get('token')
    if not token:
        raise SystemExit(f'login failed {r.status_code}: {body}')
    return token


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'login'
    client = httpx.Client(base_url=BASE, timeout=60, trust_env=False)
    token = login(client)
    headers = {'Authorization': f'Bearer {token}'}
    if cmd == 'login':
        print(now(), 'login ok token_len', len(token))
        return
    method = cmd.upper()
    path = sys.argv[2]
    payload = None
    if len(sys.argv) > 3:
        raw = sys.argv[3]
        payload = json.load(open(raw, encoding='utf-8')) if raw.endswith('.json') else json.loads(raw)
    print(now(), 'REQ', method, path, json.dumps(payload, ensure_ascii=False)[:400] if payload else '')
    if method == 'GET':
        r = client.get(path, headers=headers)
    elif method == 'DELETE':
        r = client.delete(path, headers=headers)
    elif method == 'PUT':
        r = client.put(path, headers=headers, json=payload)
    else:
        r = client.post(path, headers=headers, json=payload)
    print(now(), 'RESP', r.status_code, r.text[:4000])


if __name__ == '__main__':
    main()

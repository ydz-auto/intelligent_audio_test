# -*- coding: utf-8 -*-
"""INT-1488 探针：真实登录后对比「直连 15000」与「nginx 代理 15173」的 /logs。"""
import base64
import json
import time
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

DIRECT = 'http://127.0.0.1:15000/api/v1'
PROXY = 'http://127.0.0.1:15173/api/v1'


def http(method, url, body=None, token=None, timeout=90):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read().decode('utf-8', 'replace')
            return r.status, b, round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), round(time.time() - t0, 2)
    except Exception as e:
        return -1, str(e), round(time.time() - t0, 2)


st, key_b, _ = http('GET', DIRECT + '/auth/login/encryption-key')
key = json.loads(key_b)
pub = load_pem_public_key(key['public_key'].encode('utf-8'))
ct = pub.encrypt('JieXianTest@2026'.encode('utf-8'), padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
st, body, el = http('POST', DIRECT + '/auth/login', {
    'username': '接线测试_admin',
    'password_encrypted': base64.b64encode(ct).decode('ascii'),
    'encryption_key_id': key['kid'],
})
print('login', st, el, body[:150], flush=True)
tok = json.loads(body).get('access_token') or json.loads(body).get('data', {}).get('access_token')

for label, base in (('direct', DIRECT), ('proxy', PROXY)):
    st, body, el = http('GET', base + '/logs?page=1&per_page=20', token=tok)
    try:
        o = json.loads(body)
        d = o.get('data', o)
        print(label, 'status', st, 'elapsed', el, 'total', d.get('total'), 'items', len(d.get('items') or []),
              'first_id', (d.get('items') or [{}])[0].get('id'), flush=True)
    except Exception:
        print(label, 'status', st, 'elapsed', el, 'raw', body[:200], flush=True)

for label, base in (('direct', DIRECT), ('proxy', PROXY)):
    st, body, el = http('GET', base + '/logs/stats', token=tok)
    print(label, 'stats', st, el, body[:160], flush=True)
print('PROBE2_DONE', flush=True)

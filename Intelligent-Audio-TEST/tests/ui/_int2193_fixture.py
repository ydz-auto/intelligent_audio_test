# -*- coding: utf-8 -*-
"""INT-2193 fixture：建/删带 1 条评估映射的自建算法（不碰真实算法）。"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

GATEWAY = os.environ.get('API_GATEWAY', 'http://localhost:15000')
API = GATEWAY + '/api/v1'
TYPE = 'wiring_int2193_ui'


def req(method, path, body=None, token=None):
    r = urllib.request.Request(API + path, method=method)
    if body is not None:
        r.add_header('Content-Type', 'application/json')
        r.data = json.dumps(body).encode('utf-8')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'_raw': raw[:500]}


def login():
    st, key = req('GET', '/auth/encryption-key')
    pub = serialization.load_pem_public_key(key['public_key'].encode())
    ct = pub.encrypt(os.environ.get('DEV_PASSWORD', 'dev_password').encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    st, resp = req('POST', '/auth/login', {
        'username': os.environ.get('DEV_USER', 'dev_user'),
        'encryption_key_id': key['kid'],
        'password_encrypted': base64.b64encode(ct).decode(),
    })
    return resp['access_token']


def main(cmd):
    token = login()
    if cmd == 'dims':
        for path in ('/evaluation/dimensions?page=1&per_page=5', '/evaluation/dimensions'):
            st, resp = req('GET', path, token=token)
            print(path, st, json.dumps(resp, ensure_ascii=False)[:600])
        return
    if cmd == 'create':
        req('DELETE', f'/algorithm/definitions/{TYPE}', token=token)
        body = {
            'type': TYPE,
            'name': '接线测试_INT2193_ui',
            'status': 'online',
            'display_order': 0,
            'mappings': {'device': [], 'evaluation': [{
                'source': 'reference', 'source_param': 'query',
                'source_direction': 'output', 'target_param': 'query',
                'transform_type': 'none', 'dimension_id': 121,
            }]},
            'associated_dimensions': [{'dimension_id': 121, 'weight': 1, 'is_default': False}],
        }
        st, resp = req('POST', '/algorithm/definitions', body, token)
        print('create', st, json.dumps(resp, ensure_ascii=False)[:400])
        st, detail = req('GET', f'/algorithm/definitions/{TYPE}', token=token)
        print('detail', st, json.dumps(detail, ensure_ascii=False)[:400])
        return
    if cmd == 'read':
        st, detail = req('GET', f'/algorithm/definitions/{TYPE}', token=token)
        data = detail.get('data', detail)
        rows = [m for v in (data.get('mappings') or {}).values() for m in v]
        print('read', st, [(m.get('id'), m.get('source'), m.get('source_param'),
                            m.get('dimension_id'), m.get('transform_type')) for m in rows])
        return
    if cmd == 'delete':
        st, resp = req('DELETE', f'/algorithm/definitions/{TYPE}', token=token)
        print('delete', st, json.dumps(resp, ensure_ascii=False)[:300])


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'read')

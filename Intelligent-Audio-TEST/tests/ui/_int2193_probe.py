# -*- coding: utf-8 -*-
"""INT-2193 复现探针：PUT /algorithm/definitions/{type} 重提交参数映射。

用法（worktree 内，docker :15000）：
    python tests/ui/_int2193_probe.py
自建临时算法 type=wiring_int2193_probe / name=接线测试_INT2193_probe，结束前 DELETE。
"""
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
USER = os.environ.get('DEV_USER', 'dev_user')
PASSWORD = os.environ.get('DEV_PASSWORD', 'dev_password')
TYPE = 'wiring_int2193_probe'


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
            return e.code, {'_raw': raw[:800]}


def login():
    st, key = req('GET', '/auth/encryption-key')
    assert st == 200, (st, key)
    pub = serialization.load_pem_public_key(key['public_key'].encode())
    ct = pub.encrypt(PASSWORD.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    st, resp = req('POST', '/auth/login', {
        'username': USER,
        'encryption_key_id': key['kid'],
        'password_encrypted': base64.b64encode(ct).decode(),
    })
    assert st in (200, 201), (st, resp)
    return resp['access_token']


MAPPING = {
    'source': 'reference',
    'source_param': 'query',
    'source_direction': 'output',
    'target_param': 'query',
    'transform_type': 'none',
    'dimension_id': 72,
}

BODY = {
    'type': TYPE,
    'name': '接线测试_INT2193_probe',
    'status': 'online',
    'display_order': 0,
    'mappings': {'device': [], 'evaluation': [dict(MAPPING)]},
    'associated_dimensions': [{'dimension_id': 72, 'weight': 1, 'is_default': False}],
}


def show(label, st, resp):
    body = json.dumps(resp, ensure_ascii=False)
    print(f'\n### {label}\nstatus={st}\n{body[:1200]}')


def main():
    token = login()
    print('login ok')

    # 0. 清理可能残留
    req('DELETE', f'/algorithm/definitions/{TYPE}', token=token)

    st, resp = req('POST', '/algorithm/definitions', BODY, token)
    show('POST create', st, resp)
    if st not in (200, 201):
        return 1

    st, detail = req('GET', f'/algorithm/definitions/{TYPE}', token=token)
    data = detail.get('data', detail) if isinstance(detail, dict) else {}
    maps = (data or {}).get('mappings') or {}
    print('\nGET detail mappings keys:', list(maps.keys()))
    flat = [m for v in maps.values() for m in v]
    print('mapping rows with id:', [{'id': m.get('id'), 'source': m.get('source'),
                                     'source_param': m.get('source_param'),
                                     'dimension_id': m.get('dimension_id')} for m in flat])

    # 1. 原样重提交（不带 id）→ 期望复现 400
    st, resp = req('PUT', f'/algorithm/definitions/{TYPE}', BODY, token)
    show('PUT same body (no id) [repro]', st, resp)

    # 2. 带 id 重提交（改 transform_type）→ 期望 200
    body_with_id = json.loads(json.dumps(BODY))
    if flat and flat[0].get('id'):
        item = dict(flat[0])
        item['transform_type'] = 'json_parse'
        body_with_id['mappings'] = {'device': [], 'evaluation': [item]}
    st, resp = req('PUT', f'/algorithm/definitions/{TYPE}', body_with_id, token)
    show('PUT with mapping id + transform change', st, resp)
    st, detail = req('GET', f'/algorithm/definitions/{TYPE}', token=token)
    data = detail.get('data', detail)
    rows = [m for v in (data.get('mappings') or {}).values() for m in v]
    print('after PUT(with id) rows:', [(m.get('id'), m.get('transform_type')) for m in rows])

    # 3. 走全量保存端点（不带 id）→ 期望 200（自然键 upsert）
    save_body = json.loads(json.dumps(BODY))
    save_body['expected_updated_at'] = data.get('updated_at')
    st, resp = req('PUT', '/algorithm/definitions/save', save_body, token)
    show('PUT /definitions/save (no id)', st, resp)

    # 清理
    st, resp = req('DELETE', f'/algorithm/definitions/{TYPE}', token=token)
    show('DELETE cleanup', st, resp)
    return 0


if __name__ == '__main__':
    sys.exit(main())

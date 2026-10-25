# -*- coding: utf-8 -*-
"""INT-1499 验收：核对本 run 下单容器详情，再软删 + purge。用法：python tests/ui/int1499_task_detail.py <id> [--purge]"""
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
TOKEN = None


def req(url, method=None):
    r = urllib.request.Request(url, method=method)
    if TOKEN:
        r.add_header('Authorization', 'Bearer ' + TOKEN)
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, {'raw': raw[:200].decode('utf-8', 'replace')}


def main():
    tid = int(sys.argv[1])
    purge = '--purge' in sys.argv
    global TOKEN
    st, k = req(API + '/api/v1/auth/login/encryption-key')
    d = k.get('data', k)
    pub = serialization.load_pem_public_key(d['public_key'].encode())
    ct = pub.encrypt(PASS.encode(), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    body = urllib.parse.urlencode({'username': USER,
                                   'password_encrypted': base64.b64encode(ct).decode(),
                                   'encryption_key_id': d['kid']}).encode()
    r = urllib.request.Request(API + '/api/v1/auth/login', data=body, method='POST')
    r.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(r, timeout=60) as x:
        TOKEN = json.loads(x.read())['access_token']

    st, res = req(API + '/api/v1/tasks/%d' % tid)
    dd = res.get('data', res) if isinstance(res, dict) else res
    print('TASK', tid, 'status=%s' % st, json.dumps(
        {k2: dd.get(k2) for k2 in ('id', 'name', 'status', 'cherry_pick', 'task_type',
                                   'result_count', 'case_count', 'total_cases', 'source_task_ids')}
        if isinstance(dd, dict) else dd, ensure_ascii=False)[:600])
    st2, cases = req(API + '/api/v1/tasks/%d/cases?page=1&per_page=1' % tid)
    cd = cases.get('data', cases) if isinstance(cases, dict) else {}
    print('CASES status=%s total=%s' % (st2, cd.get('total')))
    if purge:
        print('DELETE', req(API + '/api/v1/tasks/%d' % tid, method='DELETE')[0])
        print('PURGE', req(API + '/api/v1/tasks/%d/purge' % tid, method='DELETE')[0])
        print('GET_AFTER', req(API + '/api/v1/tasks/%d' % tid)[0])


if __name__ == '__main__':
    main()

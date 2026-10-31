# -*- coding: utf-8 -*-
"""INT-2252 验收探针：评估维度「关联算法」列表/筛选的数据源一致性（只读）。

对比三处口径（真实库栈 15000）：
  A. GET /evaluation/dimensions?per_page=1000        —— 页面列表行（契约恒下发 associated_algorithms: []）
  B. GET /algorithm/dimensions/{algo}                —— 本卡前端新增的数据源
  C. GET /evaluation/dimensions/options?algorithm_type={algo} —— 基线口径
只读，不写库。
"""
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

BASE = 'http://127.0.0.1:15000/api/v1'


def http(method, path, body=None, token=None, timeout=90):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def login():
    st, body = http('GET', '/auth/login/encryption-key')
    key = json.loads(body)
    pub = load_pem_public_key(key['public_key'].encode('utf-8'))
    ct = pub.encrypt('dev_password'.encode('utf-8'), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    st, body = http('POST', '/auth/login', {
        'username': 'dev_user',
        'password_encrypted': base64.b64encode(ct).decode('ascii'),
        'encryption_key_id': key['kid'],
    })
    payload = json.loads(body)
    tok = payload.get('access_token') or (payload.get('data') or {}).get('access_token')
    if not tok:
        print('LOGIN_FAIL', st, body[:300])
        sys.exit(2)
    return tok


def get_json(tok, path):
    st, body = http('GET', path, token=tok)
    try:
        return st, json.loads(body)
    except Exception:  # noqa: BLE001
        return st, None


def unwrap(d):
    if isinstance(d, dict) and 'data' in d and isinstance(d['data'], (dict, list)):
        return d['data']
    return d


def main():
    tok = login()
    print('LOGIN_OK')

    st, opt = get_json(tok, '/algorithm/options')
    opt = unwrap(opt)
    algos = (opt or {}).get('algorithms') or []
    print('AUTH_ALGORITHMS', st, [(a.get('value') or a.get('algorithm_type'), a.get('label') or a.get('name')) for a in algos])

    st, lst = get_json(tok, '/evaluation/dimensions?per_page=1000')
    lst = unwrap(lst) or {}
    items = lst.get('items') or []
    with_assoc = [i for i in items if i.get('associated_algorithms')]
    print('A_LIST', st, 'total', lst.get('total'), 'items', len(items),
          'non_empty_associated', len(with_assoc))

    for a in algos:
        code = a.get('value') or a.get('algorithm_type')
        st_b, b = get_json(tok, '/algorithm/dimensions/%s' % urllib.parse.quote(str(code)))
        b = unwrap(b) or {}
        b_ids = sorted({int(d.get('id')) for d in (b.get('dimensions') or []) if d.get('id') is not None})
        st_c, c = get_json(tok, '/evaluation/dimensions/options?algorithm_type=%s' % urllib.parse.quote(str(code)))
        c = unwrap(c) or {}
        c_ids = sorted({int(d.get('id')) for d in (c.get('dimensions') or []) if d.get('id') is not None})
        list_ids = sorted({int(i.get('id')) for i in items})
        print('ALGO', code, '| B_status', st_b, 'B_count', len(b_ids),
              '| C_status', st_c, 'C_count', len(c_ids),
              '| B==C', b_ids == c_ids,
              '| B_in_list', len(set(b_ids) & set(list_ids)),
              '| B_defaults', sum(1 for d in (b.get('dimensions') or []) if d.get('is_default')))
        if b_ids != c_ids:
            only_b = sorted(set(b_ids) - set(c_ids))
            only_c = sorted(set(c_ids) - set(b_ids))
            print('  DIFF only_B', only_b[:10], 'only_C', only_c[:10])
        if b.get('dimensions'):
            print('  sample_dim', json.dumps(b['dimensions'][0], ensure_ascii=True)[:220])
    print('PROBE_DONE')


if __name__ == '__main__':
    main()

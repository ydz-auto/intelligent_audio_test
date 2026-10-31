# -*- coding: utf-8 -*-
"""INT-2191 复核：INT-2200 给 15173 nginx /api/ 补 proxy_read_timeout=300s 之后，
经 15173（反代）做真实库全量用例导出，核对 200 + 条数一致 + 耗时 < 300s。

只读操作（登录 + 列表 + 导出），不写业务数据。

用法：
  python -I verify_int2191_15173_full_export.py [--base http://localhost:15173]
"""
import base64
import json
import os
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173').rstrip('/')
USER = os.environ.get('LOGIN_USER', 'dev_user')
PASSWORD = os.environ.get('LOGIN_PASS', 'dev_password')
ART = os.environ.get(
    'ART',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2191'),
)
os.makedirs(ART, exist_ok=True)
TIMEOUT = 600  # 反代已放宽到 300s，客户端给足余量以便区分「反代掐断」与「后端慢」

RESULT = []


def check(name, ok, detail=None):
    RESULT.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ' | '
          + json.dumps(detail, ensure_ascii=False, default=str)[:1200], flush=True)
    return ok


def login(session):
    key = session.get(BASE + '/api/v1/auth/login/encryption-key', timeout=30).json()
    d = key.get('data', key)
    if not d.get('enabled'):
        return None  # 未启用加密：返回空 token，靠 cookie/无鉴权
    pub = serialization.load_der_public_key(base64.b64decode(
        ''.join(l for l in d['public_key'].splitlines() if not l.startswith('-----'))))
    enc = pub.encrypt(password_bytes(PASSWORD), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    body = {
        'username': USER,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': d.get('kid'),
    }
    r = session.post(BASE + '/api/v1/auth/login', data=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError('login %s %s' % (r.status_code, r.text[:300]))
    tok = r.json().get('access_token')
    if not tok:
        raise RuntimeError('login 200 but no access_token')
    return tok


def password_bytes(pw):
    return pw.encode('utf-8')


def main():
    session = requests.Session()
    out = {'base': BASE, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}

    # 0) 环境：反代后面的真的是真实库栈
    r = session.get(BASE + '/health', timeout=30)
    health = r.json() if r.status_code == 200 else {}
    out['health'] = health
    check('0 15173 /health 200 且 database=intelligent_audio_test',
          r.status_code == 200 and health.get('database') == 'intelligent_audio_test',
          {'status': r.status_code, 'health': health})

    tok = login(session)
    headers = {'Authorization': 'Bearer ' + tok} if tok else {}
    session.headers.update(headers)
    check('1 登录 dev_user 拿到 token', bool(tok), {'has_token': bool(tok)})

    # 2) 总数口径
    r = session.get(BASE + '/api/v1/testcases', params={'page': 1, 'per_page': 1},
                    timeout=60)
    body = r.json()
    data = body.get('data', body)
    total = data.get('total') or data.get('total_count')
    check('2 GET /api/v1/testcases total 可读', r.status_code == 200 and isinstance(total, int),
          {'status': r.status_code, 'total': total})

    # 3) 逐页圈定全部 id（与前端 fetchAllTestCaseIdsByFilter 同口径）
    ids, page, pages = [], 1, 1
    while page <= pages and page <= 50:
        r = session.get(BASE + '/api/v1/testcases',
                        params={'page': page, 'per_page': 200}, timeout=120)
        d = r.json().get('data', r.json())
        items = d.get('testcases') or d.get('items') or []
        ids.extend([it['id'] for it in items])
        pages = d.get('pages') or max(1, -(-(d.get('total') or 0) // 200))
        page += 1
    out['ids'] = {'count': len(ids), 'pages': pages, 'api_total': total}
    check('3 逐页圈定 id 与列表 total 一致', len(ids) == total, out['ids'])

    # 4) 全量导出（经 15173 反代，与弹窗「全量/当前筛选」同接口同载荷）
    payload = {'ids': ids, 'format': 'json'}
    t0 = time.time()
    try:
        r = session.post(BASE + '/api/v1/testcases/export', json=payload, timeout=TIMEOUT)
        elapsed = round(time.time() - t0, 1)
        status = r.status_code
        ctype = r.headers.get('content-type', '')
        try:
            j = r.json()
        except Exception:
            j = None
        env = (j or {}).get('data', j) or {}
        exported = len(env.get('test_cases') or [])
        total_count = env.get('total_count')
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        status, ctype, j, exported, total_count = 'ERR', '', None, None, None
        out['export_error'] = repr(e)

    out['export_full'] = {
        'requested': len(ids), 'status': status, 'elapsed_s': elapsed,
        'content_type': ctype, 'total_count': total_count, 'test_cases_len': exported,
        'exported_at': (env or {}).get('exported_at') if isinstance(env, dict) else None,
    }
    check('4 经 15173 全量导出 status=200', status == 200, out['export_full'])
    check('5 耗时 < 300s（未被反代掐断）', isinstance(elapsed, float) and elapsed < 300,
          {'elapsed_s': elapsed})
    check('6 导出条数 == 请求条数 == 列表 total',
          exported == len(ids) == total,
          {'exported': exported, 'requested': len(ids), 'api_total': total})
    check('7 信封 total_count 与条数一致', total_count == exported,
          {'total_count': total_count, 'test_cases_len': exported})

    # 8) 小范围非回归（3 条）
    t0 = time.time()
    r = session.post(BASE + '/api/v1/testcases/export',
                     json={'ids': ids[:3], 'format': 'json'}, timeout=120)
    el = round(time.time() - t0, 2)
    j = r.json() if r.status_code == 200 else {}
    env = j.get('data', j) or {}
    check('8 小范围 3 条导出 200 且条数=3',
          r.status_code == 200 and len(env.get('test_cases') or []) == 3,
          {'status': r.status_code, 'elapsed_s': el,
           'len': len(env.get('test_cases') or [])})

    ok = all(x['ok'] for x in RESULT)
    out['result'] = 'PASS' if ok else 'FAIL'
    out['checks'] = RESULT
    with open(os.path.join(ART, 'result_15173_full_export.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\nresult=' + out['result'], flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

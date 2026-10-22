# -*- coding: utf-8 -*-
"""INT-1255 复测探针 v2：真实 JWT 登录 + 复测项关键端点探测（JSON body 修正版）。"""
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

API = 'http://127.0.0.1:15000/api/v1'
ADMIN = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'


def http(method, path, body=None, token=None, form=False, timeout=60):
    url = API + path
    data = None
    hdrs = {'Accept': 'application/json'}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode('utf-8')
            hdrs['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            data = json.dumps(body).encode('utf-8')
            hdrs['Content-Type'] = 'application/json'
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:800]
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:800]
    except Exception as e:
        return 'ERR', f'{type(e).__name__}: {e}'


def login(username, password):
    st, key = http('GET', '/auth/login/encryption-key')
    pub = load_pem_public_key(key['public_key'].encode('utf-8'))
    ct = pub.encrypt(password.encode('utf-8'), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    pw = base64.b64encode(ct).decode('ascii')
    return http('POST', '/auth/login', {
        'username': username,
        'password_encrypted': pw,
        'encryption_key_id': key['kid'],
    }, form=True)


def main():
    st, res = login(ADMIN, PASSWORD)
    print(f'login: {st}')
    if st != 200:
        print(json.dumps(res, ensure_ascii=False)[:400]); return 1
    token = res.get('access_token') or res['data']['access_token']
    print(f'  token ok, user={res.get("user", res.get("data", {})).get("username")}')

    # ── access-token CRUD 全链（真实身份）──
    st, at = http('GET', '/auth/access-tokens', token=token)
    print(f'GET /auth/access-tokens: {st} total={(at.get("data") or {}).get("total")}')
    st, cr = http('POST', '/auth/access-tokens', {
        'name': '接线测试_复测token探针',
        'scopes': ['*'],
        'expires_at': 0,
    }, token=token)
    print(f'POST /auth/access-tokens: {st} -> {json.dumps(cr, ensure_ascii=False)[:300]}')
    did = None
    d = cr.get('data') or {}
    if isinstance(d, dict):
        did = d.get('id')
        tok = d.get('token')
        print(f'  created id={did} token_plain={"YES" if tok else "NO"} hint={d.get("token_hint")}')
    if did:
        st, pa = http('PATCH', f'/auth/access-tokens/{did}',
                      {'name': '接线测试_复测token改名'}, token=token)
        print(f'PATCH /auth/access-tokens/{did} rename: {st}')
        st, dl = http('DELETE', f'/auth/access-tokens/{did}', token=token)
        print(f'DELETE /auth/access-tokens/{did}: {st}')
        st, at2 = http('GET', '/auth/access-tokens', token=token)
        ids = [i.get('id') for i in (at2.get('data') or {}).get('items', [])]
        print(f'  after delete, list ids={ids} contains {did}? {did in ids}')

    # ── 报告列表 ──
    st, rl = http('GET', '/reports?page=1&per_page=10&sort_by=created_at&order=desc')
    items = rl.get('data', {}).get('items', []) if st == 200 else []
    print(f'GET /reports: {st} count={len(items)}')
    task_reports = [it for it in items if it.get('report_type') in ('task', None)]
    for it in task_reports[:5]:
        print(f'  report id={it.get("id")} name={it.get("name","")[:30]!r} status={it.get("status")} task_id={it.get("task_id")}')

    # ── compare：前端 snake_case vs 后端 camelCase 契约核对（短超时，避免 hang）──
    task_ids = list({it.get('task_id') for it in task_reports if it.get('task_id')})[:2]
    if len(task_ids) == 2:
        st_s, r_s = http('POST', '/reports/compare', {'task_ids': task_ids}, token=token, timeout=25)
        print(f'compare snake_case task_ids: {st_s} -> {json.dumps(r_s, ensure_ascii=False)[:200]}')
        st_c, r_c = http('POST', '/reports/compare', {'taskIds': task_ids}, token=token, timeout=25)
        print(f'compare camelCase taskIds:   {st_c} -> {json.dumps(r_c, ensure_ascii=False)[:300]}')

    report_ids = [it['id'] for it in task_reports[:2]]
    if len(report_ids) == 2:
        st_s, r_s = http('POST', '/reports/secondary-compare', {'report_ids': report_ids}, token=token, timeout=25)
        print(f'secondary-compare snake_case: {st_s} -> {json.dumps(r_s, ensure_ascii=False)[:200]}')
        st_c, r_c = http('POST', '/reports/secondary-compare', {'reportIds': report_ids}, token=token, timeout=25)
        print(f'secondary-compare camelCase:  {st_c} -> {json.dumps(r_c, ensure_ascii=False)[:300]}')

    # ── 分享（报告 493，真实身份）──
    st, sh = http('POST', '/reports/493/share', {
        'access': 'public', 'expiry': '7d', 'password': '', 'recipients': '',
    }, token=token)
    print(f'POST /reports/493/share: {st} -> {json.dumps(sh, ensure_ascii=False)[:300]}')
    tk = (sh.get('data') or {}).get('token') if isinstance(sh, dict) else None
    if tk:
        st, shg = http('GET', f'/reports/shared/{tk}')
        print(f'GET /reports/shared/{tk}: {st}')
        st, shr = http('DELETE', f'/reports/493/share/{tk}', token=token)
        print(f'DELETE /reports/493/share/{tk}: {st} -> {json.dumps(shr, ensure_ascii=False)[:200]}')

    # ── 用例日志文件列表（找带日志文件的用例）──
    found = False
    for it in task_reports[:6]:
        rid = it['id']
        st, sc = http('POST', f'/reports/{rid}/cases/search',
                      {'page': 1, 'per_page': 50, 'sort_by': 'name', 'sort_order': 'asc'}, token=token)
        cases = (sc.get('data') or {}).get('items') if st == 200 else None
        if not isinstance(cases, list):
            print(f'report {rid} cases/search: {st} -> {json.dumps(sc, ensure_ascii=False)[:200]}')
            continue
        print(f'report {rid} cases/search total={(sc.get("data") or {}).get("total")}')
        for c in cases[:20]:
            cid = c.get('id') or c.get('case_id')
            if not cid:
                continue
            st, lg = http('GET', f'/reports/{rid}/cases/{cid}/logs', token=token)
            lst = (lg.get('data') or {}).get('items') if isinstance(lg, dict) else None
            if isinstance(lst, list) and len(lst) > 0:
                print(f'  ★ LOG FILES: report={rid} case={cid} items={len(lst)} first={json.dumps(lst[0], ensure_ascii=False)[:200]}')
                st, dl = http('GET', f'/reports/{rid}/cases/{cid}/logs/download?files={urllib.parse.quote(json.dumps([lst[0]["name"]]))}', token=token)
                print(f'  download: {st} type={type(dl).__name__} len={len(dl) if isinstance(dl, str) else "?"}')
                found = True
                break
        if found:
            break
    if not found:
        print('  no case with log files found')

    # ── 数据卫生复核 ──
    st, at3 = http('GET', '/auth/access-tokens', token=token)
    names = [i.get('name') for i in (at3.get('data') or {}).get('items', [])]
    print('access-tokens after cleanup:', names)
    return 0


if __name__ == '__main__':
    sys.exit(main())

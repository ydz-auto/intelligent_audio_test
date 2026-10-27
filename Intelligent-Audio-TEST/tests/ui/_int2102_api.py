# -*- coding: utf-8 -*-
"""INT-2102 联调小工具：走 docker :15000 网关 AES? RSA-OAEP 登录并打到 /tags/by-category。

用法（在 worktree 根的任意子目录跑，不落盘 Windows 保留名）：
    python _int2102_api.py login          # 打印 token 到 stdout
    python _int2102_api.py bycategory     # 打印 GET /tags/by-category 结构
    python _int2102_api.py fixture        # 建「接线测试_」分类+标签 fixture
    python _int2102_api.py cleanup        # 删除「接线测试_」fixture
"""
import base64
import json
import os
import sys
import urllib.request

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

GATEWAY = os.environ.get('API_GATEWAY', 'http://localhost:15000')
API = GATEWAY + '/api/v1'
USER = os.environ.get('DEV_USER', 'dev_user')
PASSWORD = os.environ.get('DEV_PASSWORD', 'dev_password')


def _req(method, path, body=None, token=None):
    url = API + path
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(body).encode('utf-8')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {'_error': str(e)}


def _login():
    if not HAS_CRYPTO:
        return None, 'cryptography 缺失'
    st, key = _req('GET', '/auth/encryption-key')
    if st != 200:
        return None, f'encryption-key {st}: {key}'
    pub_pem = key['public_key'].encode('utf-8')
    kid = key['kid']
    pub = serialization.load_pem_public_key(pub_pem, backend=default_backend())
    ct = pub.encrypt(PASSWORD.encode('utf-8'), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None))
    body = {
        'username': USER,
        'encryption_key_id': kid,
        'password_encrypted': base64.b64encode(ct).decode('ascii'),
    }
    st, resp = _req('POST', '/auth/login', body)
    if st not in (200, 201):
        return None, f'login {st}: {resp}'
    # 登录响应 token 在顶层（access_token/token_type/user，无 data 信封）
    data = resp if isinstance(resp, dict) else {}
    return data.get('access_token'), resp


def _bycategory(token):
    st, resp = _req('GET', '/tags/by-category', token=token)
    return st, resp


def _cleanup(token):
    st, tags = _req('GET', '/tags?page=1&per_page=200', token=token)
    items = ((tags or {}).get('data') or {}).get('items') or []
    for t in items:
        if t.get('name', '').startswith('接线测试_'):
            _req('DELETE', f"/tags/{t['id']}?cascade=false", token=token)
    st2, cats = _req('GET', '/tags/categories?page=1&per_page=200', token=token)
    citems = ((cats or {}).get('data') or {}).get('items') or []
    for c in citems:
        if c.get('name', '').startswith('接线测试_'):
            _req('DELETE', f"/tags/categories/{c['id']}", token=token)
    return tags, cats


def _fixture(token, user):
    # 两个分类 + 未分类标签；前一个分类两个标签、后一个分类一个、未分类一个
    def cat(name, color):
        st, r = _req('POST', '/tags/categories',
                     {'name': name, 'color': color, 'description': 'INT-2102 接线验收'}, token)
        return (r.get('data') or {}).get('id')
    c1 = cat(f'接线测试_{user}_分类A', '#10b981')
    c2 = cat(f'接线测试_{user}_分类B', '#3b82f6')

    def tag(name, cid=None):
        body = {'name': name, 'color': '#94a3b8'}
        if cid:
            body['category_id'] = cid
        _req('POST', '/tags', body, token)
    tag(f'接线测试_{user}_标签1', c1)
    tag(f'接线测试_{user}_标签2', c1)
    tag(f'接线测试_{user}_标签3', c2)
    tag(f'接线测试_{user}_标签4')
    return {'catA': c1, 'catB': c2}


def _case_fixture(token, user):
    """建「接线测试_」分组 + 2 个用例，返回 {group_id, case_ids:[...]}。"""
    st, r = _req('POST', '/groups', {'name': f'接线测试_{user}_分组'}, token)
    group_id = ((r or {}).get('data') or {}).get('id')
    if not group_id:
        # 兼容旧契约（group 字段命名）
        group_id = ((r or {}).get('data') or {}).get('group_id')
    case_ids = []
    for suffix in ('用例A', '用例B'):
        st, r = _req('POST', '/testcases',
                     {'name': f'接线测试_{user}_{suffix}', 'group_id': group_id}, token)
        cid = ((r or {}).get('data') or {}).get('id')
        case_ids.append(cid)
    return {'group_id': group_id, 'case_ids': case_ids}


def _case_cleanup(token, user, group_id):
    from urllib.parse import quote
    kw = quote(f'接线测试_{user}')
    st, r = _req('GET', f'/testcases?page=1&per_page=100&include_deleted=true&keyword={kw}', token=token)
    items = ((r or {}).get('data') or {}).get('items') or []
    for c in items:
        _req('DELETE', f"/testcases/{c['id']}", token=token)
        _req('DELETE', f"/testcases/{c['id']}/purge", token=token)
    if group_id:
        _req('DELETE', f"/groups/{group_id}", token=token)
    return items


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'login'
    if cmd == 'login':
        tok, resp = _login()
        if tok:
            print(tok)
        else:
            print(json.dumps(resp, ensure_ascii=False), file=sys.stderr)
        return
    tok, err = _login()
    if not tok:
        print(f'登录失败: {err}', file=sys.stderr)
        sys.exit(1)
    if cmd == 'bycategory':
        st, resp = _bycategory(tok)
        print(json.dumps({'status': st, 'resp': resp}, ensure_ascii=False, indent=2))
    elif cmd == 'fixture':
        user = sys.argv[2] if len(sys.argv) > 2 else 'c'
        print(json.dumps(_fixture(tok, user), ensure_ascii=False))
    elif cmd == 'cleanup':
        tags, cats = _cleanup(tok)
        print(json.dumps({'cleaned': True,
                          'leftover_tags': [t['name'] for t in ((tags or {}).get('data') or {}).get('items') or [] if t['name'].startswith('接线测试_')],
                          'leftover_cats': [c['name'] for c in ((cats or {}).get('data') or {}).get('items') or [] if c['name'].startswith('接线测试_')]},
                         ensure_ascii=False))
    elif cmd == 'case-fixture':
        user = sys.argv[2] if len(sys.argv) > 2 else 'c'
        print(json.dumps(_case_fixture(tok, user), ensure_ascii=False))
    elif cmd == 'case-cleanup':
        user = sys.argv[2] if len(sys.argv) > 2 else 'c'
        group_id = sys.argv[3] if len(sys.argv) > 3 else None
        items = _case_cleanup(tok, user, group_id)
        print(json.dumps({'cleaned': len(items)}, ensure_ascii=False))
    else:
        print(f'未知命令: {cmd}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
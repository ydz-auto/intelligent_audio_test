# -*- coding: utf-8 -*-
"""INT-2174 走查（React 用例域增量）小工具。

- 登录经 docker 网关 :15000（AES/RSA-OAEP 密钥交换，同 _int2102_api）
- JSON / multipart / 字节流请求
- 夹具：分组、标签、用例（含轮次音频/维度/参考参数）
- 回读：按 keyword / id 查用例（含已删）
- 清理：只按本 run 落盘的 id 删（软删 → purge），不按 group 参数推断归属

夹具一律「接线测试_走查R2_」前缀。
"""
import base64
import io
import json
import os
import sys
import uuid
import urllib.request
import urllib.parse

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

GATEWAY = os.environ.get('API_GATEWAY', 'http://localhost:15000')
API = GATEWAY + '/api/v1'
USER = os.environ.get('DEV_USER', '接线测试_admin')
PASSWORD = os.environ.get('DEV_PASSWORD', 'JieXianTest@2026')
PREFIX = '接线测试_走查R2_'


def req(method, path, body=None, token=None, timeout=60, raw=False, retries=3):
    """JSON 请求；raw=True 时返回 (status, headers, bytes)。共享栈偶发超时/连接重置时重试。"""
    url = API + path if path.startswith('/') else path
    last = None
    for attempt in range(retries):
        r = urllib.request.Request(url, method=method)
        if body is not None:
            r.add_header('Content-Type', 'application/json')
            r.data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        if token:
            r.add_header('Authorization', 'Bearer ' + token)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                data = resp.read()
                if raw:
                    return resp.status, dict(resp.headers), data
                text = data.decode('utf-8')
                return resp.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            data = e.read()
            if raw:
                return e.code, dict(e.headers), data
            try:
                return e.code, json.loads(data.decode('utf-8'))
            except Exception:
                return e.code, {'_raw': data.decode('utf-8', 'replace')[:2000]}
        except Exception as e:
            last = e
            if attempt < retries - 1:
                import time as _t
                _t.sleep(2.0 * (attempt + 1))
    raise last


def multipart(path, file_bytes, filename, fields=None, token=None, timeout=120):
    """multipart/form-data 上传；返回 (status, json_or_text)。"""
    boundary = '----int2174' + uuid.uuid4().hex
    parts = []
    for k, v in (fields or {}).items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
         f'Content-Type: application/octet-stream\r\n\r\n').encode('utf-8'))
    parts.append(file_bytes)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
    body = b''.join(parts)
    r = urllib.request.Request(API + path, data=body, method='POST')
    r.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            text = resp.read().decode('utf-8')
            try:
                return resp.status, json.loads(text)
            except Exception:
                return resp.status, text
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, text


def login():
    if not HAS_CRYPTO:
        return None, 'cryptography 缺失'
    st, key = req('GET', '/auth/encryption-key')
    if st != 200:
        return None, f'encryption-key {st}: {key}'
    pub = serialization.load_pem_public_key(key['public_key'].encode('utf-8'),
                                            backend=default_backend())
    ct = pub.encrypt(PASSWORD.encode('utf-8'), padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    st, resp = req('POST', '/auth/login', {
        'username': USER,
        'encryption_key_id': key['kid'],
        'password_encrypted': base64.b64encode(ct).decode('ascii'),
    })
    if st not in (200, 201):
        return None, f'login {st}: {resp}'
    return (resp or {}).get('access_token'), resp


def data(resp):
    return (resp or {}).get('data')


# ---------------------------------------------------------------- fixtures
def create_group(token, name):
    st, r = req('POST', '/groups', {'name': name}, token=token)
    assert st in (200, 201), f'建组失败 {st} {r}'
    gid = (data(r) or {}).get('id')
    assert gid, f'建组无 id: {r}'
    return gid


def create_tag(token, name, color='#94a3b8', category_id=None):
    body = {'name': name, 'color': color}
    if category_id:
        body['category_id'] = category_id
    st, r = req('POST', '/tags', body, token=token)
    assert st in (200, 201), f'建标签失败 {st} {r}'
    return (data(r) or {}).get('id')


def find_audio(token, audio_type=None, keyword=None):
    qs = '/audios?page=1&per_page=5'
    if audio_type:
        qs += '&audio_type=' + audio_type
    if keyword:
        qs += '&keyword=' + urllib.parse.quote(keyword)
    st, r = req('GET', qs, token=token)
    items = (data(r) or {}).get('items') or []
    return items


def case_config(audio_id, audio_name, dimension_id=None, dimension_name=None,
                ref_text='ref-text', speaker_group_id=None, rounds=1):
    rounds_cfg = []
    for n in range(1, rounds + 1):
        aud = {'audio_id': audio_id, 'audio_name': audio_name, 'spl': 65,
               'play_order': 0}
        if speaker_group_id:
            aud['playback_speaker_group_id'] = speaker_group_id
        rd = {'round_number': n, 'audios': [aud]}
        if dimension_id:
            rd['evaluation'] = {'enabled': True,
                                'dimensions': [{'id': dimension_id, 'name': dimension_name}]}
        rounds_cfg.append(rd)
    cfg = {'rounds': rounds_cfg}
    if dimension_id:
        cfg['dimensions'] = [{'id': dimension_id, 'name': dimension_name}]
    return cfg


def create_case(token, name, group_id=None, group_name=None, config=None,
                tags=None, description='INT-2174 走查夹具'):
    body = {'name': name, 'description': description}
    if group_id:
        body['group_id'] = group_id
    elif group_name:
        body['group'] = group_name
    if config is not None:
        body['config'] = config
    if tags:
        body['tags'] = tags
    st, r = req('POST', '/testcases', body, token=token)
    assert st in (200, 201), f'建用例失败 {st} {r}'
    cid = (data(r) or {}).get('id')
    assert cid, f'建用例无 id: {r}'
    return cid


def get_case(token, cid):
    st, r = req('GET', f'/testcases/{cid}', token=token)
    return st, (data(r) or {})


def update_ref_params(token, cid, round_number, ref):
    st, r = req('PUT', f'/testcases/{cid}/rounds/{round_number}/ref-params',
                {'referenceParams': ref}, token=token)
    return st, data(r)


def list_cases(token, keyword=None, **params):
    qs = ['page=1', 'per_page=100']
    if keyword:
        qs.append('keyword=' + urllib.parse.quote(keyword))
    for k, v in params.items():
        if v is None:
            continue
        qs.append(f'{k}={urllib.parse.quote(str(v))}')
    st, r = req('GET', '/testcases?' + '&'.join(qs), token=token)
    return st, (data(r) or {})


def find_case_by_name(token, name, include_deleted=False):
    st, d = list_cases(token, keyword=name,
                       include_deleted='true' if include_deleted else None)
    for it in d.get('items') or []:
        if it.get('name') == name:
            return it
    return None


def list_groups(token):
    out, page = [], 1
    while True:
        st, r = req('GET', f'/groups?page={page}&per_page=100', token=token)
        d = data(r) or {}
        out.extend(d.get('items') or [])
        if page >= (d.get('pages') or 1):
            break
        page += 1
    return out


def delete_case_hard(token, cid):
    """软删 + purge，两步都回读确认。"""
    st1, _ = req('DELETE', f'/testcases/{cid}', token=token)
    st2, _ = req('DELETE', f'/testcases/{cid}/purge', token=token)
    return st1, st2


def delete_group(token, gid):
    return req('DELETE', f'/groups/{gid}', token=token)


def delete_tag(token, tid):
    return req('DELETE', f'/tags/{tid}?cascade=false', token=token)


def list_tags(token):
    st, r = req('GET', '/tags?page=1&per_page=200', token=token)
    return (data(r) or {}).get('items') or []


# ---------------------------------------------------------------- transfer
def export(token, ids, fmt='zip', include_reference_params=True):
    body = {'ids': ids, 'format': fmt}
    if fmt == 'zip':
        body['include_reference_params'] = include_reference_params
    st, headers, blob = req('POST', '/testcases/export', body, token=token, raw=True, timeout=180)
    return st, headers, blob


def import_preview(token, file_bytes, filename):
    return multipart('/testcases/import/preview', file_bytes, filename, token=token)


def do_import(token, file_bytes, filename, on_duplicate='skip'):
    return multipart('/testcases/import', file_bytes, filename,
                     fields={'on_duplicate': on_duplicate}, token=token)


def template(token):
    st, headers, blob = req('GET', '/testcases/template/download', token=token, raw=True)
    return st, headers, blob

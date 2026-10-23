# -*- coding: utf-8 -*-
"""INT-1567 补充探针：后端对「名称留空」发布的契约（前端已在提交前拦截，这里直接打接口）。

序列：建 → 存草稿(A) → PUT 发布 name="" → 观察状态码与草稿是否还在 → 清理。
"""
import json
import time
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:15000/api/v1'
TAG = time.strftime('%m%d%H%M%S')
TYPE = f'itest1483_v_p_{TAG}'
OUT = {'type': TYPE}


def call(path, method='GET', body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, str(e)


def def_body(name):
    return {'type': TYPE, 'name': name, 'group_id': None, 'display_order': 1, 'status': 'offline',
            'description': 'INT-1567 非法值契约探针', 'device_params': [], 'api_params': [],
            'case_params': [], 'reference_params': [],
            'mappings': {'device': [], 'api': [], 'evaluation': []},
            'associated_dimensions': []}


try:
    st, raw = call('/algorithm/definitions', 'POST', def_body('接线测试_INT1567_契约_' + TAG))
    OUT['create'] = {'status': st, 'body': raw[:160]}

    st, raw = call('/algorithm/definitions/draft', 'PUT',
                   {'algorithm_type': TYPE, 'definition': def_body('接线测试_INT1567_契约草稿_' + TAG)})
    OUT['save_draft'] = {'status': st, 'body': raw[:160]}

    st, raw = call(f'/algorithm/definitions/{TYPE}', 'PUT', def_body(''))
    OUT['publish_empty_name'] = {'status': st, 'body': raw[:300]}

    st, raw = call(f'/algorithm/definitions/draft/{TYPE}')
    data = (json.loads(raw).get('data') if raw.strip().startswith('{') else None) or {}
    OUT['draft_after_invalid'] = {'status': st, 'empty': not bool(data),
                                  'name': (data or {}).get('name')}

    st, raw = call(f'/algorithm/definitions/{TYPE}')
    d2 = (json.loads(raw).get('data') if raw.strip().startswith('{') else None) or {}
    OUT['definition_after_invalid'] = {'status': st, 'name': (d2 or {}).get('name')}
finally:
    OUT['cleanup_draft'] = call(f'/algorithm/definitions/draft/{TYPE}', 'DELETE')[0]
    OUT['cleanup_def'] = call(f'/algorithm/definitions/{TYPE}', 'DELETE')[0]
    OUT['cleanup_readback'] = call(f'/algorithm/definitions/{TYPE}')[0]

print(json.dumps(OUT, ensure_ascii=False, indent=2))

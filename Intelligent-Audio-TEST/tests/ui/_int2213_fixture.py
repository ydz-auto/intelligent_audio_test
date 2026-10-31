# -*- coding: utf-8 -*-
"""INT-2213 夹具：从真实 voice_llm 复制自建大表算法（评估映射 1192 条），供窗口化渲染验收。

自建前缀「接线测试_2213_」，run 结束 DELETE。token 从 Selenium 登录取 localStorage。
用法：
  python -I _int2213_fixture.py create --base http://localhost:5337
  python -I _int2213_fixture.py delete --base http://localhost:5337
"""
import argparse
import importlib.util
import json
import os
import urllib.error
import urllib.request

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2213')
os.makedirs(ART, exist_ok=True)
API = 'http://127.0.0.1:15000/api/v1'
BIG_TYPE = 'int2213_perf_1192'
BIG_NAME = '接线测试_2213_性能1192'


def load_audit():
    spec = importlib.util.spec_from_file_location('sa', os.path.join(HERE, '_int2121_scroll_audit.py'))
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    return sa


def get_token(base):
    sa = load_audit()
    d = sa.make_driver()
    try:
        sa.login(d, base)
        time.sleep(1.0)
        return d.execute_script("return window.localStorage.getItem('iatp:auth:token:v1')")
    finally:
        d.quit()


def api(method, path, body=None, tok=''):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + tok,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:400]


def dev_dto(p):
    return {
        'param_code': p['param_code'], 'param_name': p.get('param_name'),
        'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
        'direction': p.get('direction') or 'input', 'required': bool(p.get('required')),
        'default_value': p.get('default_value'), 'help_text': p.get('help_text'),
        'ui_order': p.get('ui_order') or 0, 'hidden': bool(p.get('hidden')),
    }


def jval(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return json.dumps(v, ensure_ascii=False)


def case_dto(p):
    return {
        'param_code': p['param_code'], 'param_name': p.get('param_name'),
        'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
        'required': bool(p.get('required')), 'default_value': jval(p.get('default_value')),
        'help_text': p.get('help_text'), 'ui_order': p.get('ui_order') or 0,
        'hidden': bool(p.get('hidden')), 'scope': p.get('scope'),
        'min_value': p.get('min_value'), 'max_value': p.get('max_value'),
        'step': p.get('step'), 'unit': p.get('unit'),
        'annotation_code': p.get('annotation_code'), 'field_path': p.get('field_path'),
    }


def ref_dto(p):
    return {
        'code': p['code'], 'name': p.get('name') or '', 'type': p.get('type') or 'text',
        'annotation_code': p.get('annotation_code'), 'annotation_format': p.get('annotation_format'),
        'field_path': p.get('field_path'), 'merge_mode': p.get('merge_mode'),
        'help_text': p.get('help_text'),
    }


def map_dto(m):
    return {
        'source': m.get('source') or 'case',
        'source_param': m.get('source_param') or '',
        'source_direction': m.get('source_direction') or 'output',
        'target_param': m.get('target_param') or '',
        'transform_type': m.get('transform_type') or 'none',
        'dimension_id': m.get('dimension_id'),
    }


def create(tok):
    out = {}
    st, res = api('GET', '/algorithm/definitions/voice_llm', tok=tok)
    src = (res or {})['data']
    out['src_eval_mappings'] = len(src['mappings']['evaluation'])
    body = {
        'type': BIG_TYPE, 'name': BIG_NAME, 'group_id': src.get('group_id'), 'display_order': 0,
        'status': 'online', 'description': 'INT-2213 自建性能夹具（run 内删除）',
        'device_params': [dev_dto(p) for p in src['device_params']],
        'case_params': [case_dto(p) for p in src['case_params']],
        'reference_params': [ref_dto(p) for p in src['reference_params']],
        'mappings': {'device': [], 'evaluation': [map_dto(m) for m in src['mappings']['evaluation']]},
        'associated_dimensions': [],
    }
    st, res = api('POST', '/algorithm/definitions', body, tok=tok)
    out['create'] = {'status': st, 'msg': str((res or {}).get('message'))[:300]}
    st, d = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    if st == 200:
        dt = d['data']
        out['readback'] = {
            'type': dt['type'], 'name': dt['name'], 'status': dt.get('status'),
            'device': len(dt['device_params']), 'case': len(dt['case_params']),
            'eval_mappings': len(dt['mappings']['evaluation']),
            'dims': len({str(m.get('dimension_id')) for m in dt['mappings']['evaluation']}),
        }
    else:
        out['readback'] = {'status': st, 'body': str(res)[:300]}
    return out


def key(m):
    # 与后端唯一约束 uq_param_mapping_algo_level 对齐：source+source_param+dimension_id
    return (m.get('source'), m.get('source_param'), m.get('dimension_id'))


def topup(tok):
    """create 走 gRPC 超时只写一部分；PUT 只提交缺失评估映射补齐。"""
    _, res = api('GET', '/algorithm/definitions/voice_llm', tok=tok)
    src = res['data']
    _, res = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    cur = res['data']
    have = {key(m) for m in cur['mappings']['evaluation']}
    missing = []
    seen = set(have)
    for m in src['mappings']['evaluation']:
        k = key(m)
        if k in seen:
            continue
        seen.add(k)
        missing.append(m)
    body = {
        'type': BIG_TYPE, 'name': cur['name'], 'group_id': cur.get('group_id'),
        'display_order': cur.get('display_order') or 0, 'status': cur.get('status') or 'online',
        'description': cur.get('description') or '',
        'device_params': [dev_dto(p) for p in cur['device_params']],
        'case_params': [case_dto(p) for p in cur['case_params']],
        'reference_params': [ref_dto(p) for p in cur['reference_params']],
        'mappings': {'device': [], 'evaluation': [map_dto(m) for m in missing]},
        'associated_dimensions': [],
    }
    out = {'have': len(have), 'missing': len(missing)}
    if missing:
        st, r = api('PUT', '/algorithm/definitions/' + BIG_TYPE, body, tok=tok)
        out['put'] = {'status': st, 'msg': str((r or {}).get('message'))[:200]}
    _, res = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    cur = res['data']
    out['now'] = {'eval_mappings': len(cur['mappings']['evaluation']),
                  'dims': len({str(m.get('dimension_id')) for m in cur['mappings']['evaluation']})}
    return out


def delete(tok):
    st, res = api('DELETE', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    out = {'delete': {'status': st, 'body': str(res)[:200]}}
    st2, res2 = api('GET', '/algorithm/definitions/' + BIG_TYPE, tok=tok)
    out['after'] = {'status': st2}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['create', 'topup', 'delete'])
    ap.add_argument('--base', default='http://localhost:5337')
    a = ap.parse_args()
    tok = get_token(a.base)
    if not tok:
        raise SystemExit('no token')
    with open(os.path.join(ART, 'token.txt'), 'w', encoding='utf-8') as f:
        f.write(tok)
    out = create(tok) if a.cmd == 'create' else topup(tok) if a.cmd == 'topup' else delete(tok)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

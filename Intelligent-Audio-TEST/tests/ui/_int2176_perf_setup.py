# -*- coding: utf-8 -*-
"""INT-2176 补证夹具：从真实 voice_llm 复制自建大表算法（评估映射全量）+
小算法（1 条评估映射，用于映射编辑/发布截图）。

自建前缀「接线测试_走查R4_」，type 带 2176 后缀；run 结束 DELETE。
"""
import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int2176')
TOK = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
API = 'http://127.0.0.1:15000/api/v1'

BIG_TYPE = 'wiring_r4_perf4_2176'
BIG_NAME = '接线测试_走查R4_性能R4'
SMALL_TYPE = 'wiring_r4_edit4_2176'
SMALL_NAME = '接线测试_走查R4_编辑映射4'


def api(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + TOK,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
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


def main():
    st, res = api('GET', '/algorithm/definitions/voice_llm')
    src = (res or {})['data']
    out = {}

    big = {
        'type': BIG_TYPE, 'name': BIG_NAME, 'group_id': src.get('group_id'), 'display_order': 0,
        'status': 'online', 'description': 'INT-2176 补证自建（run 内删除）',
        'device_params': [dev_dto(p) for p in src['device_params']],
        'case_params': [case_dto(p) for p in src['case_params']],
        'reference_params': [ref_dto(p) for p in src['reference_params']],
        'mappings': {'device': [], 'evaluation': [map_dto(m) for m in src['mappings']['evaluation']]},
        'associated_dimensions': [],
    }
    st, res = api('POST', '/algorithm/definitions', big)
    out['big_create'] = {'status': st, 'msg': str((res or {}).get('message'))[:200]}
    st, d = api('GET', '/algorithm/definitions/' + BIG_TYPE)
    if st == 200:
        dt = d['data']
        out['big'] = {'type': dt['type'], 'name': dt['name'], 'status': dt.get('status'),
                      'device': len(dt['device_params']), 'case': len(dt['case_params']),
                      'eval_mappings': len(dt['mappings']['evaluation']),
                      'refs': len(dt['reference_params'])}

    first = src['mappings']['evaluation'][0]
    small = {
        'type': SMALL_TYPE, 'name': SMALL_NAME, 'group_id': None, 'display_order': 0,
        'status': 'online', 'description': 'INT-2176 映射编辑截图自建（run 内删除）',
        'device_params': [], 'case_params': [],
        'reference_params': [ref_dto(p) for p in src['reference_params'][:1]],
        'mappings': {'device': [], 'evaluation': [map_dto(first)]},
        'associated_dimensions': [{'dimension_id': first['dimension_id'], 'weight': 1.0,
                                   'is_default': True}],
    }
    st, res = api('POST', '/algorithm/definitions', small)
    out['small_create'] = {'status': st, 'msg': str((res or {}).get('message'))[:300]}
    st, d = api('GET', '/algorithm/definitions/' + SMALL_TYPE)
    if st == 200:
        dd = d['data']
        out['small'] = {'type': dd['type'], 'name': dd['name'], 'status': dd.get('status'),
                        'eval_mappings': len(dd['mappings']['evaluation']),
                        'relations': len(dd['dimension_relations']),
                        'first': dd['mappings']['evaluation'][:1]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(ART, 'perf_setup.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

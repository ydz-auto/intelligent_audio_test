# -*- coding: utf-8 -*-
"""INT-2176 补证：大表算法补全缺失评估映射（create 走 gRPC 超时只写入一部分）。
利用 PUT 追加缺失行（已存在的行会撞 uq_param_mapping_algo_level，故只提交缺失项）。
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


def api(method, path, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + TOK,
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


def key(m):
    return (m.get('source'), m.get('source_param'), m.get('dimension_id'), m.get('target_param'))


def main():
    _, res = api('GET', '/algorithm/definitions/voice_llm')
    src = res['data']
    st, res = api('GET', '/algorithm/definitions/' + BIG_TYPE)
    cur = res['data']
    have = {key(m) for m in cur['mappings']['evaluation']}
    missing = [m for m in src['mappings']['evaluation'] if key(m) not in have]
    print('have', len(have), 'missing', len(missing))
    body = {
        'type': BIG_TYPE, 'name': cur['name'], 'group_id': cur.get('group_id'),
        'display_order': cur.get('display_order') or 0, 'status': cur.get('status') or 'online',
        'description': cur.get('description') or '',
        'device_params': [{
            'param_code': p['param_code'], 'param_name': p.get('param_name'),
            'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
            'direction': p.get('direction') or 'input', 'required': bool(p.get('required')),
            'default_value': p.get('default_value'), 'help_text': p.get('help_text'),
            'ui_order': p.get('ui_order') or 0, 'hidden': bool(p.get('hidden')),
        } for p in cur['device_params']],
        'case_params': [{
            'param_code': p['param_code'], 'param_name': p.get('param_name'),
            'label': p.get('param_name'), 'param_type': p.get('param_type') or 'text',
            'required': bool(p.get('required')),
            'default_value': p.get('default_value') if isinstance(p.get('default_value'), (str, int, float, bool)) or p.get('default_value') is None else json.dumps(p['default_value'], ensure_ascii=False),
            'help_text': p.get('help_text'), 'ui_order': p.get('ui_order') or 0,
            'hidden': bool(p.get('hidden')), 'scope': p.get('scope'),
            'min_value': p.get('min_value'), 'max_value': p.get('max_value'),
            'step': p.get('step'), 'unit': p.get('unit'),
            'annotation_code': p.get('annotation_code'), 'field_path': p.get('field_path'),
        } for p in cur['case_params']],
        'reference_params': [{
            'code': p['code'], 'name': p.get('name') or '', 'type': p.get('type') or 'text',
            'annotation_code': p.get('annotation_code'),
            'annotation_format': p.get('annotation_format'),
            'field_path': p.get('field_path'), 'merge_mode': p.get('merge_mode'),
            'help_text': p.get('help_text'),
        } for p in cur['reference_params']],
        'mappings': {'device': [], 'evaluation': [{
            'source': m.get('source') or 'case',
            'source_param': m.get('source_param') or '',
            'source_direction': m.get('source_direction') or 'output',
            'target_param': m.get('target_param') or '',
            'transform_type': m.get('transform_type') or 'none',
            'dimension_id': m.get('dimension_id'),
        } for m in missing]},
        'associated_dimensions': [],
    }
    if missing:
        st, r = api('PUT', '/algorithm/definitions/' + BIG_TYPE, body)
        print('PUT', st, str((r or {}).get('message'))[:300])
    st, res = api('GET', '/algorithm/definitions/' + BIG_TYPE)
    cur = res['data']
    print('now eval_mappings', len(cur['mappings']['evaluation']),
          'device', len(cur['device_params']), 'case', len(cur['case_params']),
          'refs', len(cur['reference_params']), 'status', cur.get('status'))
    out = {'type': BIG_TYPE, 'name': cur['name'],
           'eval_mappings': len(cur['mappings']['evaluation']),
           'device': len(cur['device_params']), 'case': len(cur['case_params']),
           'refs': len(cur['reference_params'])}
    with open(os.path.join(ART, 'big_topup.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()

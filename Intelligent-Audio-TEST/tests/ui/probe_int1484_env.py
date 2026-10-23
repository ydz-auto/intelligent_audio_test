# -*- coding: utf-8 -*-
"""INT-1484 复跑：INT-1553 环境修复核对（参数/算法落库回读 + 写操作耗时）。"""
import json, os, time, urllib.request, urllib.error

API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
NAME = '接线测试_INT1484_env_' + str(int(time.time()))[-6:]


def call(method, path, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN,
                                          'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8')
            return r.status, (json.loads(raw) if raw else None), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw), round(time.time() - t0, 1)
        except Exception:
            return e.code, raw, round(time.time() - t0, 1)


def items(body):
    return ((body or {}).get('data') or {}).get('items', []) if isinstance(body, dict) else []


def data(body):
    return (body or {}).get('data') or {} if isinstance(body, dict) else {}


def main():
    st, body, dt = call('GET', '/algorithm/options')
    print('algorithm/options', st, dt, 's ->', json.dumps(body, ensure_ascii=False)[:300])

    st, cats, dt = call('GET', '/evaluation/categories?per_page=100')
    print('categories', st, dt, 'n=', len(items(cats)))

    payload = {
        'name': NAME, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
        'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
        'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [
            {'param_code': 'p1', 'param_name': 'P1', 'label': 'P1', 'field_type': 'text',
             'required': True, 'default_value': '', 'help_text': '', 'ui_order': 1},
            {'param_code': 'p2', 'param_name': 'P2', 'label': 'P2', 'field_type': 'text',
             'required': False, 'default_value': 'd2', 'help_text': '', 'ui_order': 2},
            {'param_code': 'p3', 'param_name': 'P3', 'label': 'P3', 'field_type': 'number',
             'required': False, 'default_value': '', 'help_text': '', 'ui_order': 3},
        ],
        'output_fields': [
            {'param_code': 'score', 'param_name': '评分', 'label': '评分', 'field_path': 'score',
             'field_type': 'number', 'output_role': 'main', 'agg_role': 'value',
             'default_value': '', 'pass_threshold': '', 'visible_in_report': True,
             'help_text': '', 'ui_order': 1},
            {'param_code': 'reason', 'param_name': '理由', 'label': '理由', 'field_path': 'reason',
             'field_type': 'text', 'output_role': 'aux', 'agg_role': 'value',
             'default_value': '', 'pass_threshold': '', 'visible_in_report': True,
             'help_text': '', 'ui_order': 2},
        ],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '宿主网关',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30,
                           'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
        'associated_algorithms': [{'algorithm_type': 'voice_llm'}],
    }
    st, body, dt = call('POST', '/evaluation/dimensions', payload)
    did = data(body).get('id')
    print('create', st, dt, 's id=', did, 'resp=', json.dumps(body, ensure_ascii=False)[:200])

    if did:
        st, det, dt = call('GET', '/evaluation/dimensions/%s' % did)
        d = data(det)
        print('detail', st, dt, 's keys=', sorted(d.keys()))
        for k in ('required_inputs', 'requiredInputs', 'output_fields', 'outputFields',
                  'associated_algorithms', 'associatedAlgorithms'):
            if k in d:
                print('  ', k, '=', json.dumps(d[k], ensure_ascii=False)[:400])

        payload2 = dict(payload)
        payload2['name'] = NAME + '_改'
        payload2['description'] = 'INT-1484 env probe 已改'
        payload2['required_inputs'] = payload['required_inputs'][:2]
        st, body, dt = call('PUT', '/evaluation/dimensions/%s' % did, payload2)
        print('update', st, dt, 's resp=', json.dumps(body, ensure_ascii=False)[:200])
        st, det, dt = call('GET', '/evaluation/dimensions/%s' % did)
        d = data(det)
        print('detail-after-put', st, dt, 's name=', d.get('name'),
              'inputs=', len(d.get('required_inputs') or []),
              'outputs=', len(d.get('output_fields') or []),
              'algs=', json.dumps(d.get('associated_algorithms'), ensure_ascii=False)[:200])

        st, body, dt = call('DELETE', '/evaluation/dimensions/%s' % did)
        print('delete', st, dt, 's resp=', json.dumps(body, ensure_ascii=False)[:200])

    st, dims, dt = call('GET', '/evaluation/dimensions?per_page=1000')
    remain = [x for x in items(dims) if str(x.get('name', '')).startswith('接线测试_INT1484_')]
    print('remaining test dims', len(remain), [x['name'] for x in remain])
    st, cats, dt = call('GET', '/evaluation/categories?per_page=100')
    print('categories after', st, len(items(cats)))


if __name__ == '__main__':
    main()

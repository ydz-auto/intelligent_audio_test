# -*- coding: utf-8 -*-
"""INT-1484 探针4：维度详情 wire 键名、algorithm/options 形状、容器内可达端点。"""
import json, os, time, urllib.request, urllib.error

API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
NAME = '接线测试_INT1484_probe_' + str(int(time.time()))[-5:]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def main():
    st, body = call('GET', '/algorithm/options')
    print('algorithm/options', st, json.dumps(body, ensure_ascii=False)[:600])

    st, body = call('POST', '/evaluation/dimensions', {
        'name': NAME, 'type': 'auto', 'dimension_type': 'main',
        'category_id': None, 'status': True, 'weight': 5,
        'result_type': 1, 'result_min': 0, 'result_max': 100, 'decimal_places': 2,
        'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [{'param_code': 'p1', 'param_name': 'P1', 'label': 'P1', 'field_type': 'text',
                             'required': True, 'default_value': '', 'help_text': '', 'ui_order': 1}],
        'output_fields': [{'param_code': 'score', 'param_name': '评分', 'label': '评分', 'field_path': 'score',
                           'field_type': 'number', 'output_role': 'main', 'agg_role': 'value',
                           'default_value': '', 'pass_threshold': '', 'visible_in_report': True,
                           'help_text': '', 'ui_order': 1}],
        'api_endpoints': [
            {'url': 'http://host.docker.internal:15000/health', 'name': '宿主网关', 'priority': 1,
             'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60},
            {'url': 'http://127.0.0.1:59999/health', 'name': '不可达', 'priority': 2,
             'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60},
        ],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
    })
    dim = ((body or {}).get('data') or {}) if isinstance(body, dict) else {}
    did = dim.get('id')
    print('create', st, 'id', did)
    time.sleep(2)
    st, detail = call('GET', '/evaluation/dimensions/%s' % did)
    data = (detail.get('data') or {}) if isinstance(detail, dict) else {}
    print('detail', st, 'keys', sorted(data.keys()))
    print('detail sample', json.dumps({k: data.get(k) for k in
          ('required_inputs', 'requiredInputs', 'output_fields', 'outputFields',
           'api_endpoints', 'apiEndpoints', 'associated_algorithms', 'associatedAlgorithms')},
          ensure_ascii=False)[:1200])
    for i in range(3):
        st, health = call('GET', '/evaluation/dimensions/%s/health' % did)
        print('health try', i, st, json.dumps(health, ensure_ascii=False)[:800])
        time.sleep(1)
    st, _ = call('DELETE', '/evaluation/dimensions/%s' % did)
    print('delete', st)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1484 探针2：直读维度详情 / 健康 / 试算，落 JSON（评估域接口契约核对）。"""
import json, os, urllib.request, urllib.error

API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def main():
    out = {}
    for did in (312, 121):
        out['detail_%s' % did] = call('GET', '/evaluation/dimensions/%s' % did)
    out['health_312'] = call('GET', '/evaluation/dimensions/312/health')
    out['health_121'] = call('GET', '/evaluation/dimensions/121/health')
    out['calc_312'] = call('POST', '/evaluation/dimensions/312/calculate', {'value': 92})
    out['calc_121'] = call('POST', '/evaluation/dimensions/121/calculate', {'value': 92})
    with open(os.path.join(ART, 'api_probe2.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('written')


if __name__ == '__main__':
    main()

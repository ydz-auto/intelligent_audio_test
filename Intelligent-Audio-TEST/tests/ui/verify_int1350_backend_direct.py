# -*- coding: utf-8 -*-
"""INT-1350 后端直连验证：POST 维度带 output_fields(param_code) → GET 详情是否落库。"""
import json
import time
import urllib.request

API = 'http://127.0.0.1:5700'
USER = '接线测试_admin'
PWD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_backend_direct'


def _req(method, path, body=None, token=None):
    url = API + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    # 1. 获取加密公钥
    status, pub = _req('GET', '/api/v1/auth/encryption-key')
    print('ENC_KEY status=', status)
    # 2. 登录（表单编码）
    login_data = urllib.parse.urlencode({
        'username': USER, 'password': PWD,
    }).encode('utf-8')
    r = urllib.request.Request(API + '/api/v1/auth/login', data=login_data, method='POST')
    r.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(r, timeout=60) as resp:
        login = json.loads(resp.read().decode('utf-8'))
    print('LOGIN keys=', list(login.keys()))
    token = (login.get('data') or login).get('access_token') or (login.get('data') or {}).get('token')
    print('TOKEN?', bool(token))

    # 清理同名
    st, lst = _req('GET', f'/api/v1/evaluation/dimensions?search={NAME}&per_page=100', token=token)
    items = (lst.get('data') or {}).get('items') or []
    if isinstance(items, list):
        for it in items:
            if it.get('name') == NAME:
                _req('DELETE', f"/api/v1/evaluation/dimensions/{it['id']}", token=token)
                print('CLEAN', it['id'])

    # 3. POST 维度带 output_fields（param_code 口径）
    body = {
        'name': NAME,
        'description': 'int1350 backend direct',
        'dimension_type': 'main',
        'type': 'auto',
        'result_type': 1,
        'result_min': 0,
        'result_max': 100,
        'decimal_places': 2,
        'weight': 5,
        'statistic_method': 'average',
        'status': True,
        'rule': {'rules': [{'condition': '>=', 'value': 60, 'score': 10}]},
        'required_inputs': [
            {'param_code': 'asr_result', 'param_name': 'ASR识别结果', 'label': 'ASR识别结果',
             'field_type': 'text', 'required': True, 'ui_order': 1},
        ],
        'output_fields': [
            {'param_code': 'score', 'param_name': '评分结果', 'label': '评分结果',
             'field_path': 'score', 'field_type': 'number', 'output_role': 'main',
             'agg_role': 'value', 'visible_in_report': True, 'ui_order': 1},
            {'param_code': 'wer', 'param_name': 'WER值', 'label': 'WER值',
             'field_path': 'data.result.wer', 'field_type': 'number', 'output_role': 'aux',
             'agg_role': 'value', 'visible_in_report': True, 'ui_order': 2},
        ],
        'associated_algorithms': [],
    }
    st, created = _req('POST', '/api/v1/evaluation/dimensions', body, token=token)
    print('POST status=', st, 'body=', json.dumps(created, ensure_ascii=False)[:300])
    dim_id = (created.get('data') or {}).get('id')
    print('DIM_ID=', dim_id)
    if not dim_id:
        print('CREATE_FAILED')
        return

    # 4. GET 详情
    time.sleep(1)
    st, detail = _req('GET', f'/api/v1/evaluation/dimensions/{dim_id}', token=token)
    print('GET status=', st)
    data = detail.get('data') or {}
    of = data.get('output_fields') or []
    ri = data.get('required_inputs') or []
    print('OUTPUT_FIELDS_COUNT=', len(of), json.dumps(of, ensure_ascii=False)[:500])
    print('REQUIRED_INPUTS_COUNT=', len(ri))

    # 5. 清理
    _req('DELETE', f'/api/v1/evaluation/dimensions/{dim_id}', token=token)
    print('CLEANUP done')


if __name__ == '__main__':
    main()

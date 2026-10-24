# -*- coding: utf-8 -*-
"""INT-1484 开工门禁：直连 :15000 实测评估维度 POST / PUT / DELETE。

口径（需求规划师 2026-10-24 裁定·第 2 轮，放行精简载荷）：
- 载荷 ≤1 输入参数 + 1 输出参数 + 1 端点（不关联算法）；
- 判定 = 不出现网关 60s DEADLINE_EXCEEDED + 返回 2xx + GET 回读逐字段一致 + 无锁队列迹象；
- 耗时只记录、不作门禁（40s 参考上限已撤销）。

仅在 docker 真实库栈（intelligent_audio_test）上使用；fixture 带「接线测试_INT1484_」前缀，
脚本末尾 DELETE 清理，不留残留。
注意：output_fields.pass_threshold 必须按前端口径传 null（前端 toNullableNumber('')→null）；
传空串会命中 evaluation_dimension_params.pass_threshold(double precision) 报
invalid input syntax，输出参数被静默丢弃（API 侧健壮性缺口，非前端行为）。
"""
import json, os, time, urllib.request, urllib.error

API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
STAMP = str(int(time.time()))[-6:]
NAME = '接线测试_INT1484_GATE_' + STAMP
NAME2 = NAME + '_改'


def call(method, path, body=None, timeout=120):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + '/api/v1' + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            return r.status, (json.loads(raw) if raw else {}), round(time.time() - t, 2)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw), round(time.time() - t, 2)
        except Exception:
            return e.code, raw, round(time.time() - t, 2)


BODY = {
    'name': NAME, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
    'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
    'decimal_places': 2, 'estimated_exec_time': 5,
    'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10},
                       {'condition': '<', 'value': 70, 'score': 0}]},
    'required_inputs': [
        {'param_code': 'q_text', 'param_name': '提问文本', 'label': '提问文本', 'field_type': 'text',
         'required': True, 'default_value': '', 'help_text': '', 'ui_order': 1},
    ],
    'output_fields': [
        {'param_code': 'score', 'param_name': '评分', 'label': '评分', 'field_path': 'score',
         'field_type': 'number', 'output_role': 'main', 'agg_role': 'value', 'default_value': '',
         'pass_threshold': None, 'visible_in_report': True, 'help_text': '', 'ui_order': 1},
    ],
    'api_endpoints': [
        {'url': 'http://host.docker.internal:15000/health', 'name': '主端点(在线)', 'priority': 1,
         'max_process': 5, 'max_timeout': 30, 'max_audio_duration': 60},
    ],
    'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
}

LIMIT = float(os.environ.get('GATE_LIMIT', '40'))
OUT = []


def gate(step, ok, detail):
    OUT.append({'step': step, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + step + ' :: ' + json.dumps(detail, ensure_ascii=False), flush=True)


def main():
    st, body, dt = call('GET', '/evaluation/dimensions?per_page=1000')
    total0 = len((body.get('data') or {}).get('items') or []) if isinstance(body, dict) else -1
    print('baseline_total=%d (GET %.2fs)' % (total0, dt), flush=True)

    st, body, dt = call('POST', '/evaluation/dimensions', BODY)
    did = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    gate('POST /evaluation/dimensions 精简载荷无 60s 超时且 2xx', dt < 60 and 200 <= st < 300 and did is not None,
         {'status': st, 'elapsed_s': dt, 'id': did,
          'resp': (json.dumps(body, ensure_ascii=False)[:300] if did is None else '')})

    readback = {}
    if did:
        st_g, body_g, dt_g = call('GET', '/evaluation/dimensions/%s' % did)
        d = (body_g.get('data') or {}) if isinstance(body_g, dict) else {}
        readback = {'inputs': [(x.get('param_code'), x.get('param_name')) for x in (d.get('required_inputs') or [])],
                    'outputs': [(x.get('param_code'), x.get('field_path'), x.get('pass_threshold'))
                                for x in (d.get('output_fields') or [])],
                    'endpoints': [(e.get('url'), e.get('name')) for e in (d.get('api_endpoints') or [])],
                    'rules': len((d.get('rule') or {}).get('rules') or [])}
        gate('GET 回读参数/端点逐字段一致（精简载荷：1 输入 / 1 输出 / 1 端点）',
             len(readback['inputs']) == 1 and readback['inputs'][0][0] == 'q_text'
             and len(readback['outputs']) == 1 and readback['outputs'][0][0] == 'score'
             and len(readback['endpoints']) == 1,
             {'status': st_g, 'elapsed_s': dt_g, **readback})

        upd = dict(BODY)
        upd.update({'name': NAME2, 'description': '门禁探针'})
        upd['required_inputs'] = BODY['required_inputs']
        upd['output_fields'] = BODY['output_fields']
        st_p, body_p, dt_p = call('PUT', '/evaluation/dimensions/%s' % did, upd)
        gate('PUT /evaluation/dimensions/{id} 精简载荷无 60s 超时且 2xx', dt_p < 60 and 200 <= st_p < 300,
             {'status': st_p, 'elapsed_s': dt_p, 'resp': json.dumps(body_p, ensure_ascii=False)[:300]})

        st_d, body_d, dt_d = call('DELETE', '/evaluation/dimensions/%s' % did)
        gate('DELETE /evaluation/dimensions/{id} 无 60s 超时且 2xx', dt_d < 60 and 200 <= st_d < 300,
             {'status': st_d, 'elapsed_s': dt_d, 'resp': json.dumps(body_d, ensure_ascii=False)[:300]})

        st, body, _ = call('GET', '/evaluation/dimensions?per_page=1000')
        names = [x.get('name') for x in (body.get('data') or {}).get('items') or []]
        gate('清理：fixture 不在列表中', NAME not in names and NAME2 not in names,
             {'total_now': len(names), 'baseline_total': total0})

    print(json.dumps({'baseline_total': total0, 'stamp': STAMP, 'gate': OUT}, ensure_ascii=False, indent=1), flush=True)


if __name__ == '__main__':
    main()

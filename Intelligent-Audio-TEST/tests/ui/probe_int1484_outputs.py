# -*- coding: utf-8 -*-
"""INT-1484 复跑：输出字段落库排查（创建后看 DB 行 + evaluation_service 日志）。"""
import json, os, subprocess, time, urllib.request, urllib.error

API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
TOKEN = open(os.path.join(ART, 'token.txt'), encoding='utf-8').read().strip()
NAME = '接线测试_INT1484_out_' + str(int(time.time()))[-6:]


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


def psql(sql):
    p = subprocess.run(['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
                        '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test',
                        '-At', '-c', sql], capture_output=True, text=True, encoding='utf-8')
    return (p.stdout or '') + (p.stderr or '')


def main():
    payload = {
        'name': NAME, 'type': 'auto', 'dimension_type': 'main', 'category_id': None,
        'status': True, 'weight': 5, 'result_type': 1, 'result_min': 0, 'result_max': 100,
        'decimal_places': 2, 'estimated_exec_time': 5,
        'rule': {'rules': [{'condition': '>=', 'value': 90, 'score': 10}]},
        'required_inputs': [
            {'param_code': 'p1', 'param_name': 'P1', 'label': 'P1', 'field_type': 'text',
             'required': True, 'default_value': '', 'help_text': '', 'ui_order': 1}],
        'output_fields': [
            {'param_code': 'score', 'param_name': '评分', 'label': '评分', 'field_path': 'score',
             'field_type': 'number', 'output_role': 'main', 'agg_role': 'value',
             'default_value': '', 'pass_threshold': '', 'visible_in_report': True,
             'help_text': '', 'ui_order': 1},
            {'param_code': 'reason', 'param_name': '理由', 'label': '理由', 'field_path': 'reason',
             'field_type': 'text', 'output_role': 'aux', 'agg_role': 'value',
             'default_value': '', 'pass_threshold': '', 'visible_in_report': True,
             'help_text': '', 'ui_order': 2}],
        'api_endpoints': [{'url': 'http://host.docker.internal:15000/health', 'name': '宿主网关',
                           'priority': 1, 'max_process': 5, 'max_timeout': 30,
                           'max_audio_duration': 60}],
        'api_settings': {'method': 'POST', 'timeout': 30000, 'headers': {}, 'bodyTemplate': {}},
        'associated_algorithms': [{'algorithm_type': 'voice_llm'}],
    }
    st, body, dt = call('POST', '/evaluation/dimensions', payload)
    did = ((body or {}).get('data') or {}).get('id') if isinstance(body, dict) else None
    print('create', st, dt, 's id=', did, json.dumps(body, ensure_ascii=False)[:160])
    time.sleep(1)
    print('DB rows:')
    print(psql("select id,param_code,param_direction,coalesce(output_role,''),coalesce(field_path,'') "
               "from evaluation_dimension_params where dimension_id=%s order by id;" % did))
    st, det, dt = call('GET', '/evaluation/dimensions/%s' % did)
    d = (det or {}).get('data') or {}
    print('GET inputs=', len(d.get('required_inputs') or []), 'outputs=', len(d.get('output_fields') or []))
    print('output_fields wire:', json.dumps(d.get('output_fields'), ensure_ascii=False)[:300])
    print('eval log tail:')
    p = subprocess.run(['docker', 'exec', 'intelligent-audio-test-evaluation_service-1', 'sh', '-c',
                        'tail -n 120 /app/logs/evaluation_service/app-*.log 2>/dev/null | grep -iE '
                        '"output|param failed|ERROR|error" | tail -20'],
                       capture_output=True, text=True, encoding='utf-8')
    print((p.stdout or '')[-2000:])
    st, body, dt = call('DELETE', '/evaluation/dimensions/%s' % did)
    print('delete', st, dt, json.dumps(body, ensure_ascii=False)[:120])
    time.sleep(1)
    print('remaining params:', psql("select count(*) from evaluation_dimension_params where dimension_id=%s;" % did))


if __name__ == '__main__':
    main()

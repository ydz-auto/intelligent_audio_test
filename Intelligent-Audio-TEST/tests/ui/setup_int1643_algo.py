# -*- coding: utf-8 -*-
"""INT-1643 造数（规划师 2026-10-23 裁定：算法配置无数据 → 自建 1 个算法定义 + 1 条用例）。

1) POST /algorithm/definitions 建 wire_test_param（用例参数 threshold: number 0.5/[0,1]；关联维度 121）
2) GET 三查：/algorithm/options、/algorithm/form-schema/wire_test_param、/algorithm/definitions/wire_test_param
3) POST /testcases 建「接线测试_INT1643_参数」（group 打断与恢复，2 轮真实音频，algorithm_params round1 0.5）
4) SQL 补 reference_params 独立列（PUT /testcases 会剥离该键，见 INT-1645）→ 抽屉参考参数失败态可复现

注：POST /algorithm/definitions 实测回 400/500 DEADLINE_EXCEEDED 但已落库（15000 慢写），以三查为准。
收尾见 cleanup_int1643_round2.py。
"""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
CID = 'e57d34fd-d636-45ed-b8aa-467e2fbf7adf'
GROUP_ID = '31d8cb2d-b349-4187-b7e0-d3f7cadc0d26'
DIM_ID = 121
ALGO = 'wire_test_param'
PG = ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
      '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test', '-t', '-A']


def call(path, method='GET', body=None, timeout=180):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, 'ERR'
    except Exception as e:
        return -1, str(e)


def sql(q):
    r = subprocess.run(PG + ['-c', q], capture_output=True, text=True, encoding='utf-8')
    return (r.stdout or '') + (r.stderr or '')


body = {
    'type': ALGO, 'name': '接线测试_参数算法', 'group_id': None, 'display_order': 99,
    'status': 'online', 'description': 'INT-1643 临时算法定义（run 结束删除）',
    'device_params': [], 'api_params': [],
    'case_params': [{
        'param_code': 'threshold', 'param_name': '接线测试阈值', 'label': '接线测试阈值',
        'param_type': 'number', 'required': False, 'default_value': '0.5', 'help_text': 'INT-1643',
        'ui_order': 0, 'hidden': False, 'scope': 'common', 'min_value': 0, 'max_value': 1,
        'step': 0.1, 'unit': None, 'annotation_code': None, 'field_path': 'threshold'}],
    'reference_params': [],
    'mappings': {'device': [], 'api': [], 'evaluation': []},
    'associated_dimensions': [{'dimension_id': DIM_ID, 'weight': 1, 'is_default': True}],
}
print('POST definitions', call('/algorithm/definitions', 'POST', body)[0])
s, d = call('/algorithm/options')
print('options', [a.get('value') for a in ((d or {}).get('data') or {}).get('algorithms', [])])
s, d = call('/algorithm/form-schema/' + ALGO)
print('form-schema', s, json.dumps(d, ensure_ascii=False)[:200])
s, d = call('/algorithm/definitions/' + ALGO)
print('detail', s, 'case_params', len(((d or {}).get('data') or {}).get('case_params') or []))

case_body = {
    'name': '接线测试_INT1643_参数',
    'description': 'INT-1643 算法参数两窗取证临时用例（run 结束删除）',
    'group_id': GROUP_ID, 'tags': [], 'algorithm_type': ALGO,
    'config': {'rounds': [
        {'round_number': 1, 'audios': [{'audio_id': 1395, 'audio_name': 'DD120_...silence_1.wav',
                                        'spl': 65.0, 'playback_device_id': 5,
                                        'playback_device_name': '设备正面（0.5m+0°）', 'play_order': 0}],
         'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': True},
        {'round_number': 2, 'audios': [{'audio_id': 1394, 'audio_name': 'DD120_...response_2.wav',
                                        'spl': 65.0, 'playback_device_id': 5,
                                        'playback_device_name': '设备正面（0.5m+0°）', 'play_order': 0}],
         'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': False},
    ], 'dimensions': []},
    'algorithm_params': [{'round_number': 1, 'params': [{'field_code': 'threshold', 'field_value': 0.5}]}],
    'reference_params': [],
}
s, d = call('/testcases', 'POST', case_body)
print('POST case', s, json.dumps(d, ensure_ascii=False)[:160] if not isinstance(d, str) else d)
cid = ((d or {}).get('data') or {}).get('id')
print('new case id', cid)

# reference_params 独立列（API PUT 会剥离，故直接 SQL 落到本夹具行）
bs = chr(92)
base = 'D:' + bs + '00_static' + bs + 'static' + bs + 'ref_params' + bs + (cid or CID) + bs
ref = [{'round_number': 1, 'reference_params_path': base + 'round_1.json'},
       {'round_number': 2, 'reference_params_path': base + 'round_2.json'}]
sql_q = "UPDATE test_cases SET reference_params='%s'::jsonb WHERE id='%s';" % (
    json.dumps(ref, ensure_ascii=False).replace("'", "''"), cid or CID)
print(sql(sql_q))
s, q = call('/testcases?page=1&per_page=5&keyword=' + urllib.parse.quote('接线测试_INT1643_参数'))
print('search', s, ((q or {}).get('data') or {}).get('total'))

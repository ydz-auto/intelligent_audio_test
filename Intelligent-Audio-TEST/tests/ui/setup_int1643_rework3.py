# -*- coding: utf-8 -*-
"""INT-1643 复核轮（打回第 2 次）造数：建 1 条临时用例，用于抽屉「参考参数」真实失败态 + 重试取证。

只建 1 条「接线测试_INT1643_重试」用例（分组「打断与恢复」，2 轮真实音频，algorithm_type=voice_llm），
再把它 reference_params 独立列指向不存在的文件路径 → 抽屉打开即 400「未找到第 1 轮」失败态。
收尾见 cleanup_int1643_rework3.py（软删 → purge → SQL 物理删）。
"""
import json
import subprocess
import urllib.error

import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
GROUP_ID = '31d8cb2d-b349-4187-b7e0-d3f7cadc0d26'
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


def audio(aid, name, order):
    return {'audio_id': aid, 'audio_name': name, 'spl': 65.0, 'playback_device_id': 5,
            'playback_device_name': '设备正面（0.5m+0°）', 'play_order': order}


body = {
    'name': '接线测试_INT1643_重试',
    'description': 'INT-1643 复核轮临时用例：抽屉参考参数失败态 + 重试取证（run 结束删除）',
    'group_id': GROUP_ID, 'tags': [], 'algorithm_type': 'voice_llm',
    'config': {'rounds': [
        {'round_number': 1, 'audios': [audio(1395, 'DD120_...silence_1.wav', 0)],
         'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': True},
        {'round_number': 2, 'audios': [audio(1394, 'DD120_...response_2.wav', 0)],
         'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': False},
    ], 'dimensions': []},
    'algorithm_params': [],
    'reference_params': [],
}
s, d = call('/testcases', 'POST', body)
print('POST case', s, json.dumps(d, ensure_ascii=False)[:200] if not isinstance(d, str) else d)
cid = ((d or {}).get('data') or {}).get('id') if isinstance(d, dict) else None
print('new case id', cid)
if not cid:
    raise SystemExit('create failed')

bs = chr(92)
base = 'D:' + bs + '00_static' + bs + 'static' + bs + 'ref_params' + bs + cid + bs
ref = [{'round_number': 1, 'reference_params_path': base + 'round_1.json'},
       {'round_number': 2, 'reference_params_path': base + 'round_2.json'}]
q = "UPDATE test_cases SET reference_params='%s'::jsonb WHERE id='%s';" % (
    json.dumps(ref, ensure_ascii=False).replace("'", "''"), cid)
print('sql', sql(q))

s, d = call('/testcases/' + cid)
item = (d or {}).get('data') if isinstance(d, dict) else None
print('detail', s, 'reference_params', json.dumps((item or {}).get('reference_params'), ensure_ascii=False)[:300])
for n in (1, 2):
    s2, d2 = call('/testcases/%s/rounds/%d/ref-params' % (cid, n))
    print('ref-params round', n, s2, json.dumps(d2, ensure_ascii=False)[:160])

s, d = call('/testcases?page=1&per_page=5&group_id=' + GROUP_ID)
names = [it['name'][:22] for it in (((d or {}).get('data') or {}).get('items') or [])]
print('group first rows', names)
print('CASE_ID=' + cid)

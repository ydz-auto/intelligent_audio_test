# -*- coding: utf-8 -*-
"""INT-1643 打回第 3 轮造数：2 轮临时用例（逐轮 round_dimensions 提交键运行时取证）。

建分组「接线测试_INT1643_维度组」+ 1 条 2 轮用例「接线测试_INT1643_逐轮维度2轮」，
两轮都用真实音频 id 1395 / 1394（只读引用，不改真实行），algorithm_type=voice_llm，
初始 config.dimensions / 各轮 evaluation.dimensions 全空。
收尾见 cleanup_int1643_perround.py（软删 → purge → SQL 物理删 → 分组 DELETE）。
"""
import json
import os
import urllib.error
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'artifacts', 'int1643', 'perround_fixture.json')

GROUP = '接线测试_INT1643_维度组'
CASE = '接线测试_INT1643_逐轮维度2轮'


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


def audio(aid, name, order):
    return {'audio_id': aid, 'audio_name': name, 'spl': 65.0, 'playback_device_id': 5,
            'playback_device_name': '设备正面（0.5m+0°）', 'play_order': order}


os.makedirs(os.path.dirname(OUT), exist_ok=True)

s, d = call('/groups', 'POST', {'name': GROUP, 'description': 'INT-1643 逐轮维度取证临时分组（run 结束删除）'})
gid = ((d or {}).get('data') or {}).get('id') if isinstance(d, dict) else None
print('POST group', s, 'gid', gid, json.dumps(d, ensure_ascii=False)[:200] if not isinstance(d, str) else d)
if not gid:
    # 复用已有同名分组（上一轮残留）
    s, d = call('/groups?per_page=200&page=1')
    items = (((d or {}).get('data') or {}).get('items')) or []
    gid = next((g['id'] for g in items if g.get('name') == GROUP), None)
    print('reuse group', gid)

body = {
    'name': CASE,
    'description': 'INT-1643 临时用例：批量评估维度逐轮设置 round_dimensions 提交键取证（run 结束删除）',
    'group_id': gid, 'tags': [], 'algorithm_type': 'voice_llm',
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
cid = ((d or {}).get('data') or {}).get('id') if isinstance(d, dict) else None
print('POST case', s, 'cid', cid, json.dumps(d, ensure_ascii=False)[:300] if not isinstance(d, str) else d)
if not cid:
    raise SystemExit('create failed')

s, d = call('/testcases/' + cid)
item = (d or {}).get('data') or {}
rounds = ((item.get('config') or {}).get('rounds')) or []
print('detail', s, 'rounds', len(rounds),
      [(r.get('round_number'), (r.get('evaluation') or {}).get('dimensions')) for r in rounds])

s, d = call('/testcases?page=1&per_page=20&group_id=' + gid)
rows = (((d or {}).get('data') or {}).get('items')) or []
print('group rows', s, [(it.get('name')[:30], it.get('id')) for it in rows])

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump({'group_id': gid, 'group_name': GROUP, 'case_id': cid, 'case_name': CASE,
               'rows': [{'id': it.get('id'), 'name': it.get('name')} for it in rows]},
              f, ensure_ascii=False, indent=1)
print('FIXTURE', OUT)
print('GROUP_ID=' + gid)
print('CASE_ID=' + cid)

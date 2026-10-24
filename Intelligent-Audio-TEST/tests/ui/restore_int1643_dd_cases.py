# -*- coding: utf-8 -*-
"""INT-1643 数据修复：批量「用例专属参数」（所有轮次统一）把 threshold 写进了同组两条真实用例
DD119 / DD120 的 algorithm_params，覆盖了原 voice_llm 参数。按同族未改动用例
（DD108/DD109/DD118：一次打断-停止指令打断，silence+response 两轮）的稳定口径 SQL 还原，
并回读确认（API GET + DB 轮数）。

原口径（同族 4 条一致）：
  round 1 (silence): record_mode=case, is_interruption="true", stop_intent="false",
                     type=" ", timing="silence", is_return_to_topic="false"
  round 2 (response): record_mode=case, is_interruption="0", stop_intent="true",
                      type=" ", timing="response", is_return_to_topic="false"
注：走 SQL 而非 PUT /testcases，避免 PUT 顺带剥离 reference_params 等其它列。
"""
import json
import subprocess
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
IDS = ['67c5b319-27fc-4087-a7c6-7932ca6c7f31', '213339c6-1176-4673-9c23-4d40c7b4f99f']  # DD119, DD120
PG = ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
      '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test', '-t', '-A']

RESTORED = [
    {'round_number': 2, 'params': [
        {'field_code': 'record_mode', 'field_value': 'case'},
        {'field_code': 'is_interruption', 'field_value': '0'},
        {'field_code': 'stop_intent', 'field_value': 'true'},
        {'field_code': 'type', 'field_value': ' '},
        {'field_code': 'timing', 'field_value': 'response'},
        {'field_code': 'is_return_to_topic', 'field_value': 'false'},
    ]},
    {'round_number': 1, 'params': [
        {'field_code': 'record_mode', 'field_value': 'case'},
        {'field_code': 'is_interruption', 'field_value': 'true'},
        {'field_code': 'stop_intent', 'field_value': 'false'},
        {'field_code': 'type', 'field_value': ' '},
        {'field_code': 'timing', 'field_value': 'silence'},
        {'field_code': 'is_return_to_topic', 'field_value': 'false'},
    ]},
]

sql = "UPDATE test_cases SET algorithm_params='%s'::jsonb WHERE id IN ('%s');" % (
    json.dumps(RESTORED, ensure_ascii=False).replace("'", "''"), "','".join(IDS))
r = subprocess.run(PG + ['-c', sql], capture_output=True, text=True, encoding='utf-8')
print('UPDATE:', (r.stdout or r.stderr).strip())

for cid in IDS:
    with urllib.request.urlopen(API + '/testcases/' + cid, timeout=120) as resp:
        item = json.loads(resp.read().decode('utf-8')).get('data') or {}
    print(cid, '->', json.dumps(item.get('algorithm_params'), ensure_ascii=False)[:200])
print('db rounds:', subprocess.run(
    PG + ['-c', "SELECT id, jsonb_array_length(algorithm_params::jsonb) FROM test_cases WHERE id IN ('%s');"
          % "','".join(IDS)], capture_output=True, text=True, encoding='utf-8').stdout.strip())

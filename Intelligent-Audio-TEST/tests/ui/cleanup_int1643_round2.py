# -*- coding: utf-8 -*-
"""INT-1643 run 收尾：清理本 run 自建的临时用例与临时算法定义，并回读确认零残留。

- 临时用例「接线测试_INT1643_参数」：DELETE /testcases/{id}（进回收站）→ DELETE /testcases/{id}/purge
- 临时算法定义 wire_test_param：DELETE /algorithm/definitions/{type}（软删）→ SQL 物理清
  algorithm_definitions / case_algorithm_params / algorithm_dimension_relations
- 回读：/algorithm/options 无 wire_test_param；keyword 搜索含 only_deleted 为空
"""
import json
import subprocess
import urllib.error
import urllib.request
import urllib.parse

API = 'http://127.0.0.1:15000/api/v1'
CID = 'e57d34fd-d636-45ed-b8aa-467e2fbf7adf'
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


print('== 用例软删 ==')
print(call('/testcases/' + CID, 'DELETE'))
print('== 用例彻底删除 ==')
print(call('/testcases/' + CID + '/purge', 'DELETE'))
print('== 算法定义删除（API）==')
print(call('/algorithm/definitions/' + ALGO, 'DELETE'))
print('== SQL 物理清理 ==')
print(sql("DELETE FROM case_algorithm_params WHERE algorithm_type='%s';" % ALGO))
print(sql("DELETE FROM algorithm_dimension_relations WHERE algorithm_type='%s';" % ALGO))
print(sql("DELETE FROM algorithm_definitions WHERE type='%s';" % ALGO))
print(sql("DELETE FROM test_cases WHERE id='%s';" % CID))
print('== 回读 ==')
s, d = call('/algorithm/options')
algos = [a.get('value') for a in ((d or {}).get('data') or {}).get('algorithms', [])] if isinstance(d, dict) else []
print('options', s, algos, 'wire_test_param present:', ALGO in algos)
q = urllib.parse.quote('接线测试_INT1643')
for extra in ('', '&only_deleted=1'):
    s, d = call('/testcases?page=1&per_page=5&keyword=' + q + extra)
    total = ((d or {}).get('data') or {}).get('total') if isinstance(d, dict) else None
    print('keyword search %s -> total %s (%s)' % (extra or 'default', total, s))
print('db defs:', sql("SELECT count(*) FROM algorithm_definitions WHERE type='%s';" % ALGO).strip())
print('db case_params:', sql("SELECT count(*) FROM case_algorithm_params WHERE algorithm_type='%s';" % ALGO).strip())
print('db case:', sql("SELECT count(*) FROM test_cases WHERE id='%s';" % CID).strip())
print('DD119/DD120 params:', sql(
    "SELECT id, jsonb_array_length(algorithm_params::jsonb) FROM test_cases "
    "WHERE id IN ('67c5b319-27fc-4087-a7c6-7932ca6c7f31','213339c6-1176-4673-9c23-4d40c7b4f99f');").strip())

# -*- coding: utf-8 -*-
"""INT-1643 复核轮收尾：清理本 run 临时用例「接线测试_INT1643_重试」并回读零残留。

软删 → purge → SQL 物理删；回读 keyword 搜索（含 only_deleted）与 DB 行数。
"""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
CID = 'fc624bfa-4c50-4706-9bd9-fcea9136f1a0'
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


print('== 用例软删 ==', call('/testcases/' + CID, 'DELETE'))
print('== 用例彻底删除 ==', call('/testcases/' + CID + '/purge', 'DELETE'))
print('== SQL 物理删 ==', sql("DELETE FROM test_cases WHERE id='%s';" % CID).strip())
q = urllib.parse.quote('接线测试_INT1643')
for extra in ('', '&only_deleted=1'):
    s, d = call('/testcases?page=1&per_page=5&keyword=' + q + extra)
    total = ((d or {}).get('data') or {}).get('total') if isinstance(d, dict) else None
    print('keyword%s -> total %s (%s)' % (extra or '', total, s))
print('db row:', sql("SELECT count(*) FROM test_cases WHERE id='%s';" % CID).strip())
print('db 接线测试_INT1643 前缀:', sql(
    "SELECT count(*) FROM test_cases WHERE name LIKE '接线测试_INT1643%';").strip())
s, d = call('/algorithm/options')
algos = [a.get('value') for a in ((d or {}).get('data') or {}).get('algorithms', [])]
print('algorithm options', algos)

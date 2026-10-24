# -*- coding: utf-8 -*-
"""INT-1643 打回第 3 轮收尾：清理逐轮维度取证临时用例/分组，回读零残留。

两条临时用例（2 轮 / 3 轮）软删 → purge → SQL 物理删（尽力；docker 命令超时不影响 API 结论），
两个临时分组 DELETE；最后 keyword 搜索（含 only_deleted=1）与分组列表回读。
"""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
CASES = [
    ('733075d3-505b-4239-83a1-de371ece841c', '接线测试_INT1643_逐轮维度2轮'),
    ('5f690b31-8663-4256-97f8-82f903639692', '接线测试_INT1643_逐轮维度3轮'),
]
GROUPS = [
    ('474478b4-2a58-439b-a573-621462a2643a', '接线测试_INT1643_维度组'),
    ('2321f178-9daf-49d8-9911-35f888761b23', '接线测试_INT1643_维度组3轮'),
]
PG = ['docker', 'exec', 'intelligent-audio-test-postgres-1', 'psql',
      '-U', 'intelligent_audio_test', '-d', 'intelligent_audio_test', '-t', '-A']


def call(path, method='GET', body=None, timeout=90):
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


def sql(q, timeout=40):
    try:
        r = subprocess.run(PG + ['-c', q], capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        return ((r.stdout or '') + (r.stderr or '')).strip()
    except Exception as e:
        return 'SQL_TIMEOUT_OR_ERR: %s' % str(e)[:120]


for cid, name in CASES:
    print('--', name, cid)
    print('  soft delete', call('/testcases/' + cid, 'DELETE')[0])
    print('  purge', call('/testcases/' + cid + '/purge', 'DELETE')[0])
    print('  sql delete', sql("DELETE FROM test_cases WHERE id='%s';" % cid))

for gid, gname in GROUPS:
    print('-- group', gname, gid, 'DELETE', call('/groups/' + gid, 'DELETE')[0])

q = urllib.parse.quote('接线测试_INT1643')
for extra in ('', '&only_deleted=1'):
    s, d = call('/testcases?page=1&per_page=5&keyword=' + q + extra)
    print('keyword%s -> total %s (%s)' % (extra or '', ((d or {}).get('data') or {}).get('total') if isinstance(d, dict) else None, s))

s, d = call('/groups?per_page=200&page=1')
left = [g['name'] for g in ((((d or {}).get('data') or {}).get('items')) or []) if '接线测试_INT1643' in (g.get('name') or '')]
print('leftover groups', left, '(%s)' % s)

s, d = call('/tags?per_page=200&page=1')
tl = [t['name'] for t in ((((d or {}).get('data') or {}).get('items')) or []) if '接线测试_INT1643' in (t.get('name') or '')]
print('leftover tags', tl, '(%s)' % s)

print('db rows 接线测试_INT1643%:', sql("SELECT count(*) FROM test_cases WHERE name LIKE '接线测试_INT1643%';"))
print('db groups:', sql("SELECT count(*) FROM test_case_groups WHERE name LIKE '接线测试_INT1643%';"))

# -*- coding: utf-8 -*-
"""INT-1780 验收夹具：两个「接线测试_INT1780_」分组 + 组 A 下 2 条用例。

用法：
  python verify_int1780_fixture.py create   # 打印 env 行（GRP_A_ID=.. 等）
  python verify_int1780_fixture.py cleanup  # 按前缀删除本卡残留（硬删：先 delete 再 purge）

写库纪律：只写「接线测试_」前缀数据，run 结束前清理。
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API = os.environ.get('API_BASE', 'http://localhost:15000').rstrip('/') + '/api/v1'
GRP_A = '接线测试_INT1780_A'
GRP_B = '接线测试_INT1780_B'
CASES = ['接线测试_INT1780_用例1', '接线测试_INT1780_用例2']


def call(method, path, body=None, timeout=60):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def find_group(name):
    st, d = call('GET', '/groups?page=1&pageSize=200')
    for it in ((d or {}).get('data') or {}).get('items') or []:
        if it.get('name') == name:
            return it['id']
    return None


def create():
    out = {}
    for key, name in (('GRP_A_ID', GRP_A), ('GRP_B_ID', GRP_B)):
        gid = find_group(name)
        if not gid:
            st, d = call('POST', '/groups', {'name': name, 'description': 'INT-1780 验收临时分组（run 后删除）',
                                             'algorithm_type': ''})
            if st not in (200, 201) or not (d or {}).get('success'):
                print('GROUP FAIL', name, st, d)
                return
            gid = str((d.get('data') or {}).get('id'))
        out[key] = gid
        print(f'{key}={gid}')

    ids = []
    st, d = call('GET', '/testcases?page=1&pageSize=200&group_id=' + out['GRP_A_ID'])
    existing = {it.get('name'): it['id'] for it in ((d or {}).get('data') or {}).get('items') or []}
    for i, name in enumerate(CASES, 1):
        if name in existing:
            ids.append(existing[name])
            continue
        st, d = call('POST', '/testcases', {
            'name': name, 'group_id': out['GRP_A_ID'], 'description': 'INT-1780 验收临时用例（run 后删除）',
            'type': 'api',
            'config': {'rounds': [{'round_number': 1, 'audios': [],
                                   'evaluation': {'dimension_ids': [], 'rule': ''},
                                   'devices': []}]},
        })
        if st not in (200, 201) or not (d or {}).get('success'):
            print('CASE FAIL', name, st, d)
            return
        ids.append(str((d.get('data') or {}).get('id')))
    print(f'CASE_1_ID={ids[0]}')
    print(f'CASE_2_ID={ids[1]}')


def cleanup():
    st, d = call('GET', '/testcases?page=1&pageSize=200&status=trash')
    trash = ((d or {}).get('data') or {}).get('items') or []
    for name in CASES:
        for it in trash:
            if it.get('name') == name:
                s2, r2 = call('DELETE', '/testcases/' + str(it['id']) + '/purge')
                print('PURGE trash', name, s2, r2 if s2 >= 400 else '')
    gids = []
    for name in (GRP_A, GRP_B):
        st, d = call('GET', '/testcases?page=1&pageSize=200')
        for it in ((d or {}).get('data') or {}).get('items') or []:
            if it.get('name') in CASES:
                s2, r2 = call('DELETE', '/testcases/' + str(it['id']))
                print('DELETE case', it.get('name'), s2)
        gid = find_group(name)
        if gid:
            s3, r3 = call('DELETE', '/groups/' + gid)
            print('DELETE group', name, s3, '' if s3 < 400 else r3)
            gids.append(gid)
    # 再清一次：软删用例的 purge
    for name in CASES:
        st, d = call('GET', '/testcases?page=1&pageSize=200&status=trash')
        for it in ((d or {}).get('data') or {}).get('items') or []:
            if it.get('name') == name:
                call('DELETE', '/testcases/' + str(it['id']) + '/purge')
    st, d = call('GET', '/testcases?page=1&pageSize=200')
    left = [it.get('name') for it in ((d or {}).get('data') or {}).get('items') or [] if it.get('name') in CASES]
    print('残留用例:', left)
    print('残留分组:', [n for n in (GRP_A, GRP_B) if find_group(n)])


if __name__ == '__main__':
    {'create': create, 'cleanup': cleanup}[sys.argv[1]]()

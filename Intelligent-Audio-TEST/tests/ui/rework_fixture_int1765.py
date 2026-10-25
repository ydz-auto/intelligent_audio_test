# -*- coding: utf-8 -*-
"""INT-1765 返工 R1 复测夹具：用真实接口重建 A/B 任务与增量包变体。

链路：真实任务 321 → 整包导出/导入得 A → 再导出/导入得 B → B「导出增量」得目标为 A 的 1.1 包。
变体：坏 ZIP / 整包(1.0) / 源任务不存在(404) / caseSetHash 篡改(409) / dimension_id=null(500)。
"""
import json
import os
import sys
import time

import requests

BASE = 'http://localhost:15000/api/v1'
OUT = r'D:/00_user_data/int1765_rw_work'
SRC_TASK = 321
os.makedirs(OUT, exist_ok=True)


def log(msg):
    print(msg, flush=True)


def full_export(tid, path):
    r = requests.post(f'{BASE}/data-transfer/export',
                      json={'taskIds': [tid], 'includeRefParams': True, 'includeAudios': False},
                      timeout=600)
    log(f'export task {tid} -> {r.status_code} {len(r.content)}B')
    assert r.status_code == 200, r.text[:400]
    with open(path, 'wb') as f:
        f.write(r.content)


def post_zip(url, path, label):
    t0 = time.time()
    with open(path, 'rb') as f:
        r = requests.post(url, files={'file': (os.path.basename(path), f, 'application/zip')}, timeout=1800)
    log(f'{label} -> {r.status_code} ({time.time() - t0:.1f}s)')
    return r


def full_import(path):
    r = post_zip(f'{BASE}/data-transfer/import', path, f'import {os.path.basename(path)}')
    body = r.json()
    assert r.status_code == 200 and body.get('success'), json.dumps(body, ensure_ascii=False)[:600]
    return body['data']


def inc_export(tid, path):
    r = requests.post(f'{BASE}/data-transfer/export-incremental',
                      json={'taskIds': [tid], 'include': ['dimensions', 'reports']}, timeout=600)
    log(f'export-incremental task {tid} -> {r.status_code} {len(r.content)}B')
    assert r.status_code == 200, r.text[:400]
    with open(path, 'wb') as f:
        f.write(r.content)


def rewrite(src, dst, manifest_fn=None, dims_fn=None):
    import zipfile
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'manifest.json' and manifest_fn:
                m = json.loads(data.decode('utf-8'))
                manifest_fn(m)
                data = json.dumps(m, ensure_ascii=False).encode('utf-8')
            elif item.filename == 'db/test_result_dimensions.json' and dims_fn:
                rows = json.loads(data.decode('utf-8'))
                dims_fn(rows)
                data = json.dumps(rows, ensure_ascii=False).encode('utf-8')
            zout.writestr(item.filename, data)


if __name__ == '__main__':
    log(f'source task {SRC_TASK}: ' + json.dumps(
        (requests.get(f'{BASE}/tasks/{SRC_TASK}', timeout=60).json().get('data') or {}).get('name'),
        ensure_ascii=False))

    a_src = os.path.join(OUT, f'A_from_{SRC_TASK}.zip')
    full_export(SRC_TASK, a_src)
    d1 = full_import(a_src)
    A = int(d1['remappedIds']['tasks'][str(SRC_TASK)])
    log(f'A task id = {A}')

    a_full = os.path.join(OUT, f'full_from_A{A}.zip')
    full_export(A, a_full)
    d2 = full_import(a_full)
    B = int(d2['remappedIds']['tasks'][str(A)])
    log(f'B task id = {B}')

    inc = os.path.join(OUT, f'inc_target_A{A}.zip')
    inc_export(B, inc)
    import zipfile
    with zipfile.ZipFile(inc) as z:
        man = json.loads(z.read('manifest.json').decode('utf-8'))
    log('inc manifest: ' + json.dumps({k: man.get(k) for k in ('version', 'sourceTask', 'tasks', 'stats')},
                                      ensure_ascii=False)[:700])
    assert man['tasks'][0]['id'] == A, f"增量包目标不是 A: {man['tasks']}"

    # 变体 1：维度行 dimension_id=null → 执行期 500 并回滚
    def null_dim(rows):
        rows[0]['dimension_id'] = None

    rewrite(inc, os.path.join(OUT, 'bad_dim_null.zip'), dims_fn=null_dim)

    # 变体 2：caseSetHash 篡改 → 前置校验 409（未写入）
    def bad_hash(m):
        m['sourceTask']['caseSetHash'] = '0' * 64

    rewrite(inc, os.path.join(OUT, 'bad_casehash.zip'), manifest_fn=bad_hash)

    # 变体 3：目标任务不存在 → 404（未写入）；预检也应显示「本侧未找到」
    def missing_task(m):
        m['tasks'][0]['id'] = 9999999

    rewrite(inc, os.path.join(OUT, 'bad_missing_task.zip'), manifest_fn=missing_task)

    # 变体 4：非 ZIP（预检 400 静默问题 F1）
    with open(os.path.join(OUT, 'bad_nonzip.zip'), 'wb') as f:
        f.write('这不是一个 ZIP 包（INT-1765 返工复测夹具）'.encode('utf-8'))

    # 变体 5：整包（1.0）放进增量入口
    wrong_ver = os.path.join(OUT, 'whole_v10.zip')
    with open(a_src, 'rb') as fi, open(wrong_ver, 'wb') as fo:
        fo.write(fi.read())

    fixture = {'A': A, 'B': B, 'source': SRC_TASK}
    with open(os.path.join(OUT, 'fixture.json'), 'w', encoding='utf-8') as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1)
    log('fixture: ' + json.dumps(fixture))
    log('packages: ' + ', '.join(sorted(os.path.basename(p) for p in
                                        ['bad_dim_null.zip', 'bad_casehash.zip', 'bad_missing_task.zip',
                                         'bad_nonzip.zip', 'whole_v10.zip', os.path.basename(inc)])))

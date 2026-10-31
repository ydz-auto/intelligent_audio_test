# -*- coding: utf-8 -*-
"""INT-2174 走查（React 用例域增量）—— 导入/导出/重复策略/异常态 API 实测。

覆盖卡面第 3（导出范围条数，API 侧）、4（ZIP 数据包导出 + 重新导入回读）、
5（模板表头）、6（导入预览行级错误 + 仅合法行落库）、7（重复策略 skip/overwrite/copy）、
8（空文件/大文件/非模板格式）、11（导入后分组计数）项。

环境：docker 网关 http://localhost:15000（/health database 必须是 intelligent_audio_test），
前端页面的交互证据见 verify_int2174_ui_*.py。夹具前缀「接线测试_走查R2_<run>_」，run 结束按
落盘 id 软删 + purge，最后回读确认为 0。

用法：
    python verify_int2174_transfer_api.py [--run r2a]
输出：
    tests/ui/artifacts/int2174_transfer/report.json + 证据文件（解压清单/模板/导出包）
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

import _int2174_lib as L

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int2174_transfer')
RESULTS = []
CLEANUP_IDS = {'cases': [], 'groups': [], 'tags': []}
RUN = 'r2a'
PREFIX = f'{L.PREFIX}{RUN}_'


def record(item, name, ok, detail, evidence=None):
    RESULTS.append({'item': item, 'check': name, 'pass': bool(ok),
                    'detail': detail, 'evidence': evidence})
    print(('[PASS] ' if ok else '[FAIL] ') + f'{item} {name} :: {detail}')
    return ok


def health(tag):
    st, r = L.req('GET', 'http://localhost:15000/health')
    db = (r or {}).get('database') if isinstance(r, dict) else None
    st2, d = L.req('GET', '/testcases?page=1&per_page=1')
    total = None
    try:
        total = (L.data(_auth_get('/testcases?page=1&per_page=1')) or {}).get('total')
    except Exception:
        pass
    print(f'[health:{tag}] status={st} database={db} testcases_total={total}')
    return {'tag': tag, 'status': st, 'database': db, 'testcases_total': total}


def _auth_get(path):
    st, r = L.req('GET', path, token=TOKEN)
    return r


def cleanup(token):
    # 先按本 run 唯一前缀收口（含 copy/导入产生、未登记进 CLEANUP_IDS 的用例），再删登记 id
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    for i in d.get('items') or []:
        if (i.get('name') or '').startswith(PREFIX) and i['id'] not in CLEANUP_IDS['cases']:
            CLEANUP_IDS['cases'].append(i['id'])
    for cid in CLEANUP_IDS['cases']:
        try:
            L.delete_case_hard(token, cid)
        except Exception as e:
            print('case cleanup warn', cid, e)
    for gid in CLEANUP_IDS['groups']:
        try:
            L.delete_group(token, gid)
        except Exception as e:
            print('group cleanup warn', gid, e)
    for tid in CLEANUP_IDS['tags']:
        try:
            L.delete_tag(token, tid)
        except Exception as e:
            print('tag cleanup warn', tid, e)
    # 回读：本 run 前缀在「含已删」里也不应有残留
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    left = [(i['id'], i['name']) for i in (d.get('items') or []) if (i.get('name') or '').startswith(PREFIX)]
    groups_left = [g['name'] for g in L.list_groups(token) if (g.get('name') or '').startswith(PREFIX)]
    tags_left = [t['name'] for t in L.list_tags(token) if (t.get('name') or '').startswith(PREFIX)]
    print('[cleanup] leftover cases', left, 'groups', groups_left, 'tags', tags_left)
    return {'cases': left, 'groups': groups_left, 'tags': tags_left}


def csv_bytes(rows, header='用例名称,描述,分组,标签,raw_config'):
    out = [header]
    for r in rows:
        out.append(','.join('"' + str(v).replace('"', '""') + '"' for v in r))
    return ('\n'.join(out) + '\n').encode('utf-8')


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='r2a')
    args = ap.parse_args()
    global RUN, PREFIX
    RUN = args.run
    PREFIX = f'{L.PREFIX}{RUN}_'
    os.makedirs(ARTIFACTS, exist_ok=True)

    tok, err = L.login()
    assert tok, f'登录失败: {err}'
    TOKEN = tok
    globals()['TOKEN'] = tok

    health_checks = [health('start')]
    total_before = health_checks[0]['testcases_total']

    # ---------------- 夹具 ----------------
    gname = PREFIX + '分组'
    gid = L.create_group(TOKEN, gname)
    CLEANUP_IDS['groups'].append(gid)
    tag1 = L.create_tag(TOKEN, PREFIX + '标签1', '#3b82f6')
    tag2 = L.create_tag(TOKEN, PREFIX + '标签2', '#f59e0b')
    CLEANUP_IDS['tags'] += [tag1, tag2]
    audios = L.find_audio(TOKEN)
    audio = audios[0]
    dim_id, dim_name = 72, '测试维度占位'
    try:
        st, r = L.req('GET', '/evaluation/dimensions?page=1&per_page=1', token=TOKEN)
        item = ((L.data(r) or {}).get('items') or [{}])[0]
        dim_id, dim_name = item.get('id', dim_id), item.get('name', dim_name)
    except Exception:
        pass

    def mkcase(suffix, with_audio=True, ref=None, tags=None):
        cfg = L.case_config(audio['id'], audio['name'], dim_id, dim_name) if with_audio else {'rounds': []}
        cid = L.create_case(TOKEN, PREFIX + suffix, group_id=gid, config=cfg, tags=tags)
        CLEANUP_IDS['cases'].append(cid)
        if ref is not None:
            st, d = L.update_ref_params(TOKEN, cid, 1, ref)
            print('ref params', suffix, st, json.dumps(d, ensure_ascii=False)[:160])
        return cid

    ref_payload = [{'asr_reference_text': '识别参考A', 'round': 1}]
    cidA = mkcase('用例A', ref=ref_payload, tags=[PREFIX + '标签1'])
    cidB = mkcase('用例B')
    cidC = mkcase('用例C', with_audio=False)
    time.sleep(1.0)
    st, dA = L.get_case(TOKEN, cidA)
    st, dB = L.get_case(TOKEN, cidB)
    print('fixture A config rounds', json.dumps((dA.get('config') or {}).get('rounds'), ensure_ascii=False)[:300])
    print('fixture A reference_params', dA.get('reference_params'))

    # ---------------- 5 模板下载 / 表头 ----------------
    st, headers, blob = L.template(TOKEN)
    tpl_path = os.path.join(ARTIFACTS, 'testcase_template.xlsx')
    with open(tpl_path, 'wb') as f:
        f.write(blob)
    tpl_headers = {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(blob))
        for ws in wb.worksheets:
            tpl_headers[ws.title] = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    except Exception as e:
        print('template parse warn', e)
    need = {'TestCases': ['NAME', 'GROUP_NAME', 'TEST_TYPE', 'TAGS'],
            'AudioConfigs': ['CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL', 'PLAY_ORDER'],
            'Dimensions': ['CASE_NAME', 'DIMENSION_NAME', 'WEIGHT', 'THRESHOLD'],
            'Tags': ['TAG_NAME'], 'Groups': ['GROUP_NAME'], 'CaseTags': ['CASE_NAME', 'TAG_NAME']}
    header_ok = st == 200 and blob[:2] == b'PK' and all(
        all(col in tpl_headers.get(sheet, []) for col in cols) for sheet, cols in need.items())
    record(5, '模板下载 GET /testcases/template/download',
           header_ok,
           f'status={st} size={len(blob)} ctype={headers.get("Content-Type")} '
           f'disposition={headers.get("Content-Disposition")} sheets={ {k: len(v) for k, v in tpl_headers.items()} } '
           f'表头={json.dumps(tpl_headers, ensure_ascii=False)}',
           'testcase_template.xlsx')

    # ---------------- 3 导出范围条数（API 侧） ----------------
    gcases = [i for i in (L.list_cases(TOKEN, group_id=gid)[1].get('items') or [])]
    gids = [c['id'] for c in gcases]
    st, h, zblob = L.export(TOKEN, gids, 'zip')
    zpath = os.path.join(ARTIFACTS, 'export_group.zip')
    with open(zpath, 'wb') as f:
        f.write(zblob)
    zcount = None
    znames = []
    manifest = {}
    if st == 200 and zblob[:2] == b'PK':
        zf = zipfile.ZipFile(io.BytesIO(zblob))
        znames = zf.namelist()
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        zcount = len(json.loads(zf.read('testcases.json').decode('utf-8'))['test_cases'])
    record(3, '导出范围=当前筛选（本卡分组）预览与实际一致',
           zcount == len(gids) == 3,
           f'分组内用例={len(gids)} 导出 ZIP testcases.json={zcount} manifest.total_count={manifest.get("total_count")}',
           'export_group.zip')
    # 全量：API total 与 UI 预览条数比（UI 侧另行核对）；这里记录后端真实 total
    st, d = L.req('GET', '/testcases?page=1&per_page=1', token=TOKEN)
    total_now = (L.data(d) or {}).get('total')
    record(3, '导出范围=全量 后端 total 取值',
           isinstance(total_now, int) and total_now >= 3,
           f'GET /testcases total={total_now}', None)
    # 仅已选：两个 id 导出
    st, h, zblob2 = L.export(TOKEN, [cidA, cidB], 'zip')
    zc2 = None
    if st == 200 and zblob2[:2] == b'PK':
        zf = zipfile.ZipFile(io.BytesIO(zblob2))
        zc2 = len(json.loads(zf.read('testcases.json').decode('utf-8'))['test_cases'])
    record(3, '导出范围=仅已选 2 条', zc2 == 2, f'导出 ZIP 内用例={zc2}', None)

    # ---------------- 4 ZIP 结构与重新导入回读 ----------------
    st, h, zblob = L.export(TOKEN, [cidA, cidB], 'zip', include_reference_params=True)
    zip_bytes = zblob
    zf = zipfile.ZipFile(io.BytesIO(zblob))
    names = zf.namelist()
    doc = json.loads(zf.read('testcases.json').decode('utf-8'))
    man = json.loads(zf.read('manifest.json').decode('utf-8'))
    caseA = next(c for c in doc['test_cases'] if c['name'] == PREFIX + '用例A')
    ref_files = [n for n in names if n.startswith('reference_params/')]
    structure = {
        'files': names,
        'sizes': {n: len(zf.read(n)) for n in names},
        'manifest': man,
        'caseA': {
            'name': caseA['name'], 'group': caseA['group'], 'group_id': caseA['group_id'],
            'audios': caseA.get('audios'), 'dimensions': caseA.get('dimensions'),
            'tags': caseA.get('tags'), 'reference_params': caseA.get('reference_params'),
            'reference_param_files': caseA.get('reference_param_files'),
        },
        'audio_files_in_zip': [n for n in names if n.lower().endswith(('.wav', '.mp3', '.flac'))],
    }
    with open(os.path.join(ARTIFACTS, 'zip_structure.json'), 'w', encoding='utf-8') as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)
    audio_entries = [a for a in (caseA.get('audios') or [])]
    record(4, 'ZIP 解压结构（manifest + testcases.json + 参考参数文件）',
           st == 200 and 'manifest.json' in names and 'testcases.json' in names
           and man.get('total_count') == 2 and len(ref_files) >= 1
           and bool(audio_entries) and all(len(zf.read(n)) > 0 for n in names),
           f'files={names} sizes={structure["sizes"]} manifest.total_count={man.get("total_count")} '
           f'reference_param_file_count={man.get("reference_param_file_count")} '
           f'用例A音频={json.dumps(audio_entries, ensure_ascii=False)[:200]} '
           f'包内 wav/mp3/flac={structure["audio_files_in_zip"]}',
           'zip_structure.json')
    # 卡面口径「音频附件在包内」：当前实现只带 audio_id/audio_name 引用，不打包音频二进制
    record(4, 'ZIP 包内含音频附件文件（卡面口径）',
           bool(structure['audio_files_in_zip']),
           f'包内文件仅 {names}；音频以 audio_id/audio_name 引用（{json.dumps(audio_entries, ensure_ascii=False)[:120]}），'
           f'未见 wav/mp3/flac 文件',
           'zip_structure.json')

    # 删除夹具后重新导入 ZIP（skip）
    for cid in (cidA, cidB):
        L.delete_case_hard(TOKEN, cid)
        CLEANUP_IDS['cases'].remove(cid)
    time.sleep(0.5)
    st, r = L.do_import(TOKEN, zip_bytes, 'export_group.zip', 'skip')
    d = L.data(r) or {}
    time.sleep(1.0)
    stA, dA2 = L.get_case(TOKEN, cidA)  # 被删的 id 应 404/不可见
    instA = L.find_case_by_name(TOKEN, PREFIX + '用例A')
    instB = L.find_case_by_name(TOKEN, PREFIX + '用例B')
    for c in (instA, instB):
        if c:
            CLEANUP_IDS['cases'].append(c['id'])
    detA = L.get_case(TOKEN, instA['id'])[1] if instA else {}
    got_audios = (detA.get('config') or {}).get('rounds', [{}])[0].get('audios') if detA else None
    record(4, 'ZIP 重新导入（skip）回读字段一致',
           st == 200 and d.get('imported_count') == 2 and bool(instA) and bool(instB)
           and detA.get('group_name') == gname
           and bool(got_audios) and got_audios[0].get('audio_id') == audio['id']
           and [t.get('name') if isinstance(t, dict) else t for t in (detA.get('tags') or [])] == [PREFIX + '标签1']
           and bool(detA.get('reference_params')),
           f'POST /testcases/import status={st} added={d.get("imported_count")} errors={d.get("errors")} '
           f'回读用例A group={detA.get("group_name")} audios={json.dumps(got_audios, ensure_ascii=False)[:150]} '
           f'tags={detA.get("tags")} reference_params={json.dumps(detA.get("reference_params"), ensure_ascii=False)[:150]}',
           None)

    # ---------------- 7 重复策略 ----------------
    st, r = L.do_import(TOKEN, zip_bytes, 'export_group.zip', 'skip')
    d = L.data(r) or {}
    record(7, '重复策略 skip：同文件再导入', st == 200 and d.get('skipped_count') == 2 and d.get('imported_count') == 0,
           f'status={st} skipped={d.get("skipped_count")} imported={d.get("imported_count")} updated={d.get("updated_count")}', None)

    # 改包内描述后 overwrite
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    doc2 = json.loads(zf.read('testcases.json').decode('utf-8'))
    for c in doc2['test_cases']:
        c['description'] = 'INT-2174 覆盖后描述'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(man, ensure_ascii=False))
        z.writestr('testcases.json', json.dumps(doc2, ensure_ascii=False, default=str))
    ov_bytes = buf.getvalue()
    st, r = L.do_import(TOKEN, ov_bytes, 'export_overwrite.zip', 'overwrite')
    d = L.data(r) or {}
    time.sleep(1.0)
    detA = L.get_case(TOKEN, instA['id'])[1]
    record(7, '重复策略 overwrite：字段被文件覆盖',
           st == 200 and d.get('updated_count') == 2 and detA.get('description') == 'INT-2174 覆盖后描述'
           and L.get_case(TOKEN, instA['id'])[1]['id'] == instA['id'],
           f'status={st} updated={d.get("updated_count")} 回读 id={detA.get("id")} description={detA.get("description")}', None)

    st, r = L.do_import(TOKEN, zip_bytes, 'export_group.zip', 'copy')
    d = L.data(r) or {}
    time.sleep(1.0)
    st_list, dl = L.list_cases(TOKEN, keyword=PREFIX + '用例A')
    copy_row = next((i for i in dl.get('items') or [] if (i.get('name') or '').endswith('_copy')), None)
    if copy_row:
        CLEANUP_IDS['cases'].append(copy_row['id'])
    st_b, dcopy = L.get_case(TOKEN, copy_row['id']) if copy_row else (None, {})
    copies = [i['name'] for i in dl.get('items') or [] if (i.get('name') or '').endswith('_copy')]
    record(7, '重复策略 copy：另存副本 _copy',
           st == 200 and d.get('copied_count') == 2 and bool(copy_row)
           and dcopy.get('description') == 'INT-2174 走查夹具',
           f'status={st} copied={d.get("copied_count")} 副本={copies} 回读desc={dcopy.get("description")}', None)

    # ---------------- 6 行级校验错误 + 仅合法行落库 ----------------
    gname2 = PREFIX + '行级组'
    rows = [
        [PREFIX + '行级合法1', 'd1', gname2, '', ''],
        ['', '缺名行', gname2, '', ''],
        [PREFIX + '行级合法2', 'd2', gname2, '', ''],
        ['', '缺名行2', gname2, '', ''],
    ]
    bad_csv = csv_bytes(rows)
    with open(os.path.join(ARTIFACTS, 'import_rows_with_errors.csv'), 'wb') as f:
        f.write(bad_csv)
    st, r = L.import_preview(TOKEN, bad_csv, 'rows_with_errors.csv')
    d = L.data(r) or {}
    errs = d.get('errors') or []
    preview_ok = (st == 200 and d.get('totalRows') == 4 and len(errs) == 2
                  and errs[0] == '第2行: 用例名称不能为空' and errs[1] == '第4行: 用例名称不能为空')
    with open(os.path.join(ARTIFACTS, 'import_preview_errors.json'), 'w', encoding='utf-8') as f:
        json.dump({'file': rows, 'preview': d}, f, ensure_ascii=False, indent=2)
    record(6, '预览逐行错误（行号 + 原因）',
           preview_ok, f'status={st} totalRows={d.get("totalRows")} errors={errs}',
           'import_preview_errors.json')
    st, r = L.do_import(TOKEN, bad_csv, 'rows_with_errors.csv', 'skip')
    d = L.data(r) or {}
    time.sleep(1.0)
    stl, dl = L.list_cases(TOKEN, keyword=PREFIX + '行级')
    got = sorted(i['name'] for i in dl.get('items') or [] if (i.get('name') or '').startswith(PREFIX + '行级'))
    for i in dl.get('items') or []:
        if (i['name'] or '').startswith(PREFIX + '行级'):
            CLEANUP_IDS['cases'].append(i['id'])
    grp2 = next((g for g in L.list_groups(TOKEN) if g['name'] == gname2), None)
    if grp2:
        CLEANUP_IDS['groups'].append(grp2['id'])
    record(6, '导入后只落合法行（错误行不入库）',
           st == 200 and d.get('imported_count') == 2 and len(d.get('errors') or []) == 2
           and got == [PREFIX + '行级合法1', PREFIX + '行级合法2'],
           f'status={st} imported={d.get("imported_count")} errors={d.get("errors")} 回读={got}', None)

    # 6b 类型错误行（JSON 非字符串 name）：预览是否逐行报出（INT-2155「按导入同一口径逐行校验」）
    gname3 = PREFIX + '类型组'
    typed_rows = [
        {'name': PREFIX + '类型合法', 'group': gname3},
        {'name': {'bad': 1}, 'group': gname3},
        {'name': 12345, 'group': gname3},
    ]
    typed_json = json.dumps({'test_cases': typed_rows}, ensure_ascii=False).encode('utf-8')
    st, r = L.import_preview(TOKEN, typed_json, 'typed.json')
    typed_errors = (L.data(r) or {}).get('errors') or []
    st2, r2 = L.do_import(TOKEN, typed_json, 'typed.json', 'skip')
    typed_receipt_errors = (L.data(r2) or {}).get('errors') or []
    with open(os.path.join(ARTIFACTS, 'import_preview_type_errors.json'), 'w', encoding='utf-8') as f:
        json.dump({'rows': typed_rows, 'preview_errors': typed_errors,
                   'import_receipt_errors': typed_receipt_errors,
                   'import_receipt': L.data(r2)}, f, ensure_ascii=False, indent=2)
    record(6, '预览对「类型错误」行同样给出行级错误（与导入回执一致）',
           len(typed_errors) == 2 and len(typed_receipt_errors) == 2,
           f'预览 errors={typed_errors}；导入回执 errors={typed_receipt_errors} '
           f'（预览漏报第2/3行，导入时才失败）',
           'import_preview_type_errors.json')
    st, dl = L.list_cases(TOKEN, keyword=PREFIX + '类型')
    for i in dl.get('items') or []:
        if (i.get('name') or '').startswith(PREFIX + '类型'):
            CLEANUP_IDS['cases'].append(i['id'])
    grp3 = next((g for g in L.list_groups(TOKEN) if g['name'] == gname3), None)
    if grp3:
        CLEANUP_IDS['groups'].append(grp3['id'])

    # ---------------- 8 异常态 ----------------
    cases = [
        ('空文件 empty.csv', L.import_preview(TOKEN, b'', 'empty.csv'), 'csv'),
        ('非模板格式 x.txt', L.import_preview(TOKEN, b'hello', 'x.txt'), 'txt'),
        ('损坏 ZIP', L.import_preview(TOKEN, b'not-a-zip', 'x.zip'), 'zip'),
        ('ZIP 缺 testcases.json', L.import_preview(TOKEN, (lambda: (lambda b: (zipfile.ZipFile(b, 'w').writestr('manifest.json', '{}'), b.getvalue())[1])(io.BytesIO()))(), 'y.zip'), 'zip'),
    ]
    for label, (st, r), kind in cases:
        msg = (r or {}).get('message') if isinstance(r, dict) else str(r)
        record(8, f'异常态：{label}', st == 400 and bool(msg),
               f'status={st} message={msg}', None)
    # 大文件（600 行，超过预览重复扫描 500 上限；预览不落库）
    big_rows = [[f'{PREFIX}大文件{i:04d}', 'd' * 40, PREFIX + '大文件组', '', ''] for i in range(600)]
    big_csv = csv_bytes(big_rows)
    t0 = time.time()
    st, r = L.import_preview(TOKEN, big_csv, 'big.csv')
    dt = time.time() - t0
    d = L.data(r) or {}
    record(8, '异常态：大文件（600 行，预览不落库）',
           st == 200 and d.get('totalRows') == 600 and d.get('duplicateScanTruncated') is True,
           f'status={st} size={len(big_csv)}B totalRows={d.get("totalRows")} '
           f'duplicateScanTruncated={d.get("duplicateScanTruncated")} 耗时={dt:.1f}s', None)
    st, dl = L.list_cases(TOKEN, keyword=PREFIX + '大文件')
    created_big = (dl.get('total') or 0)
    record(8, '异常态后未产生半截数据', created_big == 0,
           f'GET /testcases?keyword={PREFIX}大文件 total={created_big}', None)

    # ---------------- 11 分组计数同步（导入后） ----------------
    grp_rows = [[PREFIX + '计数1', 'd', gname2, '', ''], [PREFIX + '计数2', 'd', gname2, '', '']]
    csv2 = csv_bytes(grp_rows)
    st, r = L.do_import(TOKEN, csv2, 'count.csv', 'skip')
    time.sleep(1.5)
    grp = next((g for g in L.list_groups(TOKEN) if g['name'] == gname2), None)
    stl, dl = L.list_cases(TOKEN, group_id=(grp or {}).get('id') if grp else None)
    for i in dl.get('items') or []:
        CLEANUP_IDS['cases'].append(i['id'])
    record(11, '导入后分组计数与组内用例一致',
           bool(grp) and (grp.get('test_case_count') or 0) == (dl.get('total') or 0) == 4,
           f'GET /groups {gname2}.test_case_count={grp.get("test_case_count") if grp else None} '
           f'GET /testcases?group_id total={dl.get("total")}', None)

    # 中间核对
    health_checks.append(health('before-delivery'))

    # ---------------- 清理 ----------------
    leftover = cleanup(TOKEN)
    record('cleanup', '本 run 夹具清理干净',
           not leftover['cases'] and not leftover['groups'] and not leftover['tags'],
           json.dumps(leftover, ensure_ascii=False), None)

    # 交付前核对
    health_checks.append(health('after-cleanup'))
    passed = sum(1 for x in RESULTS if x['pass'])
    summary = {'run': RUN, 'passed': passed, 'total': len(RESULTS),
               'health': health_checks, 'results': RESULTS, 'leftover': leftover}
    with open(os.path.join(ARTIFACTS, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f'\n==== {passed}/{len(RESULTS)} passed ====')
    print(json.dumps(health_checks, ensure_ascii=False))


if __name__ == '__main__':
    main()

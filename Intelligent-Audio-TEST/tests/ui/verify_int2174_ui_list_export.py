# -*- coding: utf-8 -*-
"""INT-2174 走查（React 用例域增量）—— 列表/分组搜索命中/导出范围条数/模板直达/导入预览 UI 实测。

覆盖卡面第 1（三视图 + 分组计数）、2（INT-2154 分组视图搜索命中）、3（导出范围条数预览
vs 实际下载条数）、5（导入弹窗模板直达）、6（导入预览行级错误 UI + 仍导入其余 N 条）、
11（导入后列表/分组计数刷新）项。ZIP 结构/重复策略/异常态/抽屉/批量见
verify_int2174_transfer_api.py 与 verify_int2174_mutate_batch.py。

环境：前端 http://localhost:15173（容器 iat-react-frontend）、后端 http://localhost:15000。
夹具前缀「接线测试_走查R2_<run>_」，按落盘 id 与唯一前缀清理。

用法：python verify_int2174_ui_list_export.py --run ui-a
输出：tests/ui/artifacts/int2174_ui/report_list.json + *.png + 下载文件
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

import _int2174_lib as L
import _int2174_ui as U
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

RESULTS = []
CLEANUP = {'cases': [], 'groups': [], 'tags': []}
RUN = 'ui-a'
PREFIX = f'{L.PREFIX}{RUN}_'
DL = os.path.join(U.ARTIFACTS, 'downloads')


def record(item, name, ok, detail, evidence=None):
    RESULTS.append({'item': item, 'check': name, 'pass': bool(ok), 'detail': detail, 'evidence': evidence})
    print(('[PASS] ' if ok else '[FAIL] ') + f'{item} {name} :: {detail}')
    return ok


def health(tag, token):
    st, r = L.req('GET', 'http://localhost:15000/health')
    db = (r or {}).get('database') if isinstance(r, dict) else None
    st2, d = L.req('GET', '/testcases?page=1&per_page=1', token=token)
    total = (L.data(d) or {}).get('total')
    print(f'[health:{tag}] status={st} database={db} total={total}')
    return {'tag': tag, 'status': st, 'database': db, 'total': total}


def cleanup(token):
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    for i in d.get('items') or []:
        if (i.get('name') or '').startswith(PREFIX) and i['id'] not in CLEANUP['cases']:
            CLEANUP['cases'].append(i['id'])
    for cid in CLEANUP['cases']:
        try:
            L.delete_case_hard(token, cid)
        except Exception as e:
            print('case cleanup warn', cid, e)
    for gid in CLEANUP['groups']:
        try:
            L.delete_group(token, gid)
        except Exception as e:
            print('group cleanup warn', gid, e)
    for tid in CLEANUP['tags']:
        try:
            L.delete_tag(token, tid)
        except Exception as e:
            print('tag cleanup warn', tid, e)
    st, d = L.list_cases(token, keyword=PREFIX, include_deleted='true')
    left = [i['name'] for i in d.get('items') or [] if (i.get('name') or '').startswith(PREFIX)]
    groups_left = [g['name'] for g in L.list_groups(token) if (g.get('name') or '').startswith(PREFIX)]
    return {'cases': left, 'groups': groups_left}


def api_total(token, **params):
    qs = '/testcases?page=1&per_page=1'
    for k, v in params.items():
        qs += f'&{k}={quote(str(v))}'
    st, r = L.req('GET', qs, token=token)
    return (L.data(r) or {}).get('total')


def download_count(path):
    """返回 (文件名, 内用例条数/或 JSON 条数, 结构说明)。"""
    name = os.path.basename(path)
    if name.endswith('.zip'):
        zf = zipfile.ZipFile(path)
        doc = json.loads(zf.read('testcases.json').decode('utf-8'))
        return name, len(doc['test_cases']), {'files': zf.namelist(),
                                              'manifest': json.loads(zf.read('manifest.json').decode('utf-8'))}
    if name.endswith('.json'):
        doc = json.load(open(path, encoding='utf-8'))
        cases = (doc.get('data') or {}).get('test_cases') if isinstance(doc.get('data'), dict) else doc.get('test_cases')
        if cases is None and isinstance(doc.get('data'), list):
            cases = doc['data']
        return name, len(cases or []), {'keys': list(doc.keys())}
    return name, None, {}


def load_more_until(drv, needle, max_clicks=8):
    """点「加载更多」直到文字出现（分组/标签视图均为每页 5 个）。"""
    for _ in range(max_clicks):
        if needle in U.body(drv):
            return True
        btns = drv.find_elements(By.XPATH, "//button[contains(., '加载更多')]")
        if not btns:
            break
        U.js_click(drv, btns[0])
        time.sleep(1.4)
    return needle in U.body(drv)


def open_export(drv):
    U.click_xpath(drv, "//button[normalize-space(.)='导出']")
    WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '导出用例')]"))


def export_preview_text(drv):
    dlg = U.find_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]")
    return dlg.text


def do_export(drv, scope='filter', fmt='ZIP 数据包（推荐）', timeout=300):
    """在导出弹窗内选范围/格式并下载，返回下载文件路径。"""
    dlg = U.find_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]")
    if scope == 'selected':
        U.js_click(drv, dlg.find_element(By.XPATH, ".//label[contains(., '仅导出已选')]/input"))
    else:
        U.js_click(drv, dlg.find_element(By.XPATH, ".//label[contains(., '按当前筛选条件导出')]/input"))
    time.sleep(0.8)
    if fmt != 'ZIP 数据包（推荐）':
        U.js_click(drv, dlg.find_element(By.XPATH, ".//button[contains(., 'ZIP 数据包')]"))
        time.sleep(0.4)
        U.click_xpath(drv, f"//*[@role='option'][contains(., '{fmt}')]")
        time.sleep(0.3)
    before = set(os.listdir(DL))
    U.click_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]//button[contains(., '开始导出')]")
    path = U.wait_download(DL, before, timeout=timeout)
    time.sleep(0.5)
    return path


def open_cases(drv):
    """进用例管理（等分组列表渲染完成，慢时最多 60s）。"""
    U.goto(drv, '/testcases/by-group')
    U.wait_text(drv, '用例管理', 60)
    WebDriverWait(drv, 60).until(lambda d: '个分组' in U.body(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='ui-a')
    args = ap.parse_args()
    global RUN, PREFIX
    RUN = args.run
    PREFIX = f'{L.PREFIX}{RUN}_'
    os.makedirs(U.ARTIFACTS, exist_ok=True)

    tok, err = L.login()
    assert tok, err
    TOKEN = tok
    health_checks = [health('start', tok)]
    total_before = health_checks[0]['total']

    # ---------------- 夹具 ----------------
    g1 = PREFIX + '分组一'
    g2 = PREFIX + '分组二'
    gid1 = L.create_group(tok, g1)
    gid2 = L.create_group(tok, g2)
    CLEANUP['groups'] += [gid1, gid2]
    tag = L.create_tag(tok, PREFIX + '标签', '#3b82f6')
    CLEANUP['tags'].append(tag)
    audio = L.find_audio(tok)[0]
    names1 = [PREFIX + '搜索A', PREFIX + '搜索B', PREFIX + '其他C']
    cids = {}
    for nm in names1:
        cids[nm] = L.create_case(tok, nm, group_id=gid1,
                                 config=L.case_config(audio['id'], audio['name']),
                                 tags=[PREFIX + '标签'])
    cids[PREFIX + '搜索D'] = L.create_case(tok, PREFIX + '搜索D', group_id=gid2,
                                           config=L.case_config(audio['id'], audio['name']),
                                           tags=[PREFIX + '标签'])
    CLEANUP['cases'] += list(cids.values())
    time.sleep(1.0)
    api_g1 = api_total(tok, group_id=gid1)
    api_g2 = api_total(tok, group_id=gid2)
    print('fixture', {'g1': api_g1, 'g2': api_g2, 'cases': list(cids)})

    # 行级错误文件（合法 2 + 缺名 2）
    g3 = PREFIX + '导入组'
    err_rows = [PREFIX + '合法1', '', PREFIX + '合法2', '']
    lines = ['用例名称,描述,分组'] + [f'"{v}","d","{g3}"' for v in err_rows]
    bad_csv_path = os.path.join(U.ARTIFACTS, 'import_rows_with_errors.csv')
    with open(bad_csv_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    drv = U.make_driver(DL)
    try:
        U.login(drv)
        U.drain_perf(drv)
        open_cases(drv)

        # ---------------- 1 三个视图 + 分组计数 ----------------
        load_more_until(drv, g2)
        hdr1 = f"//span[normalize-space(.)='{g1}']/ancestor::div[contains(@class,'cursor-pointer')][1]"
        hdr2 = f"//span[normalize-space(.)='{g2}']/ancestor::div[contains(@class,'cursor-pointer')][1]"
        U.find_xpath(drv, f"//span[normalize-space(.)='{g1}']", timeout=20)
        body = U.body(drv)
        g1_text = U.find_xpath(drv, hdr1).text
        g2_text = U.find_xpath(drv, hdr2).text
        count1_ok = f'{api_g1} 条' in g1_text
        count2_ok = f'{api_g2} 条' in g2_text
        record(1, '分组视图：分组计数与 GET /testcases 一致',
               count1_ok and count2_ok and api_g1 == 3 and api_g2 == 1,
               f'{g1} 接口 group_id total={api_g1} 组头文本={g1_text!r}；'
               f'{g2} total={api_g2} 组头文本={g2_text!r}',
               U.shot(drv, '01-group-view-light.png'))
        # 展开分组一，组内 3 行可见
        U.js_click(drv, U.find_xpath(drv, hdr1))
        U.wait_text(drv, names1[0], timeout=15)
        rows_ok = all(n in U.body(drv) for n in names1)
        record(1, '分组视图：展开组内用例可见', rows_ok, f'展开「{g1}」后三行可见={rows_ok}', None)
        # 标签视图
        U.click_xpath(drv, "//button[@role='tab' and contains(., '按标签')]")
        U.wait_text(drv, '个标签', timeout=20)
        load_more_until(drv, PREFIX + '标签')
        U.js_click(drv, U.find_xpath(
            drv, f"//span[normalize-space(.)='{PREFIX}标签']/ancestor::div[contains(@class,'cursor-pointer')][1]", timeout=10))
        time.sleep(1.2)
        tagview_ok = PREFIX + '标签' in U.body(drv) and names1[0] in U.body(drv)
        record(1, '标签视图：按标签聚合可见本卡标签与用例', tagview_ok,
               f'标签「{PREFIX}标签」与用例「{names1[0]}」同时可见={tagview_ok}',
               U.shot(drv, '02-tag-view-light.png'))
        # 回到分组视图
        U.click_xpath(drv, "//button[@role='tab' and contains(., '按分组')]")
        U.wait_text(drv, '个分组', timeout=20)
        load_more_until(drv, g1)

        # ---------------- 2 分组视图搜索命中 ----------------
        search = U.find_xpath(drv, "//input[@aria-label='搜索用例']")
        U.set_input(drv, search, PREFIX + '搜索')
        U.wait_text(drv, '命中', timeout=25)
        time.sleep(1.5)
        body = U.body(drv)
        api_hits = api_total(tok, keyword=PREFIX + '搜索')
        hit_summary = f'命中{api_hits}' in body.replace(' ', '') or f'命中 {api_hits}' in body
        g1_hit = f'命中 2 条' in body
        g2_hit = f'命中 1 条' in body
        hit_ok = api_hits == 3 and hit_summary and g1_hit and g2_hit
        record(2, '搜索命中：汇总/组头命中数与接口一致',
               hit_ok,
               f'GET /testcases?keyword={PREFIX}搜索 total={api_hits}；命中汇总={hit_summary} '
               f'组一「命中 2 条」={g1_hit} 组二「命中 1 条」={g2_hit}',
               U.shot(drv, '03-group-search-hits-light.png'))
        # 展开命中分组，命中项可见、未命中项不可见
        U.js_click(drv, U.find_xpath(drv, hdr1))
        time.sleep(1.2)
        body = U.body(drv)
        hit_rows_ok = (names1[0] in body and names1[1] in body and names1[2] not in body)
        record(2, '搜索命中：展开分组后仅命中项可见（未命中项隐藏）',
               hit_rows_ok,
               f'用例A可见={names1[0] in body} 用例B可见={names1[1] in body} 未命中C可见={names1[2] in body}',
               U.shot(drv, '04-group-search-expanded-light.png'))
        # 清空搜索恢复全量
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
        time.sleep(1.8)
        load_more_until(drv, g1)
        # 搜索态展开过的分组清空后仍保持展开；仅当行不可见时才点组头
        if names1[2] not in U.body(drv):
            U.js_click(drv, U.find_xpath(drv, hdr1))
        time.sleep(1.5)
        body = U.body(drv)
        restored = names1[2] in body and f'{api_g1} 条' in body
        record(2, '清空搜索：恢复分组全量与全量计数',
               restored,
               f'清空后未命中用例C可见={names1[2] in body} 组一计数「{api_g1} 条」={f"{api_g1} 条" in body}',
               U.shot(drv, '05-group-search-cleared-light.png'))

        # ---------------- 3 导出范围条数预览 vs 实际下载 ----------------
        # (a) 按当前筛选（无筛选=全量）：预览条数 = GET total
        U.drain_perf(drv)
        open_export(drv)
        time.sleep(1.0)
        txt = export_preview_text(drv)
        # 等统计结束（「正在统计」消失）
        WebDriverWait(drv, 60).until(lambda d: '正在统计' not in export_preview_text(d))
        txt = export_preview_text(drv)
        api_all = api_total(tok)
        import re
        mm = re.search(r'将导出\s*(\d+)\s*条用例', txt.replace('\n', ' '))
        pre_all = int(mm.group(1)) if mm else None
        record(3, '导出范围=全量：预览条数 = GET /testcases total',
               pre_all is not None and pre_all == api_all,
               f'弹窗预览={pre_all} 接口 total={api_all}', U.shot(drv, '06-export-dialog-all-light.png'))
        # 实际下载：本环境（15173 nginx 反代 15000，默认 proxy_read_timeout=60s）对 580+ 条
        # 的 ZIP 导出会在 60s 被 504 掐断；记录真实结果，再用 API 直连导出核对后端条数。
        U.drain_perf(drv)
        export_ui_ok = True
        try:
            path_all = do_export(drv, 'filter', timeout=75)
            name_all, n_all, info_all = download_count(path_all)
            record(3, '导出范围=全量：实际下载条数 = 预览条数',
                   n_all == pre_all,
                   f'{name_all} 内用例={n_all} 预览={pre_all} manifest={json.dumps(info_all.get("manifest"), ensure_ascii=False)}',
                   U.shot(drv, '07-export-done-all-light.png'))
            os.replace(path_all, os.path.join(U.ARTIFACTS, 'export_all.zip'))
            export_ui_ok = n_all == pre_all
        except TimeoutError:
            perf = U.drain_perf(drv)
            ex = [r for r in perf if '/testcases/export' in (r.get('url') or '')]
            toast_txt = U.body(drv)
            record(3, '导出范围=全量：实际下载条数 = 预览条数', False,
                   f'UI 下载超时；POST /testcases/export 状态={[(r["method"], r["status"]) for r in ex]}；'
                   f'页面出现「导出失败」={"导出失败" in toast_txt}（错误文案为空=HTML 504 不可解析）',
                   U.shot(drv, '07-export-all-504.png'))
            export_ui_ok = False
            try:
                U.click_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]//button[normalize-space(.)='取消']")
            except Exception:
                pass
        # API 直连（绕开 nginx）核对后端全量导出条数；共享栈并发繁忙时可能超时，降级为提示
        try:
            ids_all = []
            page = 1
            while True:
                st, r = L.req('GET', f'/testcases?page={page}&per_page=200', token=tok)
                d = L.data(r) or {}
                ids_all += [i['id'] for i in d.get('items') or []]
                if page >= (d.get('pages') or 1):
                    break
                page += 1
            st, h, blob_all = L.export(tok, ids_all, 'zip')
            n_api = None
            if st == 200 and blob_all[:2] == b'PK':
                zf = zipfile.ZipFile(io.BytesIO(blob_all))
                n_api = len(json.loads(zf.read('testcases.json').decode('utf-8'))['test_cases'])
                with open(os.path.join(U.ARTIFACTS, 'export_all_api.zip'), 'wb') as f:
                    f.write(blob_all)
            record(3, '后端全量导出条数 = 预览条数（API 直连，排除前端代理超时）',
                   n_api == pre_all,
                   f'POST /testcases/export(API) status={st} ids={len(ids_all)} ZIP内用例={n_api} 预览={pre_all}', None)
        except Exception as e:
            print('API 直连全量导出未完成（并发负载/超时，不计失败）:', type(e).__name__, e)

        # (b) 按当前筛选（搜索「搜索」命中 3 条，跨 2 分组）
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), PREFIX + '搜索')
        U.wait_text(drv, '命中', timeout=25)
        time.sleep(1.5)
        open_export(drv)
        WebDriverWait(drv, 60).until(lambda d: '正在统计' not in export_preview_text(d))
        txt = export_preview_text(drv)
        mm = re.search(r'将导出\s*(\d+)\s*条用例', txt.replace('\n', ' '))
        pre_filter = int(mm.group(1)) if mm else None
        api_filter = api_total(tok, keyword=PREFIX + '搜索')
        record(3, '导出范围=当前筛选：预览条数 = 接口命中数',
               pre_filter is not None and pre_filter == api_filter == 3,
               f'弹窗预览={pre_filter} 接口 total={api_filter}', U.shot(drv, '08-export-dialog-filter-light.png'))
        path_f = do_export(drv, 'filter')
        name_f, n_f, info_f = download_count(path_f)
        record(3, '导出范围=当前筛选：实际下载条数 = 预览条数',
               n_f == pre_filter,
               f'{name_f} 内用例={n_f} 预览={pre_filter}', None)
        os.replace(path_f, os.path.join(U.ARTIFACTS, 'export_filter.zip'))

        # (c) 仅已选：清空搜索后勾选 2 条
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
        time.sleep(1.8)
        U.click_xpath(drv, "//button[@role='tab' and contains(., '按分组')]")
        U.wait_text(drv, '个分组', timeout=20)
        load_more_until(drv, g1)
        if names1[0] not in U.body(drv):
            U.js_click(drv, U.find_xpath(drv, hdr1))
        U.wait_text(drv, names1[0], timeout=15)
        for nm in names1[:2]:
            cb = U.find_xpath(drv, f"//*[@role='checkbox'][@aria-label='选择 {nm}']", timeout=15)
            U.js_click(drv, cb)
            time.sleep(0.5)
        U.wait_text(drv, '已选择 2', timeout=10)
        open_export(drv)
        U.js_click(drv, U.find_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]//label[contains(., '仅导出已选')]/input"))
        WebDriverWait(drv, 10).until(lambda d: '条已选用例' in export_preview_text(d))
        txt = export_preview_text(drv)
        record(3, '导出范围=仅已选：弹窗显示 2 条已选',
               '2 条已选用例' in txt.replace('\n', ' ').replace('  ', ' '), f'弹窗文本片段={txt.replace(chr(10), " | ")[:200]}',
               U.shot(drv, '09-export-dialog-selected-light.png'))
        path_s = do_export(drv, 'selected')
        name_s, n_s, info_s = download_count(path_s)
        record(3, '导出范围=仅已选：实际下载条数 = 2',
               n_s == 2, f'{name_s} 内用例={n_s}', None)
        os.replace(path_s, os.path.join(U.ARTIFACTS, 'export_selected.zip'))
        # 取消勾选（清理页面状态）
        for nm in names1[:2]:
            try:
                U.js_click(drv, U.find_xpath(drv, f"//*[@role='checkbox'][@aria-label='选择 {nm}']", timeout=5))
                time.sleep(0.3)
            except Exception:
                pass

        # ---------------- 5 导入弹窗模板直达 ----------------
        U.drain_perf(drv)
        U.click_xpath(drv, "//button[normalize-space(.)='导入用例']")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '导入用例')]"))
        before = set(os.listdir(DL))
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]//button[contains(., '下载 Excel 模板')]")
        tpl = U.wait_download(DL, before, timeout=60)
        import openpyxl
        wb = openpyxl.load_workbook(tpl)
        tpl_sheets = {ws.title: [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))] for ws in wb.worksheets}
        tpl_ok = (os.path.basename(tpl).endswith('.xlsx') and os.path.getsize(tpl) > 0
                  and 'TestCases' in tpl_sheets
                  and all(col in tpl_sheets['TestCases'] for col in ('NAME', 'GROUP_NAME', 'TAGS')))
        perf = U.drain_perf(drv)
        tpl_req = [r for r in perf if '/testcases/template/download' in (r.get('url') or '')]
        record(5, '导入弹窗「下载 Excel 模板」可点、文件可打开、表头与导入字段一致',
               tpl_ok and bool(tpl_req) and tpl_req[0].get('status') == 200,
               f'文件={os.path.basename(tpl)} size={os.path.getsize(tpl)} sheets={list(tpl_sheets)} '
               f'TestCases表头前5={tpl_sheets.get("TestCases", [])[:5]} '
               f'网络={[(r["method"], r["url"], r["status"]) for r in tpl_req]}',
               U.shot(drv, '10-import-dialog-template-light.png'))
        tpl_kept = os.path.join(U.ARTIFACTS, 'template_from_dialog.xlsx')
        if os.path.exists(tpl_kept):
            os.remove(tpl_kept)
        os.replace(tpl, tpl_kept)

        # ---------------- 6 导入预览行级错误 + 仍导入其余 N 条 ----------------
        inp = U.find_xpath(drv, "//input[@aria-label='选择导入文件']")
        drv.execute_script("arguments[0].style.display='block';arguments[0].style.opacity='1';arguments[0].style.height='1px';arguments[0].style.width='1px';", inp)
        inp.send_keys(bad_csv_path)
        U.wait_text(drv, '未通过校验', timeout=30)
        time.sleep(1.0)
        dlg_text = U.find_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]").text
        err_line_ok = '第2行' in dlg_text and '第4行' in dlg_text and '用例名称不能为空' in dlg_text
        btn_ok = '仍导入其余 2 条' in dlg_text
        record(6, '导入预览：逐行显示行号与错误原因 + 「仍导入其余 N 条」',
               err_line_ok and btn_ok,
               f'弹窗含第2行/第4行错误={err_line_ok} 主钮「仍导入其余 2 条」={btn_ok}；'
               f'片段={dlg_text.replace(chr(10), " | ")[:400]}',
               U.shot(drv, '11-import-preview-errors-light.png'))
        before_import = api_total(tok, keyword=PREFIX + '合法')
        api_pre_import = api_total(tok)
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]//button[contains(., '仍导入其余 2 条')]")
        WebDriverWait(drv, 40).until(lambda d: all(
            k in U.find_xpath(d, "//*[@role='dialog'][contains(., '导入用例')]").text
            for k in ('覆盖', '跳过', '副本')))
        time.sleep(0.8)
        done_text = U.find_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]").text
        record(6, '导入回执：新增 2 条',
               '新增' in done_text and '2' in done_text,
               f'回执={done_text.replace(chr(10), " | ")[:200]}', U.shot(drv, '12-import-done-light.png'))
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]//button[normalize-space(.)='完成']")
        time.sleep(2.0)
        st, dl = L.list_cases(tok, keyword=PREFIX + '合法')
        imported = sorted(i['name'] for i in dl.get('items') or [] if i.get('name', '').startswith(PREFIX + '合法'))
        for i in dl.get('items') or []:
            if (i.get('name') or '').startswith(PREFIX + '合法'):
                CLEANUP['cases'].append(i['id'])
        grp3 = next((g for g in L.list_groups(tok) if g['name'] == g3), None)
        if grp3:
            CLEANUP['groups'].append(grp3['id'])
        record(6, '导入后回读：仅合法 2 条落库，错误行未落库',
               imported == [PREFIX + '合法1', PREFIX + '合法2'] and before_import == 0,
               f'GET /testcases?keyword={PREFIX}合法 回读={imported}', None)

        # ---------------- 11 导入后列表/分组计数刷新 ----------------
        time.sleep(1.5)
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), PREFIX + '合法')
        U.wait_text(drv, '命中', timeout=25)
        time.sleep(1.8)
        grp_count = None
        try:
            hdr3 = U.find_xpath(drv, f"//span[normalize-space(.)='{g3}']/ancestor::div[contains(@class,'cursor-pointer')][1]")
            tx = hdr3.text
            grp_count = '命中 2 条' in tx
            if PREFIX + '合法1' not in U.body(drv):
                U.js_click(drv, hdr3)
                time.sleep(1.2)
        except Exception as e:
            print('导入组展开 warn', e)
        time.sleep(1.2)
        body = U.body(drv)
        refresh_ok = (PREFIX + '合法1' in body) and (PREFIX + '合法2' in body)
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
        time.sleep(1.5)
        api_after = api_total(tok)
        record(11, '导入后列表可见新用例（搜索回读）且分组计数/总数同步',
               refresh_ok and grp_count and api_after == api_pre_import + 2,
               f'搜索「{PREFIX}合法」两行可见={refresh_ok}；导入组「命中 2 条」={grp_count}；'
               f'GET total {api_pre_import}→{api_after}（应 +2）',
               U.shot(drv, '13-list-after-import-light.png'))

        # ---------------- 深色截图（导出/导入弹窗同源） ----------------
        U.set_theme(drv, True)
        open_cases(drv)
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), PREFIX + '搜索')
        U.wait_text(drv, '命中', timeout=25)
        time.sleep(1.5)
        U.shot(drv, '14-group-search-hits-dark.png')
        open_export(drv)
        WebDriverWait(drv, 60).until(lambda d: '正在统计' not in export_preview_text(d))
        U.shot(drv, '15-export-dialog-dark.png')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '导出用例')]//button[normalize-space(.)='取消']")
        time.sleep(0.5)
        U.set_input(drv, U.find_xpath(drv, "//input[@aria-label='搜索用例']"), '')
        time.sleep(1.5)
        U.click_xpath(drv, "//button[normalize-space(.)='导入用例']")
        WebDriverWait(drv, 10).until(lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '导入用例')]"))
        inp = U.find_xpath(drv, "//input[@aria-label='选择导入文件']")
        drv.execute_script("arguments[0].style.display='block';arguments[0].style.opacity='1';arguments[0].style.height='1px';arguments[0].style.width='1px';", inp)
        inp.send_keys(bad_csv_path)
        U.wait_text(drv, '未通过校验', timeout=30)
        time.sleep(1.0)
        U.shot(drv, '16-import-preview-errors-dark.png')
        U.click_xpath(drv, "//*[@role='dialog'][contains(., '导入用例')]//button[normalize-space(.)='取消']")
        U.set_theme(drv, False)

        health_checks.append(health('before-delivery', tok))
    except Exception as e:
        import traceback
        traceback.print_exc()
        record('run', 'UI 实测异常中断', False, repr(e))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    # 清理（先按前缀收口）
    leftover = cleanup(tok)
    record('cleanup', '本 run 夹具清理干净',
           not leftover['cases'] and not leftover['groups'], json.dumps(leftover, ensure_ascii=False))
    health_checks.append(health('after-cleanup', tok))

    passed = sum(1 for r in RESULTS if r['pass'])
    report = {'run': RUN, 'passed': passed, 'total': len(RESULTS), 'health': health_checks,
              'results': RESULTS, 'leftover': leftover}
    with open(os.path.join(U.ARTIFACTS, 'report_list.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n==== {passed}/{len(RESULTS)} passed ====')
    print(json.dumps(health_checks, ensure_ascii=False))


def _preview_count(drv):
    return export_preview_text(drv)


if __name__ == '__main__':
    main()

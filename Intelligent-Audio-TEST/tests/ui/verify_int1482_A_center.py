# -*- coding: utf-8 -*-
"""INT-1482 批次A：报告中心弹窗组深走（生成/进度/导出/导出历史/对比/重命名/发布/删除确认）+ 浅深截图。

数据纪律：只操作自建「接线测试_」报告（对比生成），实测后软删+彻底删除；真实报告只读。
"""
import atexit
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

STAMP = time.strftime('%H%M%S')
OUT = {}


def save():
    try:
        with open(os.path.join(L.ART, 'batchA_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
    except Exception:
        pass


atexit.register(save)


def section(name, fn):
    try:
        fn()
        OUT[name + '_ok'] = True
    except Exception:
        OUT[name + '_error'] = traceback.format_exc()[-1200:]
    save()


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def rtext(el):
    return (el.get_attribute('textContent') or '').strip()


def wait_rows(d, timeout=60):
    WebDriverWait(d, timeout).until(lambda x: len(rows(x)) > 0)
    return rows(d)


def row_action(d, idx, item_text, wait=1.2):
    r = rows(d)[idx]
    btn = r.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
    L.js_click(d, btn)
    time.sleep(0.8)
    menu = [m for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if m.is_displayed()]
    for m in menu:
        if (m.text or '').strip() == item_text:
            L.js_click(d, m)
            time.sleep(wait)
            return True
    raise AssertionError('菜单项缺失 %s，现有 %s' % (item_text, [m.text for m in menu]))


def find_row_by_id(d, rid):
    for i, tr in enumerate(rows(d)):
        if ('#%s' % rid) in rtext(tr):
            return i
    return None


def req_log(d, contains=None, since=0):
    out = []
    for e in L.fetch_log(d, since):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody', 'error')})
    return out


def dlg_texts(d):
    return [x['text'][:400] for x in L.dialogs(d)]


def open_center(d):
    d.get(L.BASE + '/report-center')
    wait_rows(d, 60)
    time.sleep(1.5)


def main():
    d = L.driver()
    try:
        L.login(d)
        open_center(d)
        OUT['center_rows'] = len(rows(d))
        OUT['center_first'] = rtext(rows(d)[0])[:160]
        OUT['counts'] = req_log(d, '/reports/tab-counts')[-1:]
        OUT['list_req'] = [r for r in req_log(d, '/reports?')][-1:]
        L.shot(d, '01_report_center_light')

        # ---------- 1 生成报告 ----------
        def gen():
            L.reset_fetch_log(d)
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            time.sleep(2.5)
            OUT['gen_text'] = dl.text[:400]
            L.shot(d, '02_generate_light')
            OUT['gen_tasks_req'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in req_log(d, '/tasks')]
            opts = dl.find_elements(By.CSS_SELECTOR, 'ul li button')
            OUT['gen_task_options'] = len(opts)
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告'][-1]
            OUT['gen_submit_disabled_no_task'] = sub.get_attribute('disabled')
            # 空态筛选
            inp = dl.find_element(By.CSS_SELECTOR, "input[placeholder='搜索任务名称或ID']")
            inp.send_keys('不存在的任务ZZZ')
            time.sleep(0.7)
            OUT['gen_filter_empty'] = len(dl.find_elements(By.CSS_SELECTOR, 'ul li button'))
            OUT['gen_empty_state'] = '暂无已完成任务' in dl.text
            L.shot(d, '02b_generate_empty_light')
            inp.send_keys(Keys.CONTROL, 'a')
            inp.send_keys(Keys.DELETE)
            time.sleep(0.7)
            # 选「拒识多轮E2E测试任务 #397」（1 用例 1 设备，无既有报告）
            inp.send_keys('397')
            time.sleep(0.8)
            opts = dl.find_elements(By.CSS_SELECTOR, 'ul li button')
            if not opts:
                raise AssertionError('任务选择器为空')
            L.js_click(d, opts[0])
            time.sleep(0.4)
            OUT['gen_selected'] = rtext(opts[0])[:120]
            nm = dl.find_element(By.ID, 'report-name')
            nm.clear(); nm.send_keys('接线测试_报告_%s' % STAMP)
            dl.find_element(By.ID, 'report-desc').send_keys('INT-1482 深走查生成，run 结束前清理')
            L.reset_fetch_log(d)
            sub = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告'][-1]
            OUT['gen_submit_disabled_after'] = sub.get_attribute('disabled')
            L.js_click(d, sub)
            time.sleep(5)
            OUT['gen_reqs'] = req_log(d, '/reports/generate-task')
            OUT['gen_dialogs_after_submit'] = dlg_texts(d)
            L.shot(d, '03_progress_light')
            # 观察进度 60s
            seen = []
            for i in range(12):
                time.sleep(5)
                t = ' | '.join(dlg_texts(d)) or d.current_url
                seen.append(t[:200])
                if '/report/' in d.current_url:
                    break
            OUT['gen_progress_timeline'] = seen[-4:]
            OUT['gen_final_url'] = d.current_url
            L.shot(d, '03b_progress_after_wait_light')
            m = d.current_url.rsplit('/report/', 1)
            if len(m) == 2:
                OUT['gen_report_id'] = m[1].split('?')[0]
            # 关闭进度弹窗（错误态观察）
            OUT['gen_dialog_final_text'] = dlg_texts(d)
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('generate', gen)

        # ---------- 2 导出报告 ----------
        open_center(d)

        def export():
            L.reset_fetch_log(d)
            L.js_click(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
            time.sleep(0.8)
            for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if m.is_displayed() and '导出' in (m.text or ''):
                    L.js_click(d, m)
                    break
            dl = L.wait_dialog(d, '导出报告')
            time.sleep(1.2)
            OUT['export_text'] = dl.text[:500]
            L.shot(d, '04_export_light')
            trig = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            OUT['export_combo_n'] = len(trig)
            L.js_click(d, trig[0])
            time.sleep(0.8)
            OUT['export_format_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
            for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (i.text or '').strip() == 'Excel':
                    L.js_click(d, i)
                    break
            time.sleep(0.5)
            L.reset_fetch_log(d)
            btn = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '导出']
            L.js_click(d, btn[-1])
            time.sleep(1.0)
            L.shot(d, '05_export_progress_light')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '导出历史':
                    L.js_click(d, t)
                    time.sleep(1)
                    break
            time.sleep(6)
            dl2 = L.wait_dialog(d, '导出报告')
            OUT['export_history_text'] = dl2.text[:700]
            L.shot(d, '06_export_history_light')
            OUT['export_reqs'] = req_log(d, '/reports/export')
            dl_dir = os.path.join(L.ART, 'downloads')
            OUT['downloads'] = sorted(os.listdir(dl_dir)) if os.path.isdir(dl_dir) else []
            # 取消 / 重开是否残留
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
            OUT['export_closed_esc'] = len([x for x in L.dialogs(d)]) == 0
            L.js_click(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
            time.sleep(0.7)
            for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if m.is_displayed() and '导出' in (m.text or ''):
                    L.js_click(d, m)
                    break
            dl3 = L.wait_dialog(d, '导出报告')
            time.sleep(1)
            OUT['export_reopen_tab'] = [t.get_attribute('aria-selected') for t in dl3.find_elements(By.CSS_SELECTOR, "[role='tab']")]
            OUT['export_reopen_progress_residue'] = '完成' in dl3.text or '%' in dl3.text
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('export', export)

        # ---------- 3 报告对比（基于任务 → 同步生成自建报告） ----------
        report_id = None

        def compare():
            nonlocal report_id
            open_center(d)
            L.reset_fetch_log(d)
            L.click_text(d, '生成报告')  # 先验证取消路径由既有 evidence 覆盖，此处不做
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
            rr = rows(d)
            picked = []
            for idx in range(min(4, len(rr))):
                cbs = rows(d)[idx].find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                if cbs:
                    L.js_click(d, cbs[0]); time.sleep(0.4)
                    picked.append(rtext(rows(d)[idx])[:50])
                if len(picked) >= 2:
                    break
            OUT['compare_picked_reports'] = picked
            time.sleep(0.8)
            L.click_text(d, '批量对比')
            dl = L.wait_dialog(d, '报告对比')
            time.sleep(1.2)
            OUT['compare_text_task_tab'] = dl.text[:400]
            L.shot(d, '07_compare_light')
            # 切到对比配置
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '对比配置':
                    L.js_click(d, t); time.sleep(0.8); break
            dl = L.wait_dialog(d, '报告对比')
            cfg = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
            OUT['compare_config_combos'] = len(cfg)
            if cfg:
                L.js_click(d, cfg[0]); time.sleep(0.7)
                OUT['compare_dim_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
                d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(0.4)
            OUT['compare_metrics'] = [b.text for b in dl.find_elements(By.CSS_SELECTOR, "button[aria-pressed]")]
            OUT['compare_name_prefill'] = dl.find_element(By.ID, 'compare-name').get_attribute('value')
            L.shot(d, '07b_compare_config_light')
            # 回到基于已选报告 tab，确认两个已选报告
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '基于已选报告':
                    L.js_click(d, t); time.sleep(0.8); break
            dl = L.wait_dialog(d, '报告对比')
            OUT['compare_report_tab_text'] = dl.text[:500]
            L.shot(d, '07c_compare_report_tab_light')
            # 切回基于任务，选两个小任务（#527 3 用例 + #419）
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '基于任务':
                    L.js_click(d, t); time.sleep(0.8); break
            dl = L.wait_dialog(d, '报告对比')
            boxes = [b for b in dl.find_elements(By.CSS_SELECTOR, "[role='checkbox']")]
            OUT['compare_task_options'] = len(boxes)
            chosen = []
            for b in boxes:
                lbl = ''
                try:
                    lbl = rtext(b.find_element(By.XPATH, './ancestor::label[1]'))
                except Exception:
                    pass
                if '#412' in lbl or '#390' in lbl:
                    L.js_click(d, b); time.sleep(0.3); chosen.append(lbl[:60])
                if len(chosen) >= 2:
                    break
            OUT['compare_chosen_tasks'] = chosen
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '对比配置':
                    L.js_click(d, t); time.sleep(0.6); break
            dl = L.wait_dialog(d, '报告对比')
            nm = dl.find_element(By.ID, 'compare-name')
            nm.clear(); nm.send_keys('接线测试_对比_%s' % STAMP)
            L.reset_fetch_log(d)
            btn = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成对比报告']
            L.js_click(d, btn[-1])
            # 同步接口可能慢
            for i in range(24):
                time.sleep(5)
                if req_log(d, '/reports/compare'):
                    break
            time.sleep(3)
            OUT['compare_reqs'] = req_log(d, 'compare')
            OUT['compare_dialogs'] = dlg_texts(d)
            OUT['compare_url'] = d.current_url
            L.shot(d, '08_compare_after_light')
            if '/report/' in d.current_url:
                rid = d.current_url.rsplit('/report/', 1)[1].split('?')[0]
                report_id = rid
                OUT['compare_report_id'] = rid
                time.sleep(2)
                L.shot(d, '08b_compare_report_page_light')
        section('compare', compare)

        OUT['test_report_id'] = report_id
        rid = report_id

        # 若未拿到自建报告，退回用 API 建一个对比报告（同样为接线测试数据）
        if not rid:
            def api_create():
                r = L.api(d, '/reports/compare', 'POST', {'task_ids': [412, 390], 'name': '接线测试_对比_%s_api' % STAMP})
                OUT['api_create'] = {'status': r['status'], 'body': (r['text'] or '')[:400]}
                j = r['json'] or {}
                dd = j.get('data') or {}
                nonlocal_rid = dd.get('report_id') or dd.get('id') or (j.get('report_id') if isinstance(j, dict) else None)
                OUT['api_create_id'] = nonlocal_rid
                if nonlocal_rid:
                    OUT['test_report_id'] = nonlocal_rid
            section('api_create', api_create)
            rid = OUT.get('api_create_id')

        rid = OUT.get('test_report_id')
        OUT['using_report_id'] = rid

        # ---------- 4 重命名（编辑报告） ----------
        def rename():
            if not rid:
                raise AssertionError('无可操作自建报告')
            open_center(d)
            # 搜索定位（列表 1000 条已全量）
            idx = find_row_by_id(d, rid)
            if idx is None:
                raise AssertionError('列表找不到自建报告 #%s' % rid)
            OUT['rename_row_before'] = rtext(rows(d)[idx])[:120]
            row_action(d, idx, '编辑')
            dl = L.wait_dialog(d, '编辑报告')
            time.sleep(0.8)
            OUT['rename_text'] = dl.text[:300]
            L.shot(d, '09_rename_light')
            inp = dl.find_element(By.ID, 'rename-name')
            OUT['rename_prefill'] = inp.get_attribute('value')
            newname = '接线测试_报告_%s_改名' % STAMP
            inp.clear(); inp.send_keys(newname)
            L.reset_fetch_log(d)
            btn = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() in ('保存', '确定')]
            L.js_click(d, btn[-1])
            time.sleep(3)
            OUT['rename_reqs'] = req_log(d, '/reports/%s' % rid)
            r = L.api(d, '/reports/%s' % rid)
            dd = (r['json'] or {}).get('data') or {}
            OUT['rename_readback'] = {'status': r['status'], 'name': dd.get('name'), 'expected': newname, 'match': dd.get('name') == newname}
            open_center(d)
            idx = find_row_by_id(d, rid)
            OUT['rename_row_after'] = rtext(rows(d)[idx])[:120] if idx is not None else None
        section('rename', rename)

        # ---------- 5 发布确认 ----------
        def publish():
            if not rid:
                raise AssertionError('无可操作自建报告')
            open_center(d)
            idx = find_row_by_id(d, rid)
            if idx is None:
                raise AssertionError('列表找不到 #%s' % rid)
            # 若已发布则先取消发布？自建为 draft
            row_action(d, idx, '发布')
            dl = L.wait_dialog(d, '发布报告')
            time.sleep(0.8)
            OUT['publish_text'] = dl.text[:300]
            L.shot(d, '10_publish_light')
            L.close_dialog(d, 'esc')
            time.sleep(1)
            r = L.api(d, '/reports/%s' % rid)
            OUT['publish_cancel_status'] = ((r['json'] or {}).get('data') or {}).get('status')
            open_center(d)
            idx = find_row_by_id(d, rid)
            row_action(d, idx, '发布')
            dl = L.wait_dialog(d, '发布报告')
            L.reset_fetch_log(d)
            btn = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '发布']
            L.js_click(d, btn[-1])
            time.sleep(3)
            OUT['publish_reqs'] = req_log(d, '/publish')
            r = L.api(d, '/reports/%s' % rid)
            OUT['publish_readback'] = ((r['json'] or {}).get('data') or {}).get('status')
        section('publish', publish)

        # ---------- 6 删除确认（软删 + 回收站彻底删除自建报告） ----------
        def delete():
            if not rid:
                raise AssertionError('无可操作自建报告')
            open_center(d)
            idx = find_row_by_id(d, rid)
            if idx is None:
                raise AssertionError('列表找不到 #%s' % rid)
            row_action(d, idx, '删除')
            dl = L.wait_dialog(d, '删除报告')
            time.sleep(0.8)
            OUT['delete_text'] = dl.text[:300]
            L.shot(d, '11_delete_confirm_light')
            L.close_dialog(d, 'esc')
            time.sleep(1)
            r = L.api(d, '/reports/%s' % rid)
            OUT['delete_cancel_readback'] = {'status': r['status'], 'deleted': ((r['json'] or {}).get('data') or {}).get('deleted')}
            open_center(d)
            idx = find_row_by_id(d, rid)
            row_action(d, idx, '删除')
            dl = L.wait_dialog(d, '删除报告')
            L.reset_fetch_log(d)
            btns = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '删除']
            OUT['delete_btns'] = [b.text for b in dl.find_elements(By.TAG_NAME, 'button')]
            L.js_click(d, btns[-1])
            time.sleep(3)
            OUT['delete_reqs'] = req_log(d, '/reports/%s' % rid)
            open_center(d)
            OUT['delete_row_gone'] = find_row_by_id(d, rid) is None
            # 回收站 → 彻底删除
            d.get(L.BASE + '/report-center?trash=true')
            time.sleep(4)
            idx = find_row_by_id(d, rid)
            OUT['trash_row_found'] = idx is not None
            if idx is not None:
                row_action(d, idx, '彻底删除')
                dl = L.wait_dialog(d, '彻底删除')
                time.sleep(0.6)
                OUT['purge_text'] = dl.text[:300]
                L.shot(d, '11b_purge_confirm_light')
                L.reset_fetch_log(d)
                btns = [b for b in dl.find_elements(By.TAG_NAME, 'button') if '彻底删除' in (b.text or '')]
                L.js_click(d, btns[-1])
                time.sleep(3)
                OUT['purge_reqs'] = req_log(d, '/purge')
                open_center(d)
                d.get(L.BASE + '/report-center?trash=true')
                time.sleep(4)
                OUT['purge_row_gone'] = find_row_by_id(d, rid) is None
        section('delete', delete)

        # ---------- 7 深色截图 ----------
        def dark():
            L.apply_theme(d, 'dark')
            open_center(d)
            L.shot(d, '12_report_center_dark')
            L.click_text(d, '生成报告')
            L.wait_dialog(d, '生成报告')
            time.sleep(2)
            L.shot(d, '13_generate_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            L.js_click(d, d.find_element(By.XPATH, "//button[@aria-label='更多操作']"))
            time.sleep(0.7)
            for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if m.is_displayed() and '导出' in (m.text or ''):
                    L.js_click(d, m); break
            L.wait_dialog(d, '导出报告'); time.sleep(1)
            L.shot(d, '14_export_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if t.text.strip() == '导出历史':
                    L.js_click(d, t); time.sleep(1); break
            L.shot(d, '15_export_history_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            rr = rows(d)
            for idx in range(min(2, len(rr))):
                cbs = rows(d)[idx].find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                if cbs:
                    L.js_click(d, cbs[0]); time.sleep(0.4)
            L.click_text(d, '批量对比')
            L.wait_dialog(d, '报告对比'); time.sleep(1.2)
            L.shot(d, '16_compare_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            row_action(d, 0, '编辑')
            L.wait_dialog(d, '编辑报告'); time.sleep(1)
            L.shot(d, '17_rename_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            row_action(d, 0, '删除')
            L.wait_dialog(d, '删除报告'); time.sleep(1)
            L.shot(d, '18_delete_confirm_dark')
            L.close_dialog(d, 'esc'); time.sleep(0.8)
            L.apply_theme(d, 'light')
        section('dark', dark)

        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.endswith('.png')])
        print('DONE')
    finally:
        save()
        d.quit()


if __name__ == '__main__':
    main()

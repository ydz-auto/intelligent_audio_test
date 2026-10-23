# -*- coding: utf-8 -*-
"""INT-1482 批次2：生成报告全链路（选任务→进度→重命名→发布→删除→回收站彻底删除）。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

OUT = {}
STAMP = time.strftime('%H%M%S')
NAME = '接线测试_报告_' + STAMP
NEW_NAME = '接线测试_报告改名_' + STAMP


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def row_text(d, tr):
    return d.execute_script("return arguments[0].textContent", tr) or ''


def row_action_by_name(d, name_part, item_text):
    for tr in rows(d):
        if name_part in row_text(d, tr):
            btn = tr.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
            L.js_click(d, btn)
            time.sleep(0.6)
            for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if (m.text or '').strip() == item_text:
                    L.js_click(d, m)
                    time.sleep(1.5)
                    return True
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.5)
    return False


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        time.sleep(4)
        d.refresh()
        time.sleep(7)
        L.reset_fetch_log(d)
        t0 = L.now_ms()
        L.click_text(d, '生成报告')
        dl = L.wait_dialog(d, '生成报告')
        time.sleep(3)
        # 搜索任务并选中 527
        inp = dl.find_element(By.XPATH, ".//input[contains(@placeholder,'搜索任务')]")
        inp.send_keys('527')
        time.sleep(1.5)
        OUT['filtered'] = dl.text[:400]
        labels = dl.find_elements(By.XPATH, ".//label[contains(normalize-space(.),'INT1498')]")
        OUT['filtered_labels'] = [x.text[:60] for x in labels]
        if labels:
            L.js_click(d, labels[0])
            time.sleep(0.8)
        OUT['after_pick'] = dl.text[:300]
        name_in = dl.find_element(By.XPATH, ".//input[@placeholder='报告名称']")
        name_in.clear()
        name_in.send_keys(NAME)
        desc = dl.find_element(By.XPATH, ".//input[contains(@placeholder,'简要说明')]")
        desc.send_keys('接线测试：INT-1482 报告域深走查临时报告，验收后删除')
        OUT['form_light'] = L.shot(d, '20_generate_form_light')
        L.reset_fetch_log(d)
        t1 = L.now_ms()
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '生成报告' and b.is_displayed():
                L.js_click(d, b)
                break
        # 进度弹窗
        time.sleep(2)
        prog = None
        for _ in range(20):
            for cand in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
                try:
                    if cand.is_displayed() and '正在生成报告' in cand.text:
                        prog = cand
                        break
                except Exception:
                    pass
            if prog:
                break
            time.sleep(1)
        OUT['progress_found'] = bool(prog)
        if prog:
            OUT['progress_initial'] = prog.text[:300]
            OUT['progress_light'] = L.shot(d, '21_progress_dialog_light')
        # 等生成完成（最多 90s）
        done = False
        for i in range(90):
            time.sleep(1)
            if '正在生成报告' not in d.find_element(By.TAG_NAME, 'body').text:
                done = True
                break
        OUT['progress_done'] = done
        OUT['url_after'] = d.current_url
        OUT['body_after'] = d.find_element(By.TAG_NAME, 'body').text[:300]
        OUT['generate_req'] = [e for e in L.fetch_log(d, t1) if '/reports/generate-task' in e['url']]
        time.sleep(2)
        L.shot(d, '22_after_generate_light')

        # 回读：列表/接口查自己的报告
        r = L.api(d, '/reports?page=1&per_page=100')
        data = (r.get('json') or {}).get('data') or {}
        OUT['readback'] = [(i['id'], i['name'], i['status'], i.get('description'), (i.get('summary') or {}).get('total_cases')) for i in (data.get('items') or []) if NAME in (i['name'] or '')]
        if not OUT['readback'] or NAME not in (OUT['readback'][0][1] or ''):
            raise RuntimeError('生成的报告未查到: %s' % OUT['readback'][:3])
        rid = OUT['readback'][0][0]
        OUT['rid'] = rid

        # 重命名
        d.get(L.BASE + '/report-center')
        time.sleep(6)
        ok = row_action_by_name(d, NAME, '编辑')
        OUT['rename_open'] = ok
        dl = L.wait_dialog(d, '编辑报告')
        time.sleep(1)
        name_el = dl.find_element(By.ID, 'rename-name')
        OUT['rename_prefill'] = d.execute_script('return arguments[0].value', name_el)
        name_el.clear()
        name_el.send_keys(NEW_NAME)
        desc_el = dl.find_element(By.ID, 'rename-desc')
        desc_el.clear()
        desc_el.send_keys('改名回读验证')
        OUT['rename_light'] = L.shot(d, '23_rename_own_light')
        L.reset_fetch_log(d)
        t2 = L.now_ms()
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() in ('保存', '保存中...') and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(3)
        OUT['rename_req'] = [e for e in L.fetch_log(d, t2) if e['method'] == 'PUT']
        r = L.api(d, '/reports/%d' % rid)
        det = (r.get('json') or {}).get('data') or {}
        OUT['rename_readback'] = {'name': det.get('name'), 'description': det.get('description')}

        # 发布（真实提交）
        d.get(L.BASE + '/report-center')
        time.sleep(6)
        ok = row_action_by_name(d, NEW_NAME, '发布')
        OUT['publish_open'] = ok
        dl = L.wait_dialog(d, '发布报告')
        OUT['publish_text'] = dl.text[:200]
        L.reset_fetch_log(d)
        t3 = L.now_ms()
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '发布' and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(3)
        OUT['publish_req'] = [e for e in L.fetch_log(d, t3) if e['method'] == 'POST' and '/publish' in e['url']]
        r = L.api(d, '/reports/%d' % rid)
        OUT['publish_readback'] = ((r.get('json') or {}).get('data') or {}).get('status')

        # 删除（软删）→ 回收站 → 彻底删除
        d.get(L.BASE + '/report-center')
        time.sleep(6)
        ok = row_action_by_name(d, NEW_NAME, '删除')
        OUT['delete_open'] = ok
        dl = L.wait_dialog(d, '删除报告')
        OUT['delete_text'] = dl.text[:300]
        OUT['delete_light'] = L.shot(d, '24_delete_own_light')
        L.reset_fetch_log(d)
        t4 = L.now_ms()
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '删除' and b.is_displayed():
                L.js_click(d, b)
                break
        time.sleep(4)
        OUT['delete_req'] = [e for e in L.fetch_log(d, t4) if e['method'] == 'DELETE']
        r = L.api(d, '/reports?page=1&per_page=100&deleted=true')
        data = (r.get('json') or {}).get('data') or {}
        items = data.get('items') or []
        OUT['trash_readback'] = [(i['id'], i['name'], i.get('deleted')) for i in items if NEW_NAME in (i['name'] or '')]
        # 回收站页签
        d.get(L.BASE + '/report-center?trash=true')
        time.sleep(5)
        OUT['trash_page_rows'] = len(rows(d))
        ok = row_action_by_name(d, NEW_NAME, '彻底删除')
        OUT['purge_open'] = ok
        if ok:
            dl = L.wait_dialog(d, '彻底删除')
            OUT['purge_text'] = dl.text[:300]
            OUT['purge_light'] = L.shot(d, '25_purge_light')
            L.reset_fetch_log(d)
            t5 = L.now_ms()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '彻底删除' and b.is_displayed():
                    L.js_click(d, b)
                    break
            time.sleep(4)
            OUT['purge_req'] = [e for e in L.fetch_log(d, t5) if e['method'] == 'DELETE']
        r = L.api(d, '/reports/%d' % rid)
        OUT['after_purge_status'] = r['status']
        OUT['final_rows'] = [(i if isinstance(i, str) else i) for i in []]
    finally:
        with open(os.path.join(L.ART, 'batch2_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str)[:8000])


if __name__ == '__main__':
    main()

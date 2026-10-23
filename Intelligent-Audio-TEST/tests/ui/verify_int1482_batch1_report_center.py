# -*- coding: utf-8 -*-
"""INT-1482 批次1：报告中心弹窗组（生成/导出/对比/重命名/删除确认/发布确认）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

STAMP = time.strftime('%H%M%S')


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def row_action(d, idx, item_text):
    tr = rows(d)[idx]
    btn = tr.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
    L.js_click(d, btn)
    time.sleep(0.6)
    for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
        if (m.text or '').strip() == item_text:
            L.js_click(d, m)
            time.sleep(1.2)
            return True
    raise AssertionError('菜单项缺失 %s' % item_text)


def main():
    d = L.driver()
    out = {}

    def save():
        with open(os.path.join(L.ART, 'batch1_result.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1, default=str)

    def section(name, fn):
        try:
            fn()
        except Exception as e:
            out[name + '_error'] = traceback.format_exc()[-1200:]
        save()

    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        time.sleep(5)
        L.shot(d, '01_report_center_light')
        out['rows'] = len(rows(d))

        def gen():
            L.reset_fetch_log(d)
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            time.sleep(2.5)
            out['generate_text'] = dl.text[:600]
            out['generate_light'] = L.shot(d, '02_generate_dialog_light')
            out['generate_reqs'] = [e for e in L.fetch_log(d, 0) if '/tasks' in e['url']][-2:]
            btns = [b for b in dl.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报告']
            out['submit_disabled'] = [b.get_attribute('disabled') for b in btns]
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
            out['closed_after_esc'] = len(d.find_elements(By.CSS_SELECTOR, "[role='dialog']")) == 0
            L.click_text(d, '生成报告')
            dl = L.wait_dialog(d, '生成报告')
            out['reopen_inputs'] = [(i.get_attribute('aria-label'), i.get_attribute('value')) for i in dl.find_elements(By.TAG_NAME, 'input')]
            L.close_dialog(d, 'esc')
            time.sleep(0.8)
        section('generate', gen)

        def export():
            L.reset_fetch_log(d)
            more = d.find_element(By.XPATH, "//button[@aria-label='更多操作']")
            L.js_click(d, more)
            time.sleep(0.8)
            for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                if '导出' in (m.text or ''):
                    L.js_click(d, m)
                    break
            dl = L.wait_dialog(d, '导出报告')
            time.sleep(1)
            out['export_text'] = dl.text[:600]
            out['export_light'] = L.shot(d, '03_export_dialog_light')
            combo = dl.find_element(By.CSS_SELECTOR, "[role='combobox']")
            L.js_click(d, combo)
            time.sleep(0.8)
            out['export_formats'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            # 关闭下拉：点下拉外部
            d.find_element(By.CSS_SELECTOR, "[role='dialog']").click()
            time.sleep(0.8)
            dl = L.wait_dialog(d, '导出报告')
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '导出历史':
                    L.js_click(d, t)
            time.sleep(0.8)
            out['export_history'] = dl.text[:700]
            out['export_history_light'] = L.shot(d, '04_export_history_light')
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '导出':
                    L.js_click(d, t)
            time.sleep(0.8)
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            dl = L.wait_dialog(d, '导出报告')
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '导出' and b.is_displayed() and b.get_attribute('role') != 'tab':
                    L.js_click(d, b)
                    break
            time.sleep(4)
            dl = L.wait_dialog(d, '导出报告')
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '导出进度':
                    L.js_click(d, t)
                    break
            time.sleep(1)
            out['export_progress_text'] = dl.text[:500]
            out['export_req'] = [e for e in L.fetch_log(d, t0) if '/reports/export' in e['url']]
            out['export_after_light'] = L.shot(d, '05_export_progress_light')
            L.close_dialog(d, 'esc')
            time.sleep(1)
        section('export', export)

        def compare():
            # 小报告：384（5 用例）+ 381（5 用例），pageSize=100 全表可见
            d.get(L.BASE + '/report-center?pageSize=100')
            for _ in range(20):
                time.sleep(1)
                if rows(d):
                    break
            trs = rows(d)
            out['compare_page_rows'] = len(trs)
            picked = []
            for tr in trs:
                txt = tr.text
                if ('2026/9/23 19:08:30' in txt or '2026/9/24 16:48:55' in txt):
                    cb = tr.find_element(By.XPATH, ".//*[@role='checkbox']")
                    L.js_click(d, cb)
                    picked.append(txt[:60].replace('\n', '|'))
                    time.sleep(0.5)
            out['compare_picked'] = picked
            out['selected_text'] = [e.text for e in d.find_elements(By.XPATH, "//*[contains(normalize-space(.),'已选择')]")][:4]
            L.reset_fetch_log(d)
            L.click_text(d, '批量对比')
            dl = L.wait_dialog(d, '报告对比')
            time.sleep(2)
            out['compare_text'] = dl.text[:700]
            out['compare_light'] = L.shot(d, '06_compare_dialog_light')
            out['compare_reqs'] = [e for e in L.fetch_log(d, 0) if '/tasks' in e['url']][-2:]
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if '基于已选报告' in (t.text or ''):
                    L.js_click(d, t)
                    time.sleep(0.8)
                    break
            out['compare_report_tab'] = dl.text[:500]
            for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if '对比配置' in (t.text or ''):
                    L.js_click(d, t)
                    time.sleep(0.8)
                    break
            out['compare_config'] = dl.text[:700]
            out['compare_config_light'] = L.shot(d, '07_compare_config_light')
            name = dl.find_element(By.ID, 'compare-name')
            name.clear()
            name.send_keys('接线测试_对比_' + STAMP)
            L.reset_fetch_log(d)
            t0 = L.now_ms()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '生成对比报告' and b.is_displayed():
                    L.js_click(d, b)
                    break
            time.sleep(10)
            out['compare_after'] = d.find_element(By.TAG_NAME, 'body').text[:700]
            out['compare_req'] = [e for e in L.fetch_log(d, t0) if '/reports' in e['url'] and e['method'] != 'GET']
            out['compare_after_light'] = L.shot(d, '08_compare_after_light')
            L.close_dialog(d, 'esc')
        section('compare', compare)

        def rename():
            d.get(L.BASE + '/report-center')
            time.sleep(4)
            row_action(d, 0, '编辑')
            dl = L.wait_dialog(d, '编辑报告')
            out['rename_text'] = dl.text[:500]
            out['rename_prefill'] = [(i.get_attribute('id'), i.get_attribute('value'), d.execute_script('return arguments[0].value', i)) for i in dl.find_elements(By.TAG_NAME, 'input')]
            out['rename_light'] = L.shot(d, '09_rename_dialog_light')
            name = dl.find_element(By.ID, 'rename-name')
            name.clear()
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() in ('保存', '确定'):
                    L.js_click(d, b)
                    break
            time.sleep(1.5)
            out['rename_empty_submit'] = dl.text[:400]
            L.close_dialog(d, 'esc')
        section('rename', rename)

        def delete_confirm():
            d.get(L.BASE + '/report-center')
            time.sleep(4)
            row_action(d, 0, '删除')
            dl = L.wait_dialog(d, '删除')
            out['delete_text'] = dl.text[:400]
            out['delete_light'] = L.shot(d, '10_delete_confirm_light')
            L.close_dialog(d, 'esc')
        section('delete', delete_confirm)

        def publish_confirm():
            d.get(L.BASE + '/report-center')
            time.sleep(4)
            for i in range(len(rows(d))):
                tr = rows(d)[i]
                try:
                    btn = tr.find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
                    L.js_click(d, btn)
                    time.sleep(0.5)
                    items = [(m.text or '').strip() for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")]
                    if '发布' in items:
                        for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
                            if (m.text or '').strip() == '发布':
                                L.js_click(d, m)
                                break
                        dl = L.wait_dialog(d, '发布')
                        out['publish_text'] = dl.text[:400]
                        out['publish_light'] = L.shot(d, '11_publish_confirm_light')
                        L.close_dialog(d, 'esc')
                        out['publish_found'] = True
                        return
                    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    time.sleep(0.4)
                except Exception:
                    pass
            out['publish_found'] = False
        section('publish', publish_confirm)
    finally:
        save()
        try:
            d.quit()
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:8000])


if __name__ == '__main__':
    main()

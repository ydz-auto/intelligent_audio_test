# -*- coding: utf-8 -*-
"""INT-1482 批次D：中心确认弹窗取消路径（按报告名定位）+ 统计页执行统计/报表生成真实链路。"""
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

OUT = {}
STAMP = time.strftime('%H%M%S')
TARGET = '豆包拒识E2E测试任务_2026/10/13 17:32:23 - 测试报告'


def save():
    try:
        with open(os.path.join(L.ART, 'batchD_result.json'), 'w', encoding='utf-8') as f:
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


def find_row_by_name(d, name):
    for i, tr in enumerate(rows(d)):
        if name in rtext(tr):
            return i
    return None


def row_action(d, idx, item_text, wait=1.2):
    btn = rows(d)[idx].find_element(By.XPATH, ".//button[contains(@aria-label,'报告操作')]")
    L.js_click(d, btn)
    time.sleep(0.8)
    for m in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
        if m.is_displayed() and (m.text or '').strip() == item_text:
            L.js_click(d, m)
            time.sleep(wait)
            return True
    raise AssertionError('菜单项缺失 %s' % item_text)


def reqs(d, contains=None):
    out = []
    for e in L.fetch_log(d, 0):
        if contains and contains not in e.get('url', ''):
            continue
        out.append({k: e.get(k) for k in ('method', 'url', 'status', 'reqBody', 'resBody')})
    return out


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        WebDriverWait(d, 60).until(lambda x: len(rows(x)) > 0)
        time.sleep(2)

        def confirms():
            idx = find_row_by_name(d, TARGET)
            OUT['row_found'] = idx
            if idx is None:
                raise AssertionError('列表未找到目标报告行')
            OUT['row_text'] = rtext(rows(d)[idx])[:150]
            row_action(d, idx, '编辑')
            dl = L.wait_dialog(d, '编辑报告')
            time.sleep(0.8)
            OUT['rename_prefill'] = dl.find_element(By.ID, 'rename-name').get_attribute('value')
            OUT['rename_desc'] = dl.find_element(By.ID, 'rename-desc').get_attribute('value')
            L.shot(d, '35_rename_light')
            for b in dl.find_elements(By.TAG_NAME, 'button'):
                if (b.text or '').strip() == '取消':
                    L.js_click(d, b); break
            time.sleep(1)
            # 发布确认取消
            d.get(L.BASE + '/report-center'); time.sleep(4)
            idx = find_row_by_name(d, TARGET)
            row_action(d, idx, '发布')
            dl = L.wait_dialog(d, '发布报告')
            time.sleep(0.8)
            OUT['publish_text'] = dl.text[:300]
            L.shot(d, '36_publish_confirm_light')
            L.close_dialog(d, 'esc'); time.sleep(1)
            r = L.api(d, '/reports/481')
            OUT['publish_cancel_status'] = ((r['json'] or {}).get('data') or {}).get('status')
            # 删除确认取消
            d.get(L.BASE + '/report-center'); time.sleep(4)
            idx = find_row_by_name(d, TARGET)
            row_action(d, idx, '删除')
            dl = L.wait_dialog(d, '删除报告')
            time.sleep(0.8)
            OUT['delete_text'] = dl.text[:300]
            L.shot(d, '37_delete_confirm_light')
            L.close_dialog(d, 'esc'); time.sleep(1)
            r = L.api(d, '/reports/481')
            OUT['delete_cancel'] = {'status': r['status'], 'deleted': ((r['json'] or {}).get('data') or {}).get('deleted')}
            # 深色确认弹窗
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-center'); time.sleep(5)
            idx = find_row_by_name(d, TARGET)
            if idx is not None:
                row_action(d, idx, '删除')
                L.wait_dialog(d, '删除报告'); time.sleep(1)
                L.shot(d, '37b_delete_confirm_dark')
                L.close_dialog(d, 'esc'); time.sleep(0.8)
            L.apply_theme(d, 'light')
        section('confirms', confirms)

        def stats():
            L.reset_fetch_log(d)
            d.get(L.BASE + '/report-statistics')
            WebDriverWait(d, 60).until(lambda x: '报告统计分析' in (x.page_source or ''))
            time.sleep(5)
            OUT['stats_all_reqs_on_load'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in reqs(d)]
            OUT['stats_summary_before'] = L.body(d)[:400]
            # 执行统计分析
            btn = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '执行统计分析']
            OUT['run_btn'] = len(btn)
            if btn:
                L.js_click(d, btn[-1])
                time.sleep(6)
            OUT['stats_after_run'] = L.body(d)[:700]
            OUT['stats_reqs_after_run'] = [{k: e.get(k) for k in ('method', 'url', 'status')} for e in reqs(d)]
            L.shot(d, '39_statistics_after_run_light')
            # 报表生成页签
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '报表生成':
                    L.js_click(d, t); time.sleep(2); break
            L.shot(d, '40_statistics_report_tab_light')
            # 报表类型
            rt = d.find_element(By.ID, 'report-type')
            L.js_click(d, rt); time.sleep(0.8)
            OUT['form_type_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE); time.sleep(0.5)
            # 报表格式
            rf = d.find_element(By.ID, 'report-format')
            L.js_click(d, rf); time.sleep(0.8)
            OUT['form_format_options'] = [i.text for i in d.find_elements(By.CSS_SELECTOR, "[role='option']") if i.is_displayed()]
            for i in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if (i.text or '').strip() == 'PDF':
                    L.js_click(d, i); break
            time.sleep(0.6)
            # 内容复选
            OUT['form_content_checks'] = [c.get_attribute('aria-label') or rtext(c.find_element(By.XPATH, './ancestor::label[1]')) if c.find_elements(By.XPATH, './ancestor::label[1]') else '' for c in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")]
            # 名称
            nm = None
            for i in d.find_elements(By.TAG_NAME, 'input'):
                if '报表名称' in (i.get_attribute('placeholder') or ''):
                    nm = i
                    break
            if nm:
                nm.clear(); nm.send_keys('接线测试_统计报表_%s' % STAMP)
            dl_dir = os.path.join(L.ART, 'downloads')
            before = set(os.listdir(dl_dir)) if os.path.isdir(dl_dir) else set()
            L.reset_fetch_log(d)
            gen = [b for b in d.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '生成报表' and b.is_displayed()]
            OUT['gen_btn'] = len(gen)
            if gen:
                L.js_click(d, gen[-1])
                time.sleep(4)
            after = set(os.listdir(dl_dir)) if os.path.isdir(dl_dir) else set()
            OUT['new_files'] = sorted(after - before)
            OUT['gen_reqs'] = reqs(d)
            OUT['stats_after_generate'] = L.body(d)[:400]
            L.shot(d, '41_statistics_after_generate_light')
            # 浅深补充
            L.apply_theme(d, 'dark')
            d.get(L.BASE + '/report-statistics'); time.sleep(6)
            L.shot(d, '42_statistics_dark')
            for t in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
                if (t.text or '').strip() == '报表生成':
                    L.js_click(d, t); time.sleep(2); break
            L.shot(d, '43_statistics_report_tab_dark')
            L.apply_theme(d, 'light')
        section('stats', stats)

        OUT['artifacts'] = sorted([f for f in os.listdir(L.ART) if f.endswith('.png')])
        print('DONE')
    finally:
        save()
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1482 批次1c：报告对比弹窗（基于两份小报告二次对比）。"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By

OUT = {}


def rows(d):
    return d.find_elements(By.CSS_SELECTOR, 'table tbody tr')


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center?pageSize=100')
        for _ in range(25):
            time.sleep(1)
            if rows(d):
                break
        time.sleep(1)
        trs = rows(d)
        OUT['rows'] = len(trs)
        picked = []
        for tr in trs:
            txt = d.execute_script("return arguments[0].textContent", tr) or ''
            if ('环境理解E2E测试任务_2026/9/23 19:08:30' in txt or 'E2E测试任务_2026/9/24 16:48:55' in txt):
                cb = tr.find_element(By.XPATH, ".//*[@role='checkbox']")
                L.js_click(d, cb)
                picked.append(txt[:50])
                time.sleep(0.5)
        OUT['picked'] = picked
        body = d.find_element(By.TAG_NAME, 'body').text
        OUT['floating'] = [ln for ln in body.split('\n') if '已选择' in ln or '批量对比' in ln][:5]
        L.shot(d, '12_compare_selected_light')
        # 打开对比
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '批量对比' and b.is_displayed():
                L.js_click(d, b)
                break
        dl = L.wait_dialog(d, '报告对比')
        time.sleep(2)
        OUT['compare_text'] = dl.text[:700]
        OUT['compare_light'] = L.shot(d, '06_compare_dialog_light')
        # 基于已选报告
        for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if '基于已选报告' in (t.text or ''):
                L.js_click(d, t)
                time.sleep(0.8)
                break
        OUT['report_tab'] = dl.text[:500]
        # 对比配置
        for t in dl.find_elements(By.CSS_SELECTOR, "[role='tab']"):
            if '对比配置' in (t.text or ''):
                L.js_click(d, t)
                time.sleep(0.8)
                break
        OUT['config_tab'] = dl.text[:800]
        # 对比维度下拉选项
        combos = dl.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        OUT['combos'] = len(combos)
        if combos:
            L.js_click(d, combos[0])
            time.sleep(0.8)
            OUT['dimension_options'] = [o.text.strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
            d.find_element(By.CSS_SELECTOR, "[role='dialog']").click()
            time.sleep(0.6)
        OUT['metrics'] = [b.text.strip() for b in dl.find_elements(By.CSS_SELECTOR, "button[aria-pressed]")]
        OUT['config_light'] = L.shot(d, '07_compare_config_light')
        name = dl.find_element(By.ID, 'compare-name')
        name.clear()
        name.send_keys('接线测试_对比_' + time.strftime('%H%M%S'))
        L.reset_fetch_log(d)
        t0 = L.now_ms()
        for b in dl.find_elements(By.TAG_NAME, 'button'):
            if (b.text or '').strip() == '生成对比报告' and b.is_displayed():
                L.js_click(d, b)
                break
        # 等待结果（10s～60s）
        for i in range(60):
            time.sleep(1)
            if [e for e in L.fetch_log(d, t0) if '/secondary-compare' in e['url']]:
                time.sleep(1)
                break
        OUT['req'] = [e for e in L.fetch_log(d, t0) if '/reports' in e['url'] and e['method'] != 'GET']
        time.sleep(4)
        OUT['after_body'] = d.find_element(By.TAG_NAME, 'body').text[:800]
        OUT['after_light'] = L.shot(d, '08_compare_after_light')
        OUT['url'] = d.current_url
    finally:
        with open(os.path.join(L.ART, 'batch1c_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        d.quit()
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str)[:7000])


if __name__ == '__main__':
    main()

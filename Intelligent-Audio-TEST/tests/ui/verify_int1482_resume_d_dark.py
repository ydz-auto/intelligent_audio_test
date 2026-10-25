# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮深色补图：同源设 key（纯字符串）→ refresh → 断言 html.dark 后截图。

lib.apply_theme 用的是 JSON.stringify + about:blank，实测静默回退浅色（INT-1478/INT-1577 坑），
本轮改用仓库既有正确口径。
"""
import json
import os
import sys
import time

sys.path.insert(0, 'tests/ui')
import int1482_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}
NAME = '环境理解小艺E2E测试任务_2026/9/28 11:44:42'


def dark_page(d, path, wait_text=None, timeout=45):
    d.get(L.BASE + path)
    time.sleep(2)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    d.refresh()
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(1.5)
        txt = L.body(d)
        if '报告' in txt and (wait_text is None or wait_text in txt):
            break
    return {
        'html_class': d.execute_script("return document.documentElement.className"),
        'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor"),
        'has_text': (wait_text in L.body(d)) if wait_text else None,
    }


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        time.sleep(1)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.get(L.BASE + '/report-center')
        WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
        time.sleep(3)
        OUT['center_dark'] = {
            'html_class': d.execute_script("return document.documentElement.className"),
            'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor"),
            'has_name': NAME in L.body(d),
        }
        L.shot(d, 'd02b_report_center_dark')

        OUT['detail_dark'] = dark_page(d, '/report/564', NAME)
        L.shot(d, 'd04b_report_detail_564_dark')
        print(json.dumps(OUT, ensure_ascii=False))
    finally:
        with open(os.path.join(L.ART, 'resumeD_dark_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        try:
            d.get(L.BASE + '/report-center')
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()

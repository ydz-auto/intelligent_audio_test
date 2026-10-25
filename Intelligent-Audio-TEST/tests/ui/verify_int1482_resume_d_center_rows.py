# -*- coding: utf-8 -*-
"""INT-1482 续测 D 轮补图：报告中心列表滚到含任务名的行再截（浅/深）。"""
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


def capture(d, theme, out_name):
    d.get(L.BASE + '/report-center')
    if theme == 'dark':
        time.sleep(1)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        d.refresh()
    WebDriverWait(d, 60).until(lambda x: len(x.find_elements(By.CSS_SELECTOR, 'table tbody tr')) > 0)
    time.sleep(3)
    row_txt, found = None, False
    for tr in d.find_elements(By.CSS_SELECTOR, 'table tbody tr'):
        t = (d.execute_script("return arguments[0].textContent", tr) or '').strip()
        if NAME in t:
            d.execute_script("arguments[0].scrollIntoView({block:'center'})", tr)
            time.sleep(1.5)
            row_txt, found = t[:200], True
            break
    shot_ok = False
    L.shot(d, out_name)
    shot_ok = os.path.isfile(os.path.join(L.ART, out_name + '.png'))
    return {
        'theme': theme,
        'html_class': d.execute_script("return document.documentElement.className"),
        'body_bg': d.execute_script("return getComputedStyle(document.body).backgroundColor"),
        'row_found': found, 'row_text': row_txt, 'shot': shot_ok,
    }


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/report-center')
        time.sleep(1)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        OUT['light'] = capture(d, 'light', 'd01b_report_center_rows_light')
        OUT['dark'] = capture(d, 'dark', 'd02c_report_center_rows_dark')
        print(json.dumps(OUT, ensure_ascii=False))
    finally:
        with open(os.path.join(L.ART, 'resumeD_center_rows_result.json'), 'w', encoding='utf-8') as f:
            json.dump(OUT, f, ensure_ascii=False, indent=1, default=str)
        try:
            d.get(L.BASE + '/report-center')
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()

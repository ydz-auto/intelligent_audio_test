# -*- coding: utf-8 -*-
"""INT-1643 探针 2：搜索 + 行结构 + 批量条。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15933')
L.API = 'http://127.0.0.1:15000'

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def main():
    d = L.driver()
    try:
        L.login(d)
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        inp = d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例名称']")
        inp.click()
        inp.send_keys('DD10')
        inp.send_keys(Keys.ENTER)
        time.sleep(10)
        print('url', d.current_url)
        txt = L.body_text(d)
        print('body:', txt[:800].replace('\n', ' | '))
        for sel in ["[role='checkbox']", "input[type='checkbox']", "button[role='checkbox']",
                    "[data-state]", "[role='row']", "tr", "table"]:
            els = [e for e in d.find_elements(By.CSS_SELECTOR, sel) if vis(e)]
            print('sel', sel, len(els))
        # role=row 文本
        rows = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='row']") if vis(e)]
        for r in rows[:5]:
            print('ROW', (r.text or '')[:120].replace('\n', ' | '))
        L.save_evidence('probe2', {'url': d.current_url, 'body': txt[:2000],
                                   'rows': [r.text for r in rows[:10]]})
        L.shot(d, 'probe2_rows')
    finally:
        d.quit()


if __name__ == '__main__':
    main()

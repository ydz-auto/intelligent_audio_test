# -*- coding: utf-8 -*-
"""INT-1643 探针：nginx 注入容器（15933）上的用例页结构确认。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15933')
L.API = 'http://127.0.0.1:15000'

from selenium.webdriver.common.by import By


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def main():
    d = L.driver()
    try:
        print('login ->', L.login(d))
        d.get(L.BASE + '/testcases')
        time.sleep(8)
        print('url', d.current_url)
        print('body head:', L.body_text(d)[:600].replace('\n', ' | '))
        # 搜索框
        inputs = d.find_elements(By.CSS_SELECTOR, 'input')
        for i, el in enumerate(inputs[:8]):
            print('input', i, el.get_attribute('placeholder'), el.get_attribute('type'))
        # 复选框候选
        for sel in ["[role='checkbox']", "input[type='checkbox']", "button[role='checkbox']"]:
            els = [e for e in d.find_elements(By.CSS_SELECTOR, sel) if vis(e)]
            print('sel', sel, len(els))
    finally:
        d.quit()


if __name__ == '__main__':
    main()

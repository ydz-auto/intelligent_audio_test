# -*- coding: utf-8 -*-
"""INT-1731 补充：单选 1 轮用例时轮次范围只出「第1轮」（动态绑定，不是写死 2）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By

from verify_int1731_batch_rounds import (
    ARTIFACTS, _driver, _visible_dialog, any_dialog_visible, api_get, click_label,
    open_dialog, round_labels_in, set_input, wait_for,
)

CASE_ID = 'd72a347e-c630-41f7-b79a-37cc5a029280'
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15247')


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    info = api_get('/api/v1/testcases/' + CASE_ID)
    group_name = info['group_name']
    name = info['name']
    print('fixture rounds:', len(info['config']['rounds']))
    drv = _driver()
    try:
        drv.set_page_load_timeout(90)
        drv.get(BASE + '/')
        time.sleep(1)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode","light")')
        drv.get(BASE + '/testcases/by-group')
        time.sleep(2)
        drv.get(BASE + '/testcases/by-group')
        box = wait_for(lambda: next((e for e in drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
                                     if e.is_displayed()), None), 90, 'search')
        set_input(drv, box, 'JG0081')
        time.sleep(3)
        header = wait_for(lambda: next(
            (h for h in drv.find_elements(
                By.XPATH, "//div[contains(@class,'cursor-pointer')][.//span[contains(@class,'font-medium')]]")
             if group_name in (h.text or '')), None), 60, 'group header')
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', header)
        time.sleep(0.4)
        drv.execute_script('arguments[0].click();', header)
        card = wait_for(lambda: next(
            (e for e in drv.find_elements(By.XPATH, "//*[starts-with(@aria-label,'选择 ')]")
             if e.is_displayed() and (e.get_attribute('aria-label') or '').endswith('_copy')), None),
            90, 'single fixture card')
        drv.execute_script('arguments[0].click();', card)
        wait_for(lambda: '个用例已选择' in drv.find_element(By.TAG_NAME, 'body').text, 20, 'bulk bar')
        time.sleep(0.5)
        dlg = open_dialog(drv, '批量设置声压', '批量设置声压级')
        click_label(drv, dlg, '指定轮次（统一设置）')
        time.sleep(0.5)
        nums, texts = round_labels_in(drv, _visible_dialog(drv, '批量设置声压级'),
                                      'batch-spl-round')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'single_round_case_specific.png'))
        print('labels:', texts)
        ok = nums == [1]
        print('SINGLE-ROUND', 'PASS' if ok else 'FAIL')
        # 关闭
        for b in _visible_dialog(drv, '批量设置声压级').find_elements(
                By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]"):
            if b.is_displayed():
                drv.execute_script('arguments[0].click();', b)
        return 0 if ok else 2
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())

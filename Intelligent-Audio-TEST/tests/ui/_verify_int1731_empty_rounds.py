# -*- coding: utf-8 -*-
"""INT-1731 补充：指定轮次一个都不勾时不得提交（不发请求、提示「请至少选择一个轮次」）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By

from verify_int1731_batch_rounds import (
    ARTIFACTS,
    _driver,
    _visible_dialog,
    any_dialog_visible,
    api_get,
    api_spls,
    click_label,
    collect_requests,
    open_dialog,
    prepare_page,
    set_input,
    wait_for,
)

IDS = ['3357ba09-4346-4e0b-b85e-13d41c720a80', '8134f38c-31e8-4604-91b3-41cc20174575']
BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15247')


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    group_name = api_get('/api/v1/testcases/' + IDS[0]).get('group_name')
    before = {i: api_spls(i) for i in IDS}
    drv = _driver()
    try:
        drv.set_page_load_timeout(90)
        prepare_page(drv, BASE, 'light', group_name)
        drv.get_log('performance')  # drain
        dlg = open_dialog(drv, '批量设置声压', '批量设置声压级')
        click_label(drv, dlg, '指定轮次（统一设置）')
        time.sleep(0.5)
        dlg = _visible_dialog(drv, '批量设置声压级')
        panel = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-spl-round-specific-rounds']")
        # 取消默认勾选的第 1 轮 → 一个都不选
        cb = panel.find_element(By.XPATH, ".//label[normalize-space(.)='第1轮']//*[@role='checkbox']")
        if cb.get_attribute('aria-checked') != 'false':
            drv.execute_script('arguments[0].click();', cb)
            time.sleep(0.4)
        dlg = _visible_dialog(drv, '批量设置声压级')
        panel = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-spl-round-specific-rounds']")
        checked = {n: panel.find_element(By.XPATH, ".//label[normalize-space(.)='第%d轮']//*[@role='checkbox']" % n)
                   .get_attribute('aria-checked') for n in (1, 2)}
        print('checked state:', checked)
        num = dlg.find_element(By.XPATH, ".//input[@type='number']")
        set_input(drv, num, '77')
        time.sleep(0.6)
        dlg = _visible_dialog(drv, '批量设置声压级')
        ok_btn = dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '确定')]")
        drv.execute_script('arguments[0].click();', ok_btn)
        wait_for(lambda: '请至少选择一个轮次' in drv.find_element(By.TAG_NAME, 'body').text, 12,
                 'empty-round toast')
        drv.save_screenshot(os.path.join(ARTIFACTS, 'empty_rounds_guard.png'))
        still_open = any_dialog_visible(drv)
        time.sleep(1.5)
        reqs = collect_requests(drv)
        posts = [r for r in reqs if '/api/v1/testcases/batch' in r['url'] and r['method'] == 'POST']
        after = {i: api_spls(i) for i in IDS}
        print('dialog still open:', still_open)
        print('batch POST count:', len(posts))
        print('readback before/after:', before, after)
        ok = bool(checked == {1: 'false', 2: 'false'}) and still_open and not posts and before == after
        print('EMPTY-GUARD', 'PASS' if ok else 'FAIL')
        return 0 if ok else 2
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())

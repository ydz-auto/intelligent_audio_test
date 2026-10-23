# -*- coding: utf-8 -*-
"""INT-1544 附证 C：筛选结果为空时 filter-all 提交被拦（不再提交 case_ids=[]）。"""
import os
import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from verify_int1544_filter_all import BASE, DEVICE_NAME, FETCH_PATCH, driver_new, js_click, shot

KEYWORD = 'ZZZ_NO_SUCH_CASE_1544'


def main():
    d = driver_new()
    try:
        d.get('about:blank')
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
        d.get(BASE + '/start-test')
        WebDriverWait(d, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索用例']"))
        )
        WebDriverWait(d, 40).until(
            lambda x: '全部' in x.find_element(
                By.XPATH, "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
            ).text
        )
        d.find_element(By.CSS_SELECTOR, "input[placeholder*='搜索用例']").send_keys(KEYWORD)
        WebDriverWait(d, 40).until(
            lambda x: '全部 0 条用例' in x.find_element(
                By.XPATH, "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
            ).text
        )
        print('SUMMARY:', d.find_element(
            By.XPATH, "//span[contains(@class,'text-info')][contains(normalize-space(.),'未选择用例时')]"
        ).text)
        shot(d, 'empty_filter_step1.png')

        js_click(d, d.find_element(By.XPATH, "//button[normalize-space(.)='下一步']"))
        time.sleep(2)
        cb = WebDriverWait(d, 40).until(
            EC.presence_of_element_located((By.XPATH, "//*[@aria-label='选择设备 %s']" % DEVICE_NAME))
        )
        js_click(d, cb)
        time.sleep(1)
        js_click(d, d.find_element(By.XPATH, "//button[normalize-space(.)='开始测试']"))
        time.sleep(1.5)
        # 期望：出现 warning toast，且任务名称弹窗不出现
        toasts = [t.text for t in d.find_elements(By.CSS_SELECTOR, "[data-sonner-toast]")]
        dialogs = d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")
        shot(d, 'empty_filter_blocked.png')
        print('TOASTS:', toasts)
        print('DIALOGS:', len(dialogs))
        posts = [e for e in d.execute_script('return window.__fetchLog || []')
                 if e.get('method') == 'POST' and '/tasks' in (e.get('url') or '')]
        print('POST /tasks entries:', len(posts))
        assert any('没有可用的测试用例' in t for t in toasts), '未出现空筛选拦截提示'
        assert len(dialogs) == 0, '空筛选仍打开了任务名称弹窗'
        assert len(posts) == 0, '空筛选仍发起了 POST /tasks'
        print('OK 空筛选在入口被拦截，未发起 POST /tasks')
    finally:
        d.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1643 调试：回收站卡片按钮属性。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

GROUP = '接线测试_INT1643_目标组'


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=20, interval=0.4):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception:
            pass
        time.sleep(interval)
    return None


OUT = {}
d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 15)
    L.js_click(d, opt)
    time.sleep(5)
    t = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                            if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.js_click(d, t)
    time.sleep(5)
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 15)
    if hdr is not None:
        L.js_click(d, hdr)
        time.sleep(5)
    OUT['trash_text_tail'] = L.body_text(d)[-300:]
    btns = d.find_elements(By.TAG_NAME, 'button')
    OUT['buttons'] = [{'aria': b.get_attribute('aria-label'), 'text': (b.text or '')[:20],
                       'disabled': b.get_attribute('aria-disabled'), 'cls': (b.get_attribute('class') or '')[:60],
                       'vis': vis(b)} for b in btns if b.get_attribute('aria-label')]
    OUT['case_card_html'] = None
    for span in d.find_elements(By.XPATH, "//span[contains(text(),'批量_B')]"):
        card = span
        for _ in range(6):
            card = card.find_element(By.XPATH, '..')
        OUT['case_card_html'] = card.get_attribute('outerHTML')[:3000]
        break
    L.shot(d, 'debug_trash')
finally:
    L.save_evidence('debug_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

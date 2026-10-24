# -*- coding: utf-8 -*-
"""阶段 B2：真实用例参考参数错误态（搜索 + 展开所有分组）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

L.BASE = 'http://127.0.0.1:5333'
REAL_KW = 'DD100'
OUT = {}


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=40, interval=0.6):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


d = L.driver()
try:
    d.get(L.BASE + '/login')
    time.sleep(6)
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '进入工作台':
            L.js_click(d, b)
            time.sleep(3)
            break
    d.get(L.BASE + '/testcases')
    time.sleep(8)
    inp = retry(lambda: next((i for i in d.find_elements(By.TAG_NAME, 'input')
                              if vis(i) and '搜索用例' in (i.get_attribute('placeholder') or '')), None), 90)
    L.js_click(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(REAL_KW)
    # 等结果：直接出现编辑按钮，或先出现分组行再点开
    t0 = time.time()
    opened = 0
    while time.time() - t0 < 150:
        btns = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']") if vis(b)]
        if btns:
            break
        rows = [e for e in d.find_elements(By.CSS_SELECTOR, "div[class*='cursor-pointer']")
                if vis(e) and (e.text or '').strip().endswith('条') and REAL_KW not in '']
        for r in rows[:2]:
            L.js_click(d, r)
            opened += 1
            time.sleep(2)
        time.sleep(2)
    OUT['group_rows_clicked'] = opened
    OUT['wait_s'] = round(time.time() - t0, 1)
    OUT['body_tail'] = L.body_text(d)[-400:]
    card = next((e for e in d.find_elements(By.XPATH,
        "//*[contains(text(), '%s')]/ancestor::div[.//button[@aria-label='编辑用例']][1]" % REAL_KW) if vis(e)), None)
    OUT['card_found'] = card is not None
    if card is None:
        L.shot(d, 'B0_no_card')
        raise RuntimeError('card not found')
    L.js_click(d, card.find_element(By.CSS_SELECTOR, "button[aria-label='编辑用例']"))
    drawer = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                                 if vis(x) and any((t.text or '').strip() == '参考参数'
                                                   for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 60)
    OUT['tabs'] = [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
    t = next((x for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.text or '').strip() == '参考参数'), None)
    L.clear_fetch_log(d)
    L.js_click(d, t)
    L.shot(d, 'B1_ref_initial')
    time.sleep(6)
    OUT['ref_text'] = (drawer.text or '')[-900:]
    OUT['has_error_text'] = '参考参数内容读取失败' in (drawer.text or '')
    OUT['has_retry'] = any((b.text or '').strip() == '重试' for b in drawer.find_elements(By.TAG_NAME, 'button'))
    OUT['fetch'] = [(e.get('method'), (e.get('url') or '')[:120], e.get('status'))
                    for e in L.fetch_log(d, 'ref-params')]
    L.shot(d, 'B2_ref_error')
    L.apply_theme(d, 'dark')
    L.shot(d, 'B3_ref_error_dark')
    L.apply_theme(d, 'light')
finally:
    L.save_evidence('finalize4_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:4000])

# -*- coding: utf-8 -*-
"""调试：用例卡片按钮可见性 / 批量维度「指定轮次」控件。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

L.BASE = 'http://127.0.0.1:5333'
GROUP = '接线测试_INT1643_目标组'
A_NAME = '接线测试_INT1643_批量_A'
C_NAME = '接线测试_INT1643_批量_C'
OUT = {}


def vis(e):
    try:
        return e.is_displayed()
    except Exception:
        return False


d = L.driver()
try:
    d.get(L.BASE + '/login')
    time.sleep(5)
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '进入工作台':
            L.js_click(d, b)
            time.sleep(3)
            break
    d.get(L.BASE + '/testcases')
    time.sleep(10)
    trig = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                 if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None)
    OUT['trig'] = trig is not None
    if trig is not None:
        L.js_click(d, trig)
        time.sleep(1.5)
    opt = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                if vis(b) and (b.text or '').strip() == GROUP), None)
    OUT['group_opt'] = opt is not None
    if opt is not None:
        L.js_click(d, opt)
        time.sleep(8)
    hdr = next((e for e in d.find_elements(By.XPATH,
        "//*[normalize-space(.)='%s']/ancestor::*[contains(@class,'cursor-pointer')][1]" % GROUP) if vis(e)), None)
    OUT['hdr'] = hdr is not None
    if hdr is not None:
        L.js_click(d, hdr)
        time.sleep(3)
    t0=time.time()
    while time.time()-t0 < 150:
        if d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"):
            break
        time.sleep(2)
    OUT['wait_cards_s'] = round(time.time()-t0,1)
    OUT['body_tail'] = L.body_text(d)[-500:]
    cards = d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
    OUT['edit_btns_total'] = len(cards)
    OUT['edit_btns_visible'] = [vis(c) for c in cards]
    OUT['edit_btns_card_aria'] = [c.get_attribute('aria-label') for c in cards]
    OUT['checkbox_arias'] = [c.get_attribute('aria-label') for c in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")][:10]
    # 悬停卡片再看
    if cards:
        try:
            d.execute_script("arguments[0].scrollIntoView({block:'center'})", cards[0])
            time.sleep(0.5)
        except Exception:
            pass
        OUT['after_scroll_visible'] = [vis(c) for c in cards]
    L.shot(d, 'dbg_cards')
    # 选中 A/C 打开批量维度
    for nm in (A_NAME, C_NAME):
        cb = next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
                   if vis(x) and nm in (x.get_attribute('aria-label') or '')), None)
        OUT['cb_' + nm[-1]] = cb is not None
        if cb is not None:
            L.js_click(d, cb)
            time.sleep(1)
    bb = next((b for b in d.find_elements(By.TAG_NAME, 'button')
               if vis(b) and (b.text or '').strip() == '批量设置评估维度'), None)
    OUT['batch_btn'] = bb is not None
    if bb is not None:
        L.js_click(d, bb)
        time.sleep(2)
        dlg = next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                    if vis(x) and '批量设置评估维度' in (x.text or '')), None)
        OUT['dims_dialog'] = dlg is not None
        if dlg is not None:
            OUT['radios'] = [(r.get_attribute('role'), (r.text or '')[:20], r.get_attribute('aria-checked'),
                              r.tag_name) for r in dlg.find_elements(By.CSS_SELECTOR, "[role='radio'],[role='tab'],input[type='radio']")]
            OUT['spec_elems'] = [(e.tag_name, e.get_attribute('role'), (e.text or '')[:20])
                                 for e in dlg.find_elements(By.XPATH, "//*[contains(normalize-space(.), '指定轮次')]")][:8]
            OUT['dialog_text'] = (dlg.text or '')[:900]
            L.shot(d, 'dbg_dims')
            # 点含「指定轮次（统一设置）」的元素
            el = next((e for e in dlg.find_elements(By.XPATH, ".//*[normalize-space(.)='指定轮次（统一设置）']")), None)
            OUT['spec_label'] = el is not None
            if el is not None:
                L.js_click(d, el)
                time.sleep(2)
                OUT['after_spec_text'] = (dlg.text or '')[:900]
                L.shot(d, 'dbg_dims_specific')
finally:
    L.save_evidence('debug2_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:5000])

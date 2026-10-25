# -*- coding: utf-8 -*-
"""INT-1538 K：回收站 UI 链路（软删 → 恢复 → 软删 → 彻底删除）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {'steps': []}
G = '接线测试_INT1538_回收组'
N = '接线测试_INT1538_回收用例'


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
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


def log(step, **kw):
    kw['step'] = step
    OUT['steps'].append(kw)
    L.save_evidence('recycle2_evidence', OUT)


def confirm_dialog(texts):
    """base-ui AlertDialog 根是 [role='alertdialog']，普通 Dialog 是 [role='dialog']。"""
    for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog'], [role='dialog']"):
        if not vis(x):
            continue
        btns = [c for c in x.find_elements(By.TAG_NAME, 'button') if vis(c)]
        for c in btns:
            if (c.text or '').strip() in texts:
                nm = (c.text or '').strip()
                L.js_click(d, c)
                return nm
    return None


d = L.driver()
try:
    L.login(d)
    idcase = None
    st, p, _ = L.api_json(d, '/testcases', 'POST', {'name': N, 'group': G, 'tags': [], 'config': {'rounds': []}})
    OUT['create'] = (st, p if isinstance(p, dict) else str(p)[:200])
    if isinstance(p, dict):
        idcase = (p.get('data') or {}).get('id')
    OUT['case_id'] = idcase
    d.get(L.BASE + '/testcases')
    time.sleep(5)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 25)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == G), None), 15)
    L.js_click(d, opt)
    time.sleep(5)
    header = retry(lambda: next((e for e in d.find_elements(By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % G) if vis(e)), None), 15)
    L.js_click(d, header)
    time.sleep(6)
    log('expanded', text=L.body_text(d)[-300:])
    # 1) 软删
    b = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除用例']") if vis(x)), None), 20)
    L.js_click(d, b)
    time.sleep(1.5)
    log('delete_confirm_btn', clicked=confirm_dialog(('删除',)))
    time.sleep(3)
    log('delete_toast', toasts=L.wait_toast(d, 12))
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + N + '&only_deleted=1')
    items = ((p or {}).get('data') or {}).get('items') or []
    log('trash_api', items=[(x.get('name'), x.get('deleted')) for x in items])
    # 2) 回收站视图恢复（先重置筛选）
    reset = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '重置'), None)
    if reset:
        L.js_click(d, reset)
        time.sleep(3)
    trash = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.js_click(d, trash)
    time.sleep(6)
    L.shot(d, 'k01_trash_view')
    log('trash_view', text=L.body_text(d)[-400:])
    rb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='恢复用例']") if vis(x)), None), 15)
    L.js_click(d, rb)
    time.sleep(1.5)
    log('restore_confirm', clicked=confirm_dialog(('恢复', '确定', '确认')))
    time.sleep(3)
    log('restore_toast', toasts=L.wait_toast(d, 12))
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + N)
    items = ((p or {}).get('data') or {}).get('items') or []
    log('restored_api', items=[(x.get('name'), x.get('deleted')) for x in items])
    L.shot(d, 'k02_after_restore')
    # 3) 再软删
    time.sleep(1)
    trash = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '回收站'), None)
    if trash:
        L.js_click(d, trash)   # 退出回收站
        time.sleep(4)
    b2 = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='删除用例']") if vis(x)), None), 15)
    if b2:
        L.js_click(d, b2)
        time.sleep(1.5)
        log('delete2_confirm', clicked=confirm_dialog(('删除',)))
        time.sleep(3)
        log('delete2_toast', toasts=L.wait_toast(d, 12))
    trash = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.js_click(d, trash)
    time.sleep(6)
    pb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='彻底删除']") if vis(x)), None), 15)
    L.js_click(d, pb)
    time.sleep(1.5)
    L.shot(d, 'k03_purge_confirm')
    log('purge_confirm', clicked=confirm_dialog(('彻底删除', '删除', '确定')))
    time.sleep(4)
    log('purge_toast', toasts=L.wait_toast(d, 12))
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + N + '&only_deleted=1')
    items = ((p or {}).get('data') or {}).get('items') or []
    log('after_purge_trash', items=[(x.get('name'), x.get('deleted')) for x in items])
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=50&keyword=' + N)
    items = ((p or {}).get('data') or {}).get('items') or []
    log('after_purge_live', status=st, items=[(x.get('name'), x.get('deleted')) for x in items])
    L.shot(d, 'k04_after_purge')
finally:
    L.save_evidence('recycle2_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

# -*- coding: utf-8 -*-
"""INT-1643 收尾：回收站彻底删除 + 导出弹窗缺陷 + 抽屉五步/深浅色。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

GROUP = '接线测试_INT1643_目标组'
B_ID = '38a3fa72-1561-425d-b467-9b46ca209e23'
A_ID = '8bb822a4-243c-4f20-87e5-ae015028d724'
OUT = {}


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.4):
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


def find_dialog(kw):
    ds = [x for x in L.dialogs(d) if kw in (x.text or '')]
    return ds[-1] if ds else None


def confirm(texts=('彻底删除', '删除', '恢复', '确定', '确认')):
    for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog'], [role='dialog']"):
        if not vis(x):
            continue
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if vis(c) and (c.text or '').strip() in texts:
                nm = (c.text or '').strip()
                L.js_click(d, c)
                return nm
    return None


def trash_list():
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=100&keyword=接线测试_INT1643&only_deleted=1')
    return [x.get('name') for x in (((p or {}).get('data') or {}).get('items') or [])]


def live_list():
    st, p, _ = L.api_json(d, '/testcases?page=1&per_page=100&keyword=接线测试_INT1643')
    return [x.get('name') for x in (((p or {}).get('data') or {}).get('items') or [])]


def reset_filters():
    r = next((x for x in d.find_elements(By.TAG_NAME, 'button') if vis(x) and (x.text or '').strip() == '重置'), None)
    if r is not None:
        L.js_click(d, r)
        time.sleep(3)


def open_group():
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 15)
    L.js_click(d, opt)
    time.sleep(5)
    hdr = next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None)
    if hdr is not None:
        L.js_click(d, hdr)
        time.sleep(5)


def click_trash():
    t = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                            if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.clear_fetch_log(d)
    L.js_click(d, t)
    time.sleep(4)

    def rows():
        return [x for x in d.find_elements(By.CSS_SELECTOR,
                                           "button[aria-label='恢复用例'], button[aria-label^='彻底删除']") if vis(x)]

    def case_visible():
        return any(vis(s) for s in d.find_elements(By.XPATH, "//span[contains(text(),'批量_B')]"))

    for _ in range(3):
        time.sleep(2)
        if rows() or case_visible():
            break
        hdr = next((e for e in d.find_elements(
            By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
            if vis(e)), None)
        if hdr is None:
            break
        L.js_click(d, hdr)
        time.sleep(4)
    time.sleep(2)
    return [(e.get('method'), (e.get('url') or '')[:100], e.get('status')) for e in L.fetch_log(d)]


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    OUT['trash_before'] = trash_list()
    OUT['live_before'] = live_list()

    # 1) 回收站 → 彻底删除
    open_group()
    OUT['trash_fetch'] = click_trash()
    L.shot(d, 'g01_trash_view')
    OUT['trash_text'] = L.body_text(d)[-350:]
    OUT['purge_btns'] = len([x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='彻底删除']") if vis(x)])
    pb = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label^='彻底删除']") if vis(x)), None), 20)
    L.js_click(d, pb)
    time.sleep(1.2)
    L.shot(d, 'g02_purge_confirm')
    OUT['purge_confirm'] = confirm(('彻底删除', '删除', '确定', '确认'))
    time.sleep(3)
    OUT['purge_toast'] = L.wait_toast(d, 15)
    OUT['trash_after'] = trash_list()
    OUT['live_after'] = live_list()
    OUT['b_detail_status'] = L.api_json(d, '/testcases/' + B_ID)[0]
    L.shot(d, 'g03_after_purge')

    # 2) 导出弹窗（P2）
    tr = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '回收站'), None)
    if tr is not None:
        L.js_click(d, tr)
        time.sleep(3)
    reset_filters()
    L.clear_fetch_log(d)
    eb = retry(lambda: next((x for x in d.find_elements(By.TAG_NAME, 'button')
                             if (x.text or '').strip() == '导出' and vis(x)), None), 20)
    L.js_click(d, eb)
    dlg = retry(lambda: find_dialog('导出用例'), 20)
    time.sleep(1)
    OUT['export_text'] = (dlg.text or '')[:400]
    L.shot(d, 'e01_export_light')
    for x in dlg.find_elements(By.TAG_NAME, 'button'):
        if (x.text or '').strip() == '开始导出' and vis(x):
            L.js_click(d, x)
            break
    time.sleep(3)
    OUT['export_toasts'] = L.wait_toast(d, 15)
    OUT['export_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status')) for e in L.fetch_log(d)]
    L.apply_theme(d, 'dark')
    L.shot(d, 'e02_export_dark')
    for x in L.dialogs(d):
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if vis(c) and (c.text or '').strip() in ('取消', 'Close'):
                L.js_click(d, c)
                break
    time.sleep(1)
    L.shot(d, 'e03_list_dark')
    L.apply_theme(d, 'light')

    # 3) 抽屉五步（A 用例）
    open_group()
    ed = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']") if vis(x)), None), 20)
    L.clear_fetch_log(d)
    L.js_click(d, ed)
    drawer = retry(lambda: next((x for x in L.dialogs(d)
                                 if any((t.text or '').strip() == '算法参数'
                                        for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 25)
    time.sleep(1.5)
    OUT['drawer_open'] = drawer is not None
    OUT['drawer_load_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status')) for e in L.fetch_log(d)]
    OUT['drawer_tabs'] = [(t.text or '').strip() for t in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(t)]
    L.shot(d, 'f01_drawer_step1')
    for i, label in enumerate(['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'], start=1):
        tab = next((t for t in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
                    if vis(t) and (t.text or '').strip() == label), None)
        if tab is None:
            OUT['step_%s' % label] = 'tab missing'
            continue
        L.js_click(d, tab)
        time.sleep(1.6)
        L.shot(d, 'f%02d_drawer_%s' % (i, label))
        if label == '算法参数':
            OUT['step_algo_text'] = (drawer.text or '')[-400:]
        if label == '音频列表':
            sels = [e for e in drawer.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                    if vis(e) and ((e.get_attribute('aria-label') or '').find('播放设备') >= 0)]
            OUT['audio_device_selects'] = [(e.get_attribute('aria-label'), (e.text or '').strip()[:50]) for e in sels[:6]]
        if label == '噪声与干扰':
            OUT['noise_hint_present'] = '演示提示条' in (drawer.text or '')
            OUT['noise_step_text'] = (drawer.text or '')[-500:]
        if label == '评估维度':
            OUT['dims_step_text'] = (drawer.text or '')[-400:]
        if label == '参考参数':
            OUT['ref_step_text'] = (drawer.text or '')[-400:]
            L.clear_fetch_log(d)
            edit_btn = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
                             if vis(b) and '查看/编辑' in (b.text or '')), None)
            if edit_btn is not None:
                L.js_click(d, edit_btn)
                time.sleep(1)
                ta = next((t for t in drawer.find_elements(By.TAG_NAME, 'textarea') if vis(t)), None)
                if ta is not None:
                    ta.send_keys(Keys.CONTROL, 'a')
                    ta.send_keys(Keys.DELETE)
                    ta.send_keys('{"int1643":"probe"}')
                    sv = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').strip() == '保存'), None)
                    if sv is not None:
                        L.js_click(d, sv)
                        time.sleep(2)
                        OUT['ref_save_toasts'] = L.wait_toast(d, 12)
                        OUT['ref_save_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status'))
                                                 for e in L.fetch_log(d)]
                    L.shot(d, 'f07_ref_edit')
            else:
                OUT['ref_edit_btn'] = 'not found (未生成态)'
    L.apply_theme(d, 'dark')
    L.shot(d, 'f08_drawer_dark')
    OUT['dark_html_class'] = d.execute_script('return document.documentElement.className')
    OUT['dark_body_bg'] = d.execute_script('return getComputedStyle(document.body).backgroundColor')
    L.apply_theme(d, 'light')
    # 保存抽屉（真实 PUT）
    sv = next((b for b in drawer.find_elements(By.TAG_NAME, 'button')
               if vis(b) and (b.text or '').strip() == '保存'), None)
    if sv is not None:
        L.clear_fetch_log(d)
        L.js_click(d, sv)
        time.sleep(4)
        OUT['drawer_save_toasts'] = L.wait_toast(d, 15)
        OUT['drawer_save_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status'),
                                     (e.get('reqBody') or '')[:500]) for e in L.fetch_log(d)]
    st, p, _ = L.api_json(d, '/testcases/' + A_ID)
    x = (p or {}).get('data') or {}
    OUT['a_after'] = {k: str(x.get(k))[:200] for k in ('name', 'reference_params', 'algorithm_params')}
    OUT['a_config_keys'] = list((x.get('config') or {}).keys())
finally:
    L.save_evidence('final_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

# -*- coding: utf-8 -*-
"""INT-1643 批量播放设备窗（含 Select 闭合态 name/id 判定 + 提交回读）。"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

GROUP = '接线测试_INT1643_目标组'
CASES = {'A': '8bb822a4-243c-4f20-87e5-ae015028d724', 'B': '38a3fa72-1561-425d-b467-9b46ca209e23'}
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


def detail(cid):
    st, p, _ = L.api_json(d, '/testcases/' + cid)
    x = (p or {}).get('data') or p or {}
    cfg = x.get('config') or {}
    return [{'n': r.get('round_number'),
             'audios': [(a.get('audio_id'), a.get('playback_device_id'), a.get('playback_device_name'))
                        for a in (r.get('audios') or [])]} for r in (cfg.get('rounds') or [])]


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
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 15)
    L.js_click(d, hdr)
    time.sleep(5)
    OUT['before'] = {k: detail(v) for k, v in CASES.items()}
    OUT['device_options'] = {}
    # 打开批量修改菜单
    btn = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                              if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None), 15)
    L.js_click(d, btn)
    mi = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")
                             if vis(x) and (x.text or '').strip() == '播放设备'), None), 10)
    L.clear_fetch_log(d)
    L.js_click(d, mi)
    dlg = retry(lambda: find_dialog('批量设置播放设备'), 20)
    time.sleep(0.8)
    # 打开 Select
    tg = retry(lambda: next((e for e in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                             if vis(e) and '请选择设备' in (e.text or '')), None), 12)
    L.js_click(d, tg)
    time.sleep(1.2)
    opts = [(o.text or '').strip() for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if vis(o)]
    OUT['device_options']['list'] = opts
    L.shot(d, 'c01_device_options')
    opt = next((o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")
                if vis(o) and '设备正面（0.5m+0°）' in (o.text or '')), None)
    L.js_click(d, opt)
    time.sleep(1.2)
    # 闭合态文本（P3：应显示设备名而非 id）
    closed = retry(lambda: next((e for e in find_dialog('批量设置播放设备').find_elements(
        By.CSS_SELECTOR, "[role='combobox'], button") if vis(e) and '设备' in (e.text or '')), None), 10)
    OUT['closed_state_text'] = (closed.text or '').strip() if closed else None
    OUT['closed_state_html'] = closed.get_attribute('outerHTML')[:400] if closed else None
    L.shot(d, 'c02_device_closed_state')
    # 应用层级：勾目标人音频
    for lb in find_dialog('批量设置播放设备').find_elements(By.TAG_NAME, 'label'):
        if vis(lb) and '目标人音频' in (lb.text or ''):
            cb = lb.find_elements(By.CSS_SELECTOR, "[role='checkbox']")
            if cb:
                L.js_click(d, cb[0])
            break
    time.sleep(0.6)
    ok = next((b for b in find_dialog('批量设置播放设备').find_elements(By.TAG_NAME, 'button')
               if vis(b) and (b.text or '').strip() == '确定'), None)
    L.js_click(d, ok)
    time.sleep(2.5)
    OUT['toasts'] = L.wait_toast(d, 20)
    OUT['fetch'] = [{'status': e.get('status'), 'req': (e.get('reqBody') or '')[:900],
                     'res': (e.get('resBody') or '')[:400]}
                    for e in L.fetch_log(d) if '/testcases/batch' in (e.get('url') or '')]
    time.sleep(1.5)
    OUT['after'] = {k: detail(v) for k, v in CASES.items()}
finally:
    L.save_evidence('device_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

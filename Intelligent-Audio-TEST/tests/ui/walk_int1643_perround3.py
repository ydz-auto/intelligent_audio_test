# -*- coding: utf-8 -*-
"""INT-1643 打回第 3 轮补充取证：「-1 最后一轮」解析到**实际**最后一轮（3 轮用例差分）。

2 轮用例下「第 2 轮」与「最后一轮」指向同一轮，无法排除「-1 写死第 2 轮」的实现。本脚本建 3 轮
临时用例，逐轮设置里只给「最后一轮」选 1 个维度（权重 90），其余轮次留空：
  - 期望 round_dimensions 键 = {"1":[],"2":[],"3":[],"-1":[{B,90}]}
  - 期望回读：第 3 轮 = [B(90)]，第 1/2 轮空（若落到第 2 轮即证 -1 解析错误）。
造数与用例都在本脚本内创建，收尾见 cleanup_int1643_perround.py。
"""
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

API = 'http://127.0.0.1:15000/api/v1'
GROUP = '接线测试_INT1643_维度组3轮'
CASE = '接线测试_INT1643_逐轮维度3轮'
DIM_B = '打断失败数量'
OUT = {'group': GROUP, 'case': CASE, 'dim_last_round': DIM_B, 'last_round_weight': 90}
d = None


def call(path, method='GET', body=None, timeout=180):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, 'ERR'
    except Exception as e:
        return -1, str(e)


def audio(aid, name, order):
    return {'audio_id': aid, 'audio_name': name, 'spl': 65.0, 'playback_device_id': 5,
            'playback_device_name': '设备正面（0.5m+0°）', 'play_order': order}


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


def menu_items():
    return [x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if vis(x)]


def open_dims_dialog():
    if not menu_items():
        btn = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                                  if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None), 20)
        L.js_click(d, btn)
        retry(lambda: menu_items() or None, 10)
    mi = retry(lambda: next((x for x in menu_items() if (x.text or '').strip() == '评价维度'), None), 12)
    L.clear_fetch_log(d)
    L.js_click(d, mi)
    dlg = retry(lambda: find_dialog('批量设置评估维度'), 25)
    time.sleep(1.0)
    return dlg


def radio(label_kw):
    lb = retry(lambda: next((x for x in find_dialog('批量设置评估维度').find_elements(By.TAG_NAME, 'label')
                             if vis(x) and label_kw in (x.text or '')), None), 12)
    inp = lb.find_elements(By.TAG_NAME, 'input')
    L.js_click(d, inp[0] if inp else lb)
    time.sleep(1.0)


def click_tab(label):
    dlg = find_dialog('批量设置评估维度')
    btn = retry(lambda: next((b for b in dlg.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == label
                              and '关闭' not in (b.get_attribute('aria-label') or '')), None), 12)
    L.js_click(d, btn)
    time.sleep(1.0)


def tab_labels():
    dlg = find_dialog('批量设置评估维度')
    return [t for t in [(b.text or '').strip() for b in dlg.find_elements(By.TAG_NAME, 'button') if vis(b)]
            if t in ('第 1 轮', '第 2 轮', '第 3 轮', '第 4 轮', '最后一轮')]


def chip_click(name):
    dlg = find_dialog('批量设置评估维度')
    cloud = dlg.find_element(By.CSS_SELECTOR, "[data-testid='batch-dim-round-cloud']")
    btn = retry(lambda: next((b for b in cloud.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')
                              if vis(b) and (b.text or '').strip().startswith(name)), None), 10)
    L.js_click(d, btn)
    time.sleep(0.8)
    return (btn.text or '').strip()[:40]


def set_weight(dim_name, value):
    dlg = find_dialog('批量设置评估维度')
    card = retry(lambda: dlg.find_element(
        By.XPATH, ".//button[@aria-label='移除维度 %s']/ancestor::div[contains(@class,'ring-1')][1]" % dim_name), 10)
    el = [i for i in card.find_elements(By.TAG_NAME, 'input') if vis(i)][0]
    old = el.get_attribute('value')
    d.execute_script(
        """
        const el = arguments[0], v = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        """, el, str(value))
    time.sleep(0.6)
    return {'old': old, 'new': el.get_attribute('value')}


def summarize(x):
    cfg = x.get('config') or {}
    return {'case_level_dims': cfg.get('dimensions'),
            'rounds': [{'n': r.get('round_number'),
                        'dims': [{'id': z.get('id'), 'name': z.get('name'),
                                  'weight': z.get('weight'), 'threshold': z.get('threshold')}
                                 for z in (((r.get('evaluation') or {}).get('dimensions')) or [])]}
                       for r in (cfg.get('rounds') or [])]}


def main():
    global d
    # ---- 造数 ----
    s, dd = call('/groups', 'POST', {'name': GROUP, 'description': 'INT-1643 逐轮维度 3 轮取证临时分组（run 结束删除）'})
    gid = ((dd or {}).get('data') or {}).get('id') if isinstance(dd, dict) else None
    if not gid:
        s, dd = call('/groups?per_page=200&page=1')
        gid = next((g['id'] for g in ((((dd or {}).get('data') or {}).get('items')) or []) if g.get('name') == GROUP), None)
    OUT['group_id'] = gid
    body = {'name': CASE, 'description': 'INT-1643 临时用例：-1 最后一轮解析取证（run 结束删除）',
            'group_id': gid, 'tags': [], 'algorithm_type': 'voice_llm',
            'config': {'rounds': [
                {'round_number': 1, 'audios': [audio(1395, 'DD120_...silence_1.wav', 0)],
                 'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': True},
                {'round_number': 2, 'audios': [audio(1394, 'DD120_...response_2.wav', 0)],
                 'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': False},
                {'round_number': 3, 'audios': [audio(1394, 'DD120_...response_2.wav', 1)],
                 'evaluation': {'dimensions': []}, 'record_mode': 'case', 'is_interruption': False},
            ], 'dimensions': []},
            'algorithm_params': [], 'reference_params': []}
    s, dd = call('/testcases', 'POST', body)
    cid = ((dd or {}).get('data') or {}).get('id') if isinstance(dd, dict) else None
    OUT['case_id'] = cid
    if not cid:
        raise RuntimeError('case create failed: %s %s' % (s, dd))
    st, before = call('/testcases/' + cid)
    OUT['before'] = summarize((before or {}).get('data') or {})
    OUT['before_rounds'] = len(OUT['before']['rounds'])

    # ---- UI 走查 ----
    d = L.driver()
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(5)
    hdr = retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 20)
    L.js_click(d, hdr)
    time.sleep(5)

    dlg = open_dims_dialog()
    OUT['dialog_count_text'] = (dlg.text or '')[:120]
    radio('逐轮设置')
    OUT['per_round_tabs'] = tab_labels()
    L.shot(d, 'pr11_three_round_tabs')

    click_tab('最后一轮')
    OUT['last_chip_B'] = chip_click(DIM_B)
    OUT['last_param_B'] = set_weight(DIM_B, 90)
    L.shot(d, 'pr12_three_round_last_only')

    L.clear_fetch_log(d)
    btn = retry(lambda: next((b for b in find_dialog('批量设置评估维度').find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == '确定'), None), 10)
    L.js_click(d, btn)
    OUT['submit_at'] = time.strftime('%H:%M:%S')
    OUT['toasts'] = L.wait_toast(d, 25)
    time.sleep(3)
    fetch = [e for e in L.fetch_log(d) if '/testcases/batch' in (e.get('url') or '')]
    OUT['batch_calls'] = [{'status': e.get('status'), 'reqBody': e.get('reqBody'),
                           'resBody': e.get('resBody')} for e in fetch]
    for e in fetch:
        try:
            payload = json.loads(e.get('reqBody') or '{}')
            OUT['round_dimensions_keys'] = list((payload.get('round_dimensions') or {}).keys())
            OUT['round_dimensions'] = payload.get('round_dimensions')
        except Exception:
            OUT['req_parse_err'] = traceback.format_exc()[-300:]

    st, after = call('/testcases/' + cid)
    OUT['after'] = summarize((after or {}).get('data') or {})
    OUT['after_status'] = st


try:
    main()
except Exception:
    OUT['fatal'] = traceback.format_exc()[-2000:]
finally:
    L.save_evidence('perround3_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

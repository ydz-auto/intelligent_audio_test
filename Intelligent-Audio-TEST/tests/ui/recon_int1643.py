# -*- coding: utf-8 -*-
"""INT-1643 侦察：批量七窗 DOM 结构 + 回收站切换 + 轮次数量。

只读观察（自建夹具除外）：打开每个批量弹窗，抓弹窗文本 / 控件清单 / 截图后关闭。
产物：tests/ui/artifacts/int1643/recon_evidence.json + r*.png
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L
from selenium.webdriver.common.by import By

GROUP = '接线测试_INT1643_批量组'
CASES = ['接线测试_INT1643_批量_A', '接线测试_INT1643_批量_B', '接线测试_INT1643_批量_C']
AUDIOS = [
    {'audio_id': 2095, 'audio_name': 'HJ048_单一环境声音识别-无语义_海浪_女_silence_海浪.wav'},
    {'audio_id': 2096, 'audio_name': 'HJ048_单一环境声音识别-无语义_海浪_女_silence_用户.wav'},
    {'audio_id': 2099, 'audio_name': 'HJ050_单一环境声音识别-无语义_枪声_女_silence_枪声.wav'},
]
DEV = {'playback_device_id': 4, 'playback_device_name': '设备正右斜侧（4m+45°）'}
OUT = {'steps': []}


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
    L.save_evidence('recon_evidence', OUT)


def build_config(idx):
    return {
        'rounds': [
            {'round_number': n, 'record_mode': 'case', 'audios': [dict(
                AUDIOS[(idx + n) % len(AUDIOS)],
                spl=65.0, play_order=0, **DEV)], 'evaluation': {'dimensions': []}}
            for n in (1, 2)
        ],
        'background_noise': {'audio_id': None, 'spl': 60.0},
        'dimensions': [],
    }


def make_fixtures(d):
    OUT['fixtures'] = []
    for i, name in enumerate(CASES):
        st, p, raw = L.api_json(d, '/testcases', 'POST', {
            'name': name, 'group': GROUP, 'tags': [], 'algorithmType': 'voice_llm',
            'config': build_config(i)})
        cid = (p or {}).get('data', {}).get('id') if isinstance(p, dict) else None
        OUT['fixtures'].append({'name': name, 'status': st, 'id': cid, 'raw': (raw or '')[:200]})


def open_group(d):
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 30)
    L.js_click(d, trig)
    time.sleep(1.2)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 20)
    L.js_click(d, opt)
    time.sleep(5)


def group_header(d):
    return retry(lambda: next((e for e in d.find_elements(
        By.XPATH, "//span[normalize-space(.)='%s']/ancestor::div[contains(@class,'cursor-pointer')][1]" % GROUP)
        if vis(e)), None), 20)


def dialog_inventory(dlg):
    inv = {'text': (dlg.text or '')[:1500], 'inputs': [], 'selects': [], 'buttons': [], 'checks': [], 'tabs': []}
    for i in dlg.find_elements(By.TAG_NAME, 'input'):
        if vis(i):
            inv['inputs'].append({'aria': i.get_attribute('aria-label'), 'ph': i.get_attribute('placeholder'),
                                  'type': i.get_attribute('type'), 'val': i.get_attribute('value')})
    for s in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox'], [data-slot='select-trigger'], button[role='combobox']"):
        if vis(s):
            inv['selects'].append({'text': (s.text or '')[:60], 'aria': s.get_attribute('aria-label')})
    for b in dlg.find_elements(By.TAG_NAME, 'button'):
        if vis(b):
            inv['buttons'].append((b.text or '').strip()[:40])
    for c in dlg.find_elements(By.CSS_SELECTOR, "[role='checkbox'], [role='switch'], [role='radio']"):
        if vis(c):
            inv['checks'].append({'role': c.get_attribute('role'), 'text': (c.text or '')[:30]})
    for t in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if vis(t):
            inv['tabs'].append((t.text or '').strip()[:40])
    return inv


def find_dialog(d, keyword):
    ds = [x for x in L.dialogs(d) if keyword in (x.text or '')]
    return ds[-1] if ds else None


def close_dialog(d):
    for x in L.dialogs(d):
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if (c.text or '').strip() in ('取消', 'Close') and vis(c):
                try:
                    L.js_click(d, c)
                except Exception:
                    pass
                time.sleep(1)
                return


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)
    make_fixtures(d)
    log('fixtures', items=OUT['fixtures'])
    d.get(L.BASE + '/testcases')
    time.sleep(6)
    open_group(d)
    log('group_opened', tail=L.body_text(d)[-300:])
    hdr = group_header(d)
    if hdr is None:
        raise RuntimeError('group header not found')
    L.js_click(d, hdr)
    time.sleep(6)
    log('expanded', tail=L.body_text(d)[-400:])
    # 批量修改下拉按钮
    batch = retry(lambda: next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                                if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None), 20)
    L.js_click(d, batch)
    time.sleep(1.5)
    menu = [x.text for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if vis(x)]
    OUT['batch_menu'] = menu
    log('batch_menu', items=menu)
    items = {}
    for label in ['调整分组', '用例专属参数', '播放设备', '声压', '评价维度', '管理标签', '噪声']:
        # 重新打开菜单
        b2 = next((b for b in d.find_elements(By.CSS_SELECTOR, 'button[aria-label]')
                   if vis(b) and '批量修改' in (b.get_attribute('aria-label') or '')), None)
        if not b2:
            log('menu_btn_missing', label=label)
            continue
        L.js_click(d, b2)
        time.sleep(1.2)
        mi = next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']")
                   if vis(x) and (x.text or '').strip() == label), None)
        if mi is None:
            log('menu_item_missing', label=label, avail=[x.text for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if vis(x)])
            continue
        L.clear_fetch_log(d)
        L.js_click(d, mi)
        time.sleep(4)
        dlg = None
        for kw in ('批量调整分组', '批量设置用例专属参数', '批量设置播放设备', '批量设置声压级',
                   '批量设置评估维度', '批量管理标签', '批量设置噪声'):
            cand = find_dialog(d, kw)
            if cand is not None:
                dlg = cand
                name = kw
                break
        if dlg is None:
            log('dialog_missing', label=label, dialogs=[(x.text or '')[:200] for x in L.dialogs(d)])
        else:
            L.shot(d, 'r_%s' % label)
            items[label] = dialog_inventory(dlg)
            items[label]['fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status'))
                                     for e in L.fetch_log(d)]
            items[label]['dialog_name'] = name
            log('dialog', label=label, inv=items[label])
        close_dialog(d)
        time.sleep(1)
    OUT['dialogs'] = items
    # 回收站 toggle 行为
    L.clear_fetch_log(d)
    trash = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                                if vis(b) and (b.text or '').strip() == '回收站'), None), 15)
    L.js_click(d, trash)
    time.sleep(6)
    LOG_TRASH = L.body_text(d)[-500:]
    L.shot(d, 'r_trash_view')
    OUT['trash_view_text'] = LOG_TRASH
    OUT['trash_fetch'] = [(e.get('method'), (e.get('url') or '')[:80], e.get('status')) for e in L.fetch_log(d)]
    log('trash_view', text=LOG_TRASH, fetch=OUT['trash_fetch'])
finally:
    L.save_evidence('recon_evidence', OUT)
    try:
        d.quit()
    except Exception:
        pass

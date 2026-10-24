# -*- coding: utf-8 -*-
"""INT-1643 续测第三批：抽屉五步（A）+ 参考参数真实错误态（B）。

分组头部展开 + 卡片加载都按轮询等待（真实库栈列表偶发 50s+）。
"""
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
GROUP = '接线测试_INT1643_目标组'
C_NAME = '接线测试_INT1643_批量_C'
REAL_KW = 'DD100'
OUT = {}


def vis(e):
    try:
        return e.is_displayed()
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


def boot(url='/testcases'):
    d = L.driver()
    d.get(L.BASE + '/login')
    time.sleep(6)
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '进入工作台':
            L.js_click(d, b)
            time.sleep(3)
            break
    d.get(L.BASE + url)
    time.sleep(8)
    return d


def pick_group(d):
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 90)
    L.js_click(d, trig)
    time.sleep(1.5)
    opt = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                              if vis(b) and (b.text or '').strip() == GROUP), None), 30)
    L.js_click(d, opt)
    hdr = retry(lambda: next((e for e in d.find_elements(By.XPATH,
        "//*[normalize-space(.)='%s']/ancestor::*[contains(@class,'cursor-pointer')][1]" % GROUP) if vis(e)), None), 120)
    time.sleep(2)
    L.js_click(d, hdr)
    retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
                        if vis(x)), None), 120)
    time.sleep(2)


def open_edit(d, name_kw, timeout=60):
    def find_btn():
        for card in d.find_elements(By.XPATH, "//*[contains(text(), '%s')]/ancestor::div[.//button[@aria-label='编辑用例']][1]" % name_kw):
            if not vis(card):
                continue
            for b in card.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']"):
                if vis(b):
                    return b
        return None
    b = retry(find_btn, timeout)
    L.js_click(d, b)
    return retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                               if vis(x) and any((t.text or '').strip() == '参考参数'
                                                 for t in x.find_elements(By.CSS_SELECTOR, "[role='tab']"))), None), 60)


def tab_click(d, drawer, label):
    t = next((x for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.text or '').strip() == label), None)
    if t is None:
        return False
    L.js_click(d, t)
    time.sleep(1.5)
    return True


def close_dialogs(d):
    for x in d.find_elements(By.CSS_SELECTOR, "[role='dialog'],[role='alertdialog']"):
        if not vis(x):
            continue
        for c in x.find_elements(By.TAG_NAME, 'button'):
            if vis(c) and (c.text or '').strip() in ('取消', '关闭'):
                L.js_click(d, c)
                time.sleep(0.8)
                return


def phase_a():
    ph = {}
    d = boot()
    try:
        pick_group(d)
        drawer = open_edit(d, C_NAME)
        ph['tabs'] = [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
        texts = {}
        for i, label in enumerate(['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'], 1):
            if not tab_click(d, drawer, label):
                texts[label] = 'TAB_MISSING'
                continue
            L.shot(d, 'A%d_%s' % (i, label))
            texts[label] = (drawer.text or '')[-800:]
            if label == '音频列表':
                combos = [e for e in drawer.find_elements(By.CSS_SELECTOR, "[role='combobox']") if vis(e)]
                ph['combobox_texts'] = [(e.text or '').strip()[:100] for e in combos][:10]
                ph['device_name_in_closed'] = any('通道' in (e.text or '') for e in combos)
                ph['raw_id_only'] = any((e.text or '').strip().isdigit() for e in combos)
            if label == '噪声与干扰':
                ph['noise_demo_hint'] = '演示提示条' in (drawer.text or '')
            if label == '参考参数':
                ph['ref_initial_seen'] = '加载参考参数' in (drawer.text or '')
                L.clear_fetch_log(d)
                time.sleep(4)
                ph['ref_text'] = (drawer.text or '')[-600:]
                ph['ref_fake_path'] = '/data/ref_params/' in (drawer.text or '')
                ph['ref_fetch'] = [(e.get('method'), (e.get('url') or '')[:100], e.get('status'))
                                   for e in L.fetch_log(d, 'ref-params')]
                L.shot(d, 'A6_ref_after')
        ph['step_texts'] = texts
        L.apply_theme(d, 'dark')
        L.shot(d, 'A7_drawer_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


def phase_b():
    ph = {}
    d = boot()
    try:
        inp = retry(lambda: next((i for i in d.find_elements(By.TAG_NAME, 'input')
                                  if vis(i) and '搜索' in (i.get_attribute('placeholder') or '')), None), 60)
        L.js_click(d, inp)
        inp.send_keys(Keys.CONTROL, 'a')
        inp.send_keys(Keys.DELETE)
        inp.send_keys(REAL_KW)
        retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "button[aria-label='编辑用例']")
                            if vis(x) and REAL_KW in (x.get_attribute('aria-label') or '')), None), 120)
        L.clear_fetch_log(d)
        drawer = open_edit(d, REAL_KW)
        ph['tabs'] = [(x.text or '').strip() for x in drawer.find_elements(By.CSS_SELECTOR, "[role='tab']") if vis(x)]
        tab_click(d, drawer, '参考参数')
        L.shot(d, 'B1_ref_initial')
        time.sleep(6)
        ph['ref_text'] = (drawer.text or '')[-800:]
        ph['has_error_text'] = '参考参数内容读取失败' in (drawer.text or '')
        ph['has_retry'] = any((b.text or '').strip() == '重试' for b in drawer.find_elements(By.TAG_NAME, 'button'))
        ph['fetch'] = [(e.get('method'), (e.get('url') or '')[:120], e.get('status'))
                       for e in L.fetch_log(d, 'ref-params')]
        L.shot(d, 'B2_ref_error')
        L.apply_theme(d, 'dark')
        L.shot(d, 'B3_ref_error_dark')
        L.apply_theme(d, 'light')
        close_dialogs(d)
    except Exception:
        ph['error'] = traceback.format_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
    return ph


for name, fn in [('A_drawer', phase_a), ('B_ref_error', phase_b)]:
    try:
        OUT[name] = fn()
    except Exception:
        OUT[name] = {'fatal': traceback.format_exc()}
    print('PHASE_DONE', name, flush=True)

L.save_evidence('finalize3_evidence', OUT)
print(json.dumps({k: {kk: str(vv)[:400] for kk, vv in (v or {}).items()} for k, v in OUT.items()},
                 ensure_ascii=False, indent=1)[:7000])

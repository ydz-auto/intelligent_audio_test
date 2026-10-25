# -*- coding: utf-8 -*-
"""INT-1538 抽屉 recon：新增用例抽屉五步 + 音频库弹窗的可操作控件。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

OUT = {}


def step_snapshot(tag):
    body = None
    for dlg in L.dialogs(d):
        if '测试用例' in (dlg.text or ''):
            body = dlg
            break
    if body is None:
        OUT[tag] = {'error': 'no drawer'}
        return
    data = {
        'text': (body.text or '')[:2500],
        'buttons': [b.text.strip() for b in body.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()],
        'inputs': [(i.get_attribute('id'), i.get_attribute('placeholder'), i.get_attribute('type'), i.get_attribute('aria-label')) for i in body.find_elements(By.TAG_NAME, 'input')],
        'selects': [s.text.strip() for s in body.find_elements(By.CSS_SELECTOR, "[role='combobox']")],
        'tabs': [t.text.strip() for t in body.find_elements(By.CSS_SELECTOR, "[role='tab']")],
    }
    OUT[tag] = data


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)
    # 点「新增用例」
    btn = WebDriverWait(d, 30).until(lambda x: next((b for b in x.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip() == '新增用例'), None))
    L.js_click(d, btn)
    time.sleep(2)
    step_snapshot('step1_algo')
    L.shot(d, 'recon_drawer_step1')

    # 打开音频库弹窗（先切到音频列表）
    dlg = L.wait_dialog(d, '新增测试用例')
    for t in dlg.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (t.text or '').strip() == '音频列表':
            L.js_click(d, t)
            break
    time.sleep(1.5)
    step_snapshot('step2_audio')
    L.shot(d, 'recon_drawer_step2')
    btn = next((b for b in dlg.find_elements(By.TAG_NAME, 'button') if '从音频库选择' in (b.text or '')), None)
    OUT['audio_entry'] = bool(btn)
    L.js_click(d, btn)
    time.sleep(4)
    inner = [x for x in L.dialogs(d) if '选择音频文件' in (x.text or '')]
    if inner:
        w = inner[0]
        OUT['audio_dialog'] = {
            'text': (w.text or '')[:2500],
            'buttons': [b.text.strip() for b in w.find_elements(By.TAG_NAME, 'button') if (b.text or '').strip()],
            'inputs': [(i.get_attribute('placeholder'), i.get_attribute('aria-label')) for i in w.find_elements(By.TAG_NAME, 'input')],
            'checkboxes': len(w.find_elements(By.CSS_SELECTOR, "[role='checkbox']")),
            'rows': len(w.find_elements(By.CSS_SELECTOR, 'table tbody tr')),
        }
    else:
        OUT['audio_dialog'] = {'error': 'not found', 'dialogs': [x.text[:200] for x in L.dialogs(d)]}
    L.shot(d, 'recon_audio_dialog')
finally:
    L.save_evidence('recon_drawer', OUT)
    try:
        d.quit()
    except Exception:
        pass

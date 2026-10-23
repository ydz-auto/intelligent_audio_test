# -*- coding: utf-8 -*-
"""INT-1477：批量评估维度「逐轮设置」轮次数与选中用例真实轮次对照（MOCK_ROUND_COUNT 判定）。"""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1477_crud_batch as M

d = M.driver()
try:
    M.reload_page(d)
    M.expand_group(d, M.current_group(d))
    log = M.log
    picked = M.select_cases(d, M.NAMES)
    log('picked', picked)
    # 选中用例的真实轮次（API）
    for n in M.NAMES:
        hits = M.list_cases(d, n)
        if hits:
            cfg = hits[0].get('config') or {}
            log('  ', n, 'rounds=', len(cfg.get('rounds') or []))
    M.clear_log(d)
    M.click_text(d, '批量设置评估维度', 'button')
    time.sleep(2)
    # 切到「逐轮设置」
    try:
        M.click_text(d, '逐轮设置（每轮可不同）', 'button', exact=False, timeout=8)
    except Exception as e:
        log('  tab switch fail', e)
    time.sleep(2)
    M.shot(d, 'crud_batch_dims_per_round')
    tabs = [e.text for e in d.find_elements(By.XPATH, "//*[@role='tab']") if e.is_displayed()]
    log('  visible tabs:', tabs)
    # 对话框内所有轮次按钮（第N轮）
    body = M.dialog_text(d)
    log('  dialog text:', body[:800].replace('\n', ' | '))
    ones = [t for t in tabs if '轮' in t]
    M.clear_log(d)
    try:
        M.click_text(d, '确定', 'button', timeout=8)
        time.sleep(3)
    except Exception as e:
        log('  confirm fail', e)
    cs = M.calls(d)
    M.rec('batch-dimensions-dialog', '逐轮设置：轮次 Tab 数与用例真实轮次对照（用例各 1 轮）', cs,
          {'tabs': tabs, 'dialog': body[:600]})
    log('  calls:', M.show(cs))
finally:
    d.quit()
ev = os.path.join(M.ART, 'dims_probe.json')
json.dump({'tabs_note': 'see evidence'}, open(ev, 'w', encoding='utf-8'), ensure_ascii=False)

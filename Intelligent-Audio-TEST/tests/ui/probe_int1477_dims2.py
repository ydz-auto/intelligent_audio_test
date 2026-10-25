# -*- coding: utf-8 -*-
"""INT-1477：批量评估维度「逐轮设置」实际轮次 Tab 数（用例各 1 轮）取证。"""
import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1477_crud_batch as M

d = M.driver()
try:
    M.reload_page(d)
    M.expand_group(d, M.current_group(d))
    M.select_cases(d, M.NAMES)
    M.click_text(d, '批量设置评估维度', 'button'); time.sleep(2)
    # 点「逐轮设置（每轮可不同）」文本（radio 行）
    el = M.find(d, '逐轮设置（每轮可不同）', '*', True, 6)
    M.jsclick(d, el); time.sleep(2)
    M.shot(d, 'crud_batch_dims_per_round')
    tabs = [e.text.strip() for e in d.find_elements(By.XPATH, "//*[@role='tab']")
            if e.is_displayed() and '轮' in (e.text or '')]
    btn = [e.text.strip() for e in d.find_elements(By.XPATH, "//button")
           if e.is_displayed() and '轮' in (e.text or '') and len((e.text or '').strip()) < 8]
    M.log('  tabs:', tabs, '| btn:', btn)
    M.rec('batch-dimensions-dialog', '逐轮设置轮次 Tab（选中用例各 1 轮）',
          [], {'round_tabs': tabs or btn})
finally:
    d.quit()

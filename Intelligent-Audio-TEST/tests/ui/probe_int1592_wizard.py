# -*- coding: utf-8 -*-
"""INT-1592 向导拾取探测：点「开始挑选」，观察阶段/候选渲染。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium.webdriver.common.by import By  # noqa: E402

from verify_int1592_cherry_pick import ART, BASE, body_text, driver, js_click, shot  # noqa: E402

d = driver()
try:
    d.get(BASE + '/tasks/cherry-picks')
    time.sleep(6)
    btns = [b for b in d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '开始挑选')]") if b.is_displayed()]
    print('start buttons:', len(btns))
    js_click(d, btns[0])
    for i in range(6):
        time.sleep(5)
        print('--- t=%ds ---' % ((i + 1) * 5))
        print(body_text(d)[:700])
    shot(d, 'probe_wizard_pick.png')
finally:
    d.quit()

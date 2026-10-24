# -*- coding: utf-8 -*-
"""INT-1494 深色态补拍 + 页面非空校验（aichat/rankings/reports）。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, BASE, body_text, driver, goto, result,  # noqa: E402
                             set_theme, shot)

R = []
d = driver()
try:
    set_theme(d, 'dark')
    out = {}
    for path, name, marker in (('/ai-chat', 'aichat_empty_dark', '灵犀Agent'),
                               ('/rankings', 'rankings_dark', '排行榜'),
                               ('/reports', 'reports_dark', '浏览测试报告'),
                               ('/about', 'about_dark', '关于智能语音测试平台')):
        goto(d, path, wait_text=marker, timeout=40)
        time.sleep(5)
        t = body_text(d)
        p = shot(d, name)
        out[name] = {'len': len(t), 'head': t[:120], 'file': os.path.basename(p),
                     'dark': d.execute_script("return document.documentElement.className;")}
    # /ai-chat 供应商弹窗深色（空态按钮打开）
    goto(d, '/ai-chat', wait_text='灵犀Agent')
    time.sleep(3)
    trig = None
    for b in d.find_elements(By.CSS_SELECTOR, 'button, [role=button]'):
        txt = (b.text or '') + (b.get_attribute('aria-label') or '')
        if '未配置' in txt and b.is_displayed():
            trig = b
            break
    if trig is not None:
        d.execute_script('arguments[0].click();', trig)
        time.sleep(2)
        p = shot(d, 'aichat_manager_dark')
        out['manager_dark'] = {'file': os.path.basename(p),
                               'text': 'LLM 供应商管理' in body_text(d)}
    R.append(result('dark_recapture', all(v['len'] > 100 for v in out.values()
                                          if isinstance(v, dict) and 'len' in v), out))
finally:
    d.quit()

with open(os.path.join(ARTIFACTS, 'int1494_dark.json'), 'w', encoding='utf-8') as f:
    json.dump(R, f, ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2))

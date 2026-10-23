# -*- coding: utf-8 -*-
"""INT-1494 文档中心交互（目录锚点/代码块复制）+ 关于页文档链接跳转。"""
import json, os, sys, time
from selenium.webdriver.common.by import By
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from int1494_helpers import (ARTIFACTS, BASE, body_text, driver, goto, js_click,
                             result, set_theme, shot)
R = []
d = driver()
try:
    set_theme(d, 'light')
    st, shots = {}, []
    # 文档中心：目录锚点 + 代码块复制
    goto(d, '/user-guide-api', wait_text='API 手册')
    time.sleep(2)
    before = d.execute_script('return window.scrollY')
    anchor = None
    for a in d.find_elements(By.CSS_SELECTOR, 'nav a[href^="#"], aside a[href^="#"]'):
        if '认证' in (a.text or ''):
            anchor = a
            break
    if anchor is not None:
        js_click(d, anchor)
        time.sleep(1.5)
        st['scroll_delta'] = d.execute_script('return window.scrollY') - before
    pres = d.find_elements(By.CSS_SELECTOR, 'pre')
    st['pre_count'] = len(pres)
    st['first_pre'] = pres[0].text[:200] if pres else ''
    # 复制按钮（guide-code-block）
    copy = None
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        t = (b.text or '') + (b.get_attribute('aria-label') or '')
        if '复制' in t:
            copy = b
            break
    if copy is not None:
        js_click(d, copy)
        time.sleep(1.5)
        st['copy_feedback'] = '已复制' in body_text(d) or '复制成功' in body_text(d)
    shots.append(shot(d, 'guide_api_anchor_light'))
    # 关于页文档链接
    goto(d, '/about', wait_text='关于智能语音测试平台')
    time.sleep(2)
    links = {a.text.strip(): a.get_attribute('href') for a in d.find_elements(By.CSS_SELECTOR, 'a[href]')}
    st['about_links'] = {k: v for k, v in links.items() if k in ('使用手册', 'API 手册', '接入指南', '报告中心')}
    tgt = None
    for a in d.find_elements(By.CSS_SELECTOR, 'a[href]'):
        if (a.text or '').strip() == 'API 手册':
            tgt = a
            break
    if tgt is not None:
        js_click(d, tgt)
        time.sleep(3)
        st['after_click_url'] = d.current_url
        shots.append(shot(d, 'about_to_guide_light'))
    R.append(result('guides_about', True, st, shots))
finally:
    d.quit()
json.dump(R, open(os.path.join(ARTIFACTS, 'int1494_guides_about.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps(R, ensure_ascii=False, indent=2))

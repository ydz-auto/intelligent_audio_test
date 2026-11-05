# -*- coding: utf-8 -*-
"""INT-2387 补充探针：动作组按钮可用性 / 任务名链接跳转 / 窄视口无横向溢出。"""
import json
import os
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int2387_report_header as lib  # noqa: E402

BASE = lib.BASE
token = lib.get_token()
drv = lib._driver()
out = {}
try:
    drv.get(BASE + '/login')
    time.sleep(1.5)
    drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', lib.TOKEN_KEY, token)
    drv.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);', lib.THEME_KEY, 'light')
    drv.get(BASE + '/report/426?from=management')
    lib.wait_ready(drv)

    # 1) 动作组按钮：10 个，全部可见可用
    btns = drv.find_elements(By.CSS_SELECTOR, 'div.bg-card button')
    info = [{'text': (b.text or b.get_attribute('aria-label') or '').strip(),
             'displayed': b.is_displayed(), 'enabled': b.is_enabled()} for b in btns]
    out['buttons'] = info
    print('buttons=%d allDisplayed=%s allEnabled=%s' % (
        len(info), all(i['displayed'] for i in info), all(i['enabled'] for i in info)))
    print('  ' + json.dumps([i['text'] for i in info], ensure_ascii=False))

    # 2) 任务名链接可点击跳转
    link = drv.find_element(By.XPATH, "//div[contains(@class,'bg-card')]//a[contains(@href,'/tasks')]")
    href = link.get_attribute('href')
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", link)
    time.sleep(0.4)
    drv.execute_script('arguments[0].click()', link)
    time.sleep(3)
    out['taskLink'] = {'href': href, 'urlAfterClick': drv.current_url,
                       'bodyHasTask': '任务' in drv.find_element(By.TAG_NAME, 'body').text[:400]}
    print('taskLink -> %s (href=%s)' % (drv.current_url, href))

    # 3) 窄视口横向溢出
    over = {}
    for w, h in [(1024, 768), (1440, 900), (2560, 1440)]:
        drv.get(BASE + '/report/426?from=management')
        lib.wait_ready(drv)
        drv.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',
                            {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': False})
        time.sleep(1.5)
        over['%dx%d' % (w, h)] = drv.execute_script(
            'return {vw: innerWidth, scrollW: document.documentElement.scrollWidth,'
            ' h1w: Math.round(document.querySelector("h1").getBoundingClientRect().width*10)/10,'
            ' h1lines: (function(){var r=document.createRange();r.selectNodeContents(document.querySelector("h1"));'
            ' return Array.prototype.filter.call(r.getClientRects(),function(x){return x.width>0&&x.height>0}).length;})()'
            '}')
    out['viewportOverflow'] = over
    for k, v in over.items():
        print('  %s -> %s (overflow=%s)' % (k, v, v['scrollW'] > v['vw']))
finally:
    drv.quit()

with open(os.path.join(lib.ART, 'probe_extras.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

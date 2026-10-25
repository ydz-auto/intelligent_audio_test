# -*- coding: utf-8 -*-
"""INT-1477 探针2：展开最小分组，摸清用例卡勾选/预览/批量入口的 DOM。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    return webdriver.Chrome(options=o, service=Service(path) if path else Service())


d = driver()
try:
    d.get(BASE + '/testcases/by-group')
    time.sleep(6)
    # 展开最后一个分组（音频上传生成 3 条）
    hdrs = [e for e in d.find_elements(By.XPATH, "//*[contains(text(),'条') and (self::button or self::div or self::span)]") if e.is_displayed()]
    for h in hdrs[:15]:
        t = (h.text or '').replace('\n', ' ')
        print('CAND:', h.tag_name, repr(t[:60]))
    # 点包含「音频上传生成」的元素
    el = d.find_element(By.XPATH, "//*[normalize-space(text())='音频上传生成']")
    print('group el:', el.tag_name, el.get_attribute('class')[:80])
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    time.sleep(2)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('AFTER EXPAND tail:', body[-800:].replace('\n', ' | '))
    print('--- checkboxes ---')
    for c in d.find_elements(By.CSS_SELECTOR, "[role=checkbox]"):
        print('cb aria=', c.get_attribute('aria-label'), 'checked=', c.get_attribute('aria-checked'), 'vis=', c.is_displayed(),
              'html=', c.get_attribute('outerHTML')[:120])
    print('--- buttons now ---')
    seen = set()
    for b in d.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip().replace('\n', ' ')
        a = b.get_attribute('aria-label') or ''
        if (t or a) and (t, a) not in seen and b.is_displayed():
            seen.add((t, a))
            print(repr(t), '| aria=', a)
finally:
    d.quit()

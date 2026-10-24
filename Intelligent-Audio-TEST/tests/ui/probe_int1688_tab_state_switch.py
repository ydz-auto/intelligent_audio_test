# -*- coding: utf-8 -*-
"""INT-1688 复测补充：同一页内先看 7 轮用例切到「整体」再打开单轮用例，看默认 Tab 是否复位。

仅记录现象（P3 判定用），不做断言失败退出。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15288').rstrip('/')
MULTI_FRAG = 'DD139_多次打断'
SINGLE_FRAG = 'JG0006_单轮接管'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def build_driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1920,1200')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    import winreg
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        cands = [(int(v.split('.')[0]), os.path.join(cache, v, 'chromedriver.exe'))
                 for v in os.listdir(cache)
                 if os.path.isfile(os.path.join(cache, v, 'chromedriver.exe'))]
        same = [p for m, p in cands if m == major]
        if same:
            exe = max(same)
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_page_load_timeout(240)
    return d


def body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def wait_text(drv, t, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        if t in body(drv):
            return
        time.sleep(1)
    raise RuntimeError('timeout waiting ' + t)


def search_and_open(drv, frag):
    box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
    box.click()
    box.send_keys(Keys.CONTROL + 'a')
    box.send_keys(Keys.BACKSPACE)
    time.sleep(0.6)
    box.send_keys(frag)
    time.sleep(3.0)
    btn = drv.find_elements(By.XPATH, "//button[starts-with(@title,'查看用例详情：')]")[0]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
    wait_text(drv, '执行结果与指标')
    time.sleep(2.0)


def tab_state(drv):
    return drv.execute_script(r"""
    const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
    if (!dlg) return null;
    const tl = dlg.querySelector('[role="tablist"]');
    return {
      tabs: tl ? [...tl.querySelectorAll('[role="tab"]')].map(t => ({
        label: (t.textContent||'').trim(), selected: t.getAttribute('aria-selected') === 'true'})) : [],
      heads: [...dlg.querySelectorAll('thead th')].map(t => (t.textContent||'').trim()),
      firstRow: (() => { const tr = dlg.querySelector('tbody tr');
        return tr ? [...tr.querySelectorAll('td')].map(td => (td.textContent||'').trim()) : []; })(),
    };
    """)


def main():
    drv = build_driver()
    out = {}
    try:
        drv.get(BASE + '/tasks/402')
        for attempt in range(3):
            try:
                wait_text(drv, '关联用例', 120)
                break
            except RuntimeError:
                print('retry load, body=', body(drv)[:200])
                drv.refresh()
                time.sleep(2)
        else:
            raise RuntimeError('tasks page never loaded')
        time.sleep(4)
        # 1) 多轮用例 → 切到「整体」
        search_and_open(drv, MULTI_FRAG)
        tab = drv.find_element(
            By.XPATH, "//*[@data-slot='case-detail-dialog']//*[@role='tab'][normalize-space(.)='整体']")
        drv.execute_script("arguments[0].click()", tab)
        time.sleep(1.5)
        out['multi_after_click'] = tab_state(drv)
        # 2) 关掉弹窗（不刷新页面）
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(1.5)
        # 3) 同页换单轮用例
        search_and_open(drv, SINGLE_FRAG)
        out['single_after_switch'] = tab_state(drv)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688_tabs',
                         'T_tab_state_after_case_switch.png')
        drv.save_screenshot(p)
        print('shot:', p)
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""INT-1688 A/B 对照：共享 15173（旧镜像，不含本卡修复）同一路径的弹窗形态。"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173').rstrip('/')
ART = os.environ.get(
    'ART_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688'),
)
CASE_FRAG = 'JG0006_单轮接管-正常接管'
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
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        cands = []
        for ver in os.listdir(cache):
            p = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(p):
                cands.append((int(ver.split('.')[0]), p))
        same = [p for m, p in cands if m == major]
        if same:
            exe = max(same)
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    d.set_page_load_timeout(180)
    return d


def main():
    drv = build_driver()
    try:
        drv.get(BASE + '/tasks/402')
        for _ in range(120):
            if '关联用例' in (drv.execute_script('return document.body.textContent') or ''):
                break
            time.sleep(1)
        time.sleep(3)
        box = drv.find_element(By.XPATH, "//input[@placeholder='搜索用例名称或 ID…']")
        drv.execute_script('arguments[0].click()', box)
        box.send_keys(CASE_FRAG)
        time.sleep(3)
        btn = drv.find_element(
            By.XPATH,
            "//button[starts-with(@title,'查看用例详情：')][contains(@title,'%s')]" % CASE_FRAG)
        drv.execute_script('arguments[0].click()', btn)
        time.sleep(5)
        data = drv.execute_script(r"""
        const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
        if (!dlg) return null;
        const t = dlg.querySelector('table');
        return {
          text: (dlg.textContent||'').slice(0, 1200),
          heads: t ? [...t.querySelectorAll('thead th')].map(x=>x.textContent.trim()) : [],
          rows: t ? [...t.querySelectorAll('tbody tr')].map(tr=>[...tr.querySelectorAll('td')].map(td=>td.textContent.trim())) : [],
        };
        """)
        os.makedirs(ART, exist_ok=True)
        p = os.path.join(ART, 'AB_15173_old.png')
        drv.save_screenshot(p)
        print(json.dumps({'base': BASE, 'heads': data['heads'] if data else None,
                          'rows': data['rows'] if data else None,
                          'has_fail_text': ('失败' in (data['text'] if data else '')),
                          'shot': p}, ensure_ascii=False, indent=1))
        with open(os.path.join(ART, 'AB_15173_old.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()

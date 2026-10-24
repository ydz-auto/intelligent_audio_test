# -*- coding: utf-8 -*-
"""INT-1688 A/B 对照（旧镜像 15173）：同一用例弹窗的形态，用于证明验收脚本有区分力。

15173 镜像的 /tasks/{id} 是卡片平铺、无搜索框 → 按卡片正文文本点开。
"""
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
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1688_tabs'),
)
FRAG = os.environ.get('CASE_FRAG', 'JG0006_单轮接管')
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
    try:
        import winreg
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
    d.set_page_load_timeout(240)
    return d


COLLECT = r"""
const dlg = document.querySelector('[data-slot="case-detail-dialog"]');
if (!dlg) return null;
const t = dlg.querySelector('table');
const tablist = dlg.querySelector('[role="tablist"]');
return {
  text: (dlg.textContent||'').slice(0, 1500),
  tabs: tablist ? [...tablist.querySelectorAll('[role="tab"]')].map(x=>(x.textContent||'').trim()) : [],
  heads: t ? [...t.querySelectorAll('thead th')].map(x=>x.textContent.trim()) : [],
  rows: t ? [...t.querySelectorAll('tbody tr')].map(tr=>[...tr.querySelectorAll('td')].map(td=>td.textContent.trim())) : [],
};
"""


def main():
    drv = build_driver()
    try:
        drv.get(BASE + '/tasks/402')
        for _ in range(150):
            if '关联用例' in (drv.execute_script('return document.body.textContent') or ''):
                break
            time.sleep(1)
        time.sleep(4)
        # 旧镜像卡片平铺：点含用例片段文本的卡片
        card = drv.find_element(By.XPATH, "//*[contains(text(),'%s')]" % FRAG)
        drv.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", card)
        for _ in range(60):
            if drv.execute_script("return !!document.querySelector('[data-slot=\"case-detail-dialog\"]')"):
                break
            time.sleep(1)
        # 旧镜像详情接口慢：等骨架屏换成内容（表头「设备」或空态文案）
        for _ in range(150):
            txt = drv.execute_script(
                "const d=document.querySelector('[data-slot=\"case-detail-dialog\"]');"
                "return d ? (d.textContent||'') : ''") or ''
            if '设备' in txt or '暂无执行结果' in txt or '加载失败' in txt:
                break
            time.sleep(1)
        time.sleep(2)
        data = drv.execute_script(COLLECT)
        os.makedirs(ART, exist_ok=True)
        p = os.path.join(ART, 'AB_15173_old.png')
        drv.save_screenshot(p)
        print(json.dumps({
            'base': BASE,
            'tabs': data['tabs'] if data else None,
            'heads': data['heads'] if data else None,
            'rows': data['rows'] if data else None,
            'text_has_fail': ('失败' in (data['text'] if data else '')),
            'has_round_key': ('@round' in (data['text'] if data else '')),
            'shot': p,
        }, ensure_ascii=False, indent=1))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()

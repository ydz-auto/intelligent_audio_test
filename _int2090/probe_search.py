# -*- coding: utf-8 -*-
import os, time, json, winreg
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
BASE='http://localhost:5388'
CHROME=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
options=Options(); options.binary_location=CHROME
options.add_argument('--headless=new'); options.add_argument('--window-size=1680,1050')
options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
chrome_major=0
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
        chrome_major=int(winreg.QueryValueEx(k,'version')[0].split('.')[0])
except Exception: pass
cache_root=os.path.join(os.path.expanduser('~'),'.cache','selenium','chromedriver','win64')
drv_path=''
if chrome_major and os.path.isdir(cache_root):
    cands=[]
    for ver in os.listdir(cache_root):
        exe=os.path.join(cache_root,ver,'chromedriver.exe')
        if os.path.isfile(exe):
            try: cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()),exe))
            except ValueError: continue
    same=[exe for ver,exe in cands if ver and ver[0]==chrome_major]
    if same: drv_path=max(same)
drv=webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())
drv.set_page_load_timeout(45)
try:
    drv.get(BASE+'/login'); time.sleep(3)
    inp=drv.find_elements(By.TAG_NAME,'input'); inp[0].send_keys('admin'); inp[1].send_keys('admin123')
    for b in drv.find_elements(By.TAG_NAME,'button'):
        if '登录' in (b.text or '').replace(' ',''):
            b.click(); break
    time.sleep(3)
    drv.get(BASE+'/tasks/413'); time.sleep(5)
    # list all inputs with aria-label / placeholder
    for i in drv.find_elements(By.TAG_NAME,'input'):
        print('INPUT aria=', i.get_attribute('aria-label'), 'ph=', i.get_attribute('placeholder'), 'visible=', i.is_displayed())
    # try typing into the 搜索用例 input
    try:
        s = drv.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索用例"]')
        s.send_keys('HJ033')
        time.sleep(2)
        btns = drv.find_elements(By.CSS_SELECTOR, 'button[title^="查看用例详情"]')
        print('after search buttons:', len(btns))
        for b in btns[:5]:
            print('  title:', (b.get_attribute('title') or '')[:70])
        # also check the case-count text
        body = drv.execute_script('return document.body.textContent')
        import re
        m = re.search(r'命中 \d+ / 共 \d+', body)
        print('count marker:', m.group(0) if m else None)
    except Exception as e:
        print('search err:', e)
finally:
    drv.quit()

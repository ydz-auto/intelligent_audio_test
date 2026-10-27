# -*- coding: utf-8 -*-
import os, time, winreg
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
    drv.get(BASE+'/login')
    time.sleep(4)
    print('URL:', drv.current_url)
    print('TITLE:', drv.title)
    inputs=drv.find_elements(By.TAG_NAME,'input')
    print('inputs:', [(i.get_attribute('name'), i.get_attribute('type'), i.get_attribute('placeholder')) for i in inputs])
    btns=drv.find_elements(By.TAG_NAME,'button')
    print('buttons:', [b.text for b in btns][:10])
    print('body head:', (drv.execute_script('return document.body ? document.body.textContent.slice(0,300) : "NO BODY"') or '').replace('\n',' '))
    drv.save_screenshot(r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-2090-93d04ec988e4\worktree\_int2090\login_page.png')
finally:
    drv.quit()

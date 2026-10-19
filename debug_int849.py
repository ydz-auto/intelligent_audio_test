# -*- coding: utf-8 -*-
"""INT-849 调试：确认 /APITest 渲染的 TestFlow 模式与 API 数据可用性。"""
import os, re, sys, json
PROJECT_ROOT = r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-849-12feb1d70b3b\worktree\Intelligent-Audio-TEST'
sys.path.insert(0, PROJECT_ROOT)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from tests.ui.pages.base_page import BasePage
from tests.ui.pages.login_page import LoginPage

FRONTEND = 'http://127.0.0.1:7773'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = r'D:\00_code\V9.7.31\Intelligent-Audio-TEST\e2e_tests\selenium\drivers\chromedriver-win32\chromedriver.exe'
cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
if os.path.isdir(cache_root):
    cands = []
    for vd in os.listdir(cache_root):
        exe = os.path.join(cache_root, vd, 'chromedriver.exe')
        if os.path.isfile(exe):
            cands.append((tuple(int(x) for x in re.findall(r'\d+', vd)[:4]), exe))
    if cands:
        cands.sort(reverse=True)
        DRIVER = cands[0][1]
opts = Options()
opts.binary_location = CHROME_BINARY
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1680,1050')
driver = webdriver.Chrome(service=Service(DRIVER), options=opts)
page = BasePage(driver, FRONTEND)
try:
    lp = LoginPage(driver, FRONTEND)
    lp.goto('/login')
    lp.wait_visible(lp.CARD)
    lp.login('admin', 'admin123')
    lp.wait_left_login(timeout=25)
    lp.wait_home_rendered(timeout=25)
    print('[ok] login')

    # 直接刷新加载 #/APITest
    driver.get(FRONTEND + '/#/APITest')
    driver.refresh()
    WebDriverWait(driver, 20).until(lambda d: d.execute_script('return !!window.__VUE__') or True)
    import time; time.sleep(4)
    print('url:', driver.current_url)
    body = driver.execute_script('return document.body.innerText;')
    print('=== body (first 1500) ===')
    print(body[:1500])
    print('=== /apis fetch ===')
    result = driver.execute_script("""
        const token = window.localStorage.getItem('auth_token') || '';
        return fetch('/api/v1/apis?page=1&per_page=5', {headers: {'Authorization': 'Bearer ' + token}})
          .then(r => r.text())
          .then(t => t.slice(0, 1200));
    """)
    print(result)
    # 找 API 相关按钮
    btns = [b.text for b in driver.find_elements(By.CSS_SELECTOR, 'button')]
    print('=== buttons ===')
    for b in btns[:30]:
        print(repr(b))
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    driver.quit()

# -*- coding: utf-8 -*-
"""V9.7.10 Vue 基准对照截图：登录态注入 → 用例管理 → 打开新增用例表单 → 截关键区块。"""
import io, json, os, sys, time, winreg
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = 'http://localhost:15248'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'v9710_compare')
os.makedirs(OUT, exist_ok=True)


def drv_new():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1400')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(root):
        for v in os.listdir(root):
            e = os.path.join(root, v, 'chromedriver.exe')
            if os.path.isfile(e) and v.split('.')[0].isdigit() and int(v.split('.')[0]) == major:
                path = e
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


def txt(d):
    return d.find_element(By.TAG_NAME, 'body').text


d = drv_new()
try:
    d.get(BASE + '/')
    d.execute_script("""
      localStorage.setItem('auth_access_token','dev-off-token');
      localStorage.setItem('auth_refresh_token','dev-off-refresh');
      localStorage.setItem('auth_user', JSON.stringify({id:'dev',username:'dev_user',email:'dev@local',roles:['admin'],isAdmin:true}));
      localStorage.setItem('auth_expires_at', String(Date.now()+86400000));
    """)
    d.get(BASE + '/#/TestCaseManager')
    time.sleep(2)
    d.refresh()
    time.sleep(8)
    if 'TestCaseManager' not in d.current_url:
        d.execute_script("window.location.hash = '#/TestCaseManager'")
        time.sleep(8)
    # 等分组数据渲染（偶发并发时首个请求空，重载一次）
    for attempt in range(3):
        body = txt(d)
        if '话轮接管' in body or '没有找到测试用例分组' not in body:
            break
        time.sleep(6)
    print('TC_URL=', d.current_url)
    print('HAS_GROUP=', '话轮接管' in txt(d))
    d.save_screenshot(os.path.join(OUT, 'vue_testcase_list.png'))

    news = [b for b in d.find_elements(By.XPATH, "//button[contains(., '新增用例')]") if b.is_displayed()]
    print('NEW_BTNS=', len(news))
    if news:
        d.execute_script('arguments[0].click()', news[0])
        time.sleep(4)
        body = txt(d)
        print('MODAL_OPEN=', '用例名称' in body)
        d.save_screenshot(os.path.join(OUT, 'vue_modal_top.png'))
        print('HAS_GLOBAL_NOISE=', '全局背景噪声' in body, 'HAS_OVERALL_DIMS=', '整体评估维度' in body)
        for label, fname in (('全局背景噪声', 'vue_modal_global_noise.png'),
                             ('整体评估维度', 'vue_modal_overall_dims.png')):
            done = False
            for e in d.find_elements(By.XPATH, "//*[contains(normalize-space(.), '%s')]" % label):
                try:
                    if e.is_displayed() and len(e.text.strip()) <= 40:
                        d.execute_script('arguments[0].scrollIntoView({block:"center"})', e)
                        time.sleep(1)
                        d.save_screenshot(os.path.join(OUT, fname))
                        print('SHOT=', fname)
                        done = True
                        break
                except Exception:
                    pass
            if not done:
                print('SHOT_MISS=', label)
finally:
    d.quit()

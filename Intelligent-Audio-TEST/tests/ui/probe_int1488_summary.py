# -*- coding: utf-8 -*-
"""INT-1488 补测：导出弹窗筛选摘要是否显示原始枚举值（分类/模块/标记/算法）。"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1488_ux_audit')


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def pick(d, label, option_text):
    els = [e for e in d.find_elements(By.CSS_SELECTOR, "[aria-label='" + label + "']") if e.is_displayed()]
    js_click(d, els[0])
    time.sleep(0.8)
    for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if o.is_displayed() and (o.text or '').strip() == option_text:
            js_click(d, o)
            time.sleep(2.5)
            return True
    d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    return False


o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1050')
o.add_argument('--no-sandbox')
o.page_load_strategy = 'eager'
cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
p = ''
for v in os.listdir(cache):
    e = os.path.join(cache, v, 'chromedriver.exe')
    if os.path.isfile(e) and v.startswith('155'):
        p = e
d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
d.set_page_load_timeout(90)
try:
    d.get(BASE + '/login')
    time.sleep(2)
    if '/login' not in d.current_url:
        d.get(BASE + '/login')
        time.sleep(2)
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    d.get(BASE + '/logs')
    t0 = time.time()
    while time.time() - t0 < 120 and not d.find_elements(By.CSS_SELECTOR, 'table tbody tr'):
        time.sleep(3)
    print('picked category', pick(d, '分类', '系统日志'), flush=True)
    print('picked module', pick(d, '模块', 'API模块'), flush=True)
    print('picked mark', pick(d, '标记筛选', '黄色标记'), flush=True)
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == '导出日志' and b.is_displayed():
            js_click(d, b)
            break
    time.sleep(1.5)
    dlg = [e for e in d.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()][-1]
    print('SUMMARY', dlg.text.replace('\n', ' | ').encode('ascii', 'replace').decode(), flush=True)
    d.save_screenshot(os.path.join(ART, 'light_14_export_summary_raw.png'))
    print('SHOT light_14_export_summary_raw', flush=True)
finally:
    d.quit()
print('DONE3', flush=True)

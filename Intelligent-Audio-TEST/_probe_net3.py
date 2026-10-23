# -*- coding: utf-8 -*-
import json, time
from selenium import webdriver
from selenium.webdriver.common.by import By

BASE = 'http://127.0.0.1:5411'
DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.79\chromedriver.exe'
opts = webdriver.ChromeOptions()
opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1440,900')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-gpu')
opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
d = webdriver.Chrome(options=opts, service=webdriver.ChromeService(executable_path=DRIVER))
d.get(BASE + '/#/login')
time.sleep(2)
d.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]').send_keys('接线测试_admin')
d.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]').send_keys('JieXianTest@2026')
d.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
time.sleep(5)
d.get(BASE + '/#/AudioImport')
time.sleep(6)
logs = d.get_log('performance')
urls = set()
for l in logs:
    msg = l.get('message', '')
    if 'requestWillBeSent' in msg:
        try:
            m = json.loads(msg[msg.index('{'):])
            url = m['params']['request']['url']
            urls.add(url)
        except Exception:
            pass
for u in sorted(urls):
    print('REQ:', u)
print('TOTAL unique:', len(urls))
d.quit()

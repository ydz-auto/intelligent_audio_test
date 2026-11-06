# -*- coding: utf-8 -*-
"""探针：/testcases 两视图的用例条目可点击选择器。"""
import sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE='http://localhost:15173'
def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    o=Options(); o.binary_location=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new'); o.add_argument('--window-size=1680,1050'); o.add_argument('--no-sandbox'); o.add_argument('--lang=zh-CN')
    d=webdriver.Chrome(options=o, service=Service()); d.set_page_load_timeout(90)
    try:
        d.get(BASE+'/login')
        WebDriverWait(d,45).until(lambda x: x.find_elements(By.ID,'username'))
        d.find_element(By.ID,'username').send_keys('接线测试_admin')
        d.find_element(By.ID,'password').send_keys('JieXianTest@2026')
        d.execute_script('arguments[0].click()', d.find_element(By.CSS_SELECTOR,"button[type='submit']"))
        WebDriverWait(d,45).until(lambda x: '/login' not in x.current_url)
        for route in ('/testcases/by-tag','/testcases/by-group'):
            d.get(BASE+route)
            for wait in range(24):
                time.sleep(2)
                btns=d.find_elements(By.CSS_SELECTOR,'button[title]')
                rows=d.find_elements(By.CSS_SELECTOR,'tbody tr')
                if btns or rows: break
            time.sleep(2)
            body=(d.execute_script('return document.body.innerText') or '')[:400]
            print('=====',route,'url',d.current_url)
            print('buttons-with-title:',[(b.get_attribute('title'),(b.text or '').strip()[:30]) for b in d.find_elements(By.CSS_SELECTOR,'button[title]')][:15])
            print('tbody rows:',len(d.find_elements(By.CSS_SELECTOR,'tbody tr')))
            print('buttons total:', [(b.get_attribute('aria-label'),(b.text or '').strip()[:20]) for b in d.find_elements(By.CSS_SELECTOR,'button')][:15])
            print('body:',body.replace('\n',' | '))
            d.save_screenshot('tests/ui/artifacts/int1701/probe_cases_%s.png'%route.strip('/').replace('/','_'))
    finally:
        d.quit()
main()

# -*- coding: utf-8 -*-
import sys, time, json
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
    o.set_capability('goog:loggingPrefs',{'performance':'ALL','browser':'ALL'})
    d=webdriver.Chrome(options=o, service=Service()); d.set_page_load_timeout(90)
    try:
        d.get(BASE+'/login'); WebDriverWait(d,45).until(lambda x: x.find_elements(By.ID,'username'))
        d.find_element(By.ID,'username').send_keys('接线测试_admin')
        d.find_element(By.ID,'password').send_keys('JieXianTest@2026')
        d.execute_script('arguments[0].click()', d.find_element(By.CSS_SELECTOR,"button[type='submit']"))
        WebDriverWait(d,45).until(lambda x: '/login' not in x.current_url)
        d.get(BASE+'/testcases/by-group')
        time.sleep(6)
        rows=d.find_elements(By.CSS_SELECTOR,'tbody tr')
        print('group rows',len(rows))
        if rows:
            d.execute_script('arguments[0].click()', rows[0])
            for i in range(10):
                time.sleep(1.5)
                btns=d.find_elements(By.CSS_SELECTOR,"button[title]")
                titles=[b.get_attribute('title') for b in btns]
                if any('用例' in (t or '') for t in titles): break
            print('titled buttons:',titles[:20])
            # 点开第一个用例
            target=None
            for b in d.find_elements(By.CSS_SELECTOR,'button[title], a[title]'):
                t=(b.get_attribute('title') or '')
                if t and ('查看' in t or '详情' in t):
                    target=b; break
            print('target title', target.get_attribute('title') if target else None)
            if target:
                d.execute_script('arguments[0].click()', target)
                time.sleep(3)
                dlgs=[x for x in d.find_elements(By.CSS_SELECTOR,'[role="dialog"]') if x.is_displayed()]
                print('dialogs',len(dlgs), (dlgs[0].text[:300].replace('\n',' | ') if dlgs else ''))
                d.save_screenshot('tests/ui/artifacts/int1701/chain2_2_case_detail.png')
            d.save_screenshot('tests/ui/artifacts/int1701/chain2_1_case_list.png')
    finally:
        d.quit()
main()

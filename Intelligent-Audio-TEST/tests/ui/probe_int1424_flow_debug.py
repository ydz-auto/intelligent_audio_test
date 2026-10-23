# -*- coding: utf-8 -*-
"""INT-1424 diagnostic probe: audio select -> confirm -> audio card -> preview button."""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')

def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception: pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    vv = tuple(int(x) for x in ver.split('.') if x.isdigit())
                    if vv and vv[0] == chrome_major: drv_path = exe
                except ValueError: continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45); drv.set_script_timeout(180)
    return drv

def jsclick(drv, el):
    drv.execute_script("arguments[0].click()", el)

def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login'); time.sleep(1.5)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')
        drv.get(BASE + '/login')
        WebDriverWait(drv,20).until(lambda d: len(d.find_elements(By.ID,'username'))>0)
        drv.find_element(By.ID,'username').send_keys('接线测试_admin')
        drv.find_element(By.ID,'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH,"//button[contains(., '登 录')]").click()
        WebDriverWait(drv,25).until(lambda d: '/login' not in d.current_url)
        time.sleep(2.0)
        drv.get(BASE + '/testcases'); time.sleep(3.0)

        newb = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        if not newb:
            print('FAIL_NO_NEW_BTN'); return
        jsclick(drv, newb[0]); time.sleep(2.0)

        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)

        # dump all buttons in drawer
        btns = drv.find_elements(By.CSS_SELECTOR, 'button')
        print('BTN_TEXTS=', json.dumps([b.text for b in btns if b.text][:25], ensure_ascii=False))

        lib = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        print('LIB_COUNT=', len(lib))
        if lib:
            jsclick(drv, lib[0]); time.sleep(2.5)
            # dump dialog: rows, confirm state
            rows = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [role='button'], [role='dialog'] button")
            row_texts = [r.text[:40] for r in rows if r.text]
            print('DIALOG_ROWS=', len(row_texts), json.dumps(row_texts[:8], ensure_ascii=False))
            confirms = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
            print('CONFIRM_COUNT=', len(confirms))
            for c in confirms:
                print('CONFIRM_DISABLED=', c.get_attribute('disabled'))
            # click first checkbox-like row: use buttons with aria-pressed
            sel_rows = drv.find_elements(By.XPATH, "//button[@aria-pressed]")
            print('SELECTABLE_ROWS=', len(sel_rows))
            if sel_rows:
                jsclick(drv, sel_rows[0]); time.sleep(1.0)
                confirms = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
                if confirms:
                    print('CONFIRM_DISABLED_AFTER_SELECT=', confirms[-1].get_attribute('disabled'))
                    jsclick(drv, confirms[-1]); time.sleep(1.5)
                    # check audio cards appeared
                    previews = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='试听']")
                    print('PREVIEW_COUNT_AFTER_ADD=', len(previews))
                    cards = drv.find_elements(By.XPATH, "//*[contains(@class,'tabular-nums')]")
                    print('DURATION_SPANS=', len(cards))
        drv.save_screenshot('tests/ui/int1424_shots/probe_audio_flow.png')
    finally:
        drv.quit()

if __name__ == '__main__':
    main()

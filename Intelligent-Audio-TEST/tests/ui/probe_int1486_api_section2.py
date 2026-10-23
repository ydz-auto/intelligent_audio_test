# -*- coding: utf-8 -*-
"""INT-1486 探针 2：步骤一「选择设备/API」区结构——列出全部 aria-label / 按钮 / 页签，定位 API 卡片入口。只读。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
ART = 'tests/ui/artifacts/int1486'
TOKEN_FILE = os.path.join(ART, 'token.txt')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def make_driver(token):
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = r'D:\00_user_data\.cache\selenium\chromedriver\win64'
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_script_timeout(120)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
    return d


def snapshot(d, tag, out):
    out[tag] = {
        'aria': [e.get_attribute('aria-label') for e in d.find_elements(By.CSS_SELECTOR, '[aria-label]')
                 if e.get_attribute('aria-label')][:80],
        'buttons': [e.text.strip() for e in d.find_elements(By.TAG_NAME, 'button') if e.text.strip()][:80],
        'tabs': [(e.get_attribute('role'), e.text.strip()) for e in d.find_elements(By.CSS_SELECTOR, '[role="tab"], [role="tablist"] button')][:30],
    }


def main():
    token = open(TOKEN_FILE).read().strip()
    d = make_driver(token)
    out = {}
    try:
        d.get(BASE + '/start-test')
        WebDriverWait(d, 90).until(lambda x: '按分组' in (x.execute_script('return document.body.innerText') or ''))
        time.sleep(8)
        snapshot(d, 'initial', out)
        # 逐个点击「选择设备/API」附近的控件与页签
        for label in ['API', 'API 配置', '选择设备/API']:
            for el in d.find_elements(By.XPATH, f"//*[normalize-space(.)='{label}']"):
                try:
                    el.click(); time.sleep(1.5)
                except Exception:
                    pass
        snapshot(d, 'after_click_labels', out)
        # 点击所有 role=tab / 页签按钮
        tabs = [e for e in d.find_elements(By.CSS_SELECTOR, '[role="tab"]') if e.is_displayed()]
        out['tab_texts'] = [t.text for t in tabs]
        for t in tabs:
            try:
                d.execute_script('arguments[0].click()', t); time.sleep(1.5)
            except Exception:
                pass
        snapshot(d, 'after_tabs', out)
        body = d.execute_script('return document.body.innerText')
        out['body_tail'] = [ln for ln in body.splitlines() if ln.strip()][:60]
        d.save_screenshot(os.path.join(ART, 'probe2_api_section_light.png'))
        print(json.dumps(out, ensure_ascii=False, indent=1))
    finally:
        d.quit()


if __name__ == '__main__':
    main()

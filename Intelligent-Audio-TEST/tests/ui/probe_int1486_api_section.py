# -*- coding: utf-8 -*-
"""INT-1486 探针：步骤一 API 区卡片渲染态（是否出现选择框 / 只读说明）。只读，不写数据。"""
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


def main():
    token = open(TOKEN_FILE).read().strip()
    d = make_driver(token)
    out = {}
    try:
        d.get(BASE + '/start-test')
        WebDriverWait(d, 90).until(lambda x: '按分组' in (x.execute_script('return document.body.innerText') or ''))
        time.sleep(8)
        body = d.execute_script('return document.body.innerText')
        out['api_section_lines'] = [ln for ln in body.splitlines() if 'API' in ln][:40]
        out['aria_labels'] = [e.get_attribute('aria-label') for e in
                              d.find_elements(By.CSS_SELECTOR, '[aria-label]')
                              if e.get_attribute('aria-label') and 'API' in e.get_attribute('aria-label')][:40]
        out['checkboxes'] = len(d.find_elements(By.CSS_SELECTOR, '[role="checkbox"], span[role="checkbox"]'))
        out['has_readonly_hint'] = any('只读' in ln or '临时' in ln for ln in body.splitlines())
        # 展开 API 区（若有折叠）
        for el in d.find_elements(By.XPATH, "//*[normalize-space(.)='API 配置' or normalize-space(.)='API']"):
            try:
                el.click()
            except Exception:
                pass
        time.sleep(3)
        body2 = d.execute_script('return document.body.innerText')
        out['api_lines_after_click'] = [ln for ln in body2.splitlines() if 'API' in ln or '选择' in ln][:40]
        d.save_screenshot(os.path.join(ART, 'probe_api_section_light.png'))
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        d.quit()


if __name__ == '__main__':
    main()

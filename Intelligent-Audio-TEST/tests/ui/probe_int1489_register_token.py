# -*- coding: utf-8 -*-
"""INT-1489 探针：register 页渲染 + Access Token 创建提交诊断。"""
import json, os, time, traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
ART = 'tests/ui/artifacts/int1489'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PATCH = r"""
window.__fetchLog = [];
const f = window.fetch;
window.fetch = async function(input, init){
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const e = {url:url, method:(init&&init.method)||'GET'};
  try { const r = await f.apply(this, arguments); e.status = r.status;
        if (init && typeof init.body === 'string') e.reqBody = init.body;
        if (url.indexOf('/access-tokens') !== -1) { try { e.resBody = await r.clone().text(); } catch(x){} }
        window.__fetchLog.push(e); return r; }
  catch(err){ e.status='ERR'; window.__fetchLog.push(e); throw err; }
};
"""


def drv():
    o = Options(); o.binary_location = CHROME
    for a in ('--headless=new','--window-size=1600,1200','--disable-gpu','--no-sandbox','--lang=zh-CN','--no-first-run'):
        o.add_argument(a)
    import winreg
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe) and v.split('.')[0] == str(major):
                path = exe
    except Exception:
        pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
    return d


d = drv()
try:
    # ---- register ----
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');") if False else None
    d.get(BASE + '/login'); time.sleep(2)
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.5)
    d.get(BASE + '/register'); time.sleep(4)
    print('REGISTER url', d.current_url, 'ready', d.execute_script('return document.readyState'))
    print('REGISTER inputs', len(d.find_elements(By.ID, 'register-username')))
    print('REGISTER body', (d.execute_script('return document.body.innerText') or '')[:300].replace('\n',' | '))
    print('REGISTER console err', d.execute_script("return window.__err || null"))
    d.save_screenshot(f'{ART}/probe_register.png')

    # ---- profile / token ----
    d.get(BASE + '/login'); time.sleep(3)
    d.execute_script("localStorage.removeItem('iatp:auth:v1'); localStorage.removeItem('iatp:auth:token:v1');")
    d.get('about:blank'); time.sleep(0.5)
    d.get(BASE + '/login'); time.sleep(2)
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.XPATH, "//form//button[@type='submit']").click()
    time.sleep(4)
    print('after login', d.current_url)
    d.get(BASE + '/profile'); time.sleep(6)
    print('profile url', d.current_url)
    btns = d.find_elements(By.XPATH, "//button[@aria-label='创建新的 Access Token']")
    print('create btn', len(btns))
    if not btns:
        print('profile text', (d.execute_script('return document.body.innerText') or '')[:400].replace('\n',' | '))
        raise SystemExit
    d.execute_script('arguments[0].click()', btns[0]); time.sleep(2)
    name = f'接线测试_token_probe_{int(time.time())}'
    el = d.find_element(By.ID, 'access-token-name')
    el.send_keys(name)
    print('name value', el.get_attribute('value'))
    sel = d.find_elements(By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='全选']")
    print('select-all buttons', len(sel))
    d.execute_script('arguments[0].click()', sel[0]); time.sleep(1)
    print('name after select', el.get_attribute('value'))
    print('scopes hint', [x.text for x in d.find_elements(By.XPATH, "//*[@role='dialog']//span[contains(., '已选') and contains(., '项')]")])
    subs = d.find_elements(By.XPATH, "//*[@role='dialog']//button[@type='submit']")
    print('submit buttons', [s.text for s in subs])
    d.execute_script('arguments[0].click()', subs[0]); time.sleep(4)
    print('dialogs', [x.text[:60].replace('\n',' ') for x in d.find_elements(By.XPATH, "//*[@role='dialog']")])
    print('log', json.dumps(d.execute_script('return window.__fetchLog || []'), ensure_ascii=False)[:1200])
    d.save_screenshot(f'{ART}/probe_token_after_submit.png')
    # validation errors?
    print('errors', [x.text for x in d.find_elements(By.XPATH, "//*[@role='dialog']//p[contains(@class,'text-destructive')]")])
except SystemExit:
    pass
except Exception:
    traceback.print_exc()
finally:
    time.sleep(0.5)
    d.quit()

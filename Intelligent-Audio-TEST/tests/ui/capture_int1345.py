# -*- coding: utf-8 -*-
"""INT-1345 验收截图：系统设置六域浅/深色 + /api/option/ 渲染证据。"""
import json, os, sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1345_settings')
os.makedirs(OUT, exist_ok=True)
THEME_KEY = 'iatp:theme:v1:mode'

def _driver():
    o = Options(); o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    for a in ('--headless=new','--window-size=1680,1050','--disable-gpu','--no-sandbox','--lang=zh-CN'):
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'browser':'ALL','performance':'ALL'})
    import winreg
    cm=0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            cm=int(winreg.QueryValueEx(k,'version')[0].split('.')[0])
    except Exception: pass
    root=os.path.join(os.path.expanduser('~'),'.cache','selenium','chromedriver','win64')
    dv=''
    if cm and os.path.isdir(root):
        cands=[]
        for v in os.listdir(root):
            exe=os.path.join(root,v,'chromedriver.exe')
            if os.path.isfile(exe):
                try: cands.append((tuple(int(x) for x in v.split('.') if x.isdigit()),exe))
                except ValueError: pass
        same=[e for v,e in cands if v and v[0]==cm]
        if same: dv=max(same)
    return webdriver.Chrome(options=o, service=Service(executable_path=dv) if dv else Service())

def net(drv):
    out=[]
    for e in drv.get_log('performance'):
        m=json.loads(e['message']); inner=m.get('message',{})
        if inner.get('method')=='Network.requestWillBeSent':
            u=inner.get('params',{}).get('request',{}).get('url','')
            if '/api/' in u: out.append(u)
    return out

def goto(drv, path, wait, timeout=30):
    drv.get(BASE+path)
    WebDriverWait(drv, timeout).until(lambda d: d.execute_script('return document.readyState')=='complete')
    WebDriverWait(drv, timeout).until(lambda d: wait in (d.execute_script('return document.body.textContent||""') or ''))
    time.sleep(1.5)

def set_theme(drv, mode):
    drv.get(BASE + '/dashboard')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState')=='complete')
    time.sleep(1)
    drv.execute_script(f"window.localStorage.setItem('{THEME_KEY}', '{mode}')")
    drv.refresh()
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState')=='complete')
    time.sleep(1)

drv=_driver()
try:
    goto(drv, '/dashboard', '工作台')
    drv.execute_script('try{window.localStorage.clear()}catch(e){}')
    # light
    set_theme(drv, 'light')
    goto(drv, '/system-settings/site/info', '站点信息')
    drv.save_screenshot(os.path.join(OUT,'site_light.png'))
    open(os.path.join(OUT,'site_light_network.json'),'w',encoding='utf-8').write(json.dumps(net(drv),ensure_ascii=False,indent=2))
    # dark
    set_theme(drv, 'dark')
    goto(drv, '/system-settings/site/info', '站点信息')
    drv.save_screenshot(os.path.join(OUT,'site_dark.png'))
    open(os.path.join(OUT,'site_dark_network.json'),'w',encoding='utf-8').write(json.dumps(net(drv),ensure_ascii=False,indent=2))
    # iam users light
    set_theme(drv, 'light')
    goto(drv, '/system-settings/iam/users', '用户管理')
    drv.save_screenshot(os.path.join(OUT,'iam_users_light.png'))
    # appearance dark
    set_theme(drv, 'dark')
    goto(drv, '/system-settings/appearance', '外观')
    drv.save_screenshot(os.path.join(OUT,'appearance_dark.png'))
    print('captured OK')
except Exception:
    import traceback; traceback.print_exc()
finally:
    drv.quit()

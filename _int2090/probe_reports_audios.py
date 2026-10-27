# -*- coding: utf-8 -*-
import os, time, json, sys, winreg
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
BASE='http://localhost:5388'
CHROME=r'C:\Program Files\Google\Chrome\Application\chrome.exe'
options=Options(); options.binary_location=CHROME
options.add_argument('--headless=new'); options.add_argument('--window-size=1680,1050')
options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
chrome_major=0
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
        chrome_major=int(winreg.QueryValueEx(k,'version')[0].split('.')[0])
except Exception: pass
cache_root=os.path.join(os.path.expanduser('~'),'.cache','selenium','chromedriver','win64')
drv_path=''
if chrome_major and os.path.isdir(cache_root):
    cands=[]
    for ver in os.listdir(cache_root):
        exe=os.path.join(cache_root,ver,'chromedriver.exe')
        if os.path.isfile(exe):
            try: cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()),exe))
            except ValueError: continue
    same=[exe for ver,exe in cands if ver and ver[0]==chrome_major]
    if same: drv_path=max(same)
drv=webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())
drv.set_page_load_timeout(45)
def fetch(path, body=None):
    if body is None:
        return drv.execute_script(
            "const t=localStorage.getItem('iatp:auth:token:v1')||'';"
            "return window.fetch(arguments[0],{headers:{'Authorization':'Bearer '+t}})"
            ".then(r=>r.ok?r.json():Promise.reject(r.status)).catch(e=>({__err:String(e)}))", path)
    return drv.execute_script(
        "const t=localStorage.getItem('iatp:auth:token:v1')||'';"
        "return window.fetch(arguments[0],{method:'POST',headers:{'Authorization':'Bearer '+t,'Content-Type':'application/json'},body:JSON.stringify(arguments[1])})"
        ".then(r=>r.ok?r.json():Promise.reject(r.status)).catch(e=>({__err:String(e)}))", path, body)
try:
    drv.get(BASE+'/login'); time.sleep(3)
    inp=drv.find_elements(By.TAG_NAME,'input'); inp[0].send_keys('admin'); inp[1].send_keys('admin123')
    for b in drv.find_elements(By.TAG_NAME,'button'):
        if '登录' in (b.text or '').replace(' ',''):
            b.click(); break
    time.sleep(3)
    d = fetch('/api/v1/reports?page=1&page_size=100')
    items = (d.get('data', d)).get('items') or []
    for r in items:
        rid=r['id']
        dd = fetch(f'/api/v1/reports/{rid}/cases/search', {'page':1,'page_size':200})
        if isinstance(dd, dict) and '__err' in dd:
            print('report', rid, 'search ERR', dd['__err']); continue
        cases = (dd.get('data', dd)).get('items') or []
        with_audio = sum(1 for c in cases if (c.get('audios') or []))
        maxan = max((len(a.get('audio_name') or '') for c in cases for a in (c.get('audios') or [])), default=0)
        if with_audio:
            print(f'report {rid} task={r.get("task_id")} cases={len(cases)} with_audio={with_audio} maxAudioNameLen={maxan}')
finally:
    drv.quit()

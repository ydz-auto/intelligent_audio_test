# -*- coding: utf-8 -*-
import os, time, json, winreg
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
def fetch(path):
    return drv.execute_script(
        "const t=localStorage.getItem('iatp:auth:token:v1')||'';"
        "return window.fetch(arguments[0],{headers:{'Authorization':'Bearer '+t}})"
        ".then(r=>r.ok?r.json():Promise.reject(r.status)).catch(e=>({__err:String(e)}))", path)
try:
    drv.get(BASE+'/login'); time.sleep(3)
    inputs=drv.find_elements(By.TAG_NAME,'input'); inputs[0].send_keys('admin'); inputs[1].send_keys('admin123')
    for b in drv.find_elements(By.TAG_NAME,'button'):
        if '登录' in (b.text or '').replace(' ',''):
            b.click(); break
    time.sleep(3)
    for tid in (402, 407, 413, 596):
        d = fetch(f'/api/v1/tasks/{tid}')
        if isinstance(d, dict) and '__err' in d:
            print('task', tid, 'ERR', d['__err']); continue
        data = d.get('data', d)
        cases = data.get('cases') or []
        maxRA=0; maxRef=0; raS=''; refS=''; maxAF=0; afS=''; cntAudio=0; cntAF=0
        for c in cases[:60]:
            cid = c.get('case_id')
            cd = fetch(f'/api/v1/tasks/{tid}/cases/{cid}/detail')
            if isinstance(cd, dict) and '__err' in cd:
                continue
            cdata = cd.get('data', cd)
            for a in (cdata.get('result_audios') or []):
                n = a.get('audio_name') or ''
                cntAudio += 1
                if len(n)>maxRA: maxRA=len(n); raS=n
            for a in (cdata.get('audio_list') or []):
                n = a.get('audio_name') or ''
                cntAudio += 1
                if len(n)>maxRef: maxRef=len(n); refS=n
            for f in (cdata.get('algorithm_results') or []):
                if (f.get('param_type')=='audio_file' or f.get('paramType')=='audio_file'):
                    lab = str(f.get('label') or '')
                    cntAF += 1
                    if len(lab)>maxAF: maxAF=len(lab); afS=lab
        print(f'task {tid} cases={len(cases)}: result/ref audio count={cntAudio} maxRA={maxRA} raS={raS[:60]!r} maxRef={maxRef} refS={refS[:60]!r} | audioField count={cntAF} maxAF={maxAF} afS={afS[:60]!r}')
finally:
    drv.quit()

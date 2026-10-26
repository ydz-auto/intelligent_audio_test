# -*- coding: utf-8 -*-
"""INT-1424 维度分组兜底探针：真实库 56 维度全平铺，抓名称/关联算法/分类形态。"""
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
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1000')
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
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try: cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError: continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same: drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45); drv.set_script_timeout(180)
    return drv

def _api(drv, method, path, body=None):
    script = '''
      const method=arguments[0],path=arguments[1],body=arguments[2];
      const token=window.localStorage.getItem('iatp:auth:token:v1')||'';
      const xhr=new XMLHttpRequest(); xhr.open(method,'/api/v1'+path,false);
      xhr.setRequestHeader('Content-Type','application/json');
      xhr.setRequestHeader('Authorization','Bearer '+token);
      xhr.send(body?JSON.stringify(body):null);
      let data=null; try{data=JSON.parse(xhr.responseText||'null');}catch(e){}
      return {status:xhr.status, data};
    '''
    return drv.execute_script(script, method, path, body)

def unwrap(lst):
    data = lst.get('data') or {}
    if isinstance(data, dict) and 'items' in data: return data['items']
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        d2 = data['data']
        if isinstance(d2, dict) and 'items' in d2: return d2['items']
    if isinstance(data, dict) and 'data' in data: return data['data']
    if isinstance(data, list): return data
    return []

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

    dims = unwrap(_api(drv,'GET','/evaluation/dimensions?per_page=1000'))
    print('DIM_COUNT=', len(dims))
    # 名称前 20 + 关联算法
    algo_groups = {}
    for d in dims:
        name = d.get('name') or ''
        algos = d.get('associated_algorithms') or []
        types = [a.get('algorithm_type') if isinstance(a, dict) else str(a) for a in algos]
        key = tuple(sorted([t for t in types if t]))
        algo_groups.setdefault(key, []).append(name)
        if len([k for k in algo_groups]) <= 0: pass
    print('=== ALGO_GROUP_COUNTS ===')
    for key, names in sorted(algo_groups.items(), key=lambda x: -len(x[1])):
        print(len(names), 'dims | algos=', key, '| sample=', json.dumps(names[:5], ensure_ascii=False))
    # result_type 分布
    rt = {}
    for d in dims:
        rt[str(d.get('result_type'))] = rt.get(str(d.get('result_type')), 0) + 1
    print('RESULT_TYPE=', rt)
    # 名称样例（含 LLM judge 与否）
    for d in dims[:12]:
        print('DIM=', d.get('id'), repr((d.get('name') or '')[:30]), 'rt=', d.get('result_type'), 'type=', d.get('type'))
    # 播放设备
    devs = _api(drv,'GET','/playback-devices?per_page=200')
    dd = devs.get('data') or {}
    if isinstance(dd, dict) and 'items' in dd: devs_items = dd['items']
    elif isinstance(dd, list): devs_items = dd
    else: devs_items = dd.get('data') if isinstance(dd, dict) else []
    print('DEV_COUNT=', len(devs_items))
    if devs_items:
        print('DEV_SAMPLE=', json.dumps(devs_items[0], ensure_ascii=False)[:400])
    # strategies
    strs = unwrap(_api(drv,'GET','/evaluation-strategies?per_page=200'))
    print('STRATEGY_COUNT=', len(strs))
    # audios
    aud = unwrap(_api(drv,'GET','/audios?per_page=3'))
    print('AUDIO_COUNT=', len(aud))
    if aud:
        print('AUDIO_SAMPLE=', json.dumps(aud[0], ensure_ascii=False)[:300])
        st = _api(drv,'GET', f"/audios/{aud[0]['id']}/stream")
        print('STREAM_0=', json.dumps(st.get('data'), ensure_ascii=False)[:250])
    # folder-tree
    ft = _api(drv,'POST','/audios/folder-tree',{'depth':10})
    print('FOLDER_TREE=', json.dumps(ft.get('data'), ensure_ascii=False)[:250])
finally:
    drv.quit()

# -*- coding: utf-8 -*-
"""INT-1424 深色主题截图 + 全局噪声真实设备核验。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_shots')

def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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

def jsclick(drv, el): drv.execute_script("arguments[0].click()", el)

def api(drv, method, path, body=None):
    s = '''
      const method=arguments[0],path=arguments[1],body=arguments[2];
      const token=window.localStorage.getItem('iatp:auth:token:v1')||'';
      const xhr=new XMLHttpRequest(); xhr.open(method,'/api/v1'+path,false);
      xhr.setRequestHeader('Content-Type','application/json');
      xhr.setRequestHeader('Authorization','Bearer '+token);
      xhr.send(body?JSON.stringify(body):null);
      let data=null; try{data=JSON.parse(xhr.responseText||'null');}catch(e){}
      return {status:xhr.status, data};
    '''
    return drv.execute_script(s, method, path, body)

def unwrap(d):
    d = (d or {}).get('data') or {}
    if isinstance(d, dict) and 'items' in d: return d['items']
    if isinstance(d, dict) and isinstance(d.get('data'), dict):
        d2 = d['data']
        if isinstance(d2, dict) and 'items' in d2: return d2['items']
    return []

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
        # 真实播放设备名
        devs = unwrap(api(drv,'GET','/playback-devices?per_page=200'))
        print('REAL_DEVICES=', json.dumps([(d.get('id'), d.get('name'), d.get('channel_index')) for d in devs], ensure_ascii=False))
        # 切深色
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get(BASE + '/testcases'); time.sleep(3.0)
        newb = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        if newb: jsclick(drv, newb[0]); time.sleep(2.0)
        # 音频列表步骤（深色）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)
        drv.save_screenshot(os.path.join(OUT, 'l_dark_audio_step.png'))
        # 评估维度步骤（深色）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '评估维度')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)
        drv.save_screenshot(os.path.join(OUT, 'm_dark_dimension_step.png'))
        # 独立节（深色：整体评估维度 + 全局背景噪声 + 评估策略）
        try:
            el = drv.find_element(By.XPATH, "//h4[contains(., '整体评估维度')]")
            drv.execute_script("arguments[0].scrollIntoView({block:'start'})", el)
            time.sleep(0.8)
            drv.save_screenshot(os.path.join(OUT, 'n_dark_sections.png'))
            print('DARK_SECTIONS_SHOT')
        except Exception as e:
            print('DARK_SECTIONS_FAIL', e)
        # 全局噪声：添加 → 验证设备 chips 为真实设备
        try:
            addnoise = drv.find_elements(By.XPATH, "//button[contains(., '添加全局噪声')]")
            if addnoise:
                jsclick(drv, addnoise[0]); time.sleep(1.5)
                # 关闭音频选择弹窗（取消）
                canc = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
                if canc: jsclick(drv, canc[-1]); time.sleep(0.6)
            else:
                # 已配置态：找设备 chips 区
                pass
            # 找播放设备 chips（含「通道」文案的按钮）
            chips = drv.find_elements(By.XPATH, "//button[contains(., '通道')]")
            print('DEVICE_CHIPS=', json.dumps([c.text[:40] for c in chips], ensure_ascii=False))
            el = drv.find_element(By.XPATH, "//h4[contains(., '全局背景噪声')]")
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            time.sleep(0.8)
            drv.save_screenshot(os.path.join(OUT, 'o_dark_noise_section.png'))
        except Exception as e:
            print('NOISE_CHIP_FAIL', e)
        # Network（dark run）
        net = {}
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])['message']
                if msg.get('method') != 'Network.requestWillBeSent': continue
                url = msg.get('params', {}).get('request', {}).get('url') or ''
                for k in ['/audios', '/playback-devices', '/evaluation-strategies', '/evaluation/dimensions', '/evaluation/categories']:
                    if k in url: net[k] = net.get(k, 0) + 1
            except Exception: pass
        print('NET=', json.dumps(net, ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()

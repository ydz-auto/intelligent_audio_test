# -*- coding: utf-8 -*-
"""INT-1424 试听链路核验（含重试等待 + 播放器状态）。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
        lib = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        if not lib:
            print('FAIL_NO_LIB_BTN'); return
        jsclick(drv, lib[0]); time.sleep(2.0)
        # 选第一行音频（对话框内音频行按钮：含 AudioWaveform 图标）
        rows = drv.find_elements(By.XPATH, "//button[.//*[contains(@class,'audio-waveform') or contains(@class,'lucide-audio-waveform')]]")
        print('ROWS=', len(rows))
        if rows:
            jsclick(drv, rows[0]); time.sleep(0.5)
        confirm = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
        if confirm:
            jsclick(drv, confirm[-1])
        # 等音频卡出现
        try:
            WebDriverWait(drv,8).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='试听']")) > 0)
        except Exception as e:
            print('WAIT_PREVIEW_FAIL', e)
        previews = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='试听']")
        print('PREVIEW_COUNT=', len(previews))
        drv.save_screenshot(os.path.join(OUT, 'j_audio_card_preview.png'))
        if not previews:
            print('STOP_NO_PREVIEW'); return
        jsclick(drv, previews[0]); time.sleep(1.5)
        drv.save_screenshot(os.path.join(OUT, 'j_preview_config.png'))
        starts = drv.find_elements(By.XPATH, "//button[contains(., '开始试听')]")
        print('START_COUNT=', len(starts))
        if starts:
            jsclick(drv, starts[-1]); time.sleep(3.0)
            drv.save_screenshot(os.path.join(OUT, 'k_player.png'))
            plays = drv.find_elements(By.XPATH, "//button[contains(., '播放') or @aria-label='播放']")
            stops = drv.find_elements(By.XPATH, "//button[contains(., '停止')]")
            backs = drv.find_elements(By.XPATH, "//button[contains(., '返回试听配置')]")
            print('PLAYER_PLAY=', len(plays), 'STOP=', len(stops), 'BACK=', len(backs))
            # 点播放，验证前端真实播放（audio 元素 currentTime 推进）
            if plays:
                jsclick(drv, plays[0]); time.sleep(2.0)
                t = drv.execute_script(
                    "const a=document.querySelector('audio'); return a?{t:a.currentTime,d:isFinite(a.duration)?a.duration:0,paused:a.paused}:null")
                print('AUDIO_STATE=', json.dumps(t))
        # stream 网络请求
        net = {}
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])['message']
                if msg.get('method') != 'Network.requestWillBeSent': continue
                url = msg.get('params', {}).get('request', {}).get('url') or ''
                if '/stream' in url: net['/stream'] = net.get('/stream', 0) + 1
                if '/audios/' in url and 'stream' not in url: net['/audios/{id}'] = net.get('/audios/{id}', 0) + 1
            except Exception: pass
        print('NET_STREAM=', json.dumps(net, ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()

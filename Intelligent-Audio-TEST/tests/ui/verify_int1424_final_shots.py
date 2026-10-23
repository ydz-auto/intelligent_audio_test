# -*- coding: utf-8 -*-
"""INT-1424 验收最终截图：独立节滚动定位、深浅色、Network。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_shots')
os.makedirs(OUT, exist_ok=True)

def _driver(dark=False):
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
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

def login(drv):
    drv.get(BASE + '/login'); time.sleep(1.5)
    drv.execute_script('try { window.localStorage.clear() } catch(e) {}')
    drv.get(BASE + '/login')
    WebDriverWait(drv,20).until(lambda d: len(d.find_elements(By.ID,'username'))>0)
    drv.find_element(By.ID,'username').send_keys('接线测试_admin')
    drv.find_element(By.ID,'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH,"//button[contains(., '登 录')]").click()
    WebDriverWait(drv,25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)

def open_drawer(drv):
    drv.get(BASE + '/testcases'); time.sleep(3.0)
    newb = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
    jsclick(drv, newb[0]); time.sleep(2.0)

def scroll_to_section(drv, text):
    """滚动抽屉容器使指定文本的叶子节点进入视野中央。"""
    drv.execute_script(f'''
        const container=[...document.querySelectorAll('*')].find(e=>e.scrollHeight>e.clientHeight+50 && getComputedStyle(e).overflowY==='scroll');
        if(!container) return;
        const els=[...container.querySelectorAll('*')].filter(e=>e.children.length===0 && e.textContent.trim()==={json.dumps(text)});
        const el=els[els.length-1];
        if(el){{ el.scrollIntoView({{block:'center'}}); }}
    ''')
    time.sleep(0.8)

def main():
    # ---- 浅色 ----
    drv = _driver()
    try:
        login(drv)
        open_drawer(drv)

        # 音频列表步骤（空态，唯一入口）
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)
        scroll_to_section(drv, '从音频库选择')
        drv.save_screenshot(os.path.join(OUT, 'A1_audio_step.png'))
        print('A1_OK')

        # 音频库选择弹窗
        lib = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        if lib:
            jsclick(drv, lib[0]); time.sleep(2.5)
            drv.save_screenshot(os.path.join(OUT, 'A2_audio_select_dialog.png'))
            # 全选本页
            selpage = drv.find_elements(By.XPATH, "//button[contains(., '全选本页')]")
            if selpage:
                jsclick(drv, selpage[0]); time.sleep(0.6)
                drv.save_screenshot(os.path.join(OUT, 'A3_audio_select_page.png'))
            canc = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
            for c in canc[-1:]:
                jsclick(drv, c); time.sleep(0.6); break
        print('A2_A3_OK')

        # 评估维度步骤
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '评估维度')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)
        drv.save_screenshot(os.path.join(OUT, 'A4_dimension_step.png'))
        print('A4_OK')

        # 整体评估维度独立节
        scroll_to_section(drv, '整体评估维度')
        drv.save_screenshot(os.path.join(OUT, 'A5_overall_dims.png'))
        print('A5_OK')
        # 全局背景噪声独立节
        scroll_to_section(drv, '全局背景噪声')
        drv.save_screenshot(os.path.join(OUT, 'A6_global_noise.png'))
        print('A6_OK')
        # 评估策略节
        scroll_to_section(drv, '评估策略')
        drv.save_screenshot(os.path.join(OUT, 'A7_strategy.png'))
        print('A7_OK')

        # Network
        hits = ['/audios', '/playback-devices', '/evaluation-strategies', '/evaluation/dimensions', '/evaluation/categories']
        found = {k: 0 for k in hits}
        try:
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry['message'])['message']
                    if msg.get('method') != 'Network.requestWillBeSent': continue
                    url = (msg.get('params', {}).get('request', {}).get('url') or '')
                    for k in hits:
                        if k in url: found[k] += 1
                except Exception: pass
        except Exception: pass
        print('NET_LIGHT=', json.dumps(found, ensure_ascii=False))
    finally:
        drv.quit()

    # ---- 深色 ----
    drv2 = _driver()
    try:
        login(drv2)
        drv2.execute_script("try { localStorage.setItem('iatp:theme:v1:mode','dark'); } catch(e) {}")
        open_drawer(drv2)
        scroll_to_section(drv2, '整体评估维度')
        drv2.save_screenshot(os.path.join(OUT, 'B1_overall_dims.png'))
        scroll_to_section(drv2, '全局背景噪声')
        drv2.save_screenshot(os.path.join(OUT, 'B2_global_noise.png'))
        scroll_to_section(drv2, '评估策略')
        drv2.save_screenshot(os.path.join(OUT, 'B3_strategy.png'))
        # 音频步骤（深色）
        tabs = drv2.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv2, tabs[0]); time.sleep(1.0)
        scroll_to_section(drv2, '从音频库选择')
        drv2.save_screenshot(os.path.join(OUT, 'B4_audio_step.png'))
        print('DARK_OK')
    finally:
        drv2.quit()

if __name__ == '__main__':
    main()

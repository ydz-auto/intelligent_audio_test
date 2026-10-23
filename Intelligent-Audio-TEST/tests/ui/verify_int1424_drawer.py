# -*- coding: utf-8 -*-
"""INT-1424 浏览器实测：用例编辑抽屉 6 项修复逐项核验 + 截图 + Network。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5350')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int1424_shots')
os.makedirs(OUT, exist_ok=True)

def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new'); options.add_argument('--window-size=1600,1200')
    options.add_argument('--disable-gpu'); options.add_argument('--no-sandbox'); options.add_argument('--lang=zh-CN')
    # 保留 perf log（Network 证据）
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

def net_reqs(drv, hits):
    """从 performance log 抽 URL 命中。"""
    found = {k: 0 for k in hits}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])['message']
                if msg.get('method') != 'Network.requestWillBeSent': continue
                url = (msg.get('params', {}).get('request', {}).get('url') or '')
                for k in hits:
                    if k in url:
                        found[k] += 1
            except Exception: pass
    except Exception: pass
    return found

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
        print('LOGIN_OK', drv.current_url)

        drv.get(BASE + '/testcases')
        time.sleep(3.0)
        print('PAGE_TITLE=', drv.title, 'URL=', drv.current_url)

        # 新增用例按钮（打开编辑抽屉）
        found = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        if not found:
            # 兜底：页面任意主按钮
            found = drv.find_elements(By.CSS_SELECTOR, 'button')
            print('NO_NEW_BTN; buttons sample:', [b.text[:20] for b in found[:8] if b.text][:8])
        else:
            drv.execute_script("arguments[0].click()", found[0])
            time.sleep(2.0)
        drv.save_screenshot(os.path.join(OUT, 'a_drawer_basic.png'))
        print('DRAWER_OPENED')

        # 音频列表步骤
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs:
            drv.execute_script("arguments[0].click()", tabs[0])
            time.sleep(1.0)
        drv.save_screenshot(os.path.join(OUT, 'b_audio_step.png'))
        print('AUDIO_STEP_SHOT')
        # 从音频库选择
        lib = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        if lib:
            drv.execute_script("arguments[0].click()", lib[0])
            time.sleep(2.0)
            drv.save_screenshot(os.path.join(OUT, 'c_audio_select_dialog.png'))
            print('AUDIO_SELECT_DIALOG_SHOT')
            # 全选本页
            sel = drv.find_elements(By.XPATH, "//button[contains(., '全选本页')]")
            if sel:
                drv.execute_script("arguments[0].click()", sel[0])
                time.sleep(0.6)
                drv.save_screenshot(os.path.join(OUT, 'd_audio_select_selectpage.png'))
                print('SELECT_PAGE_SHOT')
            # 关闭弹窗（取消）
            canc = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
            for c in canc[-1:]:
                drv.execute_script("arguments[0].click()", c)
                time.sleep(0.8)
                break
        # 评估维度步骤
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '评估维度')]")
        if tabs:
            drv.execute_script("arguments[0].click()", tabs[0])
            time.sleep(1.0)
        drv.save_screenshot(os.path.join(OUT, 'e_dimension_step.png'))
        print('DIM_STEP_SHOT')

        # 整体评估维度独立节
        try:
            el = drv.find_element(By.XPATH, "//h4[contains(., '整体评估维度')]")
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            time.sleep(0.8)
            drv.save_screenshot(os.path.join(OUT, 'f_overall_dims_section.png'))
            print('OVERALL_SECTION_SHOT')
        except Exception as e:
            print('OVERALL_SECTION_FAIL', e)
        # 全局背景噪声独立节
        try:
            el = drv.find_element(By.XPATH, "//h4[contains(., '全局背景噪声')]")
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            time.sleep(0.8)
            drv.save_screenshot(os.path.join(OUT, 'g_global_noise_section.png'))
            print('NOISE_SECTION_SHOT')
        except Exception as e:
            print('NOISE_SECTION_FAIL', e)
        # 评估策略节
        try:
            el = drv.find_element(By.XPATH, "//*[contains(., '评估策略')]")
            drv.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            time.sleep(0.8)
            drv.save_screenshot(os.path.join(OUT, 'h_strategy_section.png'))
            print('STRATEGY_SECTION_SHOT')
        except Exception as e:
            print('STRATEGY_SECTION_FAIL', e)

        # Network 证据
        hits = ['/audios', '/playback-devices', '/evaluation-strategies', '/evaluation/dimensions', '/evaluation/categories']
        print('NET=', json.dumps(net_reqs(drv, hits), ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()

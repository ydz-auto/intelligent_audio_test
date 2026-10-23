# -*- coding: utf-8 -*-
"""INT-1424 验收：策略空态 + 全局噪声真实设备 chips + 深色截图。"""
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

def scroll_to_label(drv, text):
    try:
        drv.execute_script(f'''
            const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0 && e.textContent.trim()==={json.dumps(text)});
            const el=els[els.length-1];
            if (el) el.scrollIntoView({{block:'center'}});
        ''')
        time.sleep(0.6)
    except Exception:
        time.sleep(0.4)

def main():
    # ---------- 策略空态 + 全局噪声设备 ----------
    drv = _driver()
    try:
        login(drv)
        drv.get(BASE + '/testcases'); time.sleep(3.0)
        newb = drv.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        jsclick(drv, newb[0]); time.sleep(2.0)

        # 全局背景噪声：点击「添加全局噪声」→ 音频选择 → 选第一个 → 设备 chips
        scroll_to_label(drv, '全局背景噪声')
        add_noise = drv.find_elements(By.XPATH, "//button[contains(., '添加全局噪声')]")
        print('ADD_NOISE_BTN=', len(add_noise))
        if add_noise:
            jsclick(drv, add_noise[0]); time.sleep(2.0)
            dlg = None
            for d in drv.find_elements(By.XPATH, "//div[@role='dialog']"):
                try:
                    if '选择' in d.text and '音频' in d.text and ('噪声' in d.text or '搜索' in d.text):
                        dlg = d; break
                except Exception: pass
            rows = (dlg or drv).find_elements(By.XPATH, ".//button[.//*[contains(@class,'audio-waveform') or contains(@class,'lucide-audio-waveform')]]")
            print('NOISE_DIALOG_ROWS=', len(rows))
            if rows:
                jsclick(drv, rows[0]); time.sleep(0.8)
                confirms = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
                if confirms:
                    jsclick(drv, confirms[-1]); time.sleep(1.2)
                    # 设备 chips
                    dev_labels = drv.find_elements(By.XPATH, "//*[contains(., '播放设备')]")
                    print('DEV_LABELS=', len(dev_labels))
                    # 已渲染设备 chips（含设备名的按钮）
                    chips = drv.find_elements(By.XPATH, "//button[contains(., '通道') or contains(., '干声') or contains(., '噪声')]")
                    chip_texts = [c.text for c in chips if c.text][:10]
                    print('DEVICE_CHIPS=', json.dumps(chip_texts, ensure_ascii=False))
                    scroll_to_label(drv, '播放设备')
                    drv.save_screenshot(os.path.join(OUT, 'L7_global_noise_devices.png'))
                    print('NOISE_DEVICE_SHOT')
        # 试听按钮（全局噪声卡）
        previews = drv.find_elements(By.XPATH, "//button[contains(., '试听')]")
        print('NOISE_PREVIEW=', len(previews))
        if previews:
            jsclick(drv, previews[0]); time.sleep(1.5)
            starts = drv.find_elements(By.XPATH, "//button[contains(., '开始试听')]")
            print('NOISE_START=', len(starts))
            if starts:
                jsclick(drv, starts[-1]); time.sleep(2.5)
                plays = drv.find_elements(By.XPATH, "//button[contains(., '播放') or @aria-label='播放']")
                print('NOISE_PLAYER_PLAY=', len(plays))
                drv.save_screenshot(os.path.join(OUT, 'L8_noise_player.png'))
            # 返回配置 → 取消
            canc = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
            for c in canc[-1:]:
                jsclick(drv, c); time.sleep(0.5); break

        # 评估策略空态
        scroll_to_label(drv, '评估策略')
        strat = drv.find_elements(By.XPATH, "//*[contains(., '评估策略') and @role='button']")
        if not strat:
            strat = drv.find_elements(By.XPATH, "//*[contains(., '评估策略')]//*[@role='button']")
        print('STRATEGY_COLLAPSIBLE=', len(strat))
        if strat:
            jsclick(drv, strat[0]); time.sleep(1.0)
            ref = drv.find_elements(By.XPATH, "//input[@type='radio' and @value='reference']")
            print('REF_RADIO=', len(ref))
            if ref:
                jsclick(drv, ref[0]); time.sleep(1.0)
                empt = drv.find_elements(By.XPATH, "//*[contains(., '暂无可用策略')]")
                print('EMPTY_STRATEGY=', len(empt), json.dumps([e.text for e in empt][:2], ensure_ascii=False))
                drv.save_screenshot(os.path.join(OUT, 'L9_strategy_empty.png'))
                print('STRATEGY_EMPTY_SHOT')
    finally:
        drv.quit()

    # ---------- 深色：独立节 + 音频步骤 ----------
    drv2 = _driver()
    try:
        login(drv2)
        # 切深色
        drv2.execute_script("try { localStorage.setItem('iatp:theme:v1:mode', 'dark'); } catch(e) {}")
        drv2.get(BASE + '/testcases'); time.sleep(3.0)
        newb = drv2.find_elements(By.XPATH, "//button[contains(., '新增用例') or contains(., '新增测试用例')]")
        jsclick(drv2, newb[0]); time.sleep(2.0)
        scroll_to_label(drv2, '整体评估维度')
        drv2.save_screenshot(os.path.join(OUT, 'D1_overall_dims.png'))
        scroll_to_label(drv2, '全局背景噪声')
        drv2.save_screenshot(os.path.join(OUT, 'D2_global_noise.png'))
        scroll_to_label(drv2, '评估策略')
        drv2.save_screenshot(os.path.join(OUT, 'D3_strategy.png'))
        print('DARK_SHOTS_DONE')
    finally:
        drv2.quit()

if __name__ == '__main__':
    main()

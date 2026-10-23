# -*- coding: utf-8 -*-
"""INT-1424 功能核验：音频列表按钮收敛 + 音频库导入选择 + 试听真实链路。"""
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

        # 音频列表步骤
        tabs = drv.find_elements(By.XPATH, "//button[contains(., '音频列表')]")
        if tabs: jsclick(drv, tabs[0]); time.sleep(1.0)

        # 断言：无「+ 添加音频」，有「从音频库选择」
        add_btns = drv.find_elements(By.XPATH, "//button[contains(., '添加音频')]")
        lib_btns = drv.find_elements(By.XPATH, "//button[contains(., '从音频库选择')]")
        print('ADD_AUDIO_BTN_COUNT=', len(add_btns), 'LIB_BTN_COUNT=', len(lib_btns))
        assert len(add_btns) == 0, '「+ 添加音频」按钮未移除'
        assert len(lib_btns) == 1, '「从音频库选择」入口缺失'

        # 空态文案
        empty = [e.text for e in drv.find_elements(By.XPATH, "//*[contains(text(), '尚未添加音频')]")]
        print('EMPTY_TEXT=', json.dumps(empty, ensure_ascii=False))

        # 从音频库选择 → 选第一个音频 → 确认
        jsclick(drv, lib_btns[0]); time.sleep(2.0)
        rows = drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] button, .fixed button")
        # 音频行：勾选第一行（点击行按钮）
        import re
        # 找音频行（含时长的行按钮）
        row_btns = drv.find_elements(By.XPATH, "//button[.//span[contains(@class, 'tabular-nums')]]")
        print('ROW_CANDIDATES=', len(row_btns))
        if row_btns:
            jsclick(drv, row_btns[0]); time.sleep(0.5)
        confirm = drv.find_elements(By.XPATH, "//button[contains(., '确认选择')]")
        if confirm:
            jsclick(drv, confirm[-1]); time.sleep(1.0)
            drv.save_screenshot(os.path.join(OUT, 'i_audio_added.png'))
            print('AUDIO_ADDED')
        else:
            print('NO_CONFIRM_BTN')
            drv.save_screenshot(os.path.join(OUT, 'i_audio_select_fail.png'))
            return

        # 试听按钮
        preview_btns = drv.find_elements(By.XPATH, "//button[@aria-label='试听']")
        print('PREVIEW_BTN_COUNT=', len(preview_btns))
        if preview_btns:
            jsclick(drv, preview_btns[0]); time.sleep(1.5)
            drv.save_screenshot(os.path.join(OUT, 'j_preview_config.png'))
            start = drv.find_elements(By.XPATH, "//button[contains(., '开始试听')]")
            if start:
                jsclick(drv, start[-1]); time.sleep(2.0)
                drv.save_screenshot(os.path.join(OUT, 'k_player.png'))
                # 断言播放器控制钮
                play = drv.find_elements(By.XPATH, "//button[contains(., '播放') or @aria-label='播放']")
                stop = drv.find_elements(By.XPATH, "//button[contains(., '停止')]")
                back = drv.find_elements(By.XPATH, "//button[contains(., '返回试听配置')]")
                print('PLAYER_PLAY=', len(play), 'STOP=', len(stop), 'BACK=', len(back))
            # Network: stream 请求
            hits = ['/stream', '/audios/']
            net = {}
            for entry in drv.get_log('performance'):
                try:
                    msg = json.loads(entry['message'])['message']
                    if msg.get('method') != 'Network.requestWillBeSent': continue
                    url = msg.get('params', {}).get('request', {}).get('url') or ''
                    for k in ['/stream']:
                        if k in url: net[k] = net.get(k, 0) + 1
                except Exception: pass
            print('STREAM_NET=', json.dumps(net, ensure_ascii=False))
    finally:
        drv.quit()

if __name__ == '__main__':
    main()

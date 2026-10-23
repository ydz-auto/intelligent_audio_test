# -*- coding: utf-8 -*-
"""INT-1251 三修复深色截图（INT-1213 抽屉算法选项 / INT-1215 列表支持算法列 / INT-1217 离线编辑可用）。

深色：写 localStorage iatp:theme:v1:mode=dark + about:blank 打断 bfcache 强刷。
同时捕获 /algorithm/options 的 Network 请求作为 INT-1213 证据。
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5307')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1333')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
NETWORK = []


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def drain_network(drv):
    pairs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                method = msg['message']['method']
                inner = msg['message']['params']
                if method == 'Network.requestWillBeSent':
                    req = inner['request']
                    url = req.get('url', '')
                    if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                        pairs.append({'kind': 'req', 'method': req.get('method'), 'url': url})
                elif method == 'Network.responseReceived':
                    resp = inner['response']
                    url = resp.get('url', '')
                    if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                        pairs.append({'kind': 'resp', 'status': resp.get('status'), 'url': url})
            except Exception:
                pass
    except Exception:
        pass
    return pairs


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test'

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # 深色 + 强刷
        drv.get(BASE + '/login')
        time.sleep(2)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        drv.get('about:blank')
        time.sleep(1)

        # ---- 列表（INT-1215 支持算法列深色）----
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        body = drv.execute_script('return document.body.textContent || ""')
        print('list has 小艺语音大模型:', '小艺语音大模型' in body)
        print('list raw voice_llm:', 'voice_llm' in body)
        NETWORK.extend(drain_network(drv))
        drv.save_screenshot(os.path.join(ART, 'list-dark.png'))

        # ---- 添加抽屉（INT-1213 算法类型选项深色）----
        add_btn = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        NETWORK.clear()
        NETWORK.extend(drain_network(drv))
        dbody = drv.find_element(By.XPATH, "//div[@role='dialog']").text
        print('drawer has 小艺语音大模型:', '小艺语音大模型' in dbody)
        print('drawer raw asr_streaming:', 'asr_streaming' in dbody)
        for p in NETWORK:
            if 'algorithm/options' in p['url']:
                print(f"  NET {p['kind'].upper()} {p['url']} status={p.get('status')}")
        drv.save_screenshot(os.path.join(ART, 'add-drawer-dark.png'))
        # close
        cancel_btn = drv.find_element(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click()', cancel_btn)
        time.sleep(1)

        # ---- 离线行菜单编辑（INT-1217 深色）----
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        if rows:
            first_ops = rows[0].find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
            drv.execute_script('arguments[0].click()', first_ops[0])
            time.sleep(1.5)
            menu = drv.find_element(By.XPATH, "//div[@role='menu']")
            edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
            if edit_item:
                print('EDIT item disabled:', edit_item[0].get_attribute('aria-disabled'))
            drv.save_screenshot(os.path.join(ART, 'rowmenu-dark.png'))
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()

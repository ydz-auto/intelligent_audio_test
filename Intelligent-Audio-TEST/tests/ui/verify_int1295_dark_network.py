# -*- coding: utf-8 -*-
"""INT-1295 深色截图 + Network 捕获（真实库栈 5700）——最小脚本。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5315')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.dirname(os.path.abspath(__file__)) + '/artifacts/int1295_tags_pagination'
os.makedirs(ARTIFACTS, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1280,800')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--no-proxy-server')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
        if cands:
            cands.sort(key=lambda t: t[0])
            drv_path = cands[-1][1]
    service = Service(drv_path)
    return webdriver.Chrome(service=service, options=options)


def _health():
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:5700/health', timeout=8) as resp:
        health = json.loads(resp.read().decode())
    print('health.database =', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test', '连到非主库，停！'


def _set_dark(drv, dark=True):
    mode = 'dark' if dark else 'light'
    try:
        drv.execute_script(
            "window.localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('%s'));" % mode)
    except Exception:
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', '%s');" % mode)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _drain_perf(drv):
    logs = drv.get_log('performance')
    out = []
    for entry in logs:
        msg = json.loads(entry['message'])['message']
        if msg['method'] == 'Network.requestWillBeSent':
            out.append(msg['params'])
    return out


def main():
    drv = _driver()
    try:
        _health()
        _goto(drv, '/login')
        time.sleep(1.5)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        time.sleep(2)
        print('logged in')

        # 深色：标签页
        _health()
        _set_dark(drv, True)
        _goto(drv, '/TagManagement')
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'tbody tr'))
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, '06_tag_page_dark.png'))
        print('captured 06_tag_page_dark.png')

        # 深色：批量标签弹窗
        _goto(drv, '/testcases/by-group')
        time.sleep(3)
        select_all = WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="全选用例"]'))
        drv.execute_script('arguments[0].click();', select_all[0])
        time.sleep(1.0)
        tag_btn = WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.XPATH, "//button[contains(., '批量管理标签')]"))
        drv.execute_script('arguments[0].click();', tag_btn[0])
        time.sleep(1.8)
        WebDriverWait(drv, 20).until(
            lambda d: d.find_elements(By.XPATH, "//h2[contains(., '批量管理标签')]"))
        drv.save_screenshot(os.path.join(ARTIFACTS, '07_batch_tags_dialog_dark.png'))
        print('captured 07_batch_tags_dialog_dark.png')
        cancel = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click();', cancel[0])
        time.sleep(0.8)

        # 浅色 + Network：/TagManagement 真实请求
        _health()
        _set_dark(drv, False)
        _drain_perf(drv)
        _goto(drv, '/TagManagement')
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'tbody tr'))
        time.sleep(2)
        reqs = _drain_perf(drv)
        tag_reqs = []
        for r in reqs:
            url = r.get('request', {}).get('url', '')
            if '/api/v1/tags' in url:
                tag_reqs.append(url)
        print('  /tags requests:')
        for u in tag_reqs:
            print('   ', u)
        assert any('per_page=100' in u for u in tag_reqs), '应有 GET /api/v1/tags?page=1&per_page=100'
        # 缓存命中则可能复用 fetch：再强制刷新一次页面
        if not tag_reqs:
            drv.get(BASE + '/TagManagement')
            time.sleep(2)
            reqs = _drain_perf(drv)
            tag_reqs = [r.get('request', {}).get('url', '') for r in reqs if '/api/v1/tags' in r.get('request', {}).get('url', '')]
            print('  after reload /tags requests:')
            for u in tag_reqs:
                print('   ', u)
            assert any('per_page=100' in u for u in tag_reqs), '重载后应有 /tags?per_page=100'

        _health()
        print('DARK + NETWORK ALL ASSERTIONS PASSED')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""INT-1279 验收：任务 419 关联用例「快速复核」按用例评估维度显式传 dimension_ids。

真实库栈 5700（intelligent_audio_test），dev 5399。验证：
① 登录（表单 接线测试_admin）→ /tasks/419 详情 → 关联用例卡 → 某用例行「快速复核」。
② 弹窗「发起快速复核」→ Network 捕获 POST /api/v1/tasks/results/ai-review 请求体
   含 dimension_ids（用例评估维度 121~132）→ 响应 200 非 400。
③ 浅色截图 + Network 证据；④ 深色弹窗截图。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5399')
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1279_quick_review_dims')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'


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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _net_entries(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                method = inner.get('method', '')
                params = inner.get('params', {})
                if method == 'Network.requestWillBeSent':
                    url = params.get('request', {}).get('url', '')
                    post = params.get('request', {}).get('postData', '')
                    out.append(('REQ', url, post))
                elif method == 'Network.responseReceived':
                    url = params.get('response', {}).get('url', '')
                    status = params.get('response', {}).get('status')
                    out.append(('RESP', url, status))
            except Exception:
                pass
    except Exception:
        pass
    return out


def _save(name, drv, text=''):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)
    if text:
        with open(os.path.join(d, 'body.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
    print('saved', name)


def main():
    drv = _driver()
    try:
        # 登录（AUTH_MODE=dev 表单登录）
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.ID, 'username')))
        time.sleep(1)
        drv.find_element(By.ID, 'username').clear()
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').clear()
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.XPATH, "//button[contains(., '登 录') or contains(., '登录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url or 'dashboard' in d.current_url)
        time.sleep(2)
        print('after login URL:', drv.current_url)

        # 任务 419 详情
        drv.get(BASE + '/tasks/419')
        WebDriverWait(drv, 30).until(
            lambda d: ('关联用例' in _body(d) or '快速复核' in _body(d)) and '登录' not in _body(d))
        time.sleep(3)
        print('task detail body snippet:', _body(drv)[:200].replace('\n', ' '))

        # 找「快速复核」按钮（关联用例行）
        btns = drv.find_elements(By.XPATH, "//button[contains(., '快速复核')]")
        print('快速复核 buttons found:', len(btns))
        if not btns:
            raise SystemExit('NO quick review button')
        btns[0].click()
        WebDriverWait(drv, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']")))
        time.sleep(1.5)
        _save('01_quick_review_dialog_light', drv, _body(drv))

        # 点击「发起快速复核」
        launch = drv.find_elements(By.XPATH, "//button[contains(., '发起快速复核')]")
        print('发起快速复核 buttons:', len(launch))
        if not launch:
            raise SystemExit('NO launch button')
        drv.get_log('performance')  # drain
        launch[0].click()
        time.sleep(3)

        # 捕获 Network
        entries = _net_entries(drv)
        ai_req = [e for e in entries if e[0] == 'REQ' and '/tasks/results/ai-review' in e[1]]
        ai_resp = [e for e in entries if e[0] == 'RESP' and '/tasks/results/ai-review' in e[1]]
        print('ai-review REQ count:', len(ai_req))
        for r in ai_req:
            print('  REQ:', r[1])
            print('  BODY:', r[2][:500])
        print('ai-review RESP count:', len(ai_resp))
        for r in ai_resp:
            print('  RESP status:', r[2], r[1])

        # 弹窗状态（执行中/完成）
        time.sleep(2)
        _save('02_after_launch_light', drv, _body(drv))

        # 深色弹窗
        drv.execute_script(
            "window.localStorage.setItem('iatp:theme:v1:mode','dark');"
            "document.documentElement.classList.add('dark');")
        time.sleep(1)
        drv.get(BASE + '/tasks/419')
        WebDriverWait(drv, 30).until(lambda d: '快速复核' in _body(d))
        time.sleep(2)
        btns = drv.find_elements(By.XPATH, "//button[contains(., '快速复核')]")
        if btns:
            btns[0].click()
            WebDriverWait(drv, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']")))
            time.sleep(1.5)
            _save('03_quick_review_dialog_dark', drv, _body(drv))

        # 汇总 Network 证据写文件
        with open(os.path.join(ARTIFACTS, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)

        # 断言：存在含 dimension_ids 的请求且响应 200
        body_has_dims = any(
            ('dimension_ids' in r[2] and 'result_ids' in r[2]) for r in ai_req)
        resp_ok = any(r[2] == 200 for r in ai_resp)
        print('ASSERT body_has_dims:', body_has_dims)
        print('ASSERT resp_ok:', resp_ok)
        if not body_has_dims:
            raise SystemExit('FAIL: no dimension_ids in request body')
        if not resp_ok:
            raise SystemExit('FAIL: ai-review response not 200')
        print('PASS')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()

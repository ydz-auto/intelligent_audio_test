# -*- coding: utf-8 -*-
"""INT-1279 验收（重跑）：捕获快速复核发起 200 响应 + 弹窗状态。"""
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
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1279_resp_capture')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    service = Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _drain(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def _collect(drv):
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
                elif method == 'Network.responseReceivedExtraInfo':
                    url = params.get('response', {}).get('url', '')
                    status = params.get('response', {}).get('status')
                    out.append(('RESP-EXTRA', url, status))
            except Exception:
                pass
    except Exception:
        pass
    return out


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登 录') or contains(., '登录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        drv.get(BASE + '/tasks/419')
        WebDriverWait(drv, 30).until(lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '快速复核')]")) > 0)
        time.sleep(2)

        btns = drv.find_elements(By.XPATH, "//button[contains(., '快速复核')]")
        btns[0].click()
        WebDriverWait(drv, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']")))
        time.sleep(1.5)

        launch = drv.find_elements(By.XPATH, "//button[contains(., '发起快速复核')]")
        _drain(drv)
        launch[0].click()

        # poll for response up to 15s
        ai_resp = []
        ai_req = []
        for _ in range(15):
            time.sleep(1)
            for e in _collect(drv):
                if '/tasks/results/ai-review' in str(e[1]):
                    if e[0] == 'REQ':
                        ai_req.append(e)
                    else:
                        ai_resp.append(e)
            if ai_resp:
                break

        d = os.path.join(ARTIFACTS)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(ai_req + ai_resp, f, ensure_ascii=False, indent=1)

        print('=== ai-review REQ ===')
        for e in ai_req:
            print('  body:', e[2][:400])
        print('=== ai-review RESP ===')
        for e in ai_resp:
            print('  status:', e[2], e[1])

        # dialog state
        time.sleep(2)
        body = _body(drv)
        dlg_text = ''
        try:
            dlg = drv.find_element(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']")
            dlg_text = dlg.text
        except Exception:
            dlg_text = '(dialog closed)'
        with open(os.path.join(d, 'dialog_after.txt'), 'w', encoding='utf-8') as f:
            f.write(dlg_text)
        print('=== dialog after ===')
        print(dlg_text[:500])

        ok = any(e[2] == 200 for e in ai_resp) or any(
            'dimension_ids' in e[2] for e in ai_req)
        print('RESP_OK:', any(e[2] == 200 for e in ai_resp))
        print('REQ_HAS_DIMS:', any('dimension_ids' in e[2] for e in ai_req))
        if not (any(e[2] == 200 for e in ai_resp) and any('dimension_ids' in e[2] for e in ai_req)):
            raise SystemExit('NEED RESP 200 + REQ dims')
        print('PASS')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()

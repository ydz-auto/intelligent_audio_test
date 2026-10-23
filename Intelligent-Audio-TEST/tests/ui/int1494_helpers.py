# -*- coding: utf-8 -*-
"""INT-1494 复走（React 接线·AI对话与其它页面）公共辅助。

环境（负责人 2026-10-23 docker 铁律）：
- 前端 docker iat-react-frontend → http://localhost:15173（React 构建）
- 后端 docker 真实库栈 → http://localhost:15000（database=intelligent_audio_test）
- AUTH_MODE=off，注入 dev_user('*')，浏览器无需登录。

本文件只放本卡走查用的驱动/取证辅助，不含业务断言。
"""
import json
import os
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://localhost:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = r'C:\Users\public.DESKTOP-3SNNDSS\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'artifacts', 'int1494')

os.makedirs(ARTIFACTS, exist_ok=True)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass


def driver():
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    svc = Service(DRIVER) if os.path.exists(DRIVER) else Service()
    d = webdriver.Chrome(service=svc, options=opts)
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    return d


def set_theme(d, mode):
    d.get(BASE + '/user-guide')
    d.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.get(BASE + '/user-guide')


def goto(d, path, wait_text=None, timeout=45):
    d.get(BASE + path)
    try:
        WebDriverWait(d, timeout).until(
            lambda x: x.execute_script('return document.readyState') == 'complete')
    except Exception:
        pass
    if wait_text:
        try:
            WebDriverWait(d, timeout).until(
                lambda x: wait_text in x.find_element(By.TAG_NAME, 'body').text)
        except Exception:
            pass
    return d


def shot(d, name):
    path = os.path.join(ARTIFACTS, name + '.png')
    d.save_screenshot(path)
    return path


def clear_perf(d):
    try:
        d.get_log('performance')
    except Exception:
        pass


def api_calls(d, contains=None):
    """performance log 里本页面发出的 /api/ 请求（双层解包）。"""
    out = []
    try:
        logs = d.get_log('performance')
    except Exception:
        return out
    for entry in logs:
        try:
            msg = json.loads(entry['message'])
        except Exception:
            continue
        method = msg.get('message', {}).get('method')
        if method != 'Network.responseReceived':
            continue
        p = msg['message']['params']
        url = p.get('response', {}).get('url', '')
        if '/api/' not in url:
            continue
        if contains and contains not in url:
            continue
        out.append({
            'url': url.replace(API, ''),
            'status': p.get('response', {}).get('status'),
            'method': p.get('response', {}).get('requestHeadersText', '')[:0] or
                      (p.get('type') and p.get('type')),
        })
    return out


def requests_simple(d, contains=None):
    out = []
    for r in api_calls(d, contains):
        out.append(f"{r['status']} {r['url']}")
    # 去重保序
    seen, res = set(), []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        res.append(x)
    return res


def body_text(d):
    return d.find_element(By.TAG_NAME, 'body').text


def js_click(d, el):
    d.execute_script('arguments[0].click();', el)


def result(name, passed, detail, shots=()):
    return {'item': name, 'pass': bool(passed), 'detail': detail,
            'shots': list(shots)}

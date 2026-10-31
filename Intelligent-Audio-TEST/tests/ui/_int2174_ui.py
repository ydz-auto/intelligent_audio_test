# -*- coding: utf-8 -*-
"""INT-2174 走查 UI 实测公共件：Chrome(headless) + 登录 + 等待/点击/截图/Network + 下载目录。"""
import json
import os
import shutil
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
USER = os.environ.get('DEV_USER', '接线测试_admin')
PASSWORD = os.environ.get('DEV_PASSWORD', 'JieXianTest@2026')
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, 'artifacts', 'int2174_ui')


def _chromedriver():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    cands = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                cands.append(exe)
    return max(cands) if cands else None


def make_driver(download_dir=None):
    os.makedirs(ARTIFACTS, exist_ok=True)
    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
    opts = Options()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    prefs = {'download.prompt_for_download': False, 'safebrowsing.enabled': True,
             'profile.default_content_setting_values.automatic_downloads': 1}
    if download_dir:
        prefs['download.default_directory'] = download_dir
    opts.add_experimental_option('prefs', prefs)
    drv_path = _chromedriver()
    drv = webdriver.Chrome(options=opts, service=Service(executable_path=drv_path) if drv_path else Service())
    drv.set_page_load_timeout(60)
    return drv


def goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def body(drv):
    return drv.execute_script('return document.body ? document.body.textContent : ""')


def wait_text(drv, text, timeout=30):
    return WebDriverWait(drv, timeout).until(lambda d: text in body(drv))


def wait_gone(drv, text, timeout=20):
    return WebDriverWait(drv, timeout).until(lambda d: text not in body(drv))


def js_click(drv, el):
    drv.execute_script('arguments[0].click()', el)


def click_xpath(drv, xpath, timeout=15):
    el = WebDriverWait(drv, timeout).until(lambda d: d.find_element(By.XPATH, xpath))
    js_click(drv, el)
    return el


def find_xpath(drv, xpath, timeout=15):
    return WebDriverWait(drv, timeout).until(lambda d: d.find_element(By.XPATH, xpath))


def exists(drv, xpath):
    return bool(drv.find_elements(By.XPATH, xpath))


def set_input(drv, el, value):
    """React 受控 input：走原生 setter + input 事件（clear/send_keys 对部分受控框不触发 onChange）。"""
    drv.execute_script(
        "const el=arguments[0], v=arguments[1];"
        "const proto=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "Object.getOwnPropertyDescriptor(proto,'value').set.call(el,v);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));", el, value)


def login(drv):
    """登录：/login 表单 → 工作台；慢页/瞬时网络抖动时重试 3 次。"""
    for attempt in range(3):
        try:
            goto(drv, '/login')
            end = time.time() + 30
            while time.time() < end:
                if '/login' not in drv.current_url:
                    return
                if drv.find_elements(By.ID, 'username'):
                    break
                time.sleep(0.5)
            else:
                print('login: 表单未出现，重试', attempt + 1)
                continue
            drv.find_element(By.ID, 'username').send_keys(USER)
            drv.find_element(By.ID, 'password').send_keys(PASSWORD)
            for b in drv.find_elements(By.TAG_NAME, 'button'):
                if '登' in (b.text or ''):
                    js_click(drv, b)
                    break
            for _ in range(15):
                time.sleep(1.2)
                if '/login' not in drv.current_url and '工作台' in body(drv):
                    return
            print('login: 提交后未进工作台，重试', attempt + 1)
        except Exception as e:
            print('login attempt warn', attempt + 1, type(e).__name__, e)
            time.sleep(2)
    goto(drv, '/dashboard')
    if '/login' in drv.current_url:
        raise RuntimeError('登录失败: ' + drv.current_url)


def shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    return path


def set_theme(drv, dark):
    """经界面主题设置切深浅色（同源截图，避免只改 localStorage 与组件状态不一致）。"""
    want = '深色' if dark else '浅色'
    try:
        click_xpath(drv, "//button[@aria-label='打开主题设置']", timeout=8)
        WebDriverWait(drv, 6).until(lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
        click_xpath(drv, f"//*[@role='radio'][contains(., '{want}')]", timeout=8)
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(0.8)
    except Exception as e:
        print('set_theme warn', e)


def drain_perf(drv):
    """取走并解析 performance log（请求 method/url/status）。"""
    out = {}
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message') or '{}')
            except Exception:
                continue
            m = msg.get('message') or {}
            method = m.get('method')
            p = m.get('params') or {}
            if method == 'Network.requestWillBeSent':
                req = p.get('request') or {}
                out[p.get('requestId')] = {'method': req.get('method'), 'url': req.get('url'),
                                           'postData': req.get('postData') or '', 'status': None}
            elif method == 'Network.responseReceived':
                rid = p.get('requestId')
                if rid in out:
                    out[rid]['status'] = (p.get('response') or {}).get('status')
    except Exception as e:
        print('perf log warn', e)
    return [v for v in out.values()]


def wait_download(download_dir, before, timeout=240):
    """等下载目录出现新文件并稳定（.crdownload 消失）。"""
    end = time.time() + timeout
    while time.time() < end:
        now = set(os.listdir(download_dir))
        new = [f for f in now - before if not f.endswith('.crdownload') and not f.endswith('.tmp')]
        if new:
            paths = [os.path.join(download_dir, f) for f in new]
            sizes = [os.path.getsize(p) for p in paths]
            time.sleep(1.0)
            sizes2 = [os.path.getsize(p) for p in paths]
            if sizes == sizes2:
                return max(paths, key=os.path.getsize)
        time.sleep(0.6)
    raise TimeoutError('等待下载超时: ' + download_dir)


def clear_downloads(download_dir):
    if os.path.isdir(download_dir):
        for f in os.listdir(download_dir):
            try:
                os.remove(os.path.join(download_dir, f))
            except Exception:
                pass
